import json

import geopandas as gpd
import pytest
from PIL import Image

from app import scout, segment

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
    """Scripted Wonder answers (find, then review) and SAM box answers, in call order; SAM's text prompts answer
    by phrase (they run alongside Wonder, so their order isn't fixed). Records what was asked."""
    seen = {"wonder": [], "sam": [], "text": []}

    def setup(wonder, sam, text=None):
        def chat_json(messages, schema, name, *, purpose, model, provider, reasoning_effort):
            seen["wonder"].append((name, model, provider, messages[0]["content"][0]["text"]))
            assert reasoning_effort == "low"
            return wonder.pop(0)

        def sam_raw(png, prompt, *, purpose):
            if purpose.startswith("segment:"):
                seen["text"].append(prompt)
                return (text or {}).get(prompt, "")
            seen["sam"].append(prompt)
            return sam.pop(0)

        monkeypatch.setattr(scout.llm, "chat_json", chat_json)
        monkeypatch.setattr(scout.llm, "sam_raw", sam_raw)
        return seen
    return setup


def tree(box, kind="tree line"):
    return {"kind": kind, "box": box, "note": ""}


def area(polys):
    """m2 on the ground; the test mask is 10 pixels in 4 pieces, so count area, not polygons."""
    return gpd.GeoSeries(polys, crs=4326).to_crs(UTM).area.sum() if polys else 0


def test_wonder_boxes_become_tree_lines_and_text_prompts_the_rest(tile, models):
    seen = models([{"hazards": [tree([10, 20, 14, 24]), tree([40, 40, 44, 44], "woods")]}],
                  [sam_text((1, 10, 20), (2, 40, 40))],
                  {"building": sam_text((0, 20, 50)), "pond": sam_text((0, 50, 10))})
    out = scout.scout(tile)
    assert area(out["habitat"]) == pytest.approx(2000, abs=2)  # two masks, not two 25-pixel boxes
    assert area(out["building"]) == pytest.approx(1000, abs=1) and area(out["water"]) == pytest.approx(1000, abs=1)
    assert [w[:3] for w in seen["wonder"]] == [("find", "muse-wonder-1.0", "meta")]  # no review in the app
    assert "64 x 64 pixels" in seen["wonder"][0][3] and "10.0 m per pixel" in seen["wonder"][0][3]
    assert "box;x1=10;y1=20" in seen["sam"][0] and "box;x1=40;y1=40" in seen["sam"][0]
    assert sorted(seen["text"]) == sorted(segment.PHRASES["building"] + segment.PHRASES["water"])
    assert out["trace"] == ["Muse Wonder marked 2 tree lines and woods; SAM 3.1 outlined 2 of them",
                            "SAM 3.1 found 4 building and 4 possible water areas from text prompts"]  # the test mask is 4 pieces
    assert "draft" not in out


def test_review_drops_and_adds_and_keeps_the_draft(tile, models):
    seen = models([{"hazards": [tree([10, 20, 14, 24]), tree([40, 40, 44, 44])]},
                   {"keep": [2], "add": [tree([20, 50, 24, 54], "woods")]}],
                  [sam_text((1, 10, 20), (2, 40, 40)), sam_text((3, 20, 50))])
    out = scout.scout(tile, review=True)
    assert area(out["habitat"]) == pytest.approx(2000, abs=2)  # 2 kept from the first round, 3 added
    assert area(out["draft"]["habitat"]) == pytest.approx(2000, abs=2)  # 1 and 2, before the review
    assert "3<|box;x1=20;y1=50" in seen["sam"][1]
    assert out["trace"][2:] == ["Muse Wonder checked the outlines: kept 1, dropped 1",
                                "Muse Wonder marked 1 features it had missed; SAM 3.1 outlined 1"]


def test_review_cannot_keep_what_sam_never_outlined(tile, models):
    models([{"hazards": [tree([10, 20, 14, 24])]}, {"keep": [1, 7], "add": []}], [sam_text((1, 10, 20))])
    assert area(scout.scout(tile, review=True)["habitat"]) == pytest.approx(1000, abs=1)


def test_boxes_are_clamped_and_empty_ones_skipped(tile, models):
    seen = models([{"hazards": [tree([50, 50, 90, 99]), tree([30, 30, 30, 40])]}], [sam_text((1, 50, 50))])
    scout.scout(tile)
    assert "1<|box;x1=50;y1=50;x2=63;y2=63" in seen["sam"][0] and "2<|box" not in seen["sam"][0]


def test_low_confidence_masks_are_dropped(tile, models):
    weak = sam_text((1, 10, 20)).replace("|><|mask", ";c=0.2|><|mask").replace("8?|>", "8?;c=0.2|>")
    models([{"hazards": [tree([10, 20, 14, 24])]}], [weak])
    assert scout.scout(tile)["habitat"] == []


def test_no_trees_makes_no_box_call(tile, models):
    seen = models([{"hazards": []}], [])
    out = scout.scout(tile)
    assert seen["sam"] == [] and out["habitat"] == [] and out["trace"][0].startswith("Muse Wonder marked 0")


def test_more_than_16_boxes_go_in_batches(tile, models):
    seen = models([{"hazards": [tree([2 * i, 0, 2 * i + 1, 1]) for i in range(18)]}], [sam_text(), sam_text()])
    scout.scout(tile)
    assert len(seen["sam"]) == 2 and seen["sam"][0].count("<|box") == 16 and seen["sam"][1].count("<|box") == 2
