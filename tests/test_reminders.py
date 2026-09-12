from datetime import date
from decimal import Decimal

from app.application.persistence_service import PersistenceService
from app.domain.models import UnitType
from app.infrastructure.database import Base, build_database
from app.infrastructure.orm import AuditLogRecord
from app.interfaces.telegram.reminders import leases_due_for_reminder, reminder_already_sent


def make_session():
    engine, factory = build_database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return factory()


def test_only_active_leases_ending_in_15_days_are_selected():
    session = make_session()
    try:
        service = PersistenceService(session)
        unit = service.add_unit("101", "شقة 101", UnitType.APARTMENT)
        tenant = service.add_tenant("مستأجر", ["777777777"])
        service.add_lease(1, tenant.id, date(2026, 9, 1), date(2026, 9, 28), Decimal("1"), Decimal("0"), 1, "cash", True)
        session.commit()
        rows = leases_due_for_reminder(session, date(2026, 9, 13))
        assert [row.id for row in rows] == [1]
    finally:
        session.close()


def test_reminder_deduplication_is_date_specific():
    session = make_session()
    try:
        session.add(AuditLogRecord(operation="lease_expiry_reminder", entity_type="lease", entity_id=7, details="reminder_date=2026-09-13"))
        session.commit()
        assert reminder_already_sent(session, 7, date(2026, 9, 13)) is True
        assert reminder_already_sent(session, 7, date(2026, 9, 14)) is False
    finally:
        session.close()
