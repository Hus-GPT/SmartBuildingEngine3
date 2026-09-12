from __future__ import annotations

from datetime import date
from sqlalchemy.orm import Session

from app.domain.rules import BusinessRuleError
from app.infrastructure.orm import LeaseRecord


class LeaseCompletionService:
    """Validates whether a lease has all required people and documents."""

    REQUIRED_WITNESS_ORDERS = {1, 2}
    REQUIRED_DOCUMENTS = {"LEASE_CONTRACT", "GUARANTEE"}

    def __init__(self, session: Session):
        self.session = session

    def validate(self, lease_id: int) -> LeaseRecord:
        lease = self.session.get(LeaseRecord, lease_id)
        if not lease:
            raise BusinessRuleError("Lease does not exist.")
        witness_orders = [w.witness_order for w in lease.witnesses]
        if set(witness_orders) != self.REQUIRED_WITNESS_ORDERS or len(witness_orders) != 2:
            raise BusinessRuleError("The lease must have exactly two witnesses: 1 and 2.")
        if any(not w.name.strip() or not w.phone.strip() for w in lease.witnesses):
            raise BusinessRuleError("Each witness must have a name and phone number.")
        document_types = {f.attachment_type for f in lease.attachments}
        missing = self.REQUIRED_DOCUMENTS - document_types
        if missing:
            raise BusinessRuleError("Missing required lease documents: " + ", ".join(sorted(missing)))
        if lease.end_date is not None and lease.end_date < lease.start_date:
            raise BusinessRuleError("Lease end date cannot precede its start date.")
        return lease

    def duration_days(self, lease_id: int, as_of: date | None = None) -> int | None:
        lease = self.validate(lease_id)
        finish = lease.end_date or as_of
        if finish is None:
            return None
        return (finish - lease.start_date).days + 1
