from __future__ import annotations

from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.application.persistence_service import PersistenceService
from app.domain.rules import BusinessRuleError
from app.settings import settings


def _authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    return user is not None and user.id == context.application.bot_data["owner_id"]


async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        await update.message.reply_text("غير مصرح لك باستخدام هذا البوت."); return
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) not in {3, 4}:
        await update.message.reply_text("الصيغة:\n/pay invoice_id | amount | payment_method | ملاحظة اختيارية"); return
    try:
        invoice_id = int(parts[0]); amount = Decimal(parts[1]); method = parts[2]; note = parts[3] if len(parts) == 4 else ""
        session = context.application.bot_data["session_factory"]()
        try:
            service = PersistenceService(session); outstanding = service.invoice_outstanding(invoice_id)
        finally: session.close()
        context.user_data["pending_write"] = {"kind":"payment", "invoice_id":invoice_id, "amount":str(amount), "method":method, "note":note, "outstanding":str(outstanding)}
        await update.message.reply_text(f"⚠️ مراجعة تسجيل الدفعة\n\nالفاتورة: {invoice_id}\nالمبلغ: {amount} {settings.currency}\nطريقة الدفع: {method}\nالمتبقي قبل الدفع: {outstanding} {settings.currency}\n\nلن يتم تسجيل الدفعة قبل التأكيد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد تسجيل الدفعة", callback_data="payment_confirm"), InlineKeyboardButton("❌ إلغاء", callback_data="payment_cancel")]]))
    except (ValueError, BusinessRuleError) as exc:
        await update.message.reply_text(f"❌ لم يتم إعداد الدفعة: {exc}")


async def payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        await update.callback_query.answer("غير مصرح", show_alert=True); return
    query = update.callback_query; await query.answer(); pending = context.user_data.get("pending_write")
    if not pending or pending.get("kind") != "payment":
        await query.edit_message_text("انتهت صلاحية الدفعة المعلقة. لم يتم تسجيل شيء."); return
    if query.data == "payment_cancel":
        context.user_data.pop("pending_write", None); await query.edit_message_text("❌ أُلغيت عملية تسجيل الدفعة."); return
    session = context.application.bot_data["session_factory"]()
    try:
        service = PersistenceService(session)
        payment = service.record_payment(int(pending["invoice_id"]), Decimal(pending["amount"]), pending["method"], True, pending["note"])
        remaining = service.invoice_outstanding(payment.invoice_id)
        service.commit(); context.user_data.pop("pending_write", None)
        await query.edit_message_text(f"✅ تم تسجيل الدفعة رقم {payment.id}.\nالمتبقي: {remaining} {settings.currency}")
    except (BusinessRuleError, ValueError, PermissionError) as exc:
        session.rollback(); await query.edit_message_text(f"❌ لم تُسجل الدفعة.\n\nالسبب: {exc}")
    finally: session.close()
