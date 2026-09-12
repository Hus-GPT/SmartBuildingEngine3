from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import LeaseStatus
from app.domain.rules import BusinessRuleError
from app.infrastructure.orm import AuditLogRecord, LeaseRecord


class LeaseService:
    """Contract lifecycle use cases independent of Telegram."""

    def __init__(self, session: Session):
        self.session = session

    def end_lease(self, lease_id: int, end_date: date, confirmed: bool) -> LeaseRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before ending a lease.")
        lease = self.session.get(LeaseRecord, lease_id)
        if not lease:
            raise BusinessRuleError("Lease does not exist.")
        if lease.status != LeaseStatus.ACTIVE.value:
            raise BusinessRuleError("Only an active lease can be ended.")
        if end_date < lease.start_date:
            raise BusinessRuleError("Lease end date cannot precede its start date.")
        lease.end_date = end_date
        lease.status = LeaseStatus.ENDED.value
        self.session.add(AuditLogRecord(operation="end_lease", entity_type="lease", entity_id=lease.id, details=str({"end_date": end_date.isoformat()}), created_at=datetime.now(timezone.utc)))
        return lease

    def active_lease(self, unit_id: int) -> LeaseRecord | None:
        return self.session.scalar(
            select(LeaseRecord).where(
                LeaseRecord.unit_id == unit_id,
                LeaseRecord.status == LeaseStatus.ACTIVE.value,
            )
        )
