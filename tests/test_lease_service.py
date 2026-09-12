from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.lease_service import LeaseService
from app.infrastructure.database import Base
from app.infrastructure.orm import LeaseRecord, TenantRecord, UnitRecord


def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def seed(session):
    unit = UnitRecord(number="101", name="شقة 101", unit_type="apartment")
    tenant = TenantRecord(name="Test Tenant")
    session.add_all([unit, tenant]); session.flush()
    lease = LeaseRecord(unit_id=unit.id, tenant_id=tenant.id, start_date=date(2026, 1, 1), end_date=None, rent_amount=Decimal("100"), deposit_amount=Decimal("100"), due_day=1, payment_method="cash", status="active")
    session.add(lease); session.commit()
    return lease.id


def test_end_lease_requires_confirmation():
    Session = session_factory(); session = Session(); lease_id = seed(session)
    with pytest.raises(PermissionError):
        LeaseService(session).end_lease(lease_id, date(2026, 9, 1), False)


def test_end_lease_closes_active_contract():
    Session = session_factory(); session = Session(); lease_id = seed(session)
    lease = LeaseService(session).end_lease(lease_id, date(2026, 9, 1), True)
    session.commit()
    assert lease.status == "ended"
    assert lease.end_date == date(2026, 9, 1)
