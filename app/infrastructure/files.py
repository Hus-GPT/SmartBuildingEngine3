from __future__ import annotations

from pathlib import Path
from uuid import uuid4


class FileStorage:
    """Stores Telegram-uploaded documents/images outside the business layer."""

    def __init__(self, root: str | Path = "storage"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, data: bytes, original_name: str, category: str = "general") -> Path:
        safe_name = Path(original_name).name or "file"
        folder = self.root / category
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{uuid4().hex}_{safe_name}"
        target.write_bytes(data)
        return target
