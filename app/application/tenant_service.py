from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.rules import BusinessRuleError
from app.infrastructure.orm import AuditLogRecord, FileRecord, TenantRecord


class TenantService:
    """Tenant identity and dossier completeness operations."""

    def __init__(self, session: Session):
        self.session = session

    def set_identity(self, tenant_id: int, identity_type: str, identity_number: str, confirmed: bool) -> TenantRecord:
        if not confirmed:
            raise PermissionError("Explicit confirmation is required before changing tenant identity data.")
        tenant = self.session.get(TenantRecord, tenant_id)
        if not tenant:
            raise BusinessRuleError("Tenant does not exist.")
        if not identity_type.strip() or not identity_number.strip():
            raise BusinessRuleError("Identity type and identity number are required.")
        tenant.identity_type = identity_type.strip()
        tenant.identity_number = identity_number.strip()
        self.session.add(AuditLogRecord(operation="set_tenant_identity", entity_type="tenant", entity_id=tenant.id, details=str({"identity_type": tenant.identity_type}), created_at=datetime.now(timezone.utc)))
        self.session.flush()
        return tenant

    def missing_requirements(self, tenant_id: int) -> list[str]:
        tenant = self.session.get(TenantRecord, tenant_id)
        if not tenant:
            raise BusinessRuleError("Tenant does not exist.")
        types = set(
            self.session.scalars(
                select(FileRecord.attachment_type).where(FileRecord.tenant_id == tenant_id)
            ).all()
        )
        missing = []
        if not tenant.identity_type:
            missing.append("identity_type")
        if not tenant.identity_number:
            missing.append("identity_number")
        if "TENANT_ID_FRONT" not in types:
            missing.append("TENANT_ID_FRONT")
        if "TENANT_ID_BACK" not in types:
            missing.append("TENANT_ID_BACK")
        return missing
