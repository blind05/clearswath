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


def test_a_sliver_below_min_acres_is_neither_excluded_nor_a_reason():
    # the pond is 10 m east of the field and 100 m long; a 10.1 m buffer takes a ~10 m2 sliver (< 0.01 ac)
    out = plan(FIELD, {"water": [POND]}, [rule(10.1, "m")])
    assert out["status"] == "go" and out["excluded_acres"] == 0 and out["reasons"] == []


def test_any_gap_is_no_go_with_nothing_sprayable():
    out = plan(FIELD, {}, [], gaps=["USGS stream data was unavailable"])
    assert out["status"] == "no-go" and out["spray_acres"] == 0 and out["spray_zone"].is_empty
    assert out["reasons"] == [{"source": "data", "summary": "USGS stream data was unavailable"}]


RUNOFF = {"kind": "runoff", "target": None, "applies_to": "all", "value": None, "unit": None,
          "summary": "Runoff points", "quote": "Achieve at least 3 runoff mitigation points.", "page": 9}


def test_runoff_points_force_adjust_without_touching_the_map():
    clean = plan(FIELD, {}, [])
    out = plan(FIELD, {}, [RUNOFF])
    assert clean["status"] == "go" and out["status"] == "adjust"
    assert out["spray_acres"] == clean["spray_acres"] and out["excluded_acres"] == 0
    (r,) = out["reasons"]
    assert r["kind"] == "runoff" and "PALM" in r["summary"] and r["quote"] == RUNOFF["quote"] and r["page"] == 9


def test_runoff_points_never_soften_a_no_go():
    assert plan(FIELD, {}, [RUNOFF], prohibited=True)["status"] == "no-go"


def test_runoff_rule_for_ground_rigs_skips_a_drone_job():
    assert plan(FIELD, {}, [RUNOFF | {"applies_to": "ground"}], method="drone")["status"] == "go"


# Water only the aerial scout saw: a question for the applicator, never a change to the map.
INSIDE_M = box(X + 100, Y + 100, X + 140, Y + 130)  # a possible pond inside the field
FAR_M = box(X + 700, Y + 150, X + 740, Y + 190)  # 300 m east of the field
INSIDE, FAR = ll(INSIDE_M, FAR_M)


def test_possible_water_forces_adjust_without_touching_the_map():
    clean = plan(FIELD, {}, [rule()])
    out = plan(FIELD, {"possible_water": [INSIDE]}, [rule()])
    assert clean["status"] == "go" and out["status"] == "adjust"
    assert out["spray_acres"] == clean["spray_acres"] and out["excluded_acres"] == 0
    (r,) = out["reasons"]
    assert r["source"] == "review" and r["kind"] == "possible_water" and "1 possible water area" in r["summary"]


def test_possible_water_far_away_says_nothing():
    assert plan(FIELD, {"possible_water": [FAR]}, [rule(100, "ft")])["status"] == "go"


def test_possible_water_counts_when_its_setback_reaches_the_field():
    assert plan(FIELD, {"possible_water": [FAR]}, [rule(1000, "ft")])["status"] == "adjust"  # 305 m reaches it


def test_possible_water_never_softens_a_no_go():
    assert plan(FIELD, {"possible_water": [INSIDE]}, [rule()], prohibited=True)["status"] == "no-go"


# Drift buffers (engine rule 2): from the treated area toward land the user hasn't marked as managed.
import random  # noqa: E402

from shapely import make_valid, union_all  # noqa: E402
from shapely.geometry import Point, Polygon as Poly  # noqa: E402

from app.buffers import drift_zone  # noqa: E402


def drift(value=50, unit="ft", applies_to="all"):
    return {"kind": "drift", "target": None, "applies_to": applies_to, "value": value, "unit": unit,
            "summary": "Drift buffer", "quote": "Do not apply within 50 feet of non-target areas.", "page": 4}


def test_drift_buffer_takes_a_rim_unless_the_land_beyond_is_managed():
    d = 50 * 0.3048
    out = plan(FIELD, {}, [drift()])
    assert out["status"] == "adjust" and out["reasons"][0]["kind"] == "drift"
    assert out["reasons"][0]["target"] == "unmanaged land" and out["reasons"][0]["distance_ft"] == 50
    (spray,) = m(out["spray_zone"])
    assert spray.area == pytest.approx((400 - 2 * d) ** 2, rel=1e-3)  # a d-wide rim on every side
    # a road along the west side and a neighbour's field to the north are managed: no rim there
    managed = ll(box(X - 30, Y - 30, X, Y + 430), box(X - 30, Y + 400, X + 430, Y + 430))
    out = plan(FIELD, {}, [drift()], managed=managed)
    (spray,) = m(out["spray_zone"])
    assert spray.area == pytest.approx((400 - d) ** 2, rel=1e-3)  # rims only on the east and south


def test_downwind_drift_only_buffers_the_downwind_edge():
    d = 50 * 0.3048
    out = plan(FIELD, {}, [drift()], wind_from_deg=270)  # wind from the west: drift heads east
    (no_spray,) = m(out["no_spray"])
    assert no_spray.area == pytest.approx(400 * d, rel=1e-3)
    assert no_spray.intersection(box(X, Y, X + 400 - d - 0.1, Y + 400)).area < 0.01  # all of it the east strip


def test_drift_rule_for_ground_rigs_skips_a_drone_job():
    assert plan(FIELD, {}, [drift(applies_to="ground")], method="drone")["status"] == "go"


def random_drift_case(rng):
    pts = [(X + rng.uniform(0, 300), Y + rng.uniform(0, 300)) for _ in range(rng.randint(4, 9))]
    field_m = Poly(pts).convex_hull
    managed_m = [Point(X + rng.uniform(-50, 350), Y + rng.uniform(-50, 350)).buffer(rng.uniform(5, 80))
                 for _ in range(rng.randint(0, 4))]
    return field_m, managed_m, rng.uniform(3, 60), rng.choice([None, rng.uniform(0, 360)])


@pytest.mark.parametrize("seed", range(30))
def test_drift_properties_on_random_fields(seed):
    rng = random.Random(seed)
    field_m, managed_m, meters, wind = random_drift_case(rng)
    rule = drift(meters, "m")
    field, managed = ll(field_m)[0], ll(*managed_m) if managed_m else []
    out = plan(field, {}, [rule], managed=managed, wind_from_deg=wind)
    all_round = plan(field, {}, [rule], managed=managed)
    (spray,) = m(out["spray_zone"])
    (spray_all,) = m(all_round["spray_zone"])
    unmanaged = field_m.buffer(meters + 1).difference(field_m)
    if managed_m:
        unmanaged = unmanaged.difference(union_all(m(*managed)))
    unmanaged = unmanaged.buffer(-0.25).buffer(0.25)  # the engine ignores drawing slivers under 0.5 m
    # 1. with buffers all round, no sprayable area is within the drift distance of unmanaged land (zero-area
    #    slivers from the polygon difference don't count; arcs are drawn with 64 segments, ~0.1% short)
    if not spray_all.is_empty and not unmanaged.is_empty:
        assert make_valid(spray_all).intersection(unmanaged.buffer(meters * 0.998)).area < 0.01
    # 2. downwind-only never removes more than all round
    assert out["spray_acres"] >= all_round["spray_acres"] - 0.01
    # 3. marking more land as managed never shrinks what can be sprayed
    more = managed + ll(field_m.buffer(meters * 2).difference(field_m))
    assert plan(field, {}, [rule], managed=more, wind_from_deg=wind)["spray_acres"] >= out["spray_acres"] - 0.01
    # 4. the drift zone is always inside the field
    assert drift_zone(field_m, managed_m, meters, wind).difference(field_m).area <= 1e-6
