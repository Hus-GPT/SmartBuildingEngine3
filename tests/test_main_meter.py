from datetime import date
from decimal import Decimal

import pytest

from app.application.persistence_service import PersistenceService
from app.domain.models import MeterType
from app.domain.rules import BusinessRuleError
from app.infrastructure.database import Base, build_database


def make_session():
    engine, factory = build_database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return factory()


def test_building_main_meter_reading_is_saved():
    session = make_session()
    try:
        service = PersistenceService(session)
        reading = service.add_building_meter_reading(MeterType.ELECTRICITY, date(2026, 9, 1), Decimal("1000"), True)
        service.commit()
        assert reading.value == Decimal("1000")
    finally:
        session.close()


def test_building_main_meter_cannot_decrease():
    session = make_session()
    try:
        service = PersistenceService(session)
        service.add_building_meter_reading(MeterType.WATER, date(2026, 9, 1), Decimal("100"), True)
        with pytest.raises(BusinessRuleError):
            service.add_building_meter_reading(MeterType.WATER, date(2026, 9, 30), Decimal("99"), True)
    finally:
        session.close()
