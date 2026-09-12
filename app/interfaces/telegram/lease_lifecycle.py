from __future__ import annotations

from datetime import date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.application.lease_lifecycle_service import LeaseLifecycleService
from app.domain.rules import BusinessRuleError


def _authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    return user is not None and user.id == context.application.bot_data["owner_id"]


def _keyboard(kind: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد التنفيذ", callback_data=f"lease_lifecycle_confirm:{kind}"), InlineKeyboardButton("❌ إلغاء", callback_data=f"lease_lifecycle_cancel:{kind}")]])


async def endlease_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        return
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) not in {2, 3}:
        await update.message.reply_text("الصيغة:\n/endlease lease_id | YYYY-MM-DD | سبب اختياري")
        return
    try:
        lease_id = int(parts[0])
        end_date = date.fromisoformat(parts[1])
        reason = parts[2] if len(parts) == 3 else ""
        context.user_data["pending_lease_lifecycle"] = {"kind": "end", "lease_id": lease_id, "end_date": end_date.isoformat(), "reason": reason}
        await update.message.reply_text(f"⚠️ مراجعة إنهاء العقد\n\nالعقد: {lease_id}\nتاريخ الانتهاء الفعلي: {end_date}\nالسبب: {reason or 'غير محدد'}\n\nلن يتم إنهاء العقد قبل التأكيد الصريح.", reply_markup=_keyboard("end"))
    except (ValueError, BusinessRuleError) as exc:
        await update.message.reply_text(f"❌ بيانات إنهاء العقد غير صحيحة: {exc}")


async def renewlease_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        return
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) not in {2, 3}:
        await update.message.reply_text("الصيغة:\n/renewlease lease_id | YYYY-MM-DD | إيجار جديد اختياري")
        return
    try:
        lease_id = int(parts[0])
        new_end = date.fromisoformat(parts[1])
        rent = parts[2] if len(parts) == 3 and parts[2] else None
        if rent is not None:
            from decimal import Decimal
            Decimal(rent)
        context.user_data["pending_lease_lifecycle"] = {"kind": "renew", "lease_id": lease_id, "new_end_date": new_end.isoformat(), "rent_amount": rent}
        await update.message.reply_text(f"⚠️ مراجعة تجديد العقد\n\nالعقد الحالي: {lease_id}\nنهاية العقد الجديد: {new_end}\nالإيجار الجديد: {rent or 'نفس الإيجار الحالي'}\n\nالتجديد سينشئ عقدًا جديدًا يبدأ في اليوم التالي لنهاية العقد الحالي، ولن يغير العقد السابق.", reply_markup=_keyboard("renew"))
    except (ValueError, BusinessRuleError) as exc:
        await update.message.reply_text(f"❌ بيانات التجديد غير صحيحة: {exc}")


async def expiring_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        return
    try:
        days = int(context.args[0]) if context.args else 15
        session = context.application.bot_data["session_factory"]()
        try:
            rows = LeaseLifecycleService(session).expiring_within(days)
            if not rows:
                text = f"✅ لا توجد عقود نشطة تنتهي خلال {days} يومًا."
            else:
                text = f"⏰ العقود التي تنتهي خلال {days} يومًا:\n" + "\n".join(f"• العقد {x.id} — الوحدة {x.unit_id} — المستأجر {x.tenant_id} — النهاية {x.end_date}" for x in rows)
        finally:
            session.close()
        await update.message.reply_text(text)
    except (ValueError, BusinessRuleError) as exc:
        await update.message.reply_text(f"❌ تعذر فحص العقود: {exc}")


async def lease_lifecycle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        await update.callback_query.answer("غير مصرح", show_alert=True)
        return
    query = update.callback_query
    await query.answer()
    pending = context.user_data.get("pending_lease_lifecycle")
    if not pending:
        await query.edit_message_text("انتهت صلاحية العملية. لم يتم تنفيذ شيء.")
        return
    action, kind = (query.data or "").split(":", 1)
    if action == "lease_lifecycle_cancel":
        context.user_data.pop("pending_lease_lifecycle", None)
        await query.edit_message_text("❌ أُلغيت العملية ولم يتم تغيير العقد.")
        return
    session = context.application.bot_data["session_factory"]()
    try:
        service = LeaseLifecycleService(session)
        if kind == "end":
            lease = service.end_lease(int(pending["lease_id"]), date.fromisoformat(pending["end_date"]), reason=pending["reason"], confirmed=True)
            message = f"✅ تم إنهاء العقد رقم {lease.id} بتاريخ {lease.end_date}."
        elif kind == "renew":
            from decimal import Decimal
            rent = Decimal(pending["rent_amount"]) if pending["rent_amount"] else None
            lease = service.renew_lease(int(pending["lease_id"]), date.fromisoformat(pending["new_end_date"]), rent_amount=rent, confirmed=True)
            message = f"✅ تم إنشاء العقد المجدد رقم {lease.id}.\nالبداية: {lease.start_date}\nالنهاية: {lease.end_date}\nالإيجار: {lease.rent_amount}"
        else:
            raise BusinessRuleError("Unknown lease lifecycle operation.")
        session.commit()
        context.user_data.pop("pending_lease_lifecycle", None)
        await query.edit_message_text(message)
    except (BusinessRuleError, ValueError, PermissionError) as exc:
        session.rollback()
        await query.edit_message_text(f"❌ لم يتم تنفيذ العملية.\n\nالسبب: {exc}")
    finally:
        session.close()
