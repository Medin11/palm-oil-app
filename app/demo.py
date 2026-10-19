"""Load the offline example data for Ketapang into the database."""

import json
from pathlib import Path

from app.geometry import area_hectares

DEMO_FILE = Path(__file__).parent.parent / "demo_data" / "ketapang_demo.json"


def load_demo_data(conn, demo_file=DEMO_FILE):
    """Replace any old example data with a fresh copy. Returns the number of suppliers.

    Only rows marked as demo data are removed, so suppliers the user added stay.
    """
    data = json.loads(Path(demo_file).read_text(encoding="utf-8"))

    with conn:  # one transaction: either everything is saved or nothing
        # Mills and plots of these suppliers are removed too (ON DELETE CASCADE).
        conn.execute("DELETE FROM suppliers WHERE is_demo = 1")

        for supplier in data["suppliers"]:
            supplier_id = conn.execute(
                "INSERT INTO suppliers (name, certification, region, is_demo) VALUES (?, ?, ?, 1)",
                (supplier["name"], supplier["certification"], data["region"]),
            ).lastrowid

            mill = supplier["mill"]
            mill_id = conn.execute(
                "INSERT INTO mills (supplier_id, name, latitude, longitude) VALUES (?, ?, ?, ?)",
                (supplier_id, mill["name"], mill["latitude"], mill["longitude"]),
            ).lastrowid

            for plot in supplier["plots"]:
                geometry = plot["geometry"]
                conn.execute(
                    "INSERT INTO plots (supplier_id, mill_id, name, geometry, area_ha) VALUES (?, ?, ?, ?, ?)",
                    (supplier_id, mill_id, plot["properties"]["name"], json.dumps(geometry), area_hectares(geometry)),
                )

    return len(data["suppliers"])
