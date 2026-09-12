from __future__ import annotations

from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.application.persistence_service import PersistenceService
from app.domain.rules import BusinessRuleError
from app.infrastructure.orm import InvoiceRecord


def _authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    return user is not None and user.id == context.application.bot_data["owner_id"]


async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        if update.message:
            await update.message.reply_text("غير مصرح لك باستخدام هذا البوت.")
        return
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) not in {3, 4}:
        await update.message.reply_text("الصيغة:\n/pay invoice_id | amount | payment_method | ملاحظة اختيارية")
        return
    try:
        invoice_id = int(parts[0])
        amount = Decimal(parts[1])
        method = parts[2]
        note = parts[3] if len(parts) == 4 else None
        session = context.application.bot_data["session_factory"]()
        try:
            service = PersistenceService(session)
            invoice = session.get(InvoiceRecord, invoice_id)
            if not invoice:
                raise BusinessRuleError("الفاتورة غير موجودة.")
            outstanding = service.invoice_outstanding(invoice_id)
            total = service.invoice_total(invoice)
            invoice_number = invoice.invoice_number
        finally:
            session.close()
        context.user_data["pending_payment"] = {"invoice_id": invoice_id, "amount": str(amount), "method": method, "note": note}
        await update.message.reply_text(
            f"⚠️ مراجعة تسجيل الدفعة\n\nالفاتورة: {invoice_number}\nالإجمالي: {total}\nالمتبقي: {outstanding}\nالمبلغ: {amount}\nطريقة الدفع: {method}\n"
            + (f"الملاحظة: {note}\n" if note else "")
            + "\n⚠️ لم يتم تسجيل الدفعة بعد. التأكيد الصريح مطلوب.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد تسجيل الدفعة", callback_data="payment_confirm"), InlineKeyboardButton("❌ إلغاء", callback_data="payment_cancel")]]),
        )
    except (ValueError, BusinessRuleError) as exc:
        await update.message.reply_text(f"❌ لم يتم إعداد الدفعة: {exc}")


async def payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        await update.callback_query.answer("غير مصرح", show_alert=True)
        return
    query = update.callback_query
    await query.answer()
    pending = context.user_data.get("pending_payment")
    if not pending:
        await query.edit_message_text("انتهت صلاحية الدفعة المعلقة. لم يتم تسجيل شيء.")
        return
    if query.data == "payment_cancel":
        context.user_data.pop("pending_payment", None)
        await query.edit_message_text("❌ أُلغيت عملية تسجيل الدفعة.")
        return
    session = context.application.bot_data["session_factory"]()
    try:
        service = PersistenceService(session)
        payment = service.record_payment(int(pending["invoice_id"]), Decimal(pending["amount"]), pending["method"], True, pending.get("note"))
        invoice = session.get(InvoiceRecord, payment.invoice_id)
        remaining = service.invoice_outstanding(payment.invoice_id)
        status = invoice.status
        service.commit()
        context.user_data.pop("pending_payment", None)
        await query.edit_message_text(f"✅ تم تسجيل الدفعة رقم {payment.id}.\nالفاتورة: {invoice.invoice_number}\nالحالة: {status}\nالمتبقي: {remaining}")
    except (BusinessRuleError, ValueError, PermissionError) as exc:
        session.rollback()
        await query.edit_message_text(f"❌ لم تُسجل الدفعة.\n\nالسبب: {exc}")
    finally:
        session.close()
