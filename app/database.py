"""Local SQLite database: suppliers, their mills and their plots.

All data stays on the user's computer.
"""

import json
import sqlite3
from pathlib import Path

# The usual place for app data on macOS. It sits outside the project folder,
# so user data never ends up in Git, and a packaged app can still write here.
DEFAULT_DB_PATH = Path.home() / "Library" / "Application Support" / "PalmOilChecker" / "palmoil.db"

# When a supplier has no plot data, we assume the fruit could come from
# anywhere within this distance of its mill.
SOURCING_RADIUS_KM = 50

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
    risk_status TEXT NOT NULL DEFAULT 'not_checked'  -- worst result of all checks for this plot
);

CREATE TABLE IF NOT EXISTS fire_hotspots (
    id          INTEGER PRIMARY KEY,
    latitude    REAL NOT NULL,
    longitude   REAL NOT NULL,
    detected_on TEXT NOT NULL,                    -- date as YYYY-MM-DD
    satellite   TEXT NOT NULL,
    confidence  TEXT NOT NULL,                    -- 'low', 'nominal' or 'high'
    is_demo     INTEGER NOT NULL DEFAULT 0        -- 1 = simulated demo data
);

CREATE TABLE IF NOT EXISTS check_results (
    id          INTEGER PRIMARY KEY,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    plot_id     INTEGER REFERENCES plots(id) ON DELETE CASCADE,  -- empty for mill-only results
    mill_id     INTEGER REFERENCES mills(id) ON DELETE CASCADE,
    check_type  TEXT NOT NULL,                    -- 'fire' (later also 'forest', 'legality')
    status      TEXT NOT NULL,                    -- 'green', 'amber' or 'red'
    summary     TEXT NOT NULL,                    -- plain-language result
    details     TEXT NOT NULL,                    -- JSON with the numbers behind it
    checked_at  TEXT NOT NULL
);
"""

# Higher number = worse. Used to pick the worst result.
STATUS_RANK = {"not_checked": 0, "green": 1, "amber": 2, "red": 3}


def worst_status(statuses):
    return max(statuses, key=lambda s: STATUS_RANK[s], default="not_checked")


def connect(db_path=DEFAULT_DB_PATH):
    """Open the database, creating the file and tables if needed."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def get_check_results(conn, check_type):
    """All results of one check, with plot or mill names, grouped by supplier id."""
    by_supplier = {}
    for row in conn.execute(
        """
        SELECT r.supplier_id, r.status, r.summary, r.details,
               COALESCE(p.name, m.name) AS place_name,
               r.plot_id IS NULL AS is_mill
        FROM check_results r
        LEFT JOIN plots p ON p.id = r.plot_id
        LEFT JOIN mills m ON m.id = r.mill_id
        WHERE r.check_type = ?
        ORDER BY r.id
        """,
        (check_type,),
    ):
        result = dict(row)
        result["details"] = json.loads(result["details"])
        result["is_mill"] = bool(result["is_mill"])
        by_supplier.setdefault(result.pop("supplier_id"), []).append(result)
    return by_supplier


def get_suppliers(conn):
    """Return every supplier with its first mill, plot count, total area and fire result."""
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

    fire_results = get_check_results(conn, "fire")
    suppliers = []
    for row in rows:
        supplier = dict(row)
        results = fire_results.get(supplier["id"], [])
        supplier["fire"] = None
        if results:
            worst = max(results, key=lambda r: STATUS_RANK[r["status"]])
            supplier["fire"] = {"status": worst["status"], "summary": worst["summary"], "results": results}
        suppliers.append(supplier)
    return suppliers


def update_plot_risk_status(conn):
    """Set each plot's overall risk status to the worst result of all its checks."""
    with conn:
        conn.execute(
            """
            UPDATE plots SET risk_status = COALESCE(
                (SELECT CASE MAX(CASE status WHEN 'red' THEN 3 WHEN 'amber' THEN 2 WHEN 'green' THEN 1 END)
                            WHEN 3 THEN 'red' WHEN 2 THEN 'amber' WHEN 1 THEN 'green' END
                 FROM check_results WHERE plot_id = plots.id),
                'not_checked')
            """
        )


def get_last_check(conn):
    """When the last check ran, and whether it used simulated demo data."""
    row = conn.execute("SELECT MAX(checked_at) FROM check_results").fetchone()
    uses_demo = conn.execute("SELECT EXISTS (SELECT 1 FROM fire_hotspots WHERE is_demo = 1)").fetchone()[0]
    return {"checked_at": row[0], "uses_demo_data": bool(uses_demo)}


def get_map_data(conn):
    """Everything the Map page draws: mills, plots and sourcing areas.

    A sourcing area (circle around the mill) is added for every mill whose
    supplier has no plot data.
    """
    mills = [
        dict(row)
        for row in conn.execute(
            """
            SELECT m.id, m.name, m.latitude, m.longitude,
                   s.name AS supplier_name, s.certification,
                   (SELECT COUNT(*) FROM plots WHERE supplier_id = s.id) AS plot_count
            FROM mills m JOIN suppliers s ON s.id = m.supplier_id
            ORDER BY s.name, m.name
            """
        )
    ]

    plots = []
    for row in conn.execute(
        """
        SELECT p.id, p.name, p.geometry, p.area_ha, p.risk_status,
               s.name AS supplier_name, s.certification,
               r.summary AS fire_summary
        FROM plots p
        JOIN suppliers s ON s.id = p.supplier_id
        LEFT JOIN check_results r ON r.plot_id = p.id AND r.check_type = 'fire'
        ORDER BY s.name, p.name
        """
    ):
        plot = dict(row)
        plot["geometry"] = json.loads(plot["geometry"])
        plots.append(plot)

    sourcing_areas = [
        {
            "mill_name": mill["name"],
            "supplier_name": mill["supplier_name"],
            "latitude": mill["latitude"],
            "longitude": mill["longitude"],
            "radius_km": SOURCING_RADIUS_KM,
        }
        for mill in mills
        if mill["plot_count"] == 0
    ]

    return {"mills": mills, "plots": plots, "sourcing_areas": sourcing_areas}
