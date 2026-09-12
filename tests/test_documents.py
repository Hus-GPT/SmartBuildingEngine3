from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.document_service import DocumentService
from app.domain.rules import BusinessRuleError
from app.infrastructure.database import Base
from app.infrastructure.orm import FileRecord, LeaseRecord, TenantRecord, UnitRecord


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def seed(session):
    unit = UnitRecord(number="101", name="شقة 101", unit_type="apartment")
    tenant = TenantRecord(name="Test Tenant")
    session.add_all([unit, tenant])
    session.flush()
    lease = LeaseRecord(
        unit_id=unit.id,
        tenant_id=tenant.id,
        start_date=date(2026, 1, 1),
        end_date=None,
        rent_amount=Decimal("100"),
        deposit_amount=Decimal("100"),
        due_day=1,
        payment_method="cash",
        status="active",
    )
    file_record = FileRecord(
        entity_type="telegram_inbox",
        entity_id=tenant.id,
        original_name="contract.jpg",
        storage_path="storage/test/contract.jpg",
        mime_type="image/jpeg",
    )
    session.add_all([lease, file_record])
    session.commit()
    return lease.id, file_record.id


def test_document_requires_confirmation():
    session = make_session()
    lease_id, file_id = seed(session)
    with pytest.raises(PermissionError):
        DocumentService(session).attach_file(file_id, "LEASE_CONTRACT", lease_id=lease_id, confirmed=False)


def test_witnesses_are_limited_to_two_positions():
    session = make_session()
    lease_id, _ = seed(session)
    service = DocumentService(session)
    service.add_witness(lease_id, "Witness 1", "700000001", 1, True)
    service.add_witness(lease_id, "Witness 2", "700000002", 2, True)
    session.commit()
    with pytest.raises(BusinessRuleError):
        service.add_witness(lease_id, "Another", "700000003", 1, True)


def test_complete_lease_requires_two_witnesses_and_documents():
    session = make_session()
    lease_id, file_id = seed(session)
    service = DocumentService(session)
    with pytest.raises(BusinessRuleError):
        service.validate_complete_lease_documents(lease_id)
    service.add_witness(lease_id, "Witness 1", "700000001", 1, True)
    service.add_witness(lease_id, "Witness 2", "700000002", 2, True)
    contract = session.get(FileRecord, file_id)
    contract.tenant_id = None
    contract.lease_id = lease_id
    contract.attachment_type = "LEASE_CONTRACT"
    guarantee = FileRecord(
        entity_type="lease",
        entity_id=lease_id,
        lease_id=lease_id,
        attachment_type="GUARANTEE",
        original_name="guarantee.jpg",
        storage_path="storage/test/guarantee.jpg",
        mime_type="image/jpeg",
    )
    session.add(guarantee)
    session.commit()
    service.validate_complete_lease_documents(lease_id)
