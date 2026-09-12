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

    def end_lease(self, lease_id: int, end_date: date, confirmed: bool, reason: str = "") -> LeaseRecord:
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
        self._audit("end_lease", lease.id, {"end_date": end_date.isoformat(), "reason": reason.strip()})
        return lease

    def renew_lease(
        self,
        lease_id: int,
        new_end_date: date,
        confirmed: bool,
        rent_amount: object | None = None,
    ) -> LeaseRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before renewing a lease.")
        lease = self.session.get(LeaseRecord, lease_id)
        if not lease:
            raise BusinessRuleError("Lease does not exist.")
        if lease.status != LeaseStatus.ACTIVE.value:
            raise BusinessRuleError("Only an active lease can be renewed.")
        if lease.end_date is None:
            raise BusinessRuleError("A lease without an end date cannot be renewed; define its duration first.")
        if new_end_date <= lease.end_date:
            raise BusinessRuleError("Renewal end date must be later than the current end date.")
        if rent_amount is not None and str(rent_amount) != str(lease.rent_amount):
            raise BusinessRuleError("Rent cannot be increased during an active contract.")
        previous_end = lease.end_date
        lease.end_date = new_end_date
        self._audit("renew_lease", lease.id, {"previous_end_date": previous_end.isoformat(), "new_end_date": new_end_date.isoformat(), "rent_amount": str(lease.rent_amount)})
        return lease

    def active_lease(self, unit_id: int) -> LeaseRecord | None:
        return self.session.scalar(
            select(LeaseRecord).where(
                LeaseRecord.unit_id == unit_id,
                LeaseRecord.status == LeaseStatus.ACTIVE.value,
            )
        )

    def ending_within(self, days: int, today: date | None = None) -> list[LeaseRecord]:
        if days < 0:
            raise ValueError("days must be non-negative")
        today = today or date.today()
        target = date.fromordinal(today.toordinal() + days)
        return list(self.session.scalars(select(LeaseRecord).where(LeaseRecord.status == LeaseStatus.ACTIVE.value, LeaseRecord.end_date.is_not(None), LeaseRecord.end_date >= today, LeaseRecord.end_date <= target).order_by(LeaseRecord.end_date)).all())

    def _audit(self, operation: str, entity_id: int, details: dict) -> None:
        self.session.add(AuditLogRecord(operation=operation, entity_type="lease", entity_id=entity_id, details=str(details), created_at=datetime.now(timezone.utc)))
