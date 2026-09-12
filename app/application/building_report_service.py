from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import LeaseStatus
from app.infrastructure.orm import InvoiceRecord, LeaseRecord, PaymentRecord, UnitRecord


class BuildingReportService:
    """Read-only building and unit status reports."""

    def __init__(self, session: Session):
        self.session = session

    def unit_statuses(self) -> list[dict]:
        units = self.session.scalars(select(UnitRecord).order_by(UnitRecord.number)).all()
        result = []
        for unit in units:
            lease = self.session.scalar(select(LeaseRecord).where(LeaseRecord.unit_id == unit.id, LeaseRecord.status == LeaseStatus.ACTIVE.value))
            if not lease:
                result.append({"unit_id": unit.id, "number": unit.number, "name": unit.name, "type": unit.unit_type, "status": "vacant", "tenant_id": None, "tenant_name": None, "outstanding": Decimal("0")})
                continue
            outstanding = self.session.scalar(select(func.coalesce(func.sum(InvoiceRecord.electricity_current - InvoiceRecord.electricity_previous), 0)).where(InvoiceRecord.id == -1)) or Decimal("0")
            invoices = self.session.scalars(select(InvoiceRecord).where(InvoiceRecord.unit_id == unit.id, InvoiceRecord.tenant_id == lease.tenant_id)).all()
            total_due = Decimal("0")
            for invoice in invoices:
                total = ((invoice.electricity_current - invoice.electricity_previous) * invoice.electricity_price + (invoice.water_current - invoice.water_previous) * invoice.water_price + invoice.shared_expenses + invoice.arrears)
                paid = self.session.scalar(select(func.coalesce(func.sum(PaymentRecord.amount), 0)).where(PaymentRecord.invoice_id == invoice.id)) or Decimal("0")
                total_due += total - paid
            result.append({"unit_id": unit.id, "number": unit.number, "name": unit.name, "type": unit.unit_type, "status": "occupied", "tenant_id": lease.tenant_id, "tenant_name": lease.tenant.name if lease.tenant else None, "outstanding": total_due})
        return result

    def building_summary(self) -> dict:
        statuses = self.unit_statuses()
        occupied = sum(x["status"] == "occupied" for x in statuses)
        vacant = len(statuses) - occupied
        outstanding = sum((x["outstanding"] for x in statuses), Decimal("0"))
        return {"total_units": len(statuses), "occupied": occupied, "vacant": vacant, "outstanding": outstanding}
