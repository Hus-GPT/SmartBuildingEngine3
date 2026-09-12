from datetime import date
from decimal import Decimal

import pytest

from app.application.persistence_service import PersistenceService
from app.domain.models import InvoiceStatus, MeterType, UnitType
from app.domain.rules import BusinessRuleError
from app.infrastructure.database import Base, build_database


def make_service():
    engine, factory = build_database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return factory()


def seed_invoice(session):
    service = PersistenceService(session)
    unit = service.add_unit("101", "شقة 101", UnitType.APARTMENT)
    tenant = service.add_tenant("مستأجر", ["777777777"])
    service.add_lease(1, tenant.id, date(2026, 9, 1), date(2027, 8, 31), Decimal("50000"), Decimal("100000"), 1, "cash", True)
    invoice = service.create_utility_invoice(
        unit_id=unit.id, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
        electricity_previous=Decimal("100"), electricity_current=Decimal("120"), electricity_price=Decimal("50"),
        water_previous=Decimal("20"), water_current=Decimal("25"), water_price=Decimal("100"),
        shared_expenses=Decimal("500"), arrears=Decimal("1000"), note=None,
        invoice_number="INV-TEST-001", confirmed=True,
    )
    service.commit()
    return service, invoice


def test_invoice_total_and_partial_payment():
    session = make_service()
    try:
        service, invoice = seed_invoice(session)
        assert service.invoice_total(invoice) == Decimal("3500")
        payment = service.record_payment(invoice.id, Decimal("1000"), "cash", True)
        service.commit()
        assert payment.amount == Decimal("1000")
        assert service.invoice_outstanding(invoice.id) == Decimal("2500")
        assert invoice.status == InvoiceStatus.PARTIALLY_PAID.value
    finally:
        session.close()


def test_payment_cannot_exceed_outstanding():
    session = make_service()
    try:
        service, invoice = seed_invoice(session)
        with pytest.raises(BusinessRuleError):
            service.record_payment(invoice.id, Decimal("3500.01"), "cash", True)
    finally:
        session.close()


def test_issued_invoice_is_immutable_for_business_edits():
    session = make_service()
    try:
        service, invoice = seed_invoice(session)
        invoice.shared_expenses = Decimal("999999")
        with pytest.raises(BusinessRuleError):
            from app.domain.rules import validate_invoice_mutable
            validate_invoice_mutable(InvoiceStatus(invoice.status))
        session.rollback()
    finally:
        session.close()


def test_decreasing_meter_is_rejected():
    session = make_service()
    try:
        service = PersistenceService(session)
        unit = service.add_unit("102", "شقة 102", UnitType.APARTMENT)
        service.add_meter_reading(unit.id, MeterType.ELECTRICITY, date(2026, 9, 1), Decimal("100"), True)
        with pytest.raises(BusinessRuleError):
            service.add_meter_reading(unit.id, MeterType.ELECTRICITY, date(2026, 9, 30), Decimal("99"), True)
    finally:
        session.close()
