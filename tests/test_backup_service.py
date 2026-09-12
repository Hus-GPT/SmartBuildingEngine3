from pathlib import Path
from zipfile import ZipFile

from app.application.backup_service import BackupService
from app.infrastructure.database import Base, build_database


def test_backup_contains_database_and_storage(tmp_path):
    db = tmp_path / "data" / "smart_building.db"
    db.parent.mkdir()
    engine, _ = build_database(f"sqlite+pysqlite:///{db}")
    Base.metadata.create_all(engine)
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "sample.txt").write_text("backup-test", encoding="utf-8")
    backup_dir = tmp_path / "backups"
    path = BackupService(f"sqlite+pysqlite:///{db}", storage, backup_dir).create_latest()
    assert path.exists()
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        assert "data/smart_building.db" in names
        assert "storage/sample.txt" in names
