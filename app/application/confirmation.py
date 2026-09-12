from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class ConfirmationRequest:
    operation: str
    warning: str
    created_at: datetime

    @classmethod
    def create(cls, operation: str, warning: str) -> "ConfirmationRequest":
        return cls(operation, warning, datetime.now(timezone.utc))


def require_explicit_confirmation(request: ConfirmationRequest, confirmed: bool) -> None:
    if not confirmed:
        raise PermissionError(
            f"Explicit confirmation is required before executing: {request.operation}"
        )
