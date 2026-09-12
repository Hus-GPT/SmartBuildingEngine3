from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import LeaseStatus
from app.domain.rules import BusinessRuleError, ensure_one_active_lease
from app.infrastructure.orm import AuditLogRecord, FileRecord, LeaseRecord, TenantRecord, UnitRecord, WitnessRecord


class CompleteLeaseService:
    """Atomically creates a complete lease dossier after explicit confirmation."""

    REQUIRED_DOCUMENT_TYPES = {"LEASE_CONTRACT", "GUARANTEE"}

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        *,
        unit_id: int,
        tenant_id: int,
        start_date: date,
        end_date: date | None,
        rent_amount: Decimal,
        deposit_amount: Decimal,
        due_day: int,
        payment_method: str,
        witnesses: list[tuple[str, str]],
        contract_file_id: int,
        guarantee_file_id: int,
        confirmed: bool,
    ) -> LeaseRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before creating a complete lease.")
        if len(witnesses) != 2 or any(not name.strip() or not phone.strip() for name, phone in witnesses):
            raise BusinessRuleError("Exactly two witnesses with name and phone are required.")
        if not 1 <= due_day <= 31:
            raise BusinessRuleError("Due day must be between 1 and 31.")
        if rent_amount < 0 or deposit_amount < 0:
            raise BusinessRuleError("Rent and deposit cannot be negative.")
        if end_date is not None and end_date < start_date:
            raise BusinessRuleError("Lease end date cannot precede start date.")
        unit = self.session.get(UnitRecord, unit_id)
        tenant = self.session.get(TenantRecord, tenant_id)
        if not unit or not tenant:
            raise BusinessRuleError("Unit or tenant does not exist.")
        active = self.session.scalar(select(func.count(LeaseRecord.id)).where(LeaseRecord.unit_id == unit_id, LeaseRecord.status == LeaseStatus.ACTIVE.value)) or 0
        ensure_one_active_lease(active)

        contract = self.session.get(FileRecord, contract_file_id)
        guarantee = self.session.get(FileRecord, guarantee_file_id)
        if not contract or not guarantee:
            raise BusinessRuleError("Required contract or guarantee file does not exist.")
        if contract.id == guarantee.id:
            raise BusinessRuleError("Contract and guarantee must be two different files.")
        if contract.tenant_id or contract.lease_id or guarantee.tenant_id or guarantee.lease_id:
            raise BusinessRuleError("A required document is already linked to another record.")

        lease = LeaseRecord(unit_id=unit_id, tenant_id=tenant_id, start_date=start_date, end_date=end_date, rent_amount=rent_amount, deposit_amount=deposit_amount, due_day=due_day, payment_method=payment_method.strip(), status=LeaseStatus.ACTIVE.value)
        self.session.add(lease)
        self.session.flush()
        for order, (name, phone) in enumerate(witnesses, start=1):
            self.session.add(WitnessRecord(lease_id=lease.id, name=name.strip(), phone=phone.strip(), witness_order=order))
        contract.attachment_type = "LEASE_CONTRACT"
        contract.tenant_id = None
        contract.lease_id = lease.id
        contract.entity_type = "lease"
        contract.entity_id = lease.id
        guarantee.attachment_type = "GUARANTEE"
        guarantee.tenant_id = None
        guarantee.lease_id = lease.id
        guarantee.entity_type = "lease"
        guarantee.entity_id = lease.id
        self.session.add(AuditLogRecord(operation="create_complete_lease", entity_type="lease", entity_id=lease.id, details=str({"unit_id": unit_id, "tenant_id": tenant_id, "contract_file_id": contract.id, "guarantee_file_id": guarantee.id})))
        self.session.flush()
        return lease
