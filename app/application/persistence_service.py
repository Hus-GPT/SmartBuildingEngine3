from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import InvoiceStatus, LeaseStatus, MeterType, UnitType
from app.domain.rules import BusinessRuleError, ensure_one_active_lease, validate_invoice_mutable, validate_meter_reading, validate_payment_amount
from app.infrastructure.orm import AuditLogRecord, InvoiceRecord, LeaseRecord, MeterReadingRecord, PaymentRecord, TenantPhoneRecord, TenantRecord, UnitRecord


class PersistenceService:
    """Telegram-independent transactional use cases."""

    def __init__(self, session: Session):
        self.session = session

    def add_unit(self, number: str, name: str, unit_type: UnitType) -> UnitRecord:
        number, name = number.strip(), name.strip()
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

    def add_lease(self, unit_id: int, tenant_id: int, start_date: date, end_date: date | None, rent_amount: Decimal, deposit_amount: Decimal, due_day: int, payment_method: str, confirmed: bool) -> LeaseRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before creating a lease.")
        if not 1 <= due_day <= 31:
            raise BusinessRuleError("Due day must be between 1 and 31.")
        if rent_amount < 0 or deposit_amount < 0:
            raise BusinessRuleError("Rent and deposit cannot be negative.")
        if end_date and end_date < start_date:
            raise BusinessRuleError("Lease end date cannot precede start date.")
        if not self.session.get(UnitRecord, unit_id) or not self.session.get(TenantRecord, tenant_id):
            raise BusinessRuleError("Unit or tenant does not exist.")
        active = self.session.scalar(select(func.count(LeaseRecord.id)).where(LeaseRecord.unit_id == unit_id, LeaseRecord.status == LeaseStatus.ACTIVE.value)) or 0
        ensure_one_active_lease(active)
        lease = LeaseRecord(unit_id=unit_id, tenant_id=tenant_id, start_date=start_date, end_date=end_date, rent_amount=rent_amount, deposit_amount=deposit_amount, due_day=due_day, payment_method=payment_method.strip(), status=LeaseStatus.ACTIVE.value)
        self.session.add(lease)
        self.session.flush()
        self._audit("create_lease", "lease", lease.id, {"unit_id": unit_id, "tenant_id": tenant_id})
        return lease

    def add_meter_reading(self, unit_id: int, meter_type: MeterType, reading_date: date, value: Decimal, confirmed: bool) -> MeterReadingRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before saving a meter reading.")
        if value < 0:
            raise BusinessRuleError("Meter reading cannot be negative.")
        if not self.session.get(UnitRecord, unit_id):
            raise BusinessRuleError("Unit does not exist.")
        previous = self.session.scalar(select(MeterReadingRecord).where(MeterReadingRecord.unit_id == unit_id, MeterReadingRecord.meter_type == meter_type.value).order_by(MeterReadingRecord.reading_date.desc(), MeterReadingRecord.id.desc()))
        if previous:
            validate_meter_reading(previous.value, value)
        reading = MeterReadingRecord(unit_id=unit_id, meter_type=meter_type.value, reading_date=reading_date, value=value)
        self.session.add(reading)
        self.session.flush()
        self._audit("create_meter_reading", "meter_reading", reading.id, {"unit_id": unit_id, "meter_type": meter_type.value, "value": str(value)})
        return reading

    def create_utility_invoice(self, *, unit_id: int, period_start: date, period_end: date, electricity_previous: Decimal, electricity_current: Decimal, electricity_price: Decimal, water_previous: Decimal, water_current: Decimal, water_price: Decimal, shared_expenses: Decimal, arrears: Decimal, note: str | None, invoice_number: str, confirmed: bool) -> InvoiceRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before creating an invoice.")
        if period_end < period_start:
            raise BusinessRuleError("Invoice period end cannot precede its start.")
        values = (electricity_previous, electricity_current, electricity_price, water_previous, water_current, water_price, shared_expenses, arrears)
        if any(v < 0 for v in values):
            raise BusinessRuleError("Invoice numeric values cannot be negative.")
        unit = self.session.get(UnitRecord, unit_id)
        if not unit:
            raise BusinessRuleError("Unit does not exist.")
        lease = self.session.scalar(select(LeaseRecord).where(LeaseRecord.unit_id == unit_id, LeaseRecord.status == LeaseStatus.ACTIVE.value))
        if not lease:
            raise BusinessRuleError("The unit has no active tenant/lease for this invoice period.")
        if self.session.scalar(select(InvoiceRecord).where(InvoiceRecord.invoice_number == invoice_number)):
            raise BusinessRuleError("Invoice number already exists.")
        if electricity_current < electricity_previous or water_current < water_previous:
            raise BusinessRuleError("A meter reading cannot be lower than its previous reading.")
        invoice = InvoiceRecord(invoice_number=invoice_number, unit_id=unit_id, tenant_id=lease.tenant_id, period_start=period_start, period_end=period_end, electricity_previous=electricity_previous, electricity_current=electricity_current, electricity_price=electricity_price, water_previous=water_previous, water_current=water_current, water_price=water_price, shared_expenses=shared_expenses, arrears=arrears, note=note, status=InvoiceStatus.ISSUED.value)
        self.session.add(invoice)
        self.session.flush()
        self._audit("create_utility_invoice", "invoice", invoice.id, {"invoice_number": invoice_number, "unit_id": unit_id})
        return invoice

    def invoice_total(self, invoice: InvoiceRecord) -> Decimal:
        return ((invoice.electricity_current - invoice.electricity_previous) * invoice.electricity_price + (invoice.water_current - invoice.water_previous) * invoice.water_price + invoice.shared_expenses + invoice.arrears)

    def invoice_paid(self, invoice_id: int) -> Decimal:
        return self.session.scalar(select(func.coalesce(func.sum(PaymentRecord.amount), 0)).where(PaymentRecord.invoice_id == invoice_id)) or Decimal("0")

    def invoice_outstanding(self, invoice_id: int) -> Decimal:
        invoice = self.session.get(InvoiceRecord, invoice_id)
        if not invoice:
            raise BusinessRuleError("Invoice does not exist.")
        return self.invoice_total(invoice) - self.invoice_paid(invoice_id)

    def record_payment(self, invoice_id: int, amount: Decimal, payment_method: str, confirmed: bool, note: str | None = None) -> PaymentRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before recording a payment.")
        invoice = self.session.get(InvoiceRecord, invoice_id)
        if not invoice:
            raise BusinessRuleError("Invoice does not exist.")
        if InvoiceStatus(invoice.status) is InvoiceStatus.ARCHIVED:
            raise BusinessRuleError("Archived invoices cannot receive payments.")
        outstanding = self.invoice_outstanding(invoice_id)
        validate_payment_amount(amount, outstanding)
        payment = PaymentRecord(invoice_id=invoice_id, amount=amount, payment_method=payment_method.strip(), note=note)
        self.session.add(payment)
        self.session.flush()
        new_paid = self.invoice_paid(invoice_id)
        invoice.status = InvoiceStatus.PAID.value if new_paid == self.invoice_total(invoice) else InvoiceStatus.PARTIALLY_PAID.value
        self._audit("record_payment", "invoice", invoice_id, {"amount": str(amount), "payment_method": payment_method})
        return payment

    def archive_invoice(self, invoice_id: int, confirmed: bool) -> InvoiceRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before archiving an invoice.")
        invoice = self.session.get(InvoiceRecord, invoice_id)
        if not invoice:
            raise BusinessRuleError("Invoice does not exist.")
        invoice.status = InvoiceStatus.ARCHIVED.value
        invoice.archived_at = datetime.now(timezone.utc)
        self.session.flush()
        self._audit("archive_invoice", "invoice", invoice_id, {"invoice_number": invoice.invoice_number})
        return invoice

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def _audit(self, operation: str, entity_type: str, entity_id: int | None, details: dict) -> None:
        self.session.add(AuditLogRecord(operation=operation, entity_type=entity_type, entity_id=entity_id, details=str(details), created_at=datetime.now(timezone.utc)))
