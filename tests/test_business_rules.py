from datetime import date
from decimal import Decimal

import pytest

from app.application.building_service import BuildingService
from app.application.confirmation import ConfirmationRequest, require_explicit_confirmation
from app.domain.models import InvoiceStatus
from app.domain.rules import BusinessRuleError, validate_invoice_mutable, validate_meter_reading


def test_meter_reading_cannot_decrease():
    with pytest.raises(BusinessRuleError):
        validate_meter_reading(Decimal("100"), Decimal("99"))


def test_utility_invoice_calculation():
    invoice = BuildingService().build_utility_invoice(
        invoice_number="INV-0001",
        unit_id=1,
        tenant_id=1,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        electricity_previous=Decimal("100"),
        electricity_current=Decimal("125"),
        electricity_price=Decimal("50"),
        water_previous=Decimal("10"),
        water_current=Decimal("14"),
        water_price=Decimal("100"),
        shared_expenses=Decimal("500"),
        arrears=Decimal("200"),
    )
    assert invoice.electricity_usage == Decimal("25")
    assert invoice.water_usage == Decimal("4")
    assert invoice.total == Decimal("2350")


def test_archived_invoice_is_immutable():
    with pytest.raises(BusinessRuleError):
        validate_invoice_mutable(InvoiceStatus.ARCHIVED)


def test_write_requires_confirmation():
    request = ConfirmationRequest.create("archive invoice", "This action is irreversible.")
    with pytest.raises(PermissionError):
        require_explicit_confirmation(request, False)
