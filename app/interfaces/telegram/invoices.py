from __future__ import annotations

from datetime import date
from decimal import Decimal

from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select

from app.application.persistence_service import PersistenceService
from app.domain.rules import BusinessRuleError
from app.infrastructure.orm import LeaseRecord, UnitRecord


def prepare_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) != 10:
        raise BusinessRuleError("الصيغة: /invoice unit_id | بداية الفترة | نهاية الفترة | كهرباء سابق | كهرباء حالي | ماء سابق | ماء حالي | مصاريف مشتركة | متأخرات | ملاحظة")
    start, end = date.fromisoformat(parts[1]), date.fromisoformat(parts[2])
    values = [Decimal(parts[i]) for i in (3, 4, 5, 6, 7, 8)]
    session = context.application.bot_data["session_factory"]()
    try:
        unit = session.get(UnitRecord, int(parts[0]))
        lease = session.scalar(select(LeaseRecord).where(LeaseRecord.unit_id == int(parts[0]), LeaseRecord.status == "active"))
        if not unit: raise BusinessRuleError("الوحدة غير موجودة.")
        if not lease: raise BusinessRuleError("لا يوجد عقد نشط لهذه الوحدة.")
        invoice_number = f"INV-{date.today().strftime('%Y%m%d')}-{int(parts[0]):04d}-{session.query(__import__('app.infrastructure.orm', fromlist=['InvoiceRecord']).InvoiceRecord).count()+1:04d}"
    finally:
        session.close()
    context.user_data["pending_write"] = {
        "kind": "invoice", "unit_id": int(parts[0]), "start": start.isoformat(), "end": end.isoformat(),
        "ep": str(values[0]), "ec": str(values[1]), "wp": str(values[2]), "wc": str(values[3]),
        "shared": str(values[4]), "arrears": str(values[5]), "note": parts[9], "invoice_number": invoice_number,
    }


async def invoice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        prepare_invoice(update, context)
        p = context.user_data["pending_write"]
        await update.message.reply_text(
            f"⚠️ مراجعة الفاتورة قبل الإصدار\n\nرقم الفاتورة: {p['invoice_number']}\nالوحدة: {p['unit_id']}\nالفترة: {p['start']} → {p['end']}\nالكهرباء: {p['ep']} → {p['ec']}\nالماء: {p['wp']} → {p['wc']}\nالمصاريف المشتركة: {p['shared']}\nالمتأخرات: {p['arrears']}\n\nأسعار الكهرباء والماء تؤخذ من الإعدادات المركزية.\n\nلم تُصدر الفاتورة بعد.",
            reply_markup=__import__('telegram').InlineKeyboardMarkup([[__import__('telegram').InlineKeyboardButton('✅ إصدار الفاتورة', callback_data='confirm_write'), __import__('telegram').InlineKeyboardButton('❌ إلغاء', callback_data='cancel_write')]])
        )
    except (ValueError, BusinessRuleError) as exc:
        await update.message.reply_text(f"❌ لم يتم إعداد الفاتورة: {exc}")
