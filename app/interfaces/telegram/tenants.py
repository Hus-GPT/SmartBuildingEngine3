from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.application.tenant_service import TenantService
from app.domain.rules import BusinessRuleError


def _authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    return user is not None and user.id == context.application.bot_data["owner_id"]


async def tenantinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        return
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) != 3:
        await update.message.reply_text("الصيغة:\n/tenantinfo tenant_id | نوع الهوية | رقم الهوية")
        return
    try:
        tenant_id = int(parts[0])
        context.user_data["pending_tenant_identity"] = {"tenant_id": tenant_id, "identity_type": parts[1], "identity_number": parts[2]}
        await update.message.reply_text(f"⚠️ مراجعة بيانات الهوية\n\nالمستأجر: {tenant_id}\nنوع الهوية: {parts[1]}\nرقم الهوية: {parts[2]}\n\nلن يتم حفظ التغيير قبل التأكيد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد", callback_data="tenant_identity_confirm"), InlineKeyboardButton("❌ إلغاء", callback_data="tenant_identity_cancel")]]))
    except ValueError:
        await update.message.reply_text("❌ رقم المستأجر غير صحيح.")


async def tenantcheck_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        return
    try:
        tenant_id = int(context.args[0])
        session = context.application.bot_data["session_factory"]()
        try:
            missing = TenantService(session).missing_requirements(tenant_id)
        finally:
            session.close()
        if missing:
            labels = {"identity_type": "نوع الهوية", "identity_number": "رقم الهوية", "TENANT_ID_FRONT": "صورة الهوية الأمامية", "TENANT_ID_BACK": "صورة الهوية الخلفية"}
            await update.message.reply_text("⚠️ ملف المستأجر غير مكتمل.\n\nالناقص:\n" + "\n".join(f"• {labels[x]}" for x in missing))
        else:
            await update.message.reply_text("✅ ملف المستأجر مكتمل من ناحية بيانات الهوية وصور الوجهين.")
    except (ValueError, BusinessRuleError) as exc:
        await update.message.reply_text(f"❌ تعذر فحص ملف المستأجر: {exc}")


async def tenant_identity_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        await update.callback_query.answer("غير مصرح", show_alert=True)
        return
    query = update.callback_query
    await query.answer()
    pending = context.user_data.get("pending_tenant_identity")
    if not pending:
        await query.edit_message_text("انتهت صلاحية العملية.")
        return
    if query.data == "tenant_identity_cancel":
        context.user_data.pop("pending_tenant_identity", None)
        await query.edit_message_text("❌ أُلغيت العملية.")
        return
    session = context.application.bot_data["session_factory"]()
    try:
        tenant = TenantService(session).set_identity(int(pending["tenant_id"]), pending["identity_type"], pending["identity_number"], True)
        session.commit()
        context.user_data.pop("pending_tenant_identity", None)
        await query.edit_message_text(f"✅ تم تحديث بيانات هوية المستأجر {tenant.id}.")
    except (BusinessRuleError, ValueError, PermissionError) as exc:
        session.rollback()
        await query.edit_message_text(f"❌ لم يتم تحديث الهوية.\n\nالسبب: {exc}")
    finally:
        session.close()
