import json

import geopandas as gpd
import pytest
from shapely.geometry import box

from app import imagery, scout, segment

UTM = 32615
X, Y = 500_000, 4_650_000
# 1 m pixels, tile's top-left corner at (X, Y)
META = {"crs": f"EPSG:{UTM}", "transform": [1, 0, X, 0, -1, Y], "date": "2023-07-09",
        "width": 64, "height": 64}
# 5x5 one_bit mask with 10 set pixels, box at pixel (10, 20)
SAM_TEXT = "<0f>0<|box;x1=10;y1=20;x2=14;y2=24;w=64;h=64|><|mask;x=0;y=0;data=5,5,!!!!!(QO(0lu8?|>\n"
# Sample from Meta's parser docs: 60x27 mask at pixel (211, 228) on a 320x334 image
DOC_TEXT = ("<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|><|mask;x=0;y=0;"
            "data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>\n")


def small(text=SAM_TEXT, width=64, **kw):
    kw = {"min_area": 0, "simplify": 0, **kw}
    return segment.masks_to_polygons(text, width, 64, META["transform"], META["crs"], **kw)


def test_polygons_land_on_the_box():
    polys = gpd.GeoSeries(small(), crs=4326).to_crs(UTM)
    assert polys.area.sum() == pytest.approx(10, abs=0.01)
    minx, miny, maxx, maxy = polys.total_bounds
    assert (minx, maxy) == pytest.approx((X + 10, Y - 20), abs=0.01)
    assert (maxx, miny) == pytest.approx((X + 15, Y - 25), abs=0.01)


def test_mask_clipped_at_tile_edge():
    polys = gpd.GeoSeries(small(width=12), crs=4326).to_crs(UTM)
    assert polys.total_bounds[2] <= X + 12 + 0.01 and polys.area.sum() < 10


def test_min_area_drops_specks():
    assert small(min_area=50) == []


def test_meta_doc_sample():
    polys = segment.masks_to_polygons(DOC_TEXT, 320, 334, [1, 0, 650000, 0, -1, 4910000], "EPSG:32614")
    assert polys
    for p in polys:
        minx, miny, maxx, maxy = p.bounds
        assert -98 <= minx <= maxx <= -96 and 43 <= miny <= maxy <= 45


def test_empty_text():
    assert segment.masks_to_polygons("", 64, 64, META["transform"], META["crs"]) == []


def test_segment_tile_reads_sidecar(tmp_path, monkeypatch):
    png = tmp_path / "tile.png"
    png.write_bytes(b"png")
    png.with_suffix(".json").write_text(json.dumps(META))
    seen = []

    def sam_raw(p, phrase, purpose):
        seen.append((p, phrase, purpose))
        return SAM_TEXT

    monkeypatch.setattr(segment.llm, "sam_raw", sam_raw)
    assert segment.segment_tile(png, "pond", min_area=0)
    assert seen == [(png, "pond", "segment:pond")]


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

    scouted_pond, shelterbelt = box(-93.0005, 42.0, -93.0, 42.0005), box(-93.002, 42.0, -93.001, 42.0002)

    def scout_tile(png):
        calls.append("scout")
        return {"water": [scouted_pond], "building": [], "habitat": [shelterbelt], "trace": ["Muse Wonder marked 2"]}

    pond = box(-93.0, 42.0, -92.999, 42.001)

    def usgs(fp, failed):
        calls.append("usgs")
        return [pond]

    monkeypatch.setattr(imagery, "fetch_tile", fetch_tile)
    monkeypatch.setattr(imagery, "usgs_water", usgs)
    monkeypatch.setattr(scout, "scout", scout_tile)

    out = segment.find_hazards(field)
    assert out["water_source"] == "usgs" and out["imagery_date"] == "2023-07-09"
    assert len(out["water"]) == 1 and out["water"][0].equals(pond)  # the scout's pond is only possible water
    assert out["possible_water"][0].equals(scouted_pond)
    assert out["habitat"][0].equals(shelterbelt) and out["building"] == [] and out["water_warnings"] == []
    assert out["scout_trace"] == ["Muse Wonder marked 2"] and out["imagery_warnings"] == []
    assert calls == ["tile", "scout", "usgs"]

    calls.clear()
    again = segment.find_hazards(field)
    assert calls == [] and again["water_source"] == "usgs"
    assert again["possible_water"][0].equals(scouted_pond) and again["habitat"][0].equals(shelterbelt)


def test_failed_scout_warns_and_is_not_cached(tmp_path, monkeypatch):
    field = tmp_path / "field.geojson"
    field.write_text(json.dumps({"type": "Polygon", "coordinates": [[[-93, 42], [-93, 42.01],
                                                                      [-92.99, 42.01], [-93, 42]]]}))
    monkeypatch.setattr(segment, "CACHE", tmp_path / "cache")

    def fetch_tile(fp, png):
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(b"png")
        png.with_suffix(".json").write_text(json.dumps(META))

    calls = []

    def broken(png):
        calls.append("scout")
        raise TimeoutError("Wonder timed out")

    monkeypatch.setattr(imagery, "fetch_tile", fetch_tile)
    monkeypatch.setattr(imagery, "usgs_water", lambda fp, failed: [])
    monkeypatch.setattr(scout, "scout", broken)
    out = segment.find_hazards(field)
    assert out["habitat"] == out["building"] == out["water"] == out["possible_water"] == []
    assert out["water_source"] == "none"
    (w,) = out["imagery_warnings"]
    assert "couldn't check the aerial imagery" in w and "Check the field" in w
    segment.find_hazards(field)
    assert calls == ["scout", "scout"]  # retried, not cached as "nothing found"


def test_partial_usgs_warns_and_is_not_cached(tmp_path, monkeypatch):
    field = tmp_path / "field.geojson"
    field.write_text(json.dumps({"type": "Polygon", "coordinates": [[[-93, 42], [-93, 42.01],
                                                                      [-92.99, 42.01], [-93, 42]]]}))
    monkeypatch.setattr(segment, "CACHE", tmp_path / "cache")

    def fetch_tile(fp, png):
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(b"png")
        png.with_suffix(".json").write_text(json.dumps(META))

    monkeypatch.setattr(imagery, "fetch_tile", fetch_tile)
    monkeypatch.setattr(scout, "scout", lambda png: {"water": [], "building": [], "habitat": [], "trace": []})
    calls = []

    def usgs(fp, failed):
        calls.append("usgs")
        failed.append("waterbody_hr")
        return []

    monkeypatch.setattr(imagery, "usgs_water", usgs)
    out = segment.find_hazards(field)
    assert len(out["water_warnings"]) == 1 and "pond and lake" in out["water_warnings"][0]
    segment.find_hazards(field)
    assert calls == ["usgs", "usgs"]  # retried, not served from cache


def test_imagery_gap_becomes_a_warning(tmp_path, monkeypatch):
    field = tmp_path / "field.geojson"
    field.write_text(json.dumps({"type": "Polygon", "coordinates": [[[-93, 42], [-93, 42.01],
                                                                      [-92.99, 42.01], [-93, 42]]]}))
    monkeypatch.setattr(segment, "CACHE", tmp_path / "cache")

    def fetch_tile(fp, png):
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(b"png")
        png.with_suffix(".json").write_text(json.dumps(META | {"empty_fraction": 0.37}))

    monkeypatch.setattr(imagery, "fetch_tile", fetch_tile)
    monkeypatch.setattr(scout, "scout", lambda png: {"water": [], "building": [], "habitat": [], "trace": []})
    monkeypatch.setattr(imagery, "usgs_water", lambda fp, failed: [])
    (w,) = segment.find_hazards(field)["imagery_warnings"]
    assert "missing for 37%" in w
