from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.application.building_report_service import BuildingReportService


def _authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    return user is not None and user.id == context.application.bot_data["owner_id"]


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update, context):
        return
    session = context.application.bot_data["session_factory"]()
    try:
        service = BuildingReportService(session)
        summary = service.building_summary()
        rows = service.unit_statuses()
        text = f"🏢 ملخص المبنى\n\nإجمالي الوحدات: {summary['total_units']}\nالمشغولة: {summary['occupied']}\nالشاغرة: {summary['vacant']}\nإجمالي المتأخرات: {summary['outstanding']}\n\n"
        if rows:
            text += "📋 حالة الوحدات:\n" + "\n".join(f"• {r['number']} — {'مشغولة' if r['status'] == 'occupied' else 'شاغرة'}" + (f" — {r['tenant_name']} — متبقي {r['outstanding']}" if r['status'] == 'occupied' else "") for r in rows)
        else:
            text += "لا توجد وحدات مسجلة."
        await update.message.reply_text(text)
    finally:
        session.close()
