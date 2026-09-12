from datetime import date
from decimal import Decimal

import pytest

from app.application.complete_lease_service import CompleteLeaseService
from app.application.persistence_service import PersistenceService
from app.domain.models import UnitType
from app.domain.rules import BusinessRuleError
from app.infrastructure.database import Base, build_database
from app.infrastructure.orm import FileRecord


def make_session():
    engine, factory = build_database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return factory()


def seed(session):
    service = PersistenceService(session)
    unit = service.add_unit("101", "شقة 101", UnitType.APARTMENT)
    tenant = service.add_tenant("مستأجر", ["777777777"])
    contract = FileRecord(entity_type="telegram_inbox", entity_id=1, original_name="contract.pdf", storage_path="storage/contract.pdf", mime_type="application/pdf")
    guarantee = FileRecord(entity_type="telegram_inbox", entity_id=1, original_name="guarantee.jpg", storage_path="storage/guarantee.jpg", mime_type="image/jpeg")
    session.add_all([contract, guarantee])
    session.flush()
    return unit, tenant, contract, guarantee


def test_complete_lease_is_atomic_and_links_files():
    session = make_session()
    try:
        unit, tenant, contract, guarantee = seed(session)
        lease = CompleteLeaseService(session).create(
            unit_id=unit.id, tenant_id=tenant.id,
            start_date=date(2026, 9, 1), end_date=date(2027, 8, 31),
            rent_amount=Decimal("50000"), deposit_amount=Decimal("100000"), due_day=1, payment_method="cash",
            witnesses=[("شاهد 1", "711111111"), ("شاهد 2", "722222222")],
            contract_file_id=contract.id, guarantee_file_id=guarantee.id, confirmed=True,
        )
        session.commit()
        assert lease.id is not None
        assert len(lease.witnesses) == 2
        assert contract.lease_id == lease.id and contract.attachment_type == "LEASE_CONTRACT"
        assert guarantee.lease_id == lease.id and guarantee.attachment_type == "GUARANTEE"
    finally:
        session.close()


def test_complete_lease_requires_confirmation():
    session = make_session()
    try:
        unit, tenant, contract, guarantee = seed(session)
        with pytest.raises(PermissionError):
            CompleteLeaseService(session).create(
                unit_id=unit.id, tenant_id=tenant.id, start_date=date(2026, 9, 1), end_date=date(2027, 8, 31),
                rent_amount=Decimal("50000"), deposit_amount=Decimal("0"), due_day=1, payment_method="cash",
                witnesses=[("1", "711111111"), ("2", "722222222")], contract_file_id=contract.id, guarantee_file_id=guarantee.id, confirmed=False,
            )
    finally:
        session.close()


def test_complete_lease_rejects_existing_active_lease():
    session = make_session()
    try:
        unit, tenant, contract, guarantee = seed(session)
        PersistenceService(session).add_lease(unit.id, tenant.id, date(2026, 1, 1), date(2026, 8, 31), Decimal("50000"), Decimal("0"), 1, "cash", True)
        with pytest.raises(BusinessRuleError):
            CompleteLeaseService(session).create(
                unit_id=unit.id, tenant_id=tenant.id, start_date=date(2026, 9, 1), end_date=date(2027, 8, 31),
                rent_amount=Decimal("50000"), deposit_amount=Decimal("0"), due_day=1, payment_method="cash",
                witnesses=[("1", "711111111"), ("2", "722222222")], contract_file_id=contract.id, guarantee_file_id=guarantee.id, confirmed=True,
            )
    finally:
        session.close()
