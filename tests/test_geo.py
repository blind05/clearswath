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
