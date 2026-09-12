from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import LeaseStatus, MeterType, UnitType
from app.domain.rules import BusinessRuleError, validate_meter_reading, validate_payment_amount
from app.infrastructure.orm import (
    AuditLogRecord,
    InvoiceRecord,
    LeaseRecord,
    MeterReadingRecord,
    PaymentRecord,
    TenantPhoneRecord,
    TenantRecord,
    UnitRecord,
)


class PersistenceService:
    """Telegram-independent transactional use cases."""

    def __init__(self, session: Session):
        self.session = session

    def add_unit(self, number: str, name: str, unit_type: UnitType) -> UnitRecord:
        number = number.strip()
        name = name.strip()
        if not number or not name:
            raise BusinessRuleError("Unit number and name are required.")
        if self.session.scalar(select(UnitRecord).where(UnitRecord.number == number)):
            raise BusinessRuleError("A unit with this number already exists.")
        unit = UnitRecord(number=number, name=name, unit_type=unit_type.value)
        self.session.add(unit)
        self.session.flush()
        self._audit("create_unit", "unit", unit.id, {"number": number})
        return unit

    def add_tenant(self, name: str, phones: list[str]) -> TenantRecord:
        name = name.strip()
        phones = [p.strip() for p in phones if p.strip()]
        if not name or not phones:
            raise BusinessRuleError("Tenant name and at least one phone are required.")
        tenant = TenantRecord(name=name)
        tenant.phones = [TenantPhoneRecord(phone=p) for p in phones]
        self.session.add(tenant)
        self.session.flush()
        self._audit("create_tenant", "tenant", tenant.id, {"name": name})
        return tenant

    def add_lease(self, unit_id: int, tenant_id: int, start_date: date, end_date: date | None,
                  rent_amount: Decimal, deposit_amount: Decimal, due_day: int,
                  payment_method: str, confirmed: bool) -> LeaseRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before creating a lease.")
        if not 1 <= due_day <= 31:
            raise BusinessRuleError("Due day must be between 1 and 31.")
        if rent_amount < 0 or deposit_amount < 0:
            raise BusinessRuleError("Rent and deposit cannot be negative.")
        if end_date and end_date < start_date:
            raise BusinessRuleError("Lease end date cannot precede start date.")
        active = self.session.scalar(select(func.count(LeaseRecord.id)).where(
            LeaseRecord.unit_id == unit_id, LeaseRecord.status == LeaseStatus.ACTIVE.value
        )) or 0
        if active:
            raise BusinessRuleError("The unit already has an active lease.")
        lease = LeaseRecord(unit_id=unit_id, tenant_id=tenant_id, start_date=start_date,
                            end_date=end_date, rent_amount=rent_amount, deposit_amount=deposit_amount,
                            due_day=due_day, payment_method=payment_method, status=LeaseStatus.ACTIVE.value)
        self.session.add(lease)
        self.session.flush()
        self._audit("create_lease", "lease", lease.id, {"unit_id": unit_id, "tenant_id": tenant_id})
        return lease

    def add_meter_reading(self, unit_id: int, meter_type: MeterType, reading_date: date,
                          value: Decimal, confirmed: bool) -> MeterReadingRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before saving a meter reading.")
        if value < 0:
            raise BusinessRuleError("Meter reading cannot be negative.")
        previous = self.session.scalar(select(MeterReadingRecord).where(
            MeterReadingRecord.unit_id == unit_id,
            MeterReadingRecord.meter_type == meter_type.value,
        ).order_by(MeterReadingRecord.reading_date.desc(), MeterReadingRecord.id.desc()))
        if previous:
            validate_meter_reading(previous.value, value)
        reading = MeterReadingRecord(unit_id=unit_id, meter_type=meter_type.value,
                                     reading_date=reading_date, value=value)
        self.session.add(reading)
        self.session.flush()
        self._audit("create_meter_reading", "meter_reading", reading.id,
                    {"unit_id": unit_id, "meter_type": meter_type.value, "value": str(value)})
        return reading

    def record_payment(self, invoice_id: int, amount: Decimal, payment_method: str,
                       outstanding: Decimal, confirmed: bool) -> PaymentRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before recording a payment.")
        validate_payment_amount(amount, outstanding)
        payment = PaymentRecord(invoice_id=invoice_id, amount=amount, payment_method=payment_method)
        self.session.add(payment)
        self.session.flush()
        self._audit("record_payment", "invoice", invoice_id, {"amount": str(amount)})
        return payment

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def _audit(self, operation: str, entity_type: str, entity_id: int | None, details: dict) -> None:
        self.session.add(AuditLogRecord(
            operation=operation,
            entity_type=entity_type,
            entity_id=entity_id,
            details=str(details),
            created_at=datetime.now(timezone.utc),
        ))
