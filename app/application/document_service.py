from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.rules import BusinessRuleError
from app.infrastructure.orm import FileRecord, LeaseRecord, TenantRecord, WitnessRecord


ALLOWED_ATTACHMENT_TYPES = {
    "TENANT_ID_FRONT",
    "TENANT_ID_BACK",
    "LEASE_CONTRACT",
    "GUARANTEE",
    "OTHER",
}


class DocumentService:
    """Links stored files to tenants or leases without depending on Telegram."""

    def __init__(self, session: Session):
        self.session = session

    def attach_file(
        self,
        file_id: int,
        attachment_type: str,
        *,
        tenant_id: int | None = None,
        lease_id: int | None = None,
        confirmed: bool,
    ) -> FileRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before attaching a document.")
        if attachment_type not in ALLOWED_ATTACHMENT_TYPES:
            raise BusinessRuleError("Unsupported attachment type.")
        file_record = self.session.get(FileRecord, file_id)
        if not file_record:
            raise BusinessRuleError("File does not exist.")
        if (tenant_id is None) == (lease_id is None):
            raise BusinessRuleError("A file must be attached to exactly one tenant or lease.")
        if tenant_id is not None and not self.session.get(TenantRecord, tenant_id):
            raise BusinessRuleError("Tenant does not exist.")
        if lease_id is not None and not self.session.get(LeaseRecord, lease_id):
            raise BusinessRuleError("Lease does not exist.")
        file_record.attachment_type = attachment_type
        file_record.tenant_id = tenant_id
        file_record.lease_id = lease_id
        return file_record

    def add_witness(self, lease_id: int, name: str, phone: str, witness_order: int, confirmed: bool) -> WitnessRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before adding a witness.")
        if witness_order not in (1, 2) or not name.strip() or not phone.strip():
            raise BusinessRuleError("A lease must use witness positions 1 or 2, each with name and phone.")
        lease = self.session.get(LeaseRecord, lease_id)
        if not lease:
            raise BusinessRuleError("Lease does not exist.")
        existing = next((w for w in lease.witnesses if w.witness_order == witness_order), None)
        if existing:
            raise BusinessRuleError(f"Witness position {witness_order} is already occupied.")
        witness = WitnessRecord(lease_id=lease_id, name=name.strip(), phone=phone.strip(), witness_order=witness_order)
        self.session.add(witness)
        self.session.flush()
        return witness

    def validate_complete_lease_documents(self, lease_id: int) -> None:
        lease = self.session.get(LeaseRecord, lease_id)
        if not lease:
            raise BusinessRuleError("Lease does not exist.")
        orders = {w.witness_order for w in lease.witnesses}
        if orders != {1, 2}:
            raise BusinessRuleError("Lease requires exactly two witnesses before it can be considered complete.")
        types = {f.attachment_type for f in lease.attachments}
        missing = {"LEASE_CONTRACT", "GUARANTEE"} - types
        if missing:
            raise BusinessRuleError("Lease is missing required documents: " + ", ".join(sorted(missing)))
