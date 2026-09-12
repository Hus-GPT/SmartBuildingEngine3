from datetime import date
from decimal import Decimal

import pytest

from app.application.lease_lifecycle_service import LeaseLifecycleService
from app.application.persistence_service import PersistenceService
from app.domain.rules import BusinessRuleError
from app.domain.models import UnitType
from app.infrastructure.database import Base, build_database


def make_session():
    engine, factory = build_database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return factory()


def seed(session):
    service = PersistenceService(session)
    unit = service.add_unit("101", "شقة 101", UnitType.APARTMENT)
    tenant = service.add_tenant("مستأجر", ["777777777"])
    lease = service.add_lease(unit.id, tenant.id, date(2026, 9, 1), date(2027, 8, 31), Decimal("50000"), Decimal("100000"), 1, "cash", True)
    session.commit()
    return lease


def test_end_lease_requires_confirmation_and_audits():
    session = make_session()
    try:
        lease = seed(session)
        lifecycle = LeaseLifecycleService(session)
        with pytest.raises(PermissionError):
            lifecycle.end_lease(lease.id, date(2027, 1, 1), confirmed=False)
        lifecycle.end_lease(lease.id, date(2027, 1, 1), reason="early move-out", confirmed=True)
        session.commit()
        assert lease.status == "ended"
        assert lease.end_date == date(2027, 1, 1)
    finally:
        session.close()


def test_renewal_closes_old_lease_and_starts_next_day():
    session = make_session()
    try:
        old = seed(session)
        lifecycle = LeaseLifecycleService(session)
        new = lifecycle.renew_lease(old.id, date(2028, 8, 31), rent_amount=Decimal("60000"), confirmed=True)
        session.commit()
        assert old.status == "ended"
        assert new.start_date == date(2027, 9, 1)
        assert new.rent_amount == Decimal("60000")
        assert new.status == "active"
    finally:
        session.close()


def test_expiring_within_15_days():
    session = make_session()
    try:
        service = PersistenceService(session)
        unit = service.add_unit("101", "شقة 101", UnitType.APARTMENT)
        tenant = service.add_tenant("مستأجر", ["777777777"])
        service.add_lease(unit.id, tenant.id, date(2026, 9, 1), date(2026, 9, 20), Decimal("50000"), Decimal("0"), 1, "cash", True)
        session.commit()
        matches = LeaseLifecycleService(session).expiring_within(15, as_of=date(2026, 9, 10))
        assert len(matches) == 1
    finally:
        session.close()


def test_duration_calendar():
    assert LeaseLifecycleService.duration_calendar(date(2026, 1, 15), date(2027, 3, 20)) == (1, 2, 5)
    with pytest.raises(BusinessRuleError):
        LeaseLifecycleService.duration_calendar(date(2027, 1, 1), date(2026, 1, 1))
