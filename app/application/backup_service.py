from __future__ import annotations

import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.domain.rules import BusinessRuleError


class BackupService:
    """Creates one current backup containing the SQLite database and stored files."""

    def __init__(self, database_url: str, storage_dir: str | Path, backup_dir: str | Path = "backups"):
        self.database_url = database_url
        self.storage_dir = Path(storage_dir)
        self.backup_dir = Path(backup_dir)

    def _database_path(self) -> Path:
        parsed = urlparse(self.database_url)
        if parsed.scheme not in {"sqlite", "sqlite+pysqlite"}:
            raise BusinessRuleError("Current backup implementation supports SQLite only.")
        database = parsed.path
        if not database:
            raise BusinessRuleError("SQLite database path is missing.")
        # sqlite:///relative.db is a relative path; sqlite:////absolute.db is absolute.
        if database.startswith("//"):
            return Path("/") / database.lstrip("/")
        return Path(database.lstrip("/"))

    def create_latest(self) -> Path:
        db_path = self._database_path()
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        if not db_path.exists():
            raise BusinessRuleError(f"Database file does not exist: {db_path}")

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        for old in self.backup_dir.glob("smart-building-latest-*.zip"):
            old.unlink(missing_ok=True)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = self.backup_dir / f"smart-building-latest-{stamp}.zip"
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = Path(temp_dir) / "smart_building.db"
            source = sqlite3.connect(str(db_path))
            destination = sqlite3.connect(str(snapshot))
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()

            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, "data/smart_building.db")
                if self.storage_dir.exists():
                    for path in self.storage_dir.rglob("*"):
                        if path.is_file():
                            archive.write(path, str(Path("storage") / path.relative_to(self.storage_dir)))
        return target
