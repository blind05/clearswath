import json

import geopandas as gpd
import pytest
from meta_sam_parser import CompletedOutcome, image_segmentation_format
from shapely.geometry import box

from app import imagery, llm, segment

UTM = 32615
X, Y = 500_000, 4_650_000
# 1 m pixels, tile's top-left corner at (X, Y)
META = {"crs": f"EPSG:{UTM}", "transform": [1, 0, X, 0, -1, Y], "date": "2023-07-09",
        "width": 64, "height": 64}
# 5x5 one_bit mask with 10 set pixels, box at pixel (10, 20)
SAM_TEXT = "<0f>0<|box;x1=10;y1=20;x2=14;y2=24;w=64;h=64|><|mask;x=0;y=0;data=5,5,!!!!!(QO(0lu8?|>\n"


def masks():
    p = image_segmentation_format().create_parser()
    p.push(SAM_TEXT)
    return [r for r in p.finish(CompletedOutcome()).result.records if r.kind == "mask"]


def test_polygons_land_on_the_box():
    polys = gpd.GeoSeries(segment._polygons(masks(), META), crs=4326).to_crs(UTM)
    assert polys.area.sum() == pytest.approx(10, abs=0.01)
    minx, miny, maxx, maxy = polys.total_bounds
    assert (minx, maxy) == pytest.approx((X + 10, Y - 20), abs=0.01)
    assert (maxx, miny) == pytest.approx((X + 15, Y - 25), abs=0.01)


def test_polygons_empty():
    assert segment._polygons([], META) == []


def test_find_hazards_merges_and_caches(tmp_path, monkeypatch):
    field = tmp_path / "field.geojson"
    field.write_text(json.dumps({"type": "Polygon", "coordinates": [[[-93, 42], [-93, 42.01],
                                                                      [-92.99, 42.01], [-93, 42]]]}))
    monkeypatch.setattr(segment, "CACHE", tmp_path / "cache")
    calls = []

    def fetch_tile(fp, png):
        calls.append("tile")
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(b"png")
        png.with_suffix(".json").write_text(json.dumps(META))

    def sam(png, phrase, purpose):
        calls.append(purpose)
        return masks() if purpose == "segment:water" else []

    pond = box(-93.0, 42.0, -92.999, 42.001)

    def usgs(fp):
        calls.append("usgs")
        return [pond]

    monkeypatch.setattr(imagery, "fetch_tile", fetch_tile)
    monkeypatch.setattr(imagery, "usgs_water", usgs)
    monkeypatch.setattr(llm, "segment", sam)

    out = segment.find_hazards(field)
    assert out["water_source"] == "usgs+sam" and out["imagery_date"] == "2023-07-09"
    assert out["water"][0].equals(pond) and len(out["water"]) > 1
    assert out["building"] == [] and out["habitat"] == []
    assert calls.count("tile") == 1 and calls.count("usgs") == 1 and len(calls) == 5

    calls.clear()
    again = segment.find_hazards(field)
    assert calls == [] and again["water_source"] == "usgs+sam"
    assert len(again["water"]) == len(out["water"])
