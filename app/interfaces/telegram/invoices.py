from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.application.persistence_service import PersistenceService
from app.domain.rules import BusinessRuleError
from app.infrastructure.orm import LeaseRecord, UnitRecord
from app.settings import settings


def _authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    return user is not None and user.id == context.application.bot_data["owner_id"]


def _parse(context: ContextTypes.DEFAULT_TYPE) -> dict:
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) != 10:
        raise BusinessRuleError("الصيغة: /invoice unit_id | بداية الفترة | نهاية الفترة | كهرباء سابق | كهرباء حالي | ماء سابق | ماء حالي | مصاريف مشتركة | متأخرات | ملاحظة")
    unit_id = int(parts[0]); start = date.fromisoformat(parts[1]); end = date.fromisoformat(parts[2])
    values = [Decimal(parts[i]) for i in (3, 4, 5, 6, 7, 8)]
    session = context.application.bot_data["session_factory"]()
    try:
        unit = session.get(UnitRecord, unit_id)
        lease = session.scalar(select(LeaseRecord).where(LeaseRecord.unit_id == unit_id, LeaseRecord.status == "active"))
        if not unit: raise BusinessRuleError("الوحدة غير موجودة.")
        if not lease: raise BusinessRuleError("لا يوجد عقد نشط لهذه الوحدة.")
    finally: session.close()
    return {"kind":"invoice", "unit_id":unit_id, "start":start.isoformat(), "end":end.isoformat(), "ep":str(values[0]), "ec":str(values[1]), "wp":str(values[2]), "wc":str(values[3]), "shared":str(values[4]), "arrears":str(values[5]), "note":parts[9], "invoice_number":f"INV-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{unit_id:04d}", "electricity_price":str(settings.electricity_price), "water_price":str(settings.water_price)}


async def invoice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        if update.message: await update.message.reply_text("غير مصرح لك باستخدام هذا البوت.")
        return
    try:
        pending = _parse(context); context.user_data["pending_write"] = pending
        await update.message.reply_text(f"⚠️ مراجعة الفاتورة قبل الإصدار\n\nرقم: {pending['invoice_number']}\nالوحدة: {pending['unit_id']}\nالفترة: {pending['start']} → {pending['end']}\nالكهرباء: {pending['ep']} → {pending['ec']} بسعر {pending['electricity_price']}\nالماء: {pending['wp']} → {pending['wc']} بسعر {pending['water_price']}\nالمصاريف المشتركة: {pending['shared']}\nالمتأخرات: {pending['arrears']}\n\n⚠️ لم يتم إصدار الفاتورة بعد. التأكيد الصريح مطلوب.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ إصدار الفاتورة", callback_data="invoice_confirm"), InlineKeyboardButton("❌ إلغاء", callback_data="invoice_cancel")]]))
    except (ValueError, BusinessRuleError) as exc:
        await update.message.reply_text(f"❌ لم يتم إعداد الفاتورة: {exc}")


async def invoice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        await update.callback_query.answer("غير مصرح", show_alert=True); return
    query = update.callback_query; await query.answer()
    pending = context.user_data.get("pending_write")
    if not pending or pending.get("kind") != "invoice":
        await query.edit_message_text("انتهت صلاحية الفاتورة المعلقة. لم يتم إصدار أي فاتورة."); return
    if query.data == "invoice_cancel":
        context.user_data.pop("pending_write", None); await query.edit_message_text("❌ أُلغيت عملية إصدار الفاتورة."); return
    session = context.application.bot_data["session_factory"]()
    try:
        service = PersistenceService(session)
        invoice = service.create_utility_invoice(unit_id=pending["unit_id"], period_start=date.fromisoformat(pending["start"]), period_end=date.fromisoformat(pending["end"]), electricity_previous=Decimal(pending["ep"]), electricity_current=Decimal(pending["ec"]), electricity_price=Decimal(pending["electricity_price"]), water_previous=Decimal(pending["wp"]), water_current=Decimal(pending["wc"]), water_price=Decimal(pending["water_price"]), shared_expenses=Decimal(pending["shared"]), arrears=Decimal(pending["arrears"]), note=pending["note"], invoice_number=pending["invoice_number"], confirmed=True)
        service.commit(); context.user_data.pop("pending_write", None)
        await query.edit_message_text(f"✅ تم إصدار الفاتورة {invoice.invoice_number}.\nالحالة: ISSUED.\n\nالخطوة التالية: إنشاء PDF العربي وإرساله تلقائيًا.")
    except (BusinessRuleError, ValueError, PermissionError) as exc:
        session.rollback(); await query.edit_message_text(f"❌ لم تُصدر الفاتورة.\n\nالسبب: {exc}")
    finally: session.close()
