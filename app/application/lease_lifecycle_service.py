from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import LeaseStatus
from app.domain.rules import BusinessRuleError
from app.infrastructure.orm import AuditLogRecord, LeaseRecord


class LeaseLifecycleService:
    """Contract lifecycle operations independent of Telegram."""

    def __init__(self, session: Session):
        self.session = session

    def end_lease(self, lease_id: int, end_date: date, *, reason: str | None = None, confirmed: bool) -> LeaseRecord:
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
        self.session.add(AuditLogRecord(operation="end_lease", entity_type="lease", entity_id=lease.id, details=str({"end_date": end_date.isoformat(), "reason": reason or ""})))
        self.session.flush()
        return lease

    def renew_lease(self, lease_id: int, new_end_date: date, *, rent_amount: Decimal | None = None, deposit_amount: Decimal | None = None, due_day: int | None = None, payment_method: str | None = None, confirmed: bool) -> LeaseRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before renewing a lease.")
        old = self.session.get(LeaseRecord, lease_id)
        if not old:
            raise BusinessRuleError("Lease does not exist.")
        if old.status != LeaseStatus.ACTIVE.value:
            raise BusinessRuleError("Only an active lease can be renewed.")
        if old.end_date is None:
            raise BusinessRuleError("A lease without an end date cannot be renewed automatically.")
        new_start = old.end_date + timedelta(days=1)
        if new_end_date < new_start:
            raise BusinessRuleError("Renewed lease end date must be after its start date.")
        if due_day is not None and not 1 <= due_day <= 31:
            raise BusinessRuleError("Due day must be between 1 and 31.")
        rent = old.rent_amount if rent_amount is None else Decimal(rent_amount)
        deposit = old.deposit_amount if deposit_amount is None else Decimal(deposit_amount)
        if rent < 0 or deposit < 0:
            raise BusinessRuleError("Rent and deposit cannot be negative.")
        old.status = LeaseStatus.ENDED.value
        new_lease = LeaseRecord(unit_id=old.unit_id, tenant_id=old.tenant_id, start_date=new_start, end_date=new_end_date, rent_amount=rent, deposit_amount=deposit, due_day=old.due_day if due_day is None else due_day, payment_method=old.payment_method if payment_method is None else payment_method.strip(), status=LeaseStatus.ACTIVE.value)
        self.session.add(new_lease)
        self.session.flush()
        self.session.add(AuditLogRecord(operation="renew_lease", entity_type="lease", entity_id=new_lease.id, details=str({"previous_lease_id": old.id, "previous_end_date": old.end_date.isoformat(), "new_start_date": new_start.isoformat(), "new_end_date": new_end_date.isoformat(), "rent_amount": str(rent)})))
        self.session.flush()
        return new_lease

    def expiring_within(self, days: int = 15, *, as_of: date | None = None) -> list[LeaseRecord]:
        if days < 0:
            raise BusinessRuleError("Days cannot be negative.")
        today = as_of or date.today()
        deadline = today + timedelta(days=days)
        return list(self.session.scalars(select(LeaseRecord).where(LeaseRecord.status == LeaseStatus.ACTIVE.value, LeaseRecord.end_date.is_not(None), LeaseRecord.end_date >= today, LeaseRecord.end_date <= deadline).order_by(LeaseRecord.end_date, LeaseRecord.id)).all())

    @staticmethod
    def duration_days(start_date: date, end_date: date | None, *, as_of: date | None = None) -> int | None:
        finish = end_date or as_of
        if finish is None:
            return None
        if finish < start_date:
            raise BusinessRuleError("End date cannot precede start date.")
        return (finish - start_date).days + 1

    @staticmethod
    def duration_calendar(start_date: date, end_date: date) -> tuple[int, int, int]:
        if end_date < start_date:
            raise BusinessRuleError("End date cannot precede start date.")
        years = end_date.year - start_date.year
        cursor = start_date.replace(year=start_date.year + years)
        if cursor > end_date:
            years -= 1
            cursor = start_date.replace(year=start_date.year + years)
        months = 0
        while months < 11:
            candidate_month = cursor.month + 1
            candidate_year = cursor.year
            if candidate_month == 13:
                candidate_month = 1
                candidate_year += 1
            day = min(cursor.day, monthrange(candidate_year, candidate_month)[1])
            candidate = cursor.replace(year=candidate_year, month=candidate_month, day=day)
            if candidate > end_date:
                break
            cursor = candidate
            months += 1
        return years, months, (end_date - cursor).days
