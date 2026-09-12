from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from sqlalchemy import select

from app.application.persistence_service import PersistenceService
from app.domain.models import UnitType
from app.domain.rules import BusinessRuleError
from app.infrastructure.orm import TenantRecord, UnitRecord


def _authorized(update: Update, owner_id: int) -> bool:
    user = update.effective_user
    return user is not None and owner_id != 0 and user.id == owner_id


def _session(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["session_factory"]()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]):
        if update.message:
            await update.message.reply_text("غير مصرح لك باستخدام هذا البوت.")
        return
    await menu(update, context)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🏢 Smart Building Manager\n\n"
        "اختر العملية المطلوبة:\n"
        "• الوحدات والمستأجرون\n"
        "• العدادات\n"
        "• العقود\n"
        "• الفواتير والمدفوعات\n\n"
        "أي عملية كتابة حساسة تمر بالمراجعة والتحذير والتأكيد الصريح."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 الوحدات", callback_data="list_units"),
         InlineKeyboardButton("👤 المستأجرون", callback_data="list_tenants")],
        [InlineKeyboardButton("➕ إضافة وحدة", callback_data="help_add_unit"),
         InlineKeyboardButton("➕ إضافة مستأجر", callback_data="help_add_tenant")],
        [InlineKeyboardButton("📊 العدادات", callback_data="meters_info"),
         InlineKeyboardButton("🧾 الفواتير", callback_data="invoices_info")],
    ])
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    elif update.message:
        await update.message.reply_text(text, reply_markup=keyboard)


async def units(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]):
        return
    session = _session(context)
    try:
        rows = session.scalars(select(UnitRecord).order_by(UnitRecord.number)).all()
        if not rows:
            text = "🏠 لا توجد وحدات مسجلة حتى الآن."
        else:
            lines = ["🏠 الوحدات:"]
            for u in rows:
                lines.append(f"• {u.number} — {u.name} ({'شقة' if u.unit_type == 'apartment' else 'محل'})")
            text = "\n".join(lines)
        await update.message.reply_text(text)
    finally:
        session.close()


async def tenants(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]):
        return
    session = _session(context)
    try:
        rows = session.scalars(select(TenantRecord).order_by(TenantRecord.name)).all()
        if not rows:
            text = "👤 لا يوجد مستأجرون مسجلون حتى الآن."
        else:
            lines = ["👤 المستأجرون:"]
            for t in rows:
                phones = "، ".join(p.phone for p in t.phones)
                lines.append(f"• {t.id}. {t.name} — {phones}")
            text = "\n".join(lines)
        await update.message.reply_text(text)
    finally:
        session.close()


async def add_unit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]):
        return
    raw = " ".join(context.args).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 3 or parts[2].lower() not in {"apartment", "shop", "شقة", "محل"}:
        await update.message.reply_text(
            "الصيغة:\n/addunit رقم | اسم الوحدة | apartment/shop\n\n"
            "مثال:\n/addunit 101 | شقة 101 | apartment"
        )
        return
    kind = UnitType.APARTMENT if parts[2].lower() in {"apartment", "شقة"} else UnitType.SHOP
    context.user_data["pending_write"] = {"kind": "unit", "number": parts[0], "name": parts[1], "unit_type": kind.value}
    await update.message.reply_text(
        f"⚠️ مراجعة قبل التنفيذ\n\nرقم: {parts[0]}\nالاسم: {parts[1]}\nالنوع: {'شقة' if kind is UnitType.APARTMENT else 'محل'}\n\n"
        "لن يتم الحفظ إلا بعد تأكيدك.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد الحفظ", callback_data="confirm_write"),
                                             InlineKeyboardButton("❌ إلغاء", callback_data="cancel_write")]])
    )


async def add_tenant(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]):
        return
    raw = " ".join(context.args).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        await update.message.reply_text("الصيغة:\n/addtenant الاسم | الهاتف[, هاتف آخر]")
        return
    phones = [p.strip() for p in parts[1].split(",") if p.strip()]
    context.user_data["pending_write"] = {"kind": "tenant", "name": parts[0], "phones": phones}
    await update.message.reply_text(
        f"⚠️ مراجعة قبل التنفيذ\n\nالمستأجر: {parts[0]}\nالهواتف: {', '.join(phones)}\n\nلن يتم الحفظ إلا بعد تأكيدك.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد الحفظ", callback_data="confirm_write"),
                                             InlineKeyboardButton("❌ إلغاء", callback_data="cancel_write")]])
    )


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not _authorized(update, context.application.bot_data["owner_id"]):
        await query.edit_message_text("غير مصرح لك باستخدام هذا البوت.")
        return
    data = query.data or ""
    if data == "menu":
        await menu(update, context)
        return
    if data == "list_units":
        session = _session(context)
        try:
            rows = session.scalars(select(UnitRecord).order_by(UnitRecord.number)).all()
            text = "🏠 لا توجد وحدات." if not rows else "🏠 الوحدات:\n" + "\n".join(
                f"• {u.number} — {u.name} ({'شقة' if u.unit_type == 'apartment' else 'محل'})" for u in rows
            )
        finally:
            session.close()
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]]))
        return
    if data == "list_tenants":
        session = _session(context)
        try:
            rows = session.scalars(select(TenantRecord).order_by(TenantRecord.name)).all()
            text = "👤 لا يوجد مستأجرون." if not rows else "👤 المستأجرون:\n" + "\n".join(
                f"• {t.id}. {t.name} — {'، '.join(p.phone for p in t.phones)}" for t in rows
            )
        finally:
            session.close()
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]]))
        return
    if data == "help_add_unit":
        await query.edit_message_text("لإضافة وحدة استخدم:\n/addunit رقم | الاسم | apartment/shop\n\nثم ستظهر لك شاشة مراجعة وتأكيد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]]))
        return
    if data == "help_add_tenant":
        await query.edit_message_text("لإضافة مستأجر استخدم:\n/addtenant الاسم | الهاتف[, هاتف آخر]\n\nثم ستظهر لك شاشة مراجعة وتأكيد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]]))
        return
    if data in {"meters_info", "invoices_info"}:
        await query.edit_message_text("هذه الوحدة الوظيفية قيد الربط الآن، ولن يتم عرضها كجاهزة قبل اكتمال دورة العمل واختبارها.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]]))
        return
    if data == "cancel_write":
        context.user_data.pop("pending_write", None)
        await query.edit_message_text("❌ تم إلغاء العملية ولم يتم حفظ أي بيانات.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]]))
        return
    if data == "confirm_write":
        pending = context.user_data.get("pending_write")
        if not pending:
            await query.edit_message_text("انتهت صلاحية عملية التأكيد. لم يتم تنفيذ أي شيء.")
            return
        session = _session(context)
        try:
            service = PersistenceService(session)
            if pending["kind"] == "unit":
                obj = service.add_unit(pending["number"], pending["name"], UnitType(pending["unit_type"]))
                message = f"✅ تم حفظ الوحدة {obj.number} — {obj.name}."
            else:
                obj = service.add_tenant(pending["name"], pending["phones"])
                message = f"✅ تم حفظ المستأجر {obj.name} (رقم {obj.id})."
            service.commit()
            context.user_data.pop("pending_write", None)
            await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]]))
        except (BusinessRuleError, ValueError, PermissionError) as exc:
            session.rollback()
            await query.edit_message_text(f"❌ لم تُنفذ العملية.\n\nالسبب: {exc}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]]))
        finally:
            session.close()


def build_telegram_application(token: str, owner_id: int, session_factory) -> Application:
    if owner_id == 0:
        raise RuntimeError("TELEGRAM_OWNER_ID must be configured; the bot refuses to run without owner restriction.")
    application = Application.builder().token(token).build()
    application.bot_data["owner_id"] = owner_id
    application.bot_data["session_factory"] = session_factory
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("units", units))
    application.add_handler(CommandHandler("tenants", tenants))
    application.add_handler(CommandHandler("addunit", add_unit))
    application.add_handler(CommandHandler("addtenant", add_tenant))
    application.add_handler(CallbackQueryHandler(callback))
    return application
