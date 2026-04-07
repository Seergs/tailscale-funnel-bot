import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from . import k8s, tasks
from .config import (
    ALLOWED_SVC,
    ALLOWED_USER_ID,
    ANNOTATION_DURATION,
    ANNOTATION_EXPOSED_AT,
    FUNNEL_DURATION_SECONDS,
    IGNORED_NS,
    IGNORED_SVC,
)

logger = logging.getLogger(__name__)


def _parse_duration(s: str) -> int:
    """Parse a duration string like '30m' or '2h' into seconds."""
    s = s.strip().lower()
    if s.endswith("h"):
        return int(s[:-1]) * 3600
    if s.endswith("m"):
        return int(s[:-1]) * 60
    raise ValueError(f"Invalid duration '{s}'. Use format like '30m' or '2h'")


def _format_remaining(seconds: int) -> str:
    """Format a number of seconds into a human-readable remaining time string."""
    if seconds <= 0:
        return "expiring soon"
    minutes_total = seconds // 60
    hours, minutes = divmod(minutes_total, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m" if minutes else "< 1m"


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
            "Usage: `/expose namespace/service [duration]`\n"
            "Duration examples: `30m`, `2h` (default: 1h)",
            parse_mode="Markdown",
        )
        return

    try:
        ns, svc_name = _parse_ns_svc(context.args[0])
    except ValueError as e:
        await update.message.reply_text(f"`{e}`", parse_mode="Markdown")
        return

    duration_seconds = None
    if len(context.args) > 1:
        try:
            duration_seconds = _parse_duration(context.args[1])
        except ValueError as e:
            await update.message.reply_text(f"`{e}`", parse_mode="Markdown")
            return

    try:
        funnel_name = k8s.expose_service(svc_name, ns, duration_seconds)
        await update.message.reply_text(
            f"*Funnel created:* `{funnel_name}`\nI'll ping you when it's ready...",
            parse_mode="Markdown",
        )
        context.application.create_task(
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


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    try:
        ingresses = k8s.get_all_funnel_ingresses()
        active = [
            ing for ing in ingresses
            if (ing.metadata.annotations or {}).get(ANNOTATION_EXPOSED_AT)
        ]
        if not active:
            await update.message.reply_text("No active funnels")
            return

        now = int(time.time())
        lines = []
        for ing in active:
            ann = ing.metadata.annotations or {}
            exposed_at = int(ann[ANNOTATION_EXPOSED_AT])
            duration = int(ann.get(ANNOTATION_DURATION, FUNNEL_DURATION_SECONDS))
            remaining = duration - (now - exposed_at)
            svc_name = ing.metadata.name.removesuffix("-funnel")
            key = f"{ing.metadata.namespace}/{svc_name}"
            lines.append(f"`{key}`: {_format_remaining(remaining)} remaining")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error("status error", exc_info=True)
        await update.message.reply_text(f"`{e}`", parse_mode="Markdown")


async def list_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    try:
        svcs = k8s.get_services(IGNORED_NS, IGNORED_SVC, ALLOWED_SVC)
        if not svcs:
            await update.message.reply_text("No available services")
            return

        active_funnels = k8s.get_active_funnels()
        lines = []
        for svc in svcs:
            key = f"{svc.metadata.namespace}/{svc.metadata.name}"
            indicator = " 🟢 (*Active*)" if key in active_funnels else ""
            lines.append(f"`{key}`{indicator}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error("list error", exc_info=True)
        await update.message.reply_text(f"`{e}`", parse_mode="Markdown")
