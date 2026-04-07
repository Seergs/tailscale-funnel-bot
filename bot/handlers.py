import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from .config import ALLOWED_USER_ID, IGNORED_NAMESPACES
from . import k8s, tasks

logger = logging.getLogger(__name__)


def _parse_ns_svc(arg: str) -> tuple[str, str]:
    if "/" in arg:
        ns, name = arg.split("/", 1)
        if not ns or not name:
            raise ValueError(f"Invalid format: '{arg}'. Expected namespace/service")
        return ns, name
    return "default", arg


async def expose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: `/expose namespace/service`", parse_mode="Markdown"
        )
        return

    try:
        ns, svc_name = _parse_ns_svc(context.args[0])
    except ValueError as e:
        await update.message.reply_text(f"`{e}`", parse_mode="Markdown")
        return

    try:
        funnel_name = k8s.expose_service(svc_name, ns)
        await update.message.reply_text(
            f"*Funnel created:* `{funnel_name}`\nI'll ping you when it's ready...",
            parse_mode="Markdown",
        )
        asyncio.create_task(
            tasks.wait_and_notify(context.application, funnel_name, ns)
        )
    except Exception as e:
        logger.error("expose error", exc_info=True)
        await update.message.reply_text(
            f"Unable to expose service: `{e}`", parse_mode="Markdown"
        )


async def close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: `/close namespace/service`", parse_mode="Markdown"
        )
        return

    try:
        ns, svc_name = _parse_ns_svc(context.args[0])
    except ValueError as e:
        await update.message.reply_text(f"`{e}`", parse_mode="Markdown")
        return

    try:
        k8s.close_service(svc_name, ns)
        await update.message.reply_text(
            f"*Funnel disabled* for `{svc_name}` in `{ns}`", parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(
            f"Unable to disable funnel: `{e}`", parse_mode="Markdown"
        )


async def list_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    try:
        svcs = k8s.get_services(IGNORED_NAMESPACES)
        if not svcs:
            await update.message.reply_text("No available services")
            return

        active_funnels = k8s.get_active_funnels()
        lines = []
        for svc in svcs:
            key = f"{svc.metadata.namespace}/{svc.metadata.name}"
            indicator = " 🟢" if key in active_funnels else ""
            lines.append(f"`{key}`{indicator}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error("list error", exc_info=True)
        await update.message.reply_text(f"`{e}`", parse_mode="Markdown")
