import json

import geopandas as gpd
import pytest
from PIL import Image

from app import scout

UTM = 32615
X, Y = 500_000, 4_650_000
# 10 m pixels: a 10-pixel mask is 1000 m2, above the 50 m2 floor for a hazard
META = {"crs": f"EPSG:{UTM}", "transform": [10, 0, X, 0, -10, Y], "date": "2023-07-09", "width": 64, "height": 64}
MASK = "<|mask;x=0;y=0;data=5,5,!!!!!(QO(0lu8?|>"  # 5x5, 10 pixels set


def sam_text(*objects):
    """SAM's answer for box prompts: (object id, left, top) per 5x5 mask."""
    return "<0f>" + ",".join(f"{n}<|box;x1={x};y1={y};x2={x + 4};y2={y + 4};w=64;h=64|>{MASK}"
                             for n, x, y in objects) + "\n"


@pytest.fixture
def tile(tmp_path):
    png = tmp_path / "tile.png"
    Image.new("RGB", (64, 64), (60, 120, 40)).save(png)
    png.with_suffix(".json").write_text(json.dumps(META))
    return png


@pytest.fixture
def models(monkeypatch):
    """Scripted Wonder answers (find, then review) and SAM answers, in call order; records what was asked."""
    seen = {"wonder": [], "sam": []}

    def setup(wonder, sam):
        def chat_json(messages, schema, name, *, purpose, model, provider, reasoning_effort):
            seen["wonder"].append((name, model, provider, messages[0]["content"][0]["text"]))
            assert reasoning_effort == "low"
            return wonder.pop(0)

        def sam_raw(png, prompt, *, purpose):
            seen["sam"].append(prompt)
            return sam.pop(0)

        monkeypatch.setattr(scout.llm, "chat_json", chat_json)
        monkeypatch.setattr(scout.llm, "sam_raw", sam_raw)
        return seen
    return setup


def hazard(kind, box):
    return {"kind": kind, "box": box, "note": ""}


def area(polys):
    """m2 on the ground; the test mask is 10 pixels in 4 pieces, so count area, not polygons."""
    return gpd.GeoSeries(polys, crs=4326).to_crs(UTM).area.sum() if polys else 0


def test_boxes_become_hazards_by_kind(tile, models):
    seen = models([{"hazards": [hazard("tree line", [10, 20, 14, 24]), hazard("building", [40, 40, 44, 44])]},
                   {"keep": [1, 2], "add": []}],
                  [sam_text((1, 10, 20), (2, 40, 40))])
    out = scout.scout(tile)
    assert out["water"] == [] and area(out["building"]) == pytest.approx(1000, abs=1)
    assert area(out["habitat"]) == pytest.approx(1000, abs=1)  # the mask, not the 25-pixel box
    assert [s[:3] for s in seen["wonder"]] == [("find", "muse-wonder-1.0", "meta"), ("review", "muse-wonder-1.0", "meta")]
    assert "64 x 64\npixels" in seen["wonder"][0][3] and "10.0 m per pixel" in seen["wonder"][0][3] and "1: tree line" in seen["wonder"][1][3]
    assert "box;x1=10;y1=20" in seen["sam"][0] and "box;x1=40;y1=40" in seen["sam"][0]


def test_review_drops_and_adds(tile, models):
    seen = models([{"hazards": [hazard("water", [10, 20, 14, 24]), hazard("tree line", [40, 40, 44, 44])]},
                   {"keep": [2], "add": [hazard("building", [20, 50, 24, 54])]}],
                  [sam_text((1, 10, 20), (2, 40, 40)), sam_text((3, 20, 50))])
    out = scout.scout(tile)
    assert out["water"] == [] and area(out["habitat"]) == pytest.approx(1000, abs=1)
    assert area(out["building"]) == pytest.approx(1000, abs=1)
    assert "3<|box;x1=20;y1=50" in seen["sam"][1]
    assert out["trace"] == ["Muse Wonder marked 2 features; SAM 3.1 outlined 2 of them",
                            "Muse Wonder checked the outlines: kept 1, dropped 1",
                            "Muse Wonder marked 1 features it had missed; SAM 3.1 outlined 1"]


def test_review_cannot_keep_what_sam_never_outlined(tile, models):
    models([{"hazards": [hazard("woods", [10, 20, 14, 24])]}, {"keep": [1, 7], "add": []}],
           [sam_text((1, 10, 20))])
    assert area(scout.scout(tile)["habitat"]) == pytest.approx(1000, abs=1)


def test_boxes_are_clamped_and_empty_ones_skipped(tile, models):
    seen = models([{"hazards": [hazard("woods", [50, 50, 90, 99]), hazard("water", [30, 30, 30, 40])]},
                   {"keep": [1], "add": []}],
                  [sam_text((1, 50, 50))])
    scout.scout(tile)
    assert "1<|box;x1=50;y1=50;x2=63;y2=63" in seen["sam"][0] and "2<|box" not in seen["sam"][0]


def test_low_confidence_masks_are_dropped(tile, models):
    weak = sam_text((1, 10, 20)).replace("|><|mask", ";c=0.2|><|mask").replace("8?|>", "8?;c=0.2|>")
    seen = models([{"hazards": [hazard("building", [10, 20, 14, 24])]}], [weak])
    out = scout.scout(tile)
    assert out["building"] == [] and len(seen["wonder"]) == 1  # nothing outlined, so nothing to review


def test_nothing_found_makes_no_sam_call(tile, models):
    seen = models([{"hazards": []}], [])
    out = scout.scout(tile)
    assert seen["sam"] == [] and out["habitat"] == [] and out["trace"][0].startswith("Muse Wonder marked 0")


def test_more_than_16_boxes_go_in_batches(tile, models):
    boxes = [hazard("woods", [2 * i, 0, 2 * i + 1, 1]) for i in range(18)]
    seen = models([{"hazards": boxes}], [sam_text(), sam_text()])
    scout.scout(tile)
    assert len(seen["sam"]) == 2 and seen["sam"][0].count("<|box") == 16 and seen["sam"][1].count("<|box") == 2
