from __future__ import annotations

from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.infrastructure.database import build_database, initialize_database
from app.interfaces.telegram.backup import backup_command
from app.interfaces.telegram.bot import build_telegram_application
from app.interfaces.telegram.documents import document_callback, document_command, witness_callback, witness_command
from app.interfaces.telegram.invoices import invoice_callback, invoice_command
from app.interfaces.telegram.lease_lifecycle import endlease_command, expiring_command, lease_lifecycle_callback, renewlease_command
from app.interfaces.telegram.lease_wizard import lease_wizard_callback, lease_wizard_file, lease_wizard_text, newlease_command
from app.interfaces.telegram.payments import payment_callback, pay_command
from app.interfaces.telegram.reports import status_command
from app.settings import settings


def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    if not settings.telegram_owner_id:
        raise RuntimeError("TELEGRAM_OWNER_ID is required")
    engine, session_factory = build_database(settings.database_url)
    initialize_database(engine)
    application = build_telegram_application(settings.telegram_bot_token, settings.telegram_owner_id, session_factory, settings.storage_dir)
    application.bot_data["database_url"] = settings.database_url
    application.add_handler(CommandHandler("newlease", newlease_command), group=-2)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lease_wizard_text), group=-2)
    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, lease_wizard_file), group=-2)
    application.add_handler(CallbackQueryHandler(lease_wizard_callback, pattern=r"^complete_lease_(confirm|cancel)$"), group=-2)
    application.add_handler(CommandHandler("invoice", invoice_command))
    application.add_handler(CommandHandler("pay", pay_command))
    application.add_handler(CommandHandler("doc", document_command))
    application.add_handler(CommandHandler("witness", witness_command))
    application.add_handler(CommandHandler("endlease", endlease_command))
    application.add_handler(CommandHandler("renewlease", renewlease_command))
    application.add_handler(CommandHandler("expiring", expiring_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CallbackQueryHandler(invoice_callback, pattern=r"^invoice_(confirm|cancel)$"), group=-1)
    application.add_handler(CallbackQueryHandler(payment_callback, pattern=r"^payment_(confirm|cancel)$"), group=-1)
    application.add_handler(CallbackQueryHandler(document_callback, pattern=r"^document_(confirm|cancel)$"), group=-1)
    application.add_handler(CallbackQueryHandler(witness_callback, pattern=r"^witness_(confirm|cancel)$"), group=-1)
    application.add_handler(CallbackQueryHandler(lease_lifecycle_callback, pattern=r"^lease_lifecycle_(confirm|cancel):"), group=-1)
    application.run_polling(allowed_updates=None)


if __name__ == "__main__":
    main()
