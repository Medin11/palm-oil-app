"""Forest loss check: was forest cleared on or near each plot after 31 Dec 2020?

This is the core EUDR question. Only tree loss inside areas that were forest
on 31 Dec 2020 counts as deforestation. Loss outside them (for example an old
oil palm plantation being replanted) is ignored.

Red    = CLEARED_ON_PLOT_MIN_HA or more of forest cleared on the plot
Amber  = a smaller clearing on the plot, or clearing within NEARBY_DISTANCE_M
Green  = no clearing on or near the plot

Suppliers with only a mill (no plot data) are never green: they get amber,
with the forest cleared in the sourcing area around the mill.
"""

import json

from shapely.geometry import Point, shape
from shapely.ops import unary_union

from app.database import SOURCING_RADIUS_KM, plots_and_mill_only_suppliers, save_check_results
from app.geometry import shape_area_hectares, shapes_distance_metres

CUTOFF_YEAR = 2020           # EUDR cut-off: 31 Dec 2020. Loss from 2021 on counts.
CLEARED_ON_PLOT_MIN_HA = 0.5  # FAO forest definition: at least 0.5 ha
NEARBY_DISTANCE_M = 1_000

CHECK_TYPE = "forest"


def find_deforestation(forest_2020_geometries, losses):
    """Turn the raw maps into what the check needs.

    forest_2020_geometries: GeoJSON geometries of forest on 31 Dec 2020
    losses: list of (GeoJSON geometry, loss_year)

    Returns (forest_2020 as one Shapely shape, list of {"shape", "year"} where
    forest that stood in 2020 was cleared after the cut-off).
    """
    forest = unary_union([shape(g) for g in forest_2020_geometries])
    deforestation = []
    for geometry, year in losses:
        if year <= CUTOFF_YEAR:
            continue
        cleared = shape(geometry).intersection(forest)
        if not cleared.is_empty:
            deforestation.append({"shape": cleared, "year": year})
    return forest, deforestation


def load_deforestation(conn):
    forest_rows = [json.loads(row[0]) for row in conn.execute("SELECT geometry FROM forest_2020")]
    loss_rows = [(json.loads(row[0]), row[1]) for row in conn.execute("SELECT geometry, loss_year FROM forest_loss")]
    return find_deforestation(forest_rows, loss_rows)


def _nearest(place, deforestation):
    """(distance in metres, year) of the clearing closest to the place, or None."""
    pairs = [(shapes_distance_metres(place, d["shape"]), d["year"]) for d in deforestation]
    return min(pairs, default=None)


def _nearest_details(nearest):
    if nearest is None:
        return {"nearest_km": None, "nearest_year": None}
    distance, year = nearest
    return {"nearest_km": round(distance / 1000, 1), "nearest_year": year}


def check_plot(geometry, forest, deforestation):
    """Result for one plot: (status, summary, details)."""
    plot = shape(geometry)
    cleared = [(shape_area_hectares(plot.intersection(d["shape"])), d["year"]) for d in deforestation]
    cleared = [(ha, year) for ha, year in cleared if ha > 0]
    cleared_ha = sum(ha for ha, _ in cleared)
    nearest = _nearest(plot, deforestation)

    if cleared_ha >= CLEARED_ON_PLOT_MIN_HA:
        status, summary = "red", "Forest cleared on plot since 2021"
    elif cleared_ha > 0 or (nearest and nearest[0] <= NEARBY_DISTANCE_M):
        status, summary = "amber", "Forest cleared nearby"
    else:
        status, summary = "green", "No forest loss detected"

    details = {
        "forest_2020_ha": round(shape_area_hectares(plot.intersection(forest)), 1),
        "cleared_ha": round(cleared_ha, 1),
        "cleared_years": sorted({year for _, year in cleared}),
        "nearby_km": NEARBY_DISTANCE_M / 1000,
        **_nearest_details(nearest),
    }
    return status, summary, details


def check_mill_only(latitude, longitude, deforestation):
    """Result for a mill whose supplier has no plot data: always amber."""
    mill = Point(longitude, latitude)
    radius_m = SOURCING_RADIUS_KM * 1000
    in_area = [d for d in deforestation if shapes_distance_metres(mill, d["shape"]) <= radius_m]
    cleared_ha = sum(shape_area_hectares(d["shape"]) for d in in_area)

    if in_area:
        summary = "Plot data missing – forest cleared in possible sourcing area"
    else:
        summary = "Plot data missing – no forest loss found in sourcing area"

    details = {
        "cleared_in_sourcing_area_ha": round(cleared_ha, 1),
        "radius_km": SOURCING_RADIUS_KM,
        **_nearest_details(_nearest(mill, deforestation)),
    }
    return "amber", summary, details


def run_forest_check(conn):
    """Check every plot (and every mill-only supplier) and save the results.

    Returns how many results were saved.
    """
    forest, deforestation = load_deforestation(conn)
    plots, mills = plots_and_mill_only_suppliers(conn)
    results = []

    for plot in plots:
        status, summary, details = check_plot(json.loads(plot["geometry"]), forest, deforestation)
        results.append((plot["supplier_id"], plot["id"], None, status, summary, details))

    for mill in mills:
        status, summary, details = check_mill_only(mill["latitude"], mill["longitude"], deforestation)
        results.append((mill["supplier_id"], None, mill["id"], status, summary, details))

    save_check_results(conn, CHECK_TYPE, results)
    return len(results)
