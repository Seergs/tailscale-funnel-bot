import logging
import os

from pythonjsonlogger.json import JsonFormatter
from telegram.ext import ApplicationBuilder, CommandHandler

from . import handlers, tasks
from .config import TELEGRAM_TOKEN


def _configure_logging() -> None:
    if os.getenv("LOG_FORMAT", "json") == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        logging.basicConfig(handlers=[handler], level=logging.INFO)
    else:
        logging.basicConfig(
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
            level=logging.INFO,
        )


_configure_logging()

logger = logging.getLogger(__name__)


async def _post_init(application):
    await application.bot.set_my_commands([
        ("expose", "Expose a service via Tailscale Funnel"),
        ("close", "Close a Tailscale Funnel"),
        ("list", "List exposable services"),
        ("status", "Show active funnels and time remaining"),
    ])
    application.create_task(tasks.cleanup_expired_funnels(application))


def main() -> None:
    logger.info("Starting bot")
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(CommandHandler("expose", handlers.expose))
    app.add_handler(CommandHandler("close", handlers.close))
    app.add_handler(CommandHandler("list", handlers.list_services))
    app.add_handler(CommandHandler("status", handlers.status))
    app.run_polling()


if __name__ == "__main__":
    main()
