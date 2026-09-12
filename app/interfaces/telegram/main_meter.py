from __future__ import annotations

from datetime import date
from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.application.persistence_service import PersistenceService
from app.domain.models import MeterType
from app.domain.rules import BusinessRuleError


def _authorized(update: Update, owner_id: int) -> bool:
    return update.effective_user is not None and update.effective_user.id == owner_id


async def mainmeter_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]):
        return
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) != 3 or parts[0].lower() not in {"electricity", "water", "كهرباء", "ماء"}:
        await update.message.reply_text("الصيغة:\n/mainmeter electricity/water | YYYY-MM-DD | reading")
        return
    try:
        meter = MeterType.ELECTRICITY if parts[0].lower() in {"electricity", "كهرباء"} else MeterType.WATER
        reading_date = date.fromisoformat(parts[1])
        value = Decimal(parts[2])
        context.user_data["pending_main_meter"] = {"meter_type": meter.value, "date": reading_date.isoformat(), "value": str(value)}
        await update.message.reply_text(
            "⚠️ مراجعة قراءة العداد الرئيسي للمبنى\n\n"
            f"العداد: {'كهرباء' if meter is MeterType.ELECTRICITY else 'ماء'}\n"
            f"التاريخ: {reading_date}\n"
            f"القراءة: {value}\n\n"
            "لن يتم الحفظ قبل التأكيد، وستُرفض القراءة إذا كانت أقل من آخر قراءة.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد", callback_data="mainmeter_confirm"), InlineKeyboardButton("❌ إلغاء", callback_data="mainmeter_cancel")]]),
        )
    except (ValueError, ArithmeticError) as exc:
        await update.message.reply_text(f"❌ بيانات القراءة غير صحيحة: {exc}")


async def mainmeter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not _authorized(update, context.application.bot_data["owner_id"]):
        await query.edit_message_text("غير مصرح لك باستخدام هذا البوت.")
        return
    pending = context.user_data.get("pending_main_meter")
    if query.data == "mainmeter_cancel":
        context.user_data.pop("pending_main_meter", None)
        await query.edit_message_text("❌ أُلغيت قراءة العداد الرئيسي ولم تُحفظ.")
        return
    if not pending:
        await query.edit_message_text("انتهت صلاحية عملية التأكيد. لم يُنفذ شيء.")
        return
    session = context.application.bot_data["session_factory"]()
    try:
        service = PersistenceService(session)
        reading = service.add_building_meter_reading(MeterType(pending["meter_type"]), date.fromisoformat(pending["date"]), Decimal(pending["value"]), True)
        service.commit()
        context.user_data.pop("pending_main_meter", None)
        await query.edit_message_text(f"✅ تم حفظ قراءة العداد الرئيسي رقم {reading.id}.")
    except (BusinessRuleError, ValueError, PermissionError) as exc:
        session.rollback()
        await query.edit_message_text(f"❌ لم تُحفظ القراءة.\n\nالسبب: {exc}")
    finally:
        session.close()
