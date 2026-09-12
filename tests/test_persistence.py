from datetime import date
from decimal import Decimal

import pytest

from app.application.persistence_service import PersistenceService
from app.domain.models import MeterType, UnitType
from app.domain.rules import BusinessRuleError
from app.infrastructure.database import build_database, initialize_database


def service():
    engine, SessionLocal = build_database("sqlite:///:memory:")
    initialize_database(engine)
    return SessionLocal()


def test_unit_and_tenant_persist():
    session = service()
    svc = PersistenceService(session)
    unit = svc.add_unit("A-01", "Apartment 01", UnitType.APARTMENT)
    tenant = svc.add_tenant("Test Tenant", ["700000000"])
    svc.commit()
    assert unit.id is not None
    assert tenant.id is not None
    assert tenant.phones[0].phone == "700000000"


def test_second_active_lease_is_rejected():
    session = service()
    svc = PersistenceService(session)
    unit = svc.add_unit("A-01", "Apartment 01", UnitType.APARTMENT)
    t1 = svc.add_tenant("Tenant 1", ["700000001"])
    t2 = svc.add_tenant("Tenant 2", ["700000002"])
    svc.add_lease(unit.id, t1.id, date(2026, 9, 1), None, Decimal("1000"), Decimal("500"), 1, "cash", True)
    with pytest.raises(BusinessRuleError):
        svc.add_lease(unit.id, t2.id, date(2026, 9, 2), None, Decimal("1000"), Decimal("500"), 1, "cash", True)


def test_meter_cannot_decrease():
    session = service()
    svc = PersistenceService(session)
    unit = svc.add_unit("A-01", "Apartment 01", UnitType.APARTMENT)
    svc.add_meter_reading(unit.id, MeterType.ELECTRICITY, date(2026, 9, 1), Decimal("100"), True)
    with pytest.raises(BusinessRuleError):
        svc.add_meter_reading(unit.id, MeterType.ELECTRICITY, date(2026, 9, 30), Decimal("99"), True)
