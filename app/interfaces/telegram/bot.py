from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "مرحباً بك في Smart Building Manager.\n"
        "النظام قيد البناء، ولن تُنفّذ أي عملية حساسة بدون تأكيد صريح."
    )


def build_telegram_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    return application
