from __future__ import annotations

from datetime import date
from decimal import Decimal

from .models import InvoiceStatus, LeaseStatus


class BusinessRuleError(ValueError):
    """Raised when a requested business operation violates a domain rule."""


def validate_meter_reading(previous: Decimal, current: Decimal) -> None:
    if current < previous:
        raise BusinessRuleError(f"Meter reading cannot decrease: previous={previous}, current={current}")


def validate_active_lease(end_date: date | None, status: LeaseStatus) -> None:
    if status is LeaseStatus.ACTIVE and end_date is not None and end_date < date.today():
        raise BusinessRuleError("An active lease cannot already be past its end date.")


def validate_invoice_mutable(status: InvoiceStatus) -> None:
    if status in {InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID, InvoiceStatus.OVERDUE, InvoiceStatus.ARCHIVED}:
        raise BusinessRuleError("Issued and archived invoices are immutable. Create a correction record instead of editing the invoice.")


def validate_payment_amount(amount: Decimal, outstanding: Decimal) -> None:
    if amount <= 0:
        raise BusinessRuleError("Payment amount must be greater than zero.")
    if outstanding <= 0:
        raise BusinessRuleError("The invoice has no outstanding balance.")
    if amount > outstanding:
        raise BusinessRuleError("Payment cannot exceed the outstanding invoice balance.")


def ensure_one_active_lease(active_count: int) -> None:
    if active_count > 0:
        raise BusinessRuleError("A unit cannot have more than one active lease.")
