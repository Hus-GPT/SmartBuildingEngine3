from datetime import date
from decimal import Decimal

import pytest

from app.application.persistence_service import PersistenceService
from app.domain.rules import BusinessRuleError
from app.infrastructure.database import build_database, initialize_database


def _service(tmp_path):
    engine, factory = build_database(f"sqlite:///{tmp_path / 'test.db'}")
    initialize_database(engine)
    return factory()


def test_invoice_and_partial_payment(tmp_path):
    session = _service(tmp_path)
    service = PersistenceService(session)
    unit = service.add_unit("101", "شقة 101", __import__("app.domain.models", fromlist=["UnitType"]).UnitType.APARTMENT)
    tenant = service.add_tenant("أحمد", ["777000000"])
    service.add_lease(unit.id, tenant.id, date(2026, 9, 1), date(2027, 8, 31), Decimal("100000"), Decimal("100000"), 1, "cash", True)
    invoice = service.create_utility_invoice(unit_id=unit.id, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30), electricity_previous=Decimal("100"), electricity_current=Decimal("120"), electricity_price=Decimal("50"), water_previous=Decimal("10"), water_current=Decimal("12"), water_price=Decimal("100"), shared_expenses=Decimal("500"), arrears=Decimal("0"), note=None, invoice_number="INV-TEST-1", confirmed=True)
    assert service.invoice_total(invoice) == Decimal("1700")
    payment = service.record_payment(invoice.id, Decimal("700"), "cash", True)
    assert payment.id is not None
    assert service.invoice_outstanding(invoice.id) == Decimal("1000")
    session.commit()


def test_payment_cannot_exceed_balance(tmp_path):
    session = _service(tmp_path)
    service = PersistenceService(session)
    unit = service.add_unit("102", "شقة 102", __import__("app.domain.models", fromlist=["UnitType"]).UnitType.APARTMENT)
    tenant = service.add_tenant("محمد", ["777111111"])
    service.add_lease(unit.id, tenant.id, date(2026, 9, 1), None, Decimal("100000"), Decimal("0"), 1, "cash", True)
    invoice = service.create_utility_invoice(unit_id=unit.id, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30), electricity_previous=Decimal("0"), electricity_current=Decimal("10"), electricity_price=Decimal("50"), water_previous=Decimal("0"), water_current=Decimal("0"), water_price=Decimal("100"), shared_expenses=Decimal("0"), arrears=Decimal("0"), note=None, invoice_number="INV-TEST-2", confirmed=True)
    with pytest.raises(BusinessRuleError):
        service.record_payment(invoice.id, Decimal("501"), "cash", True)
