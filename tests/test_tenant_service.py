from app.application.persistence_service import PersistenceService
from app.application.tenant_service import TenantService
from app.domain.models import UnitType
from app.infrastructure.database import Base, build_database
from app.infrastructure.orm import FileRecord


def make_session():
    engine, factory = build_database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return factory()


def test_tenant_identity_and_missing_requirements():
    session = make_session()
    try:
        tenant = PersistenceService(session).add_tenant("مستأجر", ["777777777"])
        service = TenantService(session)
        assert set(service.missing_requirements(tenant.id)) == {"identity_type", "identity_number", "TENANT_ID_FRONT", "TENANT_ID_BACK"}
        service.set_identity(tenant.id, "بطاقة شخصية", "12345", True)
        front = FileRecord(entity_type="tenant", entity_id=tenant.id, tenant_id=tenant.id, attachment_type="TENANT_ID_FRONT", original_name="front.jpg", storage_path="front.jpg", mime_type="image/jpeg")
        back = FileRecord(entity_type="tenant", entity_id=tenant.id, tenant_id=tenant.id, attachment_type="TENANT_ID_BACK", original_name="back.jpg", storage_path="back.jpg", mime_type="image/jpeg")
        session.add_all([front, back])
        session.commit()
        assert service.missing_requirements(tenant.id) == []
    finally:
        session.close()
