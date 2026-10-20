"""Small geometry helpers for plot shapes."""

import math

import shapely
from shapely.geometry import Point, shape

METRES_PER_DEGREE_LAT = 110_574
METRES_PER_DEGREE_LON_AT_EQUATOR = 111_320
EARTH_RADIUS_M = 6_371_000


def _to_metres(geom, centre_lat):
    """Convert a shape from degrees to metres around the given latitude.

    That is accurate enough for plots and distances of a few kilometres.
    """
    lon_scale = METRES_PER_DEGREE_LON_AT_EQUATOR * math.cos(math.radians(centre_lat))

    def convert(coords):  # coords is a list of (longitude, latitude) pairs
        return coords * (lon_scale, METRES_PER_DEGREE_LAT)

    return shapely.transform(geom, convert)


def shape_area_hectares(geom):
    """Area of a Shapely shape (in degrees) in hectares."""
    if geom.is_empty:
        return 0.0
    return _to_metres(geom, geom.centroid.y).area / 10_000


def area_hectares(geojson_geometry):
    """Area of a GeoJSON polygon in hectares."""
    return shape_area_hectares(shape(geojson_geometry))


def shapes_distance_metres(a, b):
    """Shortest distance between two Shapely shapes in metres. 0 if they touch or overlap."""
    centre_lat = a.centroid.y
    return _to_metres(a, centre_lat).distance(_to_metres(b, centre_lat))


def distance_to_plot_metres(geojson_geometry, latitude, longitude):
    """Distance from a point to a plot in metres. 0 if the point is inside."""
    return shapes_distance_metres(shape(geojson_geometry), Point(longitude, latitude))


def distance_between_points_metres(lat1, lon1, lat2, lon2):
    """Straight-line distance between two points on Earth in metres (haversine)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))
