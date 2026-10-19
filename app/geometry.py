"""Small geometry helpers for plot shapes."""

import math

import shapely
from shapely.geometry import shape

METRES_PER_DEGREE_LAT = 110_574
METRES_PER_DEGREE_LON_AT_EQUATOR = 111_320


def area_hectares(geojson_geometry):
    """Area of a GeoJSON polygon in hectares.

    GeoJSON uses degrees, so the shape is first converted to metres around its
    own centre. That is accurate enough for plots of a few kilometres.
    """
    geom = shape(geojson_geometry)
    lon_scale = METRES_PER_DEGREE_LON_AT_EQUATOR * math.cos(math.radians(geom.centroid.y))

    def to_metres(coords):  # coords is a list of (longitude, latitude) pairs
        return coords * (lon_scale, METRES_PER_DEGREE_LAT)

    return shapely.transform(geom, to_metres).area / 10_000
