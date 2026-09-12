from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.application.complete_lease_service import CompleteLeaseService
from app.domain.rules import BusinessRuleError
from app.infrastructure.orm import FileRecord, TenantRecord, UnitRecord


def _authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    return user is not None and user.id == context.application.bot_data["owner_id"]


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد إنشاء العقد", callback_data="complete_lease_confirm"), InlineKeyboardButton("❌ إلغاء", callback_data="complete_lease_cancel")]])


async def newlease_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        return
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) != 8:
        await update.message.reply_text("الصيغة:\n/newlease unit_id | tenant_id | YYYY-MM-DD | YYYY-MM-DD أو - | rent | deposit | due_day | payment_method\n\nبعدها سيطلب البوت الشاهدين ثم ملف العقد ثم ملف الضمان ثم يعرض مراجعة نهائية.")
        return
    try:
        unit_id, tenant_id = int(parts[0]), int(parts[1])
        start = date.fromisoformat(parts[2])
        end = None if parts[3] == "-" else date.fromisoformat(parts[3])
        rent, deposit, due = Decimal(parts[4]), Decimal(parts[5]), int(parts[6])
        session = context.application.bot_data["session_factory"]()
        try:
            unit = session.get(UnitRecord, unit_id)
            tenant = session.get(TenantRecord, tenant_id)
            if not unit or not tenant:
                raise BusinessRuleError("Unit or tenant does not exist.")
        finally:
            session.close()
        context.user_data["complete_lease"] = {"stage": "witness1", "unit_id": unit_id, "tenant_id": tenant_id, "start": start.isoformat(), "end": parts[3], "rent": str(rent), "deposit": str(deposit), "due": due, "payment_method": parts[7]}
        await update.message.reply_text(f"📄 بدء إنشاء عقد كامل\n\nالوحدة: {unit.number} — {unit.name}\nالمستأجر: {tenant.name}\n\nأرسل الآن بيانات الشاهد الأول بهذا الشكل:\nالاسم | الهاتف")
    except (ValueError, BusinessRuleError) as exc:
        await update.message.reply_text(f"❌ بيانات العقد غير صحيحة: {exc}")


async def lease_wizard_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        return
    state = context.user_data.get("complete_lease")
    if not state or state.get("stage") not in {"witness1", "witness2"}:
        return
    parts = [p.strip() for p in (update.effective_message.text or "").split("|")]
    if len(parts) != 2 or not all(parts):
        await update.effective_message.reply_text("الصيغة المطلوبة: الاسم | الهاتف")
        return
    if state["stage"] == "witness1":
        state["witness1"] = [parts[0], parts[1]]
        state["stage"] = "witness2"
        await update.effective_message.reply_text("تم تسجيل الشاهد الأول مؤقتًا.\nأرسل الآن بيانات الشاهد الثاني:\nالاسم | الهاتف")
    else:
        state["witness2"] = [parts[0], parts[1]]
        state["stage"] = "contract_file"
        await update.effective_message.reply_text("تم تسجيل الشاهدين مؤقتًا.\n📎 أرسل الآن صورة أو ملف العقد.")


async def lease_wizard_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        return
    state = context.user_data.get("complete_lease")
    if not state or state.get("stage") not in {"contract_file", "guarantee_file"}:
        from app.interfaces.telegram.bot import receive_file
        await receive_file(update, context)
        return
    message = update.effective_message
    storage_dir = Path(context.application.bot_data["storage_dir"])
    inbox = storage_dir / "telegram_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    if message.document:
        source = message.document
        telegram_file = await context.bot.get_file(source.file_id)
        safe_name = Path(source.file_name or f"document-{source.file_unique_id}").name
        target = inbox / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{safe_name}"
        await telegram_file.download_to_drive(custom_path=str(target))
        mime = source.mime_type
        original = safe_name
    elif message.photo:
        source = message.photo[-1]
        telegram_file = await context.bot.get_file(source.file_id)
        target = inbox / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{source.file_unique_id}.jpg"
        await telegram_file.download_to_drive(custom_path=str(target))
        mime = "image/jpeg"
        original = target.name
    else:
        return
    session = context.application.bot_data["session_factory"]()
    try:
        record = FileRecord(entity_type="telegram_inbox", entity_id=update.effective_user.id, original_name=original, storage_path=str(target), mime_type=mime)
        session.add(record)
        session.commit()
        if state["stage"] == "contract_file":
            state["contract_file_id"] = record.id
            state["stage"] = "guarantee_file"
            await message.reply_text(f"📎 تم حفظ ملف العقد رقم {record.id}.\n\nأرسل الآن صورة أو ملف الضمان.")
        else:
            state["guarantee_file_id"] = record.id
            state["stage"] = "review"
            await message.reply_text(_review_text(state), reply_markup=_confirm_keyboard())
    finally:
        session.close()


def _review_text(state: dict) -> str:
    return ("⚠️ المراجعة النهائية — لم يتم إنشاء العقد بعد.\n\n"
            f"الوحدة: {state['unit_id']}\nالمستأجر: {state['tenant_id']}\n"
            f"البداية: {state['start']}\nالنهاية: {state['end']}\n"
            f"الإيجار: {state['rent']}\nالتأمين: {state['deposit']}\n"
            f"يوم الاستحقاق: {state['due']}\nطريقة الدفع: {state['payment_method']}\n"
            f"الشاهد 1: {state['witness1'][0]} — {state['witness1'][1]}\n"
            f"الشاهد 2: {state['witness2'][0]} — {state['witness2'][1]}\n"
            f"ملف العقد: {state['contract_file_id']}\nملف الضمان: {state['guarantee_file_id']}\n\n"
            "⚠️ عند التأكيد سيتم إنشاء العقد وربط المستندين والشاهدين في معاملة واحدة.")


async def lease_wizard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        await update.callback_query.answer("غير مصرح", show_alert=True)
        return
    query = update.callback_query
    await query.answer()
    state = context.user_data.get("complete_lease")
    if not state or state.get("stage") != "review":
        await query.edit_message_text("انتهت صلاحية إنشاء العقد. لم يتم تنفيذ شيء.")
        return
    if query.data == "complete_lease_cancel":
        context.user_data.pop("complete_lease", None)
        await query.edit_message_text("❌ أُلغيت عملية إنشاء العقد. الملفات المرفوعة بقيت في صندوق الملفات غير المرتبطة ولم يُنشأ عقد.")
        return
    session = context.application.bot_data["session_factory"]()
    try:
        lease = CompleteLeaseService(session).create(
            unit_id=int(state["unit_id"]), tenant_id=int(state["tenant_id"]),
            start_date=date.fromisoformat(state["start"]), end_date=None if state["end"] == "-" else date.fromisoformat(state["end"]),
            rent_amount=Decimal(state["rent"]), deposit_amount=Decimal(state["deposit"]), due_day=int(state["due"]), payment_method=state["payment_method"],
            witnesses=[tuple(state["witness1"]), tuple(state["witness2"])], contract_file_id=int(state["contract_file_id"]), guarantee_file_id=int(state["guarantee_file_id"]), confirmed=True,
        )
        session.commit()
        context.user_data.pop("complete_lease", None)
        await query.edit_message_text(f"✅ تم إنشاء العقد الكامل بنجاح.\nرقم العقد: {lease.id}\nالوحدة: {lease.unit_id}\nالمستأجر: {lease.tenant_id}")
    except (BusinessRuleError, ValueError, PermissionError) as exc:
        session.rollback()
        await query.edit_message_text(f"❌ لم يتم إنشاء العقد. لم تُحفظ أي علاقة جزئية.\n\nالسبب: {exc}")
    finally:
        session.close()
