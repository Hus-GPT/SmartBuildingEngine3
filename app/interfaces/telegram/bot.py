from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from sqlalchemy import select

from app.application.persistence_service import PersistenceService
from app.domain.models import MeterType, UnitType
from app.domain.rules import BusinessRuleError
from app.infrastructure.orm import FileRecord, TenantRecord, UnitRecord


def _authorized(update: Update, owner_id: int) -> bool:
    user = update.effective_user
    return user is not None and owner_id != 0 and user.id == owner_id


def _session(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["session_factory"]()


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد التنفيذ", callback_data="confirm_write"), InlineKeyboardButton("❌ إلغاء", callback_data="cancel_write")]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]):
        if update.message: await update.message.reply_text("غير مصرح لك باستخدام هذا البوت.")
        return
    await menu(update, context)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = "🏢 Smart Building Manager\n\nاختر العملية المطلوبة:\n• الوحدات والمستأجرون\n• العقود والعدادات\n• الفواتير والمدفوعات\n• الملفات والصور\n\n⚠️ كل عملية كتابة حساسة تمر بالمراجعة والتحذير والتأكيد الصريح."
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 الوحدات", callback_data="list_units"), InlineKeyboardButton("👤 المستأجرون", callback_data="list_tenants")],
        [InlineKeyboardButton("➕ إضافة وحدة", callback_data="help_add_unit"), InlineKeyboardButton("➕ إضافة مستأجر", callback_data="help_add_tenant")],
        [InlineKeyboardButton("📄 عقد جديد", callback_data="help_add_lease"), InlineKeyboardButton("📊 قراءة عداد", callback_data="help_meter")],
        [InlineKeyboardButton("🧾 الفواتير", callback_data="invoices_info")],
    ])
    if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    elif update.message: await update.message.reply_text(text, reply_markup=keyboard)


async def units(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]): return
    session = _session(context)
    try:
        rows = session.scalars(select(UnitRecord).order_by(UnitRecord.number)).all()
        text = "🏠 لا توجد وحدات مسجلة." if not rows else "🏠 الوحدات:\n" + "\n".join(f"• {u.id} — {u.number} — {u.name} ({'شقة' if u.unit_type == 'apartment' else 'محل'})" for u in rows)
        await update.message.reply_text(text)
    finally: session.close()


async def tenants(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]): return
    session = _session(context)
    try:
        rows = session.scalars(select(TenantRecord).order_by(TenantRecord.name)).all()
        text = "👤 لا يوجد مستأجرون مسجلون." if not rows else "👤 المستأجرون:\n" + "\n".join(f"• {t.id}. {t.name} — {'، '.join(p.phone for p in t.phones)}" for t in rows)
        await update.message.reply_text(text)
    finally: session.close()


async def add_unit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]): return
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) != 3 or parts[2].lower() not in {"apartment", "shop", "شقة", "محل"}:
        await update.message.reply_text("الصيغة:\n/addunit رقم | الاسم | apartment/shop\nمثال: /addunit 101 | شقة 101 | apartment"); return
    kind = UnitType.APARTMENT if parts[2].lower() in {"apartment", "شقة"} else UnitType.SHOP
    context.user_data["pending_write"] = {"kind":"unit", "number":parts[0], "name":parts[1], "unit_type":kind.value}
    await update.message.reply_text(f"⚠️ مراجعة قبل الحفظ\n\nالوحدة: {parts[0]} — {parts[1]}\nالنوع: {'شقة' if kind is UnitType.APARTMENT else 'محل'}\n\nلم يتم الحفظ بعد.", reply_markup=_confirm_keyboard())


async def add_tenant(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]): return
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        await update.message.reply_text("الصيغة:\n/addtenant الاسم | الهاتف[, هاتف آخر]"); return
    phones = [p.strip() for p in parts[1].split(",") if p.strip()]
    context.user_data["pending_write"] = {"kind":"tenant", "name":parts[0], "phones":phones}
    await update.message.reply_text(f"⚠️ مراجعة قبل الحفظ\n\nالمستأجر: {parts[0]}\nالهواتف: {', '.join(phones)}\n\nلم يتم الحفظ بعد.", reply_markup=_confirm_keyboard())


async def add_lease(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]): return
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) != 8:
        await update.message.reply_text("الصيغة:\n/addlease unit_id | tenant_id | YYYY-MM-DD | YYYY-MM-DD أو - | rent | deposit | due_day | payment_method"); return
    try:
        start = date.fromisoformat(parts[2]); end = None if parts[3] == "-" else date.fromisoformat(parts[3]); rent = Decimal(parts[4]); deposit = Decimal(parts[5]); due = int(parts[6])
        session = _session(context)
        try:
            unit = session.get(UnitRecord, int(parts[0])); tenant = session.get(TenantRecord, int(parts[1]))
            if not unit or not tenant: raise BusinessRuleError("Unit or tenant does not exist.")
        finally: session.close()
        context.user_data["pending_write"] = {"kind":"lease","unit_id":int(parts[0]),"tenant_id":int(parts[1]),"start":start.isoformat(),"end":parts[3],"rent":str(rent),"deposit":str(deposit),"due":due,"payment_method":parts[7]}
        await update.message.reply_text(f"⚠️ عقد جديد\n\nالوحدة: {unit.number} — {unit.name}\nالمستأجر: {tenant.name}\nالبداية: {start}\nالنهاية: {parts[3]}\nالإيجار: {rent}\nالتأمين: {deposit}\nيوم الاستحقاق: {due}\nطريقة الدفع: {parts[7]}\n\nلن يتم إنشاء العقد قبل التأكيد.", reply_markup=_confirm_keyboard())
    except (ValueError, BusinessRuleError) as exc: await update.message.reply_text(f"❌ بيانات العقد غير صحيحة: {exc}")


async def add_meter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]): return
    parts = [p.strip() for p in " ".join(context.args).split("|")]
    if len(parts) != 4 or parts[1].lower() not in {"electricity","water","كهرباء","ماء"}:
        await update.message.reply_text("الصيغة:\n/meter unit_id | electricity/water | YYYY-MM-DD | reading"); return
    try:
        meter = MeterType.ELECTRICITY if parts[1].lower() in {"electricity","كهرباء"} else MeterType.WATER; reading_date = date.fromisoformat(parts[2]); value = Decimal(parts[3])
        session = _session(context)
        try:
            unit = session.get(UnitRecord, int(parts[0]))
            if not unit: raise BusinessRuleError("Unit does not exist.")
        finally: session.close()
        context.user_data["pending_write"] = {"kind":"meter","unit_id":int(parts[0]),"meter_type":meter.value,"date":reading_date.isoformat(),"value":str(value)}
        await update.message.reply_text(f"⚠️ مراجعة قراءة العداد\n\nالوحدة: {unit.number} — {unit.name}\nالعداد: {'كهرباء' if meter is MeterType.ELECTRICITY else 'ماء'}\nالتاريخ: {reading_date}\nالقراءة: {value}\n\nسيتم رفضها تلقائيًا إذا كانت أقل من آخر قراءة.", reply_markup=_confirm_keyboard())
    except (ValueError, BusinessRuleError) as exc: await update.message.reply_text(f"❌ بيانات القراءة غير صحيحة: {exc}")


async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context.application.bot_data["owner_id"]): return
    message = update.effective_message
    if not message: return
    storage_dir = Path(context.application.bot_data["storage_dir"]); inbox = storage_dir / "telegram_inbox"; inbox.mkdir(parents=True, exist_ok=True)
    document = message.document
    if document:
        telegram_file = await context.bot.get_file(document.file_id)
        safe_name = Path(document.file_name or f"document-{document.file_id}").name
        target = inbox / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{safe_name}"
        await telegram_file.download_to_drive(custom_path=str(target))
        mime = document.mime_type
        original = safe_name
    elif message.photo:
        photo = message.photo[-1]
        telegram_file = await context.bot.get_file(photo.file_id)
        target = inbox / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{photo.file_unique_id}.jpg"
        await telegram_file.download_to_drive(custom_path=str(target))
        mime = "image/jpeg"; original = target.name
    else: return
    session = _session(context)
    try:
        record = FileRecord(entity_type="telegram_inbox", entity_id=update.effective_user.id, original_name=original, storage_path=str(target), mime_type=mime)
        session.add(record); session.commit()
        await message.reply_text(f"📎 تم حفظ الملف بأمان.\nالاسم: {original}\nرقم الملف: {record.id}")
    finally: session.close()


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer()
    if not _authorized(update, context.application.bot_data["owner_id"]): await query.edit_message_text("غير مصرح لك باستخدام هذا البوت."); return
    data = query.data or ""
    if data == "menu": await menu(update, context); return
    if data == "cancel_write":
        context.user_data.pop("pending_write", None); await query.edit_message_text("❌ أُلغيت العملية ولم تُحفظ بيانات.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]])); return
    if data == "confirm_write":
        pending = context.user_data.get("pending_write")
        if not pending: await query.edit_message_text("انتهت صلاحية عملية التأكيد. لم يُنفذ شيء."); return
        session = _session(context)
        try:
            service = PersistenceService(session); kind = pending["kind"]
            if kind == "unit": obj = service.add_unit(pending["number"], pending["name"], UnitType(pending["unit_type"])); message = f"✅ تم حفظ الوحدة {obj.number} — {obj.name}."
            elif kind == "tenant": obj = service.add_tenant(pending["name"], pending["phones"]); message = f"✅ تم حفظ المستأجر {obj.name} (رقم {obj.id})."
            elif kind == "lease": obj = service.add_lease(int(pending["unit_id"]), int(pending["tenant_id"]), date.fromisoformat(pending["start"]), None if pending["end"] == "-" else date.fromisoformat(pending["end"]), Decimal(pending["rent"]), Decimal(pending["deposit"]), int(pending["due"]), pending["payment_method"], True); message = f"✅ تم إنشاء العقد رقم {obj.id}."
            elif kind == "meter": obj = service.add_meter_reading(int(pending["unit_id"]), MeterType(pending["meter_type"]), date.fromisoformat(pending["date"]), Decimal(pending["value"]), True); message = f"✅ تم حفظ قراءة العداد رقم {obj.id}."
            else: raise BusinessRuleError("Unknown pending operation.")
            service.commit(); context.user_data.pop("pending_write", None)
            await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]]))
        except (BusinessRuleError, ValueError, PermissionError) as exc:
            session.rollback(); await query.edit_message_text(f"❌ لم تُنفذ العملية.\n\nالسبب: {exc}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]]))
        finally: session.close()
        return
    if data == "list_units":
        session = _session(context)
        try: rows = session.scalars(select(UnitRecord).order_by(UnitRecord.number)).all(); text = "🏠 لا توجد وحدات." if not rows else "🏠 الوحدات:\n" + "\n".join(f"• {u.id} — {u.number} — {u.name} ({'شقة' if u.unit_type == 'apartment' else 'محل'})" for u in rows)
        finally: session.close()
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]])); return
    if data == "list_tenants":
        session = _session(context)
        try: rows = session.scalars(select(TenantRecord).order_by(TenantRecord.name)).all(); text = "👤 لا يوجد مستأجرون." if not rows else "👤 المستأجرون:\n" + "\n".join(f"• {t.id}. {t.name} — {'، '.join(p.phone for p in t.phones)}" for t in rows)
        finally: session.close()
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]])); return
    help_text = {"help_add_unit":"/addunit رقم | الاسم | apartment/shop", "help_add_tenant":"/addtenant الاسم | الهاتف[, هاتف آخر]", "help_add_lease":"/addlease unit_id | tenant_id | YYYY-MM-DD | YYYY-MM-DD أو - | rent | deposit | due_day | payment_method", "help_meter":"/meter unit_id | electricity/water | YYYY-MM-DD | reading", "invoices_info":"🧾 دورة الفواتير قيد الاستكمال والاختبار؛ لن تُعلن جاهزة قبل اكتمال الحساب، التأكيد، PDF، والمدفوعات."}
    if data in help_text: await query.edit_message_text(help_text[data], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ القائمة", callback_data="menu")]]))


def build_telegram_application(token: str, owner_id: int, session_factory, storage_dir: str | Path = "storage") -> Application:
    if owner_id == 0: raise RuntimeError("TELEGRAM_OWNER_ID must be configured; the bot refuses to run without owner restriction.")
    application = Application.builder().token(token).build()
    application.bot_data["owner_id"] = owner_id; application.bot_data["session_factory"] = session_factory; application.bot_data["storage_dir"] = Path(storage_dir)
    application.add_handler(CommandHandler("start", start)); application.add_handler(CommandHandler("menu", menu)); application.add_handler(CommandHandler("units", units)); application.add_handler(CommandHandler("tenants", tenants)); application.add_handler(CommandHandler("addunit", add_unit)); application.add_handler(CommandHandler("addtenant", add_tenant)); application.add_handler(CommandHandler("addlease", add_lease)); application.add_handler(CommandHandler("meter", add_meter)); application.add_handler(CallbackQueryHandler(callback)); application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, receive_file))
    return application
