import asyncio
import logging
import socket
import time

from telegram.ext import Application

from .config import ALLOWED_USER_ID, ANNOTATION_EXPOSED_AT, FUNNEL_DURATION_SECONDS
from . import k8s

logger = logging.getLogger(__name__)


async def cleanup_expired_funnels(app: Application) -> None:
    while True:
        try:
            now = int(time.time())
            for ingress in k8s.get_all_funnel_ingresses():
                ann = ingress.metadata.annotations or {}
                exposed_at = ann.get(ANNOTATION_EXPOSED_AT)
                if not exposed_at:
                    continue

                try:
                    elapsed = now - int(exposed_at)
                except ValueError:
                    logger.warning(
                        "Invalid %s annotation on %s/%s, skipping",
                        ANNOTATION_EXPOSED_AT,
                        ingress.metadata.namespace,
                        ingress.metadata.name,
                    )
                    continue

                if elapsed >= FUNNEL_DURATION_SECONDS:
                    name = ingress.metadata.name
                    ns = ingress.metadata.namespace
                    logger.info("Closing expired funnel: %s/%s", ns, name)
                    k8s.delete_ingress(name=name, namespace=ns)
                    await app.bot.send_message(
                        chat_id=ALLOWED_USER_ID,
                        text=f"**Expired:** Funnel `{name}` in `{ns}` closed automatically.",
                        parse_mode="Markdown",
                    )
        except Exception:
            logger.exception("Cleanup loop error")

        await asyncio.sleep(300)


async def wait_and_notify(app: Application, ingress_name: str, namespace: str) -> None:
    hostname: str | None = None

    for _ in range(12):
        await asyncio.sleep(5)
        try:
            ingress = k8s.read_ingress(ingress_name, namespace)
            lb = ingress.status.load_balancer
            if lb and lb.ingress and lb.ingress[0].hostname:
                hostname = lb.ingress[0].hostname
                logger.info("Hostname assigned: %s", hostname)
                break
        except Exception:
            logger.exception("Error reading ingress status")

    if not hostname:
        await app.bot.send_message(
            chat_id=ALLOWED_USER_ID,
            text="*Timeout:* No Tailscale hostname assigned after 60s",
            parse_mode="Markdown",
        )
        return

    for attempt in range(24):
        await asyncio.sleep(15)
        try:
            socket.getaddrinfo(hostname, None)
            logger.info("DNS resolves for %s", hostname)
            await app.bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text=f"*Funnel ready:* https://{hostname}",
                parse_mode="Markdown",
            )
            return
        except socket.gaierror:
            logger.debug("DNS not ready for %s, attempt %d/24", hostname, attempt + 1)

    await app.bot.send_message(
        chat_id=ALLOWED_USER_ID,
        text=f"*Timeout:* `{hostname}` did not resolve after 6 minutes",
        parse_mode="Markdown",
    )
