from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.lease_completion_service import LeaseCompletionService
from app.domain.rules import BusinessRuleError
from app.infrastructure.database import Base
from app.infrastructure.orm import FileRecord, LeaseRecord, TenantRecord, UnitRecord, WitnessRecord


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def seed(session):
    unit = UnitRecord(number="101", name="شقة 101", unit_type="apartment")
    tenant = TenantRecord(name="Test")
    session.add_all([unit, tenant])
    session.flush()
    lease = LeaseRecord(unit_id=unit.id, tenant_id=tenant.id, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), rent_amount=Decimal("100"), deposit_amount=Decimal("100"), due_day=1, payment_method="cash", status="active")
    session.add(lease)
    session.flush()
    return lease


def test_incomplete_lease_is_rejected():
    session = make_session()
    lease = seed(session)
    with pytest.raises(BusinessRuleError):
        LeaseCompletionService(session).validate(lease.id)


def test_complete_lease_is_accepted_and_duration_calculated():
    session = make_session()
    lease = seed(session)
    session.add_all([
        WitnessRecord(lease_id=lease.id, name="Witness 1", phone="111", witness_order=1),
        WitnessRecord(lease_id=lease.id, name="Witness 2", phone="222", witness_order=2),
        FileRecord(entity_type="lease", entity_id=lease.id, lease_id=lease.id, attachment_type="LEASE_CONTRACT", original_name="contract.pdf", storage_path="leases/1/contract.pdf"),
        FileRecord(entity_type="lease", entity_id=lease.id, lease_id=lease.id, attachment_type="GUARANTEE", original_name="guarantee.jpg", storage_path="leases/1/guarantee.jpg"),
    ])
    session.commit()
    service = LeaseCompletionService(session)
    service.validate(lease.id)
    assert service.duration_days(lease.id) == 365
