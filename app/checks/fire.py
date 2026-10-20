"""Fire check: were satellite fire detections seen on or near each plot?

Red    = a fire on the plot (inside it, or within ON_PLOT_BUFFER_M)
Amber  = a fire within NEARBY_DISTANCE_M
Green  = no fire within NEARBY_DISTANCE_M

Suppliers with only a mill (no plot data) are never green: we cannot check
land we cannot see. They get amber, and we look for fires in the sourcing
area around the mill instead.
"""

import json
from datetime import date, timedelta

from app.database import SOURCING_RADIUS_KM, plots_and_mill_only_suppliers, save_check_results
from app.geometry import distance_between_points_metres, distance_to_plot_metres

# A satellite fire pixel is about 375 m wide (VIIRS), so a fire just outside
# the drawn plot may still be on it.
ON_PLOT_BUFFER_M = 500
NEARBY_DISTANCE_M = 5_000
LOOKBACK_DAYS = 365
IGNORED_CONFIDENCE = {"low"}  # the satellite itself is unsure about these

CHECK_TYPE = "fire"


def relevant_hotspots(conn, today=None):
    """Fire detections the check uses: recent enough and not low-confidence."""
    today = today or date.today()
    start = today - timedelta(days=LOOKBACK_DAYS)
    rows = conn.execute(
        "SELECT * FROM fire_hotspots WHERE detected_on BETWEEN ? AND ? ORDER BY detected_on",
        (start.isoformat(), today.isoformat()),
    )
    return [dict(row) for row in rows if row["confidence"] not in IGNORED_CONFIDENCE]


def _nearest(distances):
    """(distance, hotspot) pair closest to the place, or None."""
    return min(distances, key=lambda pair: pair[0], default=None)


def _nearest_details(nearest):
    if nearest is None:
        return {"nearest_km": None, "nearest_date": None, "nearest_satellite": None}
    distance, hotspot = nearest
    return {
        "nearest_km": round(distance / 1000, 1),
        "nearest_date": hotspot["detected_on"],
        "nearest_satellite": hotspot["satellite"],
    }


def check_plot(geometry, hotspots):
    """Result for one plot: (status, summary, details)."""
    distances = [(distance_to_plot_metres(geometry, h["latitude"], h["longitude"]), h) for h in hotspots]
    on_plot = sum(1 for d, _ in distances if d <= ON_PLOT_BUFFER_M)
    nearby = sum(1 for d, _ in distances if d <= NEARBY_DISTANCE_M)

    if on_plot:
        status, summary = "red", "Fire detected on plot"
    elif nearby:
        status, summary = "amber", "Fires detected nearby"
    else:
        status, summary = "green", "No fires detected nearby"

    details = {
        "fires_on_plot": on_plot,
        "fires_nearby": nearby,
        "nearby_km": NEARBY_DISTANCE_M / 1000,
        **_nearest_details(_nearest(distances)),
    }
    return status, summary, details


def check_mill_only(latitude, longitude, hotspots):
    """Result for a mill whose supplier has no plot data: always amber."""
    radius_m = SOURCING_RADIUS_KM * 1000
    distances = [
        (distance_between_points_metres(latitude, longitude, h["latitude"], h["longitude"]), h) for h in hotspots
    ]
    in_area = sum(1 for d, _ in distances if d <= radius_m)

    if in_area:
        summary = "Plot data missing – fires in possible sourcing area"
    else:
        summary = "Plot data missing – no fires found in sourcing area"

    details = {"fires_in_sourcing_area": in_area, "radius_km": SOURCING_RADIUS_KM, **_nearest_details(_nearest(distances))}
    return "amber", summary, details


def run_fire_check(conn, today=None):
    """Check every plot (and every mill-only supplier) and save the results.

    Returns how many results were saved.
    """
    hotspots = relevant_hotspots(conn, today)
    plots, mills = plots_and_mill_only_suppliers(conn)
    results = []  # (supplier_id, plot_id, mill_id, status, summary, details)

    for plot in plots:
        status, summary, details = check_plot(json.loads(plot["geometry"]), hotspots)
        results.append((plot["supplier_id"], plot["id"], None, status, summary, details))

    for mill in mills:
        status, summary, details = check_mill_only(mill["latitude"], mill["longitude"], hotspots)
        results.append((mill["supplier_id"], None, mill["id"], status, summary, details))

    save_check_results(conn, CHECK_TYPE, results)
    return len(results)
