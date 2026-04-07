import asyncio
import logging

from telegram.ext import ApplicationBuilder, CommandHandler

from .config import TELEGRAM_TOKEN
from . import handlers, tasks

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)


async def _post_init(application):
    await application.bot.set_my_commands([
        ("expose", "Expose a service via Tailscale Funnel"),
        ("close", "Close a Tailscale Funnel"),
        ("list", "List exposable services"),
    ])
    asyncio.create_task(tasks.cleanup_expired_funnels(application))


def main() -> None:
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(CommandHandler("expose", handlers.expose))
    app.add_handler(CommandHandler("close", handlers.close))
    app.add_handler(CommandHandler("list", handlers.list_services))
    app.run_polling()


if __name__ == "__main__":
    main()
