from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.models import Lease, LeaseStatus, MeterType, UtilityInvoice
from app.domain.rules import (
    ensure_one_active_lease,
    validate_meter_reading,
)


class BuildingService:
    """Application use cases. No Telegram imports are allowed here."""

    def create_lease(
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
        existing_active_leases: int,
    ) -> Lease:
        ensure_one_active_lease(existing_active_leases)
        if not 1 <= due_day <= 31:
            raise ValueError("due_day must be between 1 and 31")
        if rent_amount < 0 or deposit_amount < 0:
            raise ValueError("Rent and deposit cannot be negative")
        if end_date is not None and end_date < start_date:
            raise ValueError("Lease end date cannot precede start date")
        return Lease(
            unit_id=unit_id,
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            rent_amount=rent_amount,
            deposit_amount=deposit_amount,
            due_day=due_day,
            payment_method=payment_method,
        )

    def validate_new_meter_reading(self, previous: Decimal, current: Decimal) -> None:
        validate_meter_reading(previous, current)

    def build_utility_invoice(
        self,
        *,
        invoice_number: str,
        unit_id: int,
        tenant_id: int,
        period_start: date,
        period_end: date,
        electricity_previous: Decimal,
        electricity_current: Decimal,
        electricity_price: Decimal,
        water_previous: Decimal,
        water_current: Decimal,
        water_price: Decimal,
        shared_expenses: Decimal,
        arrears: Decimal = Decimal("0"),
        note: str | None = None,
    ) -> UtilityInvoice:
        validate_meter_reading(electricity_previous, electricity_current)
        validate_meter_reading(water_previous, water_current)
        if period_end < period_start:
            raise ValueError("Invoice period end cannot precede its start")
        if any(x < 0 for x in (electricity_price, water_price, shared_expenses, arrears)):
            raise ValueError("Invoice monetary values cannot be negative")
        return UtilityInvoice(
            invoice_number=invoice_number,
            unit_id=unit_id,
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            electricity_previous=electricity_previous,
            electricity_current=electricity_current,
            electricity_price=electricity_price,
            water_previous=water_previous,
            water_current=water_current,
            water_price=water_price,
            shared_expenses=shared_expenses,
            arrears=arrears,
            note=note,
        )
