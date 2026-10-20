"""Plain-language formats used in the app and the PDF report: 19 Oct 2026, hectares, km."""

from datetime import date, datetime

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def format_date(value):
    """"2026-09-14", "2026-09-14T10:05:00" or a date -> "14 Sep 2026"."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, (date, datetime)):
        return f"{value.day} {MONTHS[value.month - 1]} {value.year}"
    raise TypeError(f"Not a date: {value!r}")


def format_hectares(value):
    """1000.4 -> "1,000 ha", 2.84 -> "2.8 ha" (small areas keep one decimal)."""
    if value < 10:
        rounded = round(value, 1)
        text = f"{rounded:,.1f}".rstrip("0").rstrip(".")
    else:
        text = f"{round(value):,}"
    return f"{text} ha"


def format_km(value):
    """2.0 -> "2 km", 0.65 -> "0.7 km"."""
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{text} km"


def plural(count, word):
    """1 -> "1 fire", 3 -> "3 fires"."""
    return f"{count} {word}{'' if count == 1 else 's'}"
