import gzip
import os
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

def resolve_backup_dir(config: dict) -> Path:
    """Resolve the backup directory from config, defaulting to ~/.config/pomocli/backups."""
    dir_str = config.get("backup_dir", "").strip()
    if dir_str:
        return Path(dir_str).expanduser().resolve()
    return Path.home() / ".config" / "pomocli" / "backups"

def run_db_backup(*, db_path: Path, backup_dir: Path, max_versions: int, compress: bool = True) -> Tuple[Path, int]:
    """
    Perform a consistent SQLite backup, optionally gzip it, and rotate old backups.
    Returns (path_to_new_backup, number_of_old_backups_deleted).
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    if str(backup_dir.resolve()) == str(db_path.resolve()):
        raise ValueError("Backup directory cannot be the database file itself.")

    backup_dir.mkdir(parents=True, exist_ok=True)
    max_versions = max(1, max_versions)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base_name = f"pomocli-{timestamp}.db"
    temp_db = backup_dir / f".{base_name}.tmp"
    
    # 1. Consistent SQLite backup
    source_conn = sqlite3.connect(db_path)
    dest_conn = sqlite3.connect(temp_db)
    with source_conn, dest_conn:
        source_conn.backup(dest_conn)
    dest_conn.close()
    source_conn.close()

    # 2. Compress or move to final name
    if compress:
        final_path = backup_dir / f"{base_name}.gz"
        with open(temp_db, "rb") as f_in:
            with gzip.open(final_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        temp_db.unlink()
    else:
        final_path = backup_dir / base_name
        temp_db.replace(final_path)

    # 3. Rotate
    pattern = "pomocli-*.db.gz" if compress else "pomocli-*.db"
    existing_backups = sorted(backup_dir.glob(pattern), key=lambda p: p.name)
    
    deleted = 0
    if len(existing_backups) > max_versions:
        to_delete = existing_backups[:-max_versions]
        for p in to_delete:
            try:
                p.unlink()
                deleted += 1
            except OSError:
                pass

    return final_path, deleted

def maybe_run_automatic_backup(config: dict, db_path: Path) -> bool:
    """
    Run an automatic backup if the interval has passed.
    Returns True if a backup was performed.
    """
    interval_days = config.get("backup_interval_days", 0)
    if interval_days <= 0 or not db_path.exists():
        return False

    backup_dir = resolve_backup_dir(config)
    state_file = backup_dir / ".last_automatic_backup"
    
    now = time.time()
    
    if state_file.exists():
        try:
            last_run = float(state_file.read_text().strip())
            days_passed = (now - last_run) / 86400.0
            if days_passed < interval_days:
                return False
        except ValueError:
            pass # Corrupt state file, run backup anyway

    # Time to run
    max_versions = config.get("backup_max_versions", 7)
    compress = config.get("backup_compress", True)
    
    try:
        run_db_backup(
            db_path=db_path,
            backup_dir=backup_dir,
            max_versions=max_versions,
            compress=compress
        )
        # Update state only on success
        state_file.write_text(str(now))
        return True
    except Exception:
        return False
