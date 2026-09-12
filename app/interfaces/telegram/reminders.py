from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from telegram.ext import ContextTypes

from app.domain.models import LeaseStatus
from app.infrastructure.orm import AuditLogRecord, LeaseRecord, UnitRecord


REMINDER_OPERATION = "lease_expiry_reminder"


def leases_due_for_reminder(session, today: date | None = None) -> list[LeaseRecord]:
    today = today or datetime.now(timezone.utc).date()
    target = today + timedelta(days=15)
    return session.scalars(
        select(LeaseRecord)
        .where(
            LeaseRecord.status == LeaseStatus.ACTIVE.value,
            LeaseRecord.end_date == target,
        )
        .order_by(LeaseRecord.id)
    ).all()


def reminder_already_sent(session, lease_id: int, reminder_date: date) -> bool:
    return session.scalar(
        select(AuditLogRecord.id).where(
            AuditLogRecord.operation == REMINDER_OPERATION,
            AuditLogRecord.entity_type == "lease",
            AuditLogRecord.entity_id == lease_id,
            AuditLogRecord.details == f"reminder_date={reminder_date.isoformat()}",
        )
    ) is not None


async def lease_expiry_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    application = context.application
    owner_id = application.bot_data["owner_id"]
    session = application.bot_data["session_factory"]()
    today = datetime.now(timezone.utc).date()
    try:
        leases = leases_due_for_reminder(session, today)
        for lease in leases:
            if reminder_already_sent(session, lease.id, today):
                continue
            unit = session.get(UnitRecord, lease.unit_id)
            tenant = lease.tenant
            unit_label = f"{unit.number} — {unit.name}" if unit else str(lease.unit_id)
            tenant_name = tenant.name if tenant else str(lease.tenant_id)
            await context.bot.send_message(
                chat_id=owner_id,
                text=(
                    "🔔 تذكير بانتهاء عقد\n\n"
                    f"الوحدة: {unit_label}\n"
                    f"المستأجر: {tenant_name}\n"
                    f"رقم العقد: {lease.id}\n"
                    f"تاريخ الانتهاء: {lease.end_date}\n"
                    "المتبقي: 15 يومًا.\n\n"
                    "يرجى مراجعة التجديد أو إنهاء العقد."
                ),
            )
            session.add(
                AuditLogRecord(
                    operation=REMINDER_OPERATION,
                    entity_type="lease",
                    entity_id=lease.id,
                    details=f"reminder_date={today.isoformat()}",
                    created_at=datetime.now(timezone.utc),
                )
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
