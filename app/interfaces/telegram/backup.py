from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.application.backup_service import BackupService


def _authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    return user is not None and user.id == context.application.bot_data["owner_id"]


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        return
    await update.message.reply_text("⏳ جارٍ إنشاء النسخة الاحتياطية الحالية...")
    service = BackupService(context.application.bot_data["database_url"], context.application.bot_data["storage_dir"])
    try:
        path = service.create_latest()
        with path.open("rb") as stream:
            await update.message.reply_document(document=stream, filename=path.name, caption="✅ تم إنشاء النسخة الاحتياطية الحالية. تم استبدال النسخة السابقة.")
    except Exception as exc:
        await update.message.reply_text(f"❌ فشل إنشاء النسخة الاحتياطية: {exc}")
