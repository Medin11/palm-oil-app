"""One-off script: build the offline background map for the Map page.

Cuts the land outline around West Kalimantan out of Natural Earth's
1:10m land data (public domain, https://www.naturalearthdata.com) and saves
it as ui/data/kalimantan_land.js.

The app itself does not need this script. It is kept so the step can be
repeated. It needs pyshp, which is not in requirements.txt:

    .venv/bin/pip install pyshp
    .venv/bin/python tools/make_basemap.py path/to/ne_10m_land.zip
"""

import json
import sys
from pathlib import Path

import shapefile  # pyshp
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

# Area to keep: West Kalimantan with some margin (west, south, east, north).
BOUNDS = (107.5, -4.5, 114.0, 2.5)
# Simplify outlines to about 300 m. Enough detail for a background map.
SIMPLIFY_DEGREES = 0.003

OUTPUT = Path(__file__).parent.parent / "ui" / "data" / "kalimantan_land.js"


def round_coords(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, (list, tuple)):
        return [round_coords(v) for v in value]
    return value


def main(zip_path):
    area = box(*BOUNDS)
    pieces = []
    for record in shapefile.Reader(zip_path).iterShapes():
        land = shape(record.__geo_interface__)
        if land.intersects(area):
            pieces.append(land.intersection(area))

    land = unary_union(pieces).simplify(SIMPLIFY_DEGREES, preserve_topology=True)
    geometry = mapping(land)
    geometry["coordinates"] = round_coords(geometry["coordinates"])

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "// Offline background map: land around West Kalimantan.\n"
        "// Made with tools/make_basemap.py from Natural Earth (public domain).\n"
        f"const KALIMANTAN_LAND = {json.dumps(geometry, separators=(',', ':'))};\n",
        encoding="utf-8",
    )
    print(f"Saved {OUTPUT} ({OUTPUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main(sys.argv[1])
