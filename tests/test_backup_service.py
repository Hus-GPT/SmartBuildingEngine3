from pathlib import Path
from zipfile import ZipFile

from app.application.backup_service import BackupService
from app.infrastructure.database import Base, build_database
from app.domain.rules import BusinessRuleError


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


def test_backup_uses_relative_sqlite_path_and_replaces_previous(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "data" / "smart_building.db"
    db.parent.mkdir()
    engine, _ = build_database("sqlite+pysqlite:///data/smart_building.db")
    Base.metadata.create_all(engine)
    backup_dir = tmp_path / "backups"
    service = BackupService("sqlite+pysqlite:///data/smart_building.db", tmp_path / "storage", backup_dir)

    first = service.create_latest()
    assert first.exists()
    first.write_bytes(first.read_bytes() + b"marker")
    second = service.create_latest()

    assert second.exists()
    assert first != second or first.name == second.name
    backups = list(backup_dir.glob("smart-building-latest-*.zip"))
    assert backups == [second]


def test_backup_rejects_non_sqlite_database(tmp_path):
    service = BackupService("postgresql://example/db", tmp_path / "storage", tmp_path / "backups")
    try:
        service.create_latest()
    except BusinessRuleError as exc:
        assert "SQLite" in str(exc)
    else:
        raise AssertionError("Expected non-SQLite backup to be rejected")
