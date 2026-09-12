from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Optional


class UnitType(StrEnum):
    APARTMENT = "apartment"
    SHOP = "shop"


class LeaseStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


class MeterType(StrEnum):
    ELECTRICITY = "electricity"
    WATER = "water"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    ARCHIVED = "archived"


@dataclass(slots=True)
class Unit:
    number: str
    name: str
    unit_type: UnitType
    id: Optional[int] = None


@dataclass(slots=True)
class Tenant:
    name: str
    phones: list[str]
    identity_type: Optional[str] = None
    identity_number: Optional[str] = None
    id: Optional[int] = None


@dataclass(slots=True)
class Lease:
    unit_id: int
    tenant_id: int
    start_date: date
    end_date: Optional[date]
    rent_amount: Decimal
    deposit_amount: Decimal
    due_day: int
    payment_method: str
    status: LeaseStatus = LeaseStatus.ACTIVE
    id: Optional[int] = None


@dataclass(slots=True)
class MeterReading:
    unit_id: int
    meter_type: MeterType
    reading_date: date
    value: Decimal
    id: Optional[int] = None


@dataclass(slots=True)
class InvoiceLine:
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


@dataclass(slots=True)
class UtilityInvoice:
    invoice_number: str
    unit_id: int
    tenant_id: int
    period_start: date
    period_end: date
    electricity_previous: Decimal
    electricity_current: Decimal
    electricity_price: Decimal
    water_previous: Decimal
    water_current: Decimal
    water_price: Decimal
    shared_expenses: Decimal
    arrears: Decimal = Decimal("0")
    note: Optional[str] = None
    status: InvoiceStatus = InvoiceStatus.DRAFT
    id: Optional[int] = None

    @property
    def electricity_usage(self) -> Decimal:
        return self.electricity_current - self.electricity_previous

    @property
    def water_usage(self) -> Decimal:
        return self.water_current - self.water_previous

    @property
    def electricity_amount(self) -> Decimal:
        return self.electricity_usage * self.electricity_price

    @property
    def water_amount(self) -> Decimal:
        return self.water_usage * self.water_price

    @property
    def total(self) -> Decimal:
        return self.electricity_amount + self.water_amount + self.shared_expenses + self.arrears
