from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from sqlalchemy import select

from app.application.document_service import DocumentService
from app.domain.rules import BusinessRuleError
from app.infrastructure.orm import FileRecord, LeaseRecord, TenantRecord


def _authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    return user is not None and user.id == context.application.bot_data["owner_id"]


async def document_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Link the most recently uploaded file to a tenant or lease after review."""
    if not _authorized(update, context):
        return
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) != 3:
        await update.message.reply_text(
            "الصيغة:\n/doc file_id | tenant_id أو lease_id | النوع\n\n"
            "الأنواع: TENANT_ID_FRONT, TENANT_ID_BACK, LEASE_CONTRACT, GUARANTEE, OTHER"
        )
        return
    try:
        file_id = int(parts[0]); target_id = int(parts[1]); attachment_type = parts[2].upper()
        session = context.application.bot_data["session_factory"]()
        try:
            file_record = session.get(FileRecord, file_id)
            if not file_record:
                raise BusinessRuleError("File does not exist.")
            tenant = session.get(TenantRecord, target_id)
            lease = session.get(LeaseRecord, target_id)
            if not tenant and not lease:
                raise BusinessRuleError("Tenant or lease does not exist.")
            if tenant and lease:
                raise BusinessRuleError("Use an unambiguous target: target ID matches both tenant and lease.")
            target_label = f"المستأجر {tenant.name}" if tenant else f"العقد {lease.id}"
        finally:
            session.close()
        context.user_data["pending_document"] = {
            "file_id": file_id,
            "target_type": "tenant" if tenant else "lease",
            "target_id": target_id,
            "attachment_type": attachment_type,
        }
        await update.message.reply_text(
            f"⚠️ مراجعة ربط المستند\n\nالملف: {file_id}\nالهدف: {target_label}\nالنوع: {attachment_type}\n\nلن يتم تغيير علاقة الملف قبل التأكيد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد الربط", callback_data="document_confirm"), InlineKeyboardButton("❌ إلغاء", callback_data="document_cancel")]])
        )
    except (ValueError, BusinessRuleError) as exc:
        await update.message.reply_text(f"❌ لم يتم إعداد الربط: {exc}")


async def document_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        await update.callback_query.answer("غير مصرح", show_alert=True); return
    query = update.callback_query; await query.answer()
    pending = context.user_data.get("pending_document")
    if not pending:
        await query.edit_message_text("انتهت صلاحية عملية ربط المستند. لم يتم تغيير شيء."); return
    if query.data == "document_cancel":
        context.user_data.pop("pending_document", None)
        await query.edit_message_text("❌ أُلغيت عملية ربط المستند."); return
    session = context.application.bot_data["session_factory"]()
    try:
        service = DocumentService(session)
        kwargs = {"tenant_id": pending["target_id"]} if pending["target_type"] == "tenant" else {"lease_id": pending["target_id"]}
        service.attach_file(pending["file_id"], pending["attachment_type"], confirmed=True, **kwargs)
        session.commit(); context.user_data.pop("pending_document", None)
        await query.edit_message_text("✅ تم ربط المستند بنجاح.")
    except (BusinessRuleError, ValueError, PermissionError) as exc:
        session.rollback(); await query.edit_message_text(f"❌ لم يتم ربط المستند.\n\nالسبب: {exc}")
    finally:
        session.close()


async def witness_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        return
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) != 4:
        await update.message.reply_text("الصيغة:\n/witness lease_id | 1 أو 2 | اسم الشاهد | الهاتف")
        return
    try:
        lease_id = int(parts[0]); order = int(parts[1]); name = parts[2]; phone = parts[3]
        context.user_data["pending_witness"] = {"lease_id": lease_id, "order": order, "name": name, "phone": phone}
        await update.message.reply_text(
            f"⚠️ مراجعة إضافة الشاهد\n\nالعقد: {lease_id}\nالشاهد: {order}\nالاسم: {name}\nالهاتف: {phone}\n\nلم يتم الحفظ بعد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد", callback_data="witness_confirm"), InlineKeyboardButton("❌ إلغاء", callback_data="witness_cancel")]])
        )
    except ValueError as exc:
        await update.message.reply_text(f"❌ بيانات غير صحيحة: {exc}")


async def witness_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        await update.callback_query.answer("غير مصرح", show_alert=True); return
    query = update.callback_query; await query.answer(); pending = context.user_data.get("pending_witness")
    if not pending:
        await query.edit_message_text("انتهت صلاحية عملية الشاهد."); return
    if query.data == "witness_cancel":
        context.user_data.pop("pending_witness", None); await query.edit_message_text("❌ أُلغيت العملية."); return
    session = context.application.bot_data["session_factory"]()
    try:
        witness = DocumentService(session).add_witness(pending["lease_id"], pending["name"], pending["phone"], pending["order"], True)
        session.commit(); context.user_data.pop("pending_witness", None)
        await query.edit_message_text(f"✅ تم حفظ الشاهد {witness.witness_order} للعقد {witness.lease_id}.")
    except (BusinessRuleError, ValueError, PermissionError) as exc:
        session.rollback(); await query.edit_message_text(f"❌ لم يتم حفظ الشاهد.\n\nالسبب: {exc}")
    finally:
        session.close()
