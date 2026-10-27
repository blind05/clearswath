import json

import pytest
from shapely.geometry import Point, box, mapping

from app import geo

SQ = box(-93.0, 42.0, -92.99, 42.01)


@pytest.mark.parametrize("gj", [
    mapping(SQ),
    {"type": "Feature", "geometry": mapping(SQ), "properties": {}},
    {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": mapping(Point(0, 0)), "properties": {}},
        {"type": "Feature", "geometry": mapping(SQ), "properties": {}}]},
])
def test_load_field(tmp_path, gj):
    p = tmp_path / "f.geojson"
    p.write_text(json.dumps(gj))
    assert geo.load_field(p).equals(SQ)


def test_load_field_no_polygon(tmp_path):
    p = tmp_path / "f.geojson"
    p.write_text(json.dumps(mapping(Point(0, 0))))
    with pytest.raises(ValueError):
        geo.load_field(p)


def test_round_trip(tmp_path):
    p = tmp_path / "out" / "s.geojson"
    geo.save_shapes([SQ, Point(1, 2)], p, [{"k": 1}, {"k": 2}])
    assert json.loads(p.read_text())["features"][1]["properties"] == {"k": 2}
    a, b = geo.load_shapes(p)
    assert a.equals(SQ) and b.equals(Point(1, 2))


def write(tmp_path, geom):
    p = tmp_path / "f.geojson"
    p.write_text(json.dumps(mapping(geom) if not isinstance(geom, dict) else geom))
    return p


@pytest.mark.parametrize("geom, message", [
    (box(-103.0, 43.0, -96.5, 45.9), "acres; the limit is 640"),                                    # most of SD
    ({"type": "Polygon", "coordinates": [[[-93, 42], [-92.99, 42.01], [-92.99, 42], [-93, 42.01], [-93, 42]]]},
     "isn't a valid shape"),                                                                      # bow-tie
    ({"type": "Polygon", "coordinates": [[[500, 95], [501, 95], [501, 96], [500, 95]]]}, "longitude/latitude"),
    (box(-157.9, 21.3, -157.89, 21.31), "outside the contiguous US"),                                # Hawaii
    (box(500000, 4650000, 500400, 4650400), "longitude/latitude"),                                   # UTM metres
])
def test_bad_fields_are_refused(tmp_path, geom, message):
    with pytest.raises(geo.FieldError, match=message):
        geo.load_field(write(tmp_path, geom))


def test_too_many_points(tmp_path):
    ring = Point(-93.0, 42.0).buffer(0.005, quad_segs=600)  # ~2,400 points, a few acres
    with pytest.raises(geo.FieldError, match="points; the limit is 2,000"):
        geo.load_field(write(tmp_path, ring))


def test_a_640_acre_square_mile_is_fine(tmp_path):
    import geopandas as gpd

    utm = 32615
    sq = gpd.GeoSeries([box(500000, 4650000, 501600, 4651600)], crs=utm).to_crs(4326)[0]  # 1.6 km = ~632 ac
    assert geo.load_field(write(tmp_path, sq)).equals(sq)
