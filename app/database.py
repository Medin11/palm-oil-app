"""Local SQLite database: suppliers, their mills and their plots.

All data stays on the user's computer.
"""

import json
import sqlite3
from datetime import datetime
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

CREATE TABLE IF NOT EXISTS forest_2020 (          -- areas that were forest on 31 Dec 2020
    id       INTEGER PRIMARY KEY,
    geometry TEXT NOT NULL,                       -- GeoJSON geometry as text
    is_demo  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS forest_loss (          -- areas where trees were lost, by year
    id        INTEGER PRIMARY KEY,
    geometry  TEXT NOT NULL,
    loss_year INTEGER NOT NULL,
    is_demo   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS check_results (
    id          INTEGER PRIMARY KEY,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    plot_id     INTEGER REFERENCES plots(id) ON DELETE CASCADE,  -- empty for mill-only results
    mill_id     INTEGER REFERENCES mills(id) ON DELETE CASCADE,
    check_type  TEXT NOT NULL,                    -- 'fire', 'forest' (later also 'legality')
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


CHECK_TYPES = ("fire", "forest")


def get_suppliers(conn):
    """Return every supplier with its first mill, plot count, total area and check results.

    supplier["checks"]["fire"] is None before a check, otherwise
    {"status", "summary", "results": [one per plot or mill-only mill]}.
    """
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

    results_by_check = {check: get_check_results(conn, check) for check in CHECK_TYPES}
    suppliers = []
    for row in rows:
        supplier = dict(row)
        supplier["checks"] = {}
        for check, by_supplier in results_by_check.items():
            results = by_supplier.get(supplier["id"], [])
            summary = None
            if results:
                worst = max(results, key=lambda r: STATUS_RANK[r["status"]])
                summary = {"status": worst["status"], "summary": worst["summary"], "results": results}
            supplier["checks"][check] = summary
        suppliers.append(supplier)
    return suppliers


def save_check_results(conn, check_type, results):
    """Replace all results of one check.

    results: list of (supplier_id, plot_id, mill_id, status, summary, details).
    """
    checked_at = datetime.now().isoformat(timespec="seconds")
    with conn:  # one transaction
        conn.execute("DELETE FROM check_results WHERE check_type = ?", (check_type,))
        conn.executemany(
            """
            INSERT INTO check_results
                (supplier_id, plot_id, mill_id, check_type, status, summary, details, checked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (supplier_id, plot_id, mill_id, check_type, status, summary, json.dumps(details), checked_at)
                for supplier_id, plot_id, mill_id, status, summary, details in results
            ],
        )


def plots_and_mill_only_suppliers(conn):
    """What a check has to look at: every plot, and every mill whose supplier has no plots."""
    plots = conn.execute("SELECT id, supplier_id, geometry FROM plots").fetchall()
    mills = conn.execute(
        """
        SELECT m.id, m.supplier_id, m.latitude, m.longitude FROM mills m
        WHERE NOT EXISTS (SELECT 1 FROM plots p WHERE p.supplier_id = m.supplier_id)
        """
    ).fetchall()
    return plots, mills


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
    uses_demo = conn.execute(
        """
        SELECT EXISTS (SELECT 1 FROM fire_hotspots WHERE is_demo = 1)
            OR EXISTS (SELECT 1 FROM forest_loss WHERE is_demo = 1)
        """
    ).fetchone()[0]
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
                   s.id AS supplier_id, s.name AS supplier_name, s.certification,
                   (SELECT COUNT(*) FROM plots WHERE supplier_id = s.id) AS plot_count
            FROM mills m JOIN suppliers s ON s.id = m.supplier_id
            ORDER BY s.name, m.name
            """
        )
    ]

    # Each plot's results, e.g. {7: {"fire": {"status": "red", "summary": "..."}, "forest": {...}}}
    plot_checks = {}
    for row in conn.execute("SELECT plot_id, check_type, status, summary FROM check_results WHERE plot_id IS NOT NULL"):
        plot_checks.setdefault(row["plot_id"], {})[row["check_type"]] = {"status": row["status"], "summary": row["summary"]}

    plots = []
    for row in conn.execute(
        """
        SELECT p.id, p.name, p.geometry, p.area_ha, p.risk_status,
               s.id AS supplier_id, s.name AS supplier_name, s.certification
        FROM plots p
        JOIN suppliers s ON s.id = p.supplier_id
        ORDER BY s.name, p.name
        """
    ):
        plot = dict(row)
        plot["geometry"] = json.loads(plot["geometry"])
        plot["checks"] = plot_checks.get(plot["id"], {})
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
