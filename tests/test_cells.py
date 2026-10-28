import random

import geopandas as gpd
import pytest
from shapely import union_all
from shapely.geometry import Point, Polygon, box

from app import cells

UTM = 32614  # eastern South Dakota
X, Y = 640_000, 4_900_000


def ll(*shapes):
    return list(gpd.GeoSeries(shapes, crs=UTM).to_crs(4326))


FIELD_M = box(X, Y, X + 100, Y + 60)
FIELD = ll(FIELD_M)[0]


def test_grid_tiles_the_field_exactly():
    cs = cells.grid(FIELD_M, 10.0)
    assert len(cs) == 60 and sum(c.area for c in cs) == pytest.approx(FIELD_M.area)


def test_grid_clips_to_an_irregular_field():
    tri = Polygon([(X, Y), (X + 100, Y), (X + 30, Y + 60)])  # cells along the slanted edges get clipped
    cs = cells.grid(tri, 7.0)
    assert sum(c.area for c in cs) == pytest.approx(tri.area, rel=1e-6)
    assert all(c.within(tri.buffer(1e-6)) for c in cs)


def test_states_and_summary():
    weed = ll(box(X + 12, Y + 12, X + 18, Y + 18))[0]  # inside cell (1, 1)
    buffer_ = ll(box(X + 90, Y, X + 100, Y + 60))[0]  # the eastern column
    weed_in_buffer = ll(box(X + 92, Y + 2, X + 95, Y + 5))[0]
    res = cells.classify(FIELD, [weed, weed_in_buffer], buffer_, 10.0)
    states = [c["state"] for c in res["cells"]]
    assert states.count("spray") == 1 and states.count("buffered") == 6 and states.count("clean") == 53
    s = cells.summary(res)
    assert s["treated_acres"] == pytest.approx(100 / cells.SQM_PER_ACRE, abs=0.01)
    assert s["field_acres"] == pytest.approx(6000 / cells.SQM_PER_ACRE, abs=0.01)


def test_threshold():
    speck = ll(Point(X + 15, Y + 15).buffer(0.2))[0]  # ~0.13 m2 in a 100 m2 cell = 0.13%
    assert all(c["state"] == "clean" for c in cells.classify(FIELD, [speck], None, 10.0)["cells"])
    low = cells.classify(FIELD, [speck], None, 10.0, threshold=0.001)["cells"]
    assert [c["state"] for c in low].count("spray") == 1


def test_shared_edge_is_not_a_touch():
    buffer_ = ll(box(X + 100, Y, X + 120, Y + 60))[0]  # just east of the field
    assert not [c for c in cells.classify(FIELD, [], buffer_, 10.0)["cells"] if c["state"] == "buffered"]


def test_bad_cell_size():
    with pytest.raises(ValueError):
        cells.grid(FIELD_M, 0)


def random_case(rng):
    w, h = rng.uniform(40, 200), rng.uniform(40, 200)
    field_m = box(X, Y, X + w, Y + h)
    weeds_m = [Point(X + rng.uniform(0, w), Y + rng.uniform(0, h)).buffer(rng.uniform(0.2, 4))
               for _ in range(rng.randint(0, 12))]
    bx = rng.uniform(-20, w)
    buffer_m = box(X + bx, Y - 5, X + bx + rng.uniform(1, 30), Y + h + 5) if rng.random() < 0.8 else None
    return field_m, weeds_m, buffer_m, rng.choice([2.0, 5.0, 7.5, 13.0])


@pytest.mark.parametrize("seed", range(40))
def test_properties_hold_on_random_fields(seed):
    rng = random.Random(seed)
    field_m, weeds_m, buffer_m, size = random_case(rng)
    field = ll(field_m)[0]
    weeds = ll(*weeds_m) if weeds_m else []
    buffer_ = ll(buffer_m)[0] if buffer_m is not None else None
    res = cells.classify(field, weeds, buffer_, size)
    # 1. no spray cell is ever inside the no-spray area
    if buffer_m is not None:
        buffer_utm = gpd.GeoSeries([buffer_], crs=4326).to_crs(res["utm"])[0]
        for c in res["cells"]:
            if c["state"] == "spray":
                assert c["cell"].intersection(buffer_utm).area <= 1e-6
    # 2. spray + clean + buffered covers the field exactly
    assert sum(c["cell"].area for c in res["cells"]) == pytest.approx(field_m.area, rel=1e-4)
    # 3. sprayed cells really have weed cover at the threshold
    weeds_utm = union_all(list(gpd.GeoSeries(weeds, crs=4326).to_crs(res["utm"]))) if weeds else None
    for c in res["cells"]:
        if c["state"] == "spray":
            assert c["cell"].intersection(weeds_utm).area / c["cell"].area >= cells.DEFAULT_THRESHOLD - 1e-9
    # 4. same inputs, same hash; a different cell size, a different hash
    again = cells.classify(field, weeds, buffer_, size)
    assert again["hash"] == res["hash"] and cells.classify(field, weeds, buffer_, size + 1)["hash"] != res["hash"]
