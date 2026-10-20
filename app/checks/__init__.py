"""Risk checks. Each check gives every plot a green, amber or red result."""

from app import database
from app.checks import fire, forest

# Every check, in the order the app and the report show them.
CHECKS = {
    "fire": {"label": "Fire risk", "module": fire},
    "forest": {"label": "Forest loss", "module": forest},
}


def get_suppliers_with_details(conn):
    """database.get_suppliers, plus plain-language "lines" for every result."""
    suppliers = database.get_suppliers(conn)
    for supplier in suppliers:
        for check_type, outcome in supplier["checks"].items():
            if outcome is None:
                continue
            for result in outcome["results"]:
                result["lines"] = CHECKS[check_type]["module"].detail_lines(result["details"], result["is_mill"])
    return suppliers
