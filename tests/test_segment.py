import json

import geopandas as gpd
import pytest
from shapely.geometry import box

from app import imagery, segment

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

    sam_pond = box(-93.0005, 42.0, -93.0, 42.0005)

    def segment_tile(png, phrase):
        calls.append(phrase)
        return [sam_pond] if phrase == "pond" else []

    pond = box(-93.0, 42.0, -92.999, 42.001)

    def usgs(fp, failed):
        calls.append("usgs")
        return [pond]

    monkeypatch.setattr(imagery, "fetch_tile", fetch_tile)
    monkeypatch.setattr(imagery, "usgs_water", usgs)
    monkeypatch.setattr(segment, "segment_tile", segment_tile)

    out = segment.find_hazards(field)
    assert out["water_source"] == "usgs+sam" and out["imagery_date"] == "2023-07-09"
    assert out["water"][0].equals(pond) and out["water"][1].equals(sam_pond)
    assert out["building"] == [] and out["habitat"] == [] and out["water_warnings"] == []
    phrases = [p for ps in segment.PHRASES.values() for p in ps]
    assert calls == ["tile", *phrases, "usgs"]

    calls.clear()
    again = segment.find_hazards(field)
    assert calls == [] and again["water_source"] == "usgs+sam"
    assert len(again["water"]) == 2


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
    monkeypatch.setattr(segment, "segment_tile", lambda png, phrase: [])
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
