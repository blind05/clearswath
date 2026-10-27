import geopandas as gpd
import pytest
from shapely.geometry import box

from app.buffers import plan

UTM = 32615  # Iowa; test shapes are built in metres here, then sent in as lon/lat
X, Y = 500_000, 4_650_000


def ll(*shapes):
    return list(gpd.GeoSeries(shapes, crs=UTM).to_crs(4326))


def m(*shapes):
    return list(gpd.GeoSeries(shapes, crs=4326).to_crs(UTM))


FIELD_M = box(X, Y, X + 400, Y + 400)  # 400 m square, ~39.5 ac
POND_M = box(X + 410, Y + 150, X + 460, Y + 250)  # 10 m east of the field
FIELD, POND = ll(FIELD_M, POND_M)


def rule(value=100, unit="ft", target="water", applies_to="all"):
    return {"kind": "buffer", "target": target, "applies_to": applies_to, "value": value,
            "unit": unit, "summary": "Buffer", "quote": "Do not apply within 100 feet of water.",
            "page": 3}


def test_go_without_hazards():
    out = plan(FIELD, {}, [rule()])
    assert out["status"] == "go" and out["reasons"] == []
    assert out["spray_acres"] == out["field_acres"] == pytest.approx(39.54, abs=0.01)


def test_label_buffer_in_feet():
    out = plan(FIELD, {"water": [POND]}, [rule(100, "ft")])
    assert out["status"] == "adjust"
    assert out["spray_zone"].is_valid and out["no_spray"].is_valid
    spray, pond = m(out["spray_zone"], POND)
    assert spray.distance(pond) == pytest.approx(100 * 0.3048, abs=0.05)
    (r,) = out["reasons"]
    assert r["source"] == "label" and r["distance_ft"] == 100 and r["page"] == 3 and r["quote"]
    assert out["spray_acres"] + out["excluded_acres"] == pytest.approx(out["field_acres"], abs=0.02)


def test_label_buffer_in_metres():
    out = plan(FIELD, {"water": [POND]}, [rule(30, "m")])
    assert out["reasons"][0]["distance_ft"] == 98.4
    spray, pond = m(out["spray_zone"], POND)
    assert spray.distance(pond) == pytest.approx(30, abs=0.05)


def test_drone_counts_as_aerial():
    out = plan(FIELD, {"water": [POND]}, [rule(applies_to="aerial")], method="drone")
    assert out["reasons"][0]["source"] == "label"


def test_water_fallback_when_rule_does_not_apply():
    pond_in = ll(box(X + 100, Y + 100, X + 200, Y + 200))[0]  # 1 ha inside the field
    out = plan(FIELD, {"water": [pond_in]}, [rule(applies_to="ground")], method="drone")
    assert out["status"] == "adjust"
    assert [r["source"] for r in out["reasons"]] == ["rule:water"]
    assert out["excluded_acres"] == pytest.approx(2.47, abs=0.01)


def test_prohibited_is_no_go():
    out = plan(FIELD, {}, [], prohibited=True)
    assert out["status"] == "no-go" and out["spray_acres"] == 0
    assert out["reasons"][0]["source"] == "bulletin"


def test_no_sprayable_area_is_no_go():
    out = plan(FIELD, {"water": [POND]}, [rule(2000, "ft")])
    assert out["status"] == "no-go" and out["spray_acres"] == 0


def test_restricted_area_excluded():
    strip = ll(box(X, Y, X + 400, Y + 50))[0]
    out = plan(FIELD, {}, [], restricted=[strip])
    assert out["status"] == "adjust" and out["reasons"][0]["source"] == "bulletin"
    assert out["excluded_acres"] == pytest.approx(4.94, abs=0.01)


def test_buffer_that_misses_the_field_is_not_a_reason():
    # the pond is 10 m east of the field: a 25 ft (7.6 m) buffer stops short, a 100 ft one reaches in
    out = plan(FIELD, {"water": [POND]}, [rule(25, "ft"), rule(100, "ft")])
    assert out["status"] == "adjust"
    assert [r["distance_ft"] for r in out["reasons"]] == [100]


def test_go_lists_no_reasons_when_nothing_reaches():
    out = plan(FIELD, {"water": [POND]}, [rule(25, "ft")])
    assert out["status"] == "go" and out["reasons"] == []


def test_far_restricted_area_is_not_a_reason():
    far = ll(box(X + 5000, Y, X + 5100, Y + 100))[0]
    out = plan(FIELD, {}, [], restricted=[far])
    assert out["status"] == "go" and out["reasons"] == []
