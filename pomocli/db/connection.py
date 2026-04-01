import sqlite3
import os
from pathlib import Path

DB_DIR = Path.home() / ".config" / "pomocli"
DB_PATH = Path(os.environ.get("POMOCLI_DB_PATH", DB_DIR / "pomocli.db"))
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

def get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Initialize the database schema."""
    conn = get_connection()
    with open(SCHEMA_PATH, "r") as f:
        schema = f.read()
    
    with conn:
        conn.executescript(schema)
    conn.close()

if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
