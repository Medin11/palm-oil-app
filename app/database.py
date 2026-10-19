"""Local SQLite database: suppliers, their mills and their plots.

All data stays on the user's computer.
"""

import sqlite3
from pathlib import Path

# The usual place for app data on macOS. It sits outside the project folder,
# so user data never ends up in Git, and a packaged app can still write here.
DEFAULT_DB_PATH = Path.home() / "Library" / "Application Support" / "PalmOilChecker" / "palmoil.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    certification TEXT NOT NULL DEFAULT 'none',   -- 'RSPO', 'ISPO', 'RSPO+ISPO' or 'none'
    region        TEXT,
    is_demo       INTEGER NOT NULL DEFAULT 0,     -- 1 = example data
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mills (
    id          INTEGER PRIMARY KEY,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    latitude    REAL NOT NULL,
    longitude   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS plots (
    id          INTEGER PRIMARY KEY,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    mill_id     INTEGER REFERENCES mills(id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    geometry    TEXT NOT NULL,                    -- GeoJSON geometry as text
    area_ha     REAL,
    risk_status TEXT NOT NULL DEFAULT 'not_checked'  -- filled in by the risk checks later
);
"""


def connect(db_path=DEFAULT_DB_PATH):
    """Open the database, creating the file and tables if needed."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def get_suppliers(conn):
    """Return every supplier with its first mill, plot count and total area."""
    rows = conn.execute(
        """
        SELECT s.id,
               s.name,
               s.certification,
               s.is_demo,
               (SELECT name FROM mills WHERE supplier_id = s.id ORDER BY id LIMIT 1) AS mill_name,
               (SELECT COUNT(*) FROM plots WHERE supplier_id = s.id) AS plot_count,
               (SELECT COALESCE(SUM(area_ha), 0) FROM plots WHERE supplier_id = s.id) AS total_area_ha
        FROM suppliers s
        ORDER BY s.name
        """
    ).fetchall()
    return [dict(row) for row in rows]
