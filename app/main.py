from __future__ import annotations

from telegram.ext import CallbackQueryHandler, CommandHandler

from app.infrastructure.database import build_database, initialize_database
from app.interfaces.telegram.bot import build_telegram_application
from app.interfaces.telegram.invoices import invoice_callback, invoice_command
from app.settings import settings


def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    if not settings.telegram_owner_id:
        raise RuntimeError("TELEGRAM_OWNER_ID is required")
    engine, session_factory = build_database(settings.database_url)
    initialize_database(engine)
    application = build_telegram_application(settings.telegram_bot_token, settings.telegram_owner_id, session_factory, settings.storage_dir)
    application.add_handler(CommandHandler("invoice", invoice_command))
    application.add_handler(CallbackQueryHandler(invoice_callback, pattern=r"^invoice_(confirm|cancel)$"), group=-1)
    application.run_polling(allowed_updates=None)


if __name__ == "__main__":
    main()
