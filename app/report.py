"""PDF due diligence report.

Cover, summary, one page per supplier, method and limits, data sources and an
appendix with plot locations. Built from what is in the database after
"Check suppliers" has run.
"""

import math
import tempfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw
from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from shapely.geometry import shape

from app import database
from app.checks import CHECKS, fire, forest, get_suppliers_with_details
from app.formatting import format_date, format_hectares, format_km, plural

TITLE = "Palm oil supplier risk screening"
DISCLAIMER = "Risk screening – not a legal guarantee"

ACCENT = colors.HexColor("#2f6b45")
TEXT = colors.HexColor("#1f2a24")
MUTED = colors.HexColor("#6b746e")
BORDER = colors.HexColor("#e3e0d8")
SOFT = colors.HexColor("#f6f4ef")
AMBER_SOFT = colors.HexColor("#fdf3dc")

STATUS_HEX = {"green": "#2e9e57", "amber": "#e0a526", "red": "#d0453a", "not_checked": "#9aa39d"}
OVERALL_LABELS = {
    "red": "Risk found",
    "amber": "Possible risk",
    "green": "No risk found",
    "not_checked": "Not checked",
}
CERTIFICATION_LABELS = {"RSPO+ISPO": "RSPO + ISPO", "RSPO": "RSPO", "ISPO": "ISPO", "none": "No certification"}

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN


class ReportError(Exception):
    """Something the user has to do first, e.g. run the checks."""


# ---------- Text styles ----------

def _style(name, **kwargs):
    base = {"fontName": "Helvetica", "fontSize": 9.5, "leading": 13, "textColor": TEXT}
    base.update(kwargs)
    return ParagraphStyle(name, **base)


STYLES = {
    "title": _style("title", fontName="Helvetica-Bold", fontSize=26, leading=31, textColor=ACCENT),
    "subtitle": _style("subtitle", fontSize=13, leading=18, textColor=MUTED),
    "h1": _style("h1", fontName="Helvetica-Bold", fontSize=17, leading=22, spaceAfter=4),
    "h2": _style("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=3),
    "body": _style("body"),
    "muted": _style("muted", textColor=MUTED),
    "small": _style("small", fontSize=8.5, leading=11.5, textColor=MUTED),
    "cell": _style("cell", fontSize=9, leading=12),
    "cell_bold": _style("cell_bold", fontName="Helvetica-Bold", fontSize=9, leading=12),
    "bullet": _style("bullet", leftIndent=10, bulletIndent=0, spaceAfter=2),
}


def _p(text, style="body"):
    """Paragraph from plain text (escaped, so names can never break the PDF)."""
    return Paragraph(escape(str(text)), STYLES[style])


DOT_FOLDER = Path(tempfile.gettempdir()) / "palm-oil-checker-report"


def _dot_image(status):
    """Path to a small round PNG in the status colour (made once, reused).

    A drawn image looks the same in every PDF viewer; symbol fonts do not.
    """
    path = DOT_FOLDER / f"dot-{status}.png"
    if not path.exists():
        DOT_FOLDER.mkdir(parents=True, exist_ok=True)
        size = 64  # drawn large, shown small, so the edge is smooth
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(image).ellipse((2, 2, size - 3, size - 3), fill=STATUS_HEX[status])
        image.save(path)
    return path


def _dot(status, text, style="cell"):
    """Coloured dot + text, e.g. (red) "Fire detected on plot"."""
    return Paragraph(
        f'<img src="{_dot_image(status)}" width="6.5" height="6.5" valign="0.5"/>&nbsp;&nbsp;{escape(text)}',
        STYLES[style],
    )


def _bullets(lines):
    return [Paragraph(escape(line), STYLES["bullet"], bulletText="•") for line in lines]


def _box(paragraphs, background):
    table = Table([[paragraphs]], colWidths=[CONTENT_WIDTH])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _table(rows, col_widths, header=True):
    table = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), SOFT), ("LINEBELOW", (0, 0), (-1, 0), 0.8, MUTED)]
    table.setStyle(TableStyle(style))
    return table


# ---------- Helpers ----------

def overall_status(supplier):
    """Worst result of all checks for a supplier."""
    statuses = [outcome["status"] for outcome in supplier["checks"].values() if outcome]
    return database.worst_status(statuses)


def sorted_suppliers(suppliers):
    """Worst results first, then by name."""
    return sorted(suppliers, key=lambda s: (-database.STATUS_RANK[overall_status(s)], s["name"].lower()))


def _plots_text(supplier):
    if supplier["plot_count"] == 0:
        return "Plot data missing – only the mill location is known"
    return f"{plural(supplier['plot_count'], 'plot')} · {format_hectares(supplier['total_area_ha'])}"


def _coords(lat, lon):
    return f"{lat:.5f}, {lon:.5f}"


# ---------- Plot drawing ----------

STATUS_COLOURS = {status: colors.HexColor(hex_value) for status, hex_value in STATUS_HEX.items()}
STATUS_COLOURS["not_checked"] = colors.HexColor("#4f6283")


def _nice_scale(target_km):
    for value in (0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100):
        if value >= target_km:
            return value
    return 100


def plot_drawing(plots, mills, sourcing_areas, width=CONTENT_WIDTH, height=62 * mm):
    """A simple outline drawing of a supplier's plots and mill, north up, to scale."""
    shapes = [(shape(p["geometry"]), p) for p in plots]
    points = [(m["longitude"], m["latitude"]) for m in mills]
    for area, _ in shapes:
        minx, miny, maxx, maxy = area.bounds
        points += [(minx, miny), (maxx, maxy)]
    for area in sourcing_areas:
        dlat = area["radius_km"] / 110.574
        dlon = area["radius_km"] / (111.320 * math.cos(math.radians(area["latitude"])))
        points += [(area["longitude"] - dlon, area["latitude"] - dlat), (area["longitude"] + dlon, area["latitude"] + dlat)]

    min_lon = min(p[0] for p in points)
    max_lon = max(p[0] for p in points)
    min_lat = min(p[1] for p in points)
    max_lat = max(p[1] for p in points)
    lon_factor = math.cos(math.radians((min_lat + max_lat) / 2))
    extent_x = max((max_lon - min_lon) * lon_factor, 0.005)
    extent_y = max(max_lat - min_lat, 0.005)
    pad = 12
    pad_bottom = 24  # keeps a free strip for the scale bar
    scale = min((width - 2 * pad) / extent_x, (height - pad - pad_bottom) / extent_y)
    offset_x = (width - extent_x * scale) / 2
    offset_y = pad_bottom + (height - pad - pad_bottom - extent_y * scale) / 2

    def xy(lon, lat):
        return offset_x + (lon - min_lon) * lon_factor * scale, offset_y + (lat - min_lat) * scale

    drawing = Drawing(width, height)
    drawing.add(Rect(0, 0, width, height, fillColor=SOFT, strokeColor=BORDER, strokeWidth=0.5))

    for area in sourcing_areas:
        cx, cy = xy(area["longitude"], area["latitude"])
        radius = area["radius_km"] / 110.574 * scale
        drawing.add(Circle(cx, cy, radius, fillColor=None, strokeColor=MUTED, strokeWidth=0.8, strokeDashArray=[3, 3]))
        drawing.add(String(cx, cy - radius * 0.6, f"Possible sourcing area ({area['radius_km']} km)",
                           fontName="Helvetica", fontSize=7, fillColor=MUTED, textAnchor="middle"))

    for area, plot in shapes:
        outline = area.exterior if area.geom_type == "Polygon" else area.convex_hull.exterior
        coords = [value for lon, lat in outline.coords for value in xy(lon, lat)]
        colour = STATUS_COLOURS.get(plot["risk_status"], STATUS_COLOURS["not_checked"])
        fill = colors.Color(colour.red, colour.green, colour.blue, alpha=0.3)
        drawing.add(Polygon(coords, fillColor=fill, strokeColor=colour, strokeWidth=1))
        # Name just above the plot, so it never covers the outline
        label_x, _ = xy(area.centroid.x, area.centroid.y)
        _, top = xy(area.centroid.x, area.bounds[3])
        drawing.add(String(label_x, top + 3, plot["name"], fontName="Helvetica", fontSize=7, fillColor=TEXT, textAnchor="middle"))

    for mill in mills:
        mx, my = xy(mill["longitude"], mill["latitude"])
        drawing.add(Circle(mx, my, 3, fillColor=TEXT, strokeColor=colors.white, strokeWidth=1))
        drawing.add(String(mx + 5, my - 2.5, mill["name"], fontName="Helvetica", fontSize=7, fillColor=MUTED))

    # Scale bar, bottom left
    km_per_unit = 110.574 / scale
    bar_km = _nice_scale(width * 0.15 * km_per_unit)
    bar = bar_km / km_per_unit
    drawing.add(Line(8, 8, 8 + bar, 8, strokeColor=TEXT, strokeWidth=1.2))
    drawing.add(String(8, 11, format_km(bar_km), fontName="Helvetica", fontSize=7, fillColor=TEXT))
    drawing.add(String(width - 6, 6, "North is up", fontName="Helvetica", fontSize=7, fillColor=MUTED, textAnchor="end"))
    return drawing


# ---------- Report sections ----------

def _cover(last_check, suppliers, plots, uses_demo, today):
    total_area = sum(p["area_ha"] or 0 for p in plots)
    facts = [
        ["Report date", format_date(today)],
        ["Checks run", f"{format_date(last_check['checked_at'])}, {last_check['checked_at'][11:16]}"],
        ["Suppliers", str(len(suppliers))],
        ["Plots", f"{len(plots)} ({format_hectares(total_area)})"],
        ["Checks", ", ".join(c["label"] for c in CHECKS.values())],
    ]
    facts_table = Table([[_p(k, "muted"), _p(v)] for k, v in facts], colWidths=[40 * mm, CONTENT_WIDTH - 40 * mm])
    facts_table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER), ("TOPPADDING", (0, 0), (-1, -1), 5)]))

    story = [
        Spacer(1, 45 * mm),
        _p(TITLE, "title"),
        Spacer(1, 3 * mm),
        _p("EU Deforestation Regulation (EUDR) – supplier due diligence support", "subtitle"),
        Spacer(1, 14 * mm),
        facts_table,
        Spacer(1, 12 * mm),
        _box(
            [
                _p("This is a risk screening, not a legal guarantee or certification.", "cell_bold"),
                _p(
                    "Results are based on satellite data, which has limits (clouds, haze, small clearings). "
                    "Suppliers marked red or amber need follow-up before you rely on them.",
                    "cell",
                ),
            ],
            SOFT,
        ),
    ]
    if uses_demo:
        story += [
            Spacer(1, 5 * mm),
            _box(
                [
                    _p("Contains simulated demo data – not real satellite data.", "cell_bold"),
                    _p("Fire and forest data are made up for demonstration. Supplier names are fictional.", "cell"),
                ],
                AMBER_SOFT,
            ),
        ]
    return story + [PageBreak()]


def _summary(suppliers):
    counts = {status: 0 for status in OVERALL_LABELS}
    for supplier in suppliers:
        counts[overall_status(supplier)] += 1
    totals = " · ".join(
        f"{plural(counts[s], 'supplier')} – {OVERALL_LABELS[s].lower()}" for s in ("red", "amber", "green") if counts[s]
    )

    header = [_p("Supplier", "cell_bold"), _p("Certification", "cell_bold")]
    header += [_p(c["label"], "cell_bold") for c in CHECKS.values()] + [_p("Overall", "cell_bold")]
    rows = [header]
    for supplier in suppliers:
        row = [_p(supplier["name"], "cell"), _p(CERTIFICATION_LABELS.get(supplier["certification"], supplier["certification"]), "cell")]
        for check_type in CHECKS:
            outcome = supplier["checks"][check_type]
            row.append(_dot(outcome["status"], outcome["summary"]) if outcome else _dot("not_checked", "Not checked"))
        status = overall_status(supplier)
        row.append(_dot(status, OVERALL_LABELS[status], "cell_bold"))
        rows.append(row)

    widths = [40 * mm, 24 * mm, 40 * mm, 40 * mm, CONTENT_WIDTH - 144 * mm]
    return [
        _p("Summary", "h1"),
        _p(totals, "muted"),
        Spacer(1, 5 * mm),
        _table(rows, widths),
        Spacer(1, 4 * mm),
        _p(
            "Overall = the worst result of all checks. Suppliers with only a mill location (plot data missing) "
            "are never rated “No risk found”, because their land cannot be checked.",
            "small",
        ),
        PageBreak(),
    ]


def _supplier_section(supplier, plots, mills, sourcing_areas):
    name = supplier["name"] + ("  (demo)" if supplier["is_demo"] else "")
    mill_text = "No mill added"
    if mills:
        mill_text = "; ".join(f"{m['name']} ({_coords(m['latitude'], m['longitude'])})" for m in mills)
    status = overall_status(supplier)
    facts = [
        [_p("Mill", "muted"), _p(mill_text, "cell")],
        [_p("Certification", "muted"), _p(CERTIFICATION_LABELS.get(supplier["certification"], supplier["certification"]), "cell")],
        [_p("Plots", "muted"), _p(_plots_text(supplier), "cell")],
        [_p("Overall", "muted"), _dot(status, OVERALL_LABELS[status], "cell_bold")],
    ]
    facts_table = Table(facts, colWidths=[30 * mm, CONTENT_WIDTH - 30 * mm])
    facts_table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER), ("VALIGN", (0, 0), (-1, -1), "TOP")]))

    story = [_p(name, "h1"), facts_table, Spacer(1, 5 * mm)]
    if plots or mills:
        story += [
            plot_drawing(plots, mills, sourcing_areas),
            _p("Plot outlines drawn from the supplier's coordinates. Colours show each plot's overall result.", "small"),
        ]

    for check_type, check in CHECKS.items():
        outcome = supplier["checks"][check_type]
        heading = [_p(check["label"], "h2")]
        if not outcome:
            story += heading + [_dot("not_checked", "Not checked", "body")]
            continue
        rows = []
        for result in outcome["results"]:
            place = [_p(result["place_name"], "cell_bold"), _dot(result["status"], result["summary"])]
            lines = Paragraph("<br/>".join(escape(line) for line in result["lines"]), STYLES["cell"])
            rows.append([place, lines])
        table = _table(rows, [62 * mm, CONTENT_WIDTH - 62 * mm], header=False)
        story.append(KeepTogether(heading + [_dot(outcome["status"], outcome["summary"], "body"), Spacer(1, 2 * mm), table]))
    return story + [PageBreak()]


def _method(uses_demo):
    since = forest.CUTOFF_YEAR + 1
    months = fire.LOOKBACK_DAYS // 30
    sources = []
    if uses_demo:
        sources += [
            "Fire detections: simulated fire data (demo). Made up for this demonstration, not NASA FIRMS data.",
            "Forest maps: simulated forest data (demo). Made up for this demonstration, not JRC or Global Forest Watch data.",
        ]
    else:
        sources += [
            "Fire detections: stored in the app from the configured fire data source.",
            "Forest maps: stored in the app from the configured forest data source.",
        ]
    sources.append("Supplier, mill and plot data: entered or imported by the user (or the built-in example data).")

    return [
        _p("Method and limits", "h1"),
        _p("Fire risk", "h2"),
        *_bullets(
            [
                f"Red – Fire detected on plot: a satellite fire detection inside the plot or within "
                f"{fire.ON_PLOT_BUFFER_M} m of it (one detection covers about 375 m).",
                f"Amber – Fires detected nearby: a detection within {format_km(fire.NEARBY_DISTANCE_M / 1000)}.",
                f"Green – No fires detected nearby: no detection within {format_km(fire.NEARBY_DISTANCE_M / 1000)}.",
                f"Only detections from the last {months} months are used. Low-confidence detections are ignored.",
            ]
        ),
        _p("Forest loss", "h2"),
        *_bullets(
            [
                f"Only tree loss inside areas that were forest on 31 Dec {forest.CUTOFF_YEAR} (the EUDR cut-off date) "
                "counts. Loss outside them, such as an old plantation being replanted, is ignored.",
                f"Red – Forest cleared on plot: {forest.CLEARED_ON_PLOT_MIN_HA} ha or more cleared since {since} "
                "(0.5 ha is the minimum size of a forest in the FAO definition).",
                f"Amber – Forest cleared nearby: a smaller clearing on the plot, or clearing within "
                f"{format_km(forest.NEARBY_DISTANCE_M / 1000)}.",
                f"Green – No forest loss detected: no clearing on or within {format_km(forest.NEARBY_DISTANCE_M / 1000)} of the plot.",
            ]
        ),
        _p("Suppliers without plot data", "h2"),
        *_bullets(
            [
                f"If only the mill location is known, the checks look at a {database.SOURCING_RADIUS_KM} km "
                "sourcing area around the mill. These suppliers are never rated green: their land cannot be "
                "checked without plot locations, which the EUDR requires.",
            ]
        ),
        _p("Limits", "h2"),
        *_bullets(
            [
                "Satellites can miss fires under clouds or haze, and short fires between satellite passes.",
                "Forest maps use 30 m pixels. Small clearings, or clearings hidden by clouds, can be missed.",
                "Tree loss is not always deforestation, so red results need a closer look with the supplier.",
                "Legality (state forest area, concession boundaries) is not checked in this version.",
                "Results depend on the accuracy of the plot coordinates supplied.",
            ]
        ),
        _p("Data sources", "h2"),
        *_bullets(sources),
        PageBreak(),
    ]


def _appendix(suppliers, plots_by_supplier, mills_by_supplier):
    rows = [[_p(h, "cell_bold") for h in ("Supplier", "Plot", "Area", "Centre (lat, lon)", "Outline points (lat, lon)")]]
    for supplier in sorted(suppliers, key=lambda s: s["name"].lower()):
        plots = plots_by_supplier.get(supplier["id"], [])
        for plot in plots:
            area = shape(plot["geometry"])
            outline = area.exterior.coords if area.geom_type == "Polygon" else area.convex_hull.exterior.coords
            corners = "; ".join(_coords(lat, lon) for lon, lat in list(outline)[:-1])
            rows.append(
                [
                    _p(supplier["name"], "cell"),
                    _p(plot["name"], "cell"),
                    _p(format_hectares(plot["area_ha"] or 0), "cell"),
                    _p(_coords(area.centroid.y, area.centroid.x), "cell"),
                    _p(corners, "small"),
                ]
            )
        if not plots:
            for mill in mills_by_supplier.get(supplier["id"], []):
                rows.append(
                    [
                        _p(supplier["name"], "cell"),
                        _p(f"Mill only: {mill['name']}", "cell"),
                        _p("–", "cell"),
                        _p(_coords(mill["latitude"], mill["longitude"]), "cell"),
                        _p("Plot data missing", "small"),
                    ]
                )
    widths = [34 * mm, 28 * mm, 16 * mm, 30 * mm, CONTENT_WIDTH - 108 * mm]
    return [
        _p("Appendix: plot locations", "h1"),
        _p("Coordinates in decimal degrees (WGS 84), as used for EUDR geolocation.", "muted"),
        Spacer(1, 4 * mm),
        _table(rows, widths),
    ]


def _footer(today):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 10 * mm, f"{TITLE} · {format_date(today)} · {DISCLAIMER}")
        canvas.drawRightString(PAGE_WIDTH - MARGIN, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw


def build_report(conn, output_path, today=None, compress=True):
    """Write the PDF report. Returns {"pages", "suppliers"}.

    Raises ReportError if there is nothing to report yet.
    """
    today = today or date.today()
    last_check = database.get_last_check(conn)
    suppliers = get_suppliers_with_details(conn)
    if not suppliers:
        raise ReportError("There are no suppliers to report on yet.")
    if not last_check["checked_at"]:
        raise ReportError("Check your suppliers first, then export the report.")

    suppliers = sorted_suppliers(suppliers)
    map_data = database.get_map_data(conn)
    plots_by_supplier, mills_by_supplier, areas_by_mill = {}, {}, {}
    for plot in map_data["plots"]:
        plots_by_supplier.setdefault(plot["supplier_id"], []).append(plot)
    for mill in map_data["mills"]:
        mills_by_supplier.setdefault(mill["supplier_id"], []).append(mill)
    for area in map_data["sourcing_areas"]:
        areas_by_mill.setdefault((area["latitude"], area["longitude"]), []).append(area)

    uses_demo = last_check["uses_demo_data"] or any(s["is_demo"] for s in suppliers)

    story = _cover(last_check, suppliers, map_data["plots"], uses_demo, today)
    story += _summary(suppliers)
    for supplier in suppliers:
        mills = mills_by_supplier.get(supplier["id"], [])
        areas = [a for m in mills for a in areas_by_mill.get((m["latitude"], m["longitude"]), [])]
        story += _supplier_section(supplier, plots_by_supplier.get(supplier["id"], []), mills, areas)
    story += _method(uses_demo)
    story += _appendix(suppliers, plots_by_supplier, mills_by_supplier)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=20 * mm,
        title=TITLE,
        author="Palm Oil Supply Chain Checker",
        subject=DISCLAIMER,
        pageCompression=1 if compress else 0,
    )
    footer = _footer(today)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return {"pages": doc.page, "suppliers": len(suppliers)}
