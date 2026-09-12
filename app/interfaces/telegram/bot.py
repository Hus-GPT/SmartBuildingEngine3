from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


def _authorized(update: Update, owner_id: int) -> bool:
    user = update.effective_user
    return user is not None and owner_id != 0 and user.id == owner_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner_id = context.application.bot_data["owner_id"]
    if not _authorized(update, owner_id):
        if update.message:
            await update.message.reply_text("غير مصرح لك باستخدام هذا البوت.")
        return
    if update.message:
        await update.message.reply_text(
            "مرحباً بك في Smart Building Manager.\n"
            "النظام قيد البناء. أي عملية حساسة ستتطلب مراجعة وتحذيراً وتأكيداً صريحاً قبل التنفيذ."
        )


def build_telegram_application(token: str, owner_id: int) -> Application:
    application = Application.builder().token(token).build()
    application.bot_data["owner_id"] = owner_id
    application.add_handler(CommandHandler("start", start))
    return application
