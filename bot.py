import os
import time
import asyncio
import logging
import argparse
import socket
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from kubernetes import client, config

TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID"))
ANNOTATION_FUNNEL = "tailscale.com/funnel"
ANNOTATION_EXPOSED_AT = "funnel-bot.io/exposed-at"
DEFAULT_DURATION = 3600 
DEFAULT_IGNORED_NAMESPACES = {
    "kube-system",
    "tailscale",
    "funnel-bot",
    "flux-system",
    "longhorn-system",
}


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

try:
    config.load_incluster_config()
except:
    config.load_kube_config()

v1 = client.CoreV1Api()
networking_v1 = client.NetworkingV1Api()

def parse_ns_svc(arg: str) -> tuple[str, str]:
    if "/" in arg:
        ns, name = arg.split("/", 1)
        return ns, name
    return "default", arg

def get_active_funnels() -> set:
    active = set()
    for ing in networking_v1.list_ingress_for_all_namespaces().items:
        ann = ing.metadata.annotations or {}
        if ANNOTATION_EXPOSED_AT in ann:
            active.add(f"{ing.metadata.namespace}/{ing.metadata.name.removesuffix('-funnel')}")
    return active


def get_ignored_namespaces() -> set:
    raw = os.getenv("IGNORED_NAMESPACES", "")
    if not raw:
        return DEFAULT_IGNORED_NAMESPACES.copy()
    return {ns.strip() for ns in raw.split(",") if ns.strip()}

IGNORED_NAMESPACES = get_ignored_namespaces()

async def cleanup_expired_funnels(app):
    while True:
        try:
            all_ingresses = networking_v1.list_ingress_for_all_namespaces()
            now = int(time.time())
            
            for ingress in all_ingresses.items:
                ann = ingress.metadata.annotations or {}
                exposed_at = ann.get(ANNOTATION_EXPOSED_AT)
                
                if exposed_at and ingress.metadata.name.endswith("-funnel"):
                    elapsed = now - int(exposed_at)
                    if elapsed >= DEFAULT_DURATION:
                        name = ingress.metadata.name
                        ns = ingress.metadata.namespace
                        
                        logging.info(f"Closing expired funnel: {ns}/{name}")
                        networking_v1.delete_namespaced_ingress(name=name, namespace=ns)
                        
                        await app.bot.send_message(
                            chat_id=ALLOWED_USER_ID,
                            text=f"**Expired:** Funnel for `{name}` in `{ns}` has been automatically closed.",
                            parse_mode="Markdown"
                        )
        except Exception as e:
            logging.error(f"Cleanup loop error: {e}")
        
        await asyncio.sleep(300)

async def expose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/expose namespace/service`", parse_mode="Markdown")
        return

    ns, svc_name = parse_ns_svc(context.args[0])

    try:
        funnel_name = expose_service(svc_name, ns)
        await update.message.reply_text(
            f"*Funnel created:* `{funnel_name}`\nI'll ping you when it's ready...",
            parse_mode="Markdown"
        )
        asyncio.create_task(wait_and_notify(context.application, funnel_name, ns))
    except Exception as e:
        logging.error(f"expose error: {e}", exc_info=True)
        await update.message.reply_text(f"Unable to expose service: `{e}`", parse_mode="Markdown")

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/close namespace/service>`", parse_mode="Markdown")
        return
    
    ns, svc_name = parse_ns_svc(context.args[0])

    try:
        close_service(svc_name, ns)
        await update.message.reply_text(f"**Funnel Disabled** for `{svc_name}` in `{ns}`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Unable to disable funnel: `{e}`", parse_mode="Markdown")

def expose_service(svc_name, namespace):
    original = v1.read_namespaced_service(name=svc_name, namespace=namespace)

    funnel_ingress_name = f"{svc_name}-funnel"
    port = original.spec.ports[0].port

    body = client.V1Ingress(
        metadata=client.V1ObjectMeta(
            name=funnel_ingress_name,
            namespace=namespace,
            annotations={
                ANNOTATION_FUNNEL: "true",
                ANNOTATION_EXPOSED_AT: str(int(time.time()))
            }
        ),
        spec=client.V1IngressSpec(
            ingress_class_name="tailscale",
            rules=[
                client.V1IngressRule(
                    http=client.V1HTTPIngressRuleValue(
                        paths=[
                            client.V1HTTPIngressPath(
                                path="/",
                                path_type="Prefix",
                                backend=client.V1IngressBackend(
                                    service=client.V1IngressServiceBackend(
                                        name=svc_name,
                                        port=client.V1ServiceBackendPort(number=port)
                                    )
                                )
                            )
                        ]
                    )
                )
            ],
            tls=[client.V1IngressTLS(hosts=[funnel_ingress_name])]
        )
    )


    try:
        networking_v1.create_namespaced_ingress(namespace=namespace, body=body)
    except client.exceptions.ApiException as e:
        if e.status == 409:  # Already exists
            networking_v1.replace_namespaced_ingress(name=funnel_ingress_name, namespace=namespace, body=body)
        else:
            raise
    
    return funnel_ingress_name

def close_service(svc_name, namespace):
    funnel_ingress_name = f"{svc_name}-funnel"
    try:
        ingress = networking_v1.read_namespaced_ingress(name=funnel_ingress_name, namespace=namespace)
    except client.exceptions.ApiException as e:
        if e.status == 404:
            raise ValueError(f"No active funnel found for {svc_name}")
        raise

    ann = ingress.metadata.annotations or {}

    if ANNOTATION_EXPOSED_AT not in ann:
        raise ValueError(f"`{funnel_ingress_name}` exists but was not created by funnel-bot, aborting")

    networking_v1.delete_namespaced_ingress(name=funnel_ingress_name, namespace=namespace)

async def wait_and_notify(app, ingress_name, namespace):
    hostname = None
    for attempt in range(12):
        await asyncio.sleep(5)
        try:
            ingress = networking_v1.read_namespaced_ingress(name=ingress_name, namespace=namespace)
            lb = ingress.status.load_balancer
            if lb and lb.ingress and lb.ingress[0].hostname:
                hostname = lb.ingress[0].hostname
                logging.info(f"Hostname assigned: {hostname}")
                break

        except Exception as e:
            logging.error(f"Error reading ingress status: {e}")

    if not hostname:
        await app.bot.send_message(
            chat_id=ALLOWED_USER_ID,
            text=f"*Timeout:* No tailscale hostname assigned after 60s", parse_mode="Markdown"
        )
        return

    for attempt in range(24):
        await asyncio.sleep(15)
        try:
            socket.getaddrinfo(hostname, None)
            logging.info(f"DNS resolves for {hostname}")
            await app.bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text=f"*Funnel ready:* https://{hostname}",
                parse_mode="Markdown"
            )
            return
        except socket.gaierror:
            logging.info(f"DNS resolution not ready for {hostname}, attempt {attempt +  1}/24")

    await app.bot.send_message(
        chat_id=ALLOWED_USER_ID,
        text=f"*Timeout:* `{hostname}` not resolved after 6 minutes",
        parse_mode="Markdown"
    )

async def list_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    try:
        all_services = v1.list_service_for_all_namespaces()

        svcs = [
            svc for svc in all_services.items
            if svc.spec.type == "ClusterIP"
            and svc.metadata.name != "kubernetes"
            and not svc.metadata.name.endswith("-funnel")
            and svc.metadata.namespace not in IGNORED_NAMESPACES
        ]

        if not svcs:
            await update.message.reply_text("No available services")
            return 
        
        active_funnels = get_active_funnels()

        lines = []
        for svc in svcs:
            name = svc.metadata.name
            ns = svc.metadata.namespace
            key = f"{ns}/{name}"
            indicator = " 🟢 (Active)" if key in active_funnels else ""
            lines.append(f"`{ns}/{name}`{indicator}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        logging.error(f"list error: {e}", exc_info=True)
        await update.message.reply_text(f"`{e}`", parse_mode="Markdown")

if __name__ == '__main__':
    if not TOKEN:
        exit(1)

    async def post_init(application):
        await application.bot.set_my_commands([
            ("expose", "Expose a service via Tailscale Funnel: /expose <service> [-n <namespace>]"),
            ("close", "Close a Tailscale Funnel: /close <service> [-n <namespace>]"),
            ("list", "View available services that can be exposed using Funnel"),
        ])

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("expose", expose))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("list", list_services))

    loop = asyncio.get_event_loop()
    loop.create_task(cleanup_expired_funnels(app))

    app.run_polling()
