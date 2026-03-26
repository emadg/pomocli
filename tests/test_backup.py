import gzip
import sqlite3
from pathlib import Path
from pomocli.db.backup import resolve_backup_dir, run_db_backup, maybe_run_automatic_backup

def test_resolve_backup_dir(tmp_path):
    # Empty config -> default
    assert resolve_backup_dir({}).name == "backups"
    
    # Custom config
    custom = tmp_path / "my_backups"
    assert resolve_backup_dir({"backup_dir": str(custom)}) == custom.resolve()

def test_run_db_backup_compressed(tmp_path):
    db_path = tmp_path / "test.db"
    backup_dir = tmp_path / "backups"
    
    # Create dummy DB
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE foo (id INTEGER)")
    conn.close()
    
    # Run backup 1
    new_file, deleted = run_db_backup(
        db_path=db_path, backup_dir=backup_dir, max_versions=2, compress=True
    )
    assert new_file.exists()
    assert new_file.suffix == ".gz"
    assert deleted == 0
    
    # Verify gzip contents
    with gzip.open(new_file, "rb") as f:
        header = f.read(16)
        assert b"SQLite format 3" in header

    # Run backup 2 (sleep slightly to ensure distinct timestamp if machine is fast)
    import time
    time.sleep(1)
    new_file2, deleted = run_db_backup(
        db_path=db_path, backup_dir=backup_dir, max_versions=2, compress=True
    )
    assert deleted == 0
    
    # Run backup 3 (should rotate out backup 1)
    time.sleep(1)
    new_file3, deleted = run_db_backup(
        db_path=db_path, backup_dir=backup_dir, max_versions=2, compress=True
    )
    assert deleted == 1
    
    # Only 2 files should remain
    files = list(backup_dir.glob("*.db.gz"))
    assert len(files) == 2
    assert new_file2 in files
    assert new_file3 in files
    assert new_file not in files

def test_run_db_backup_uncompressed(tmp_path):
    db_path = tmp_path / "test.db"
    backup_dir = tmp_path / "backups"
    
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE foo (id INTEGER)")
    conn.close()
    
    new_file, _ = run_db_backup(
        db_path=db_path, backup_dir=backup_dir, max_versions=1, compress=False
    )
    assert new_file.exists()
    assert new_file.suffix == ".db"
    
    with open(new_file, "rb") as f:
        header = f.read(16)
        assert b"SQLite format 3" in header

def test_maybe_run_automatic_backup_disabled(tmp_path):
    db_path = tmp_path / "test.db"
    db_path.touch()
    
    # Interval 0 -> disabled
    ran = maybe_run_automatic_backup({"backup_interval_days": 0}, db_path)
    assert not ran
