import json
from datetime import datetime, timezone
from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import httpx
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin
from shapely.geometry import LineString, box, mapping

from app import imagery

UTM = 32615
X, Y = 500_000, 4_650_000
FIELD_M = box(X, Y, X + 400, Y + 400)


@pytest.fixture
def field_path(tmp_path):
    p = tmp_path / "field.geojson"
    p.write_text(json.dumps(mapping(gpd.GeoSeries([FIELD_M], crs=UTM).to_crs(4326)[0])))
    return p


@pytest.fixture
def naip(tmp_path, monkeypatch):
    """A 1 m, 4-band GeoTIFF covering the field plus 1 km, served as the only NAIP item."""
    tif = tmp_path / "naip.tif"
    size = 2400
    with rasterio.open(tif, "w", driver="GTiff", width=size, height=size, count=4, dtype="uint8",
                       crs=f"EPSG:{UTM}", transform=from_origin(X - 1000, Y + 1400, 1, 1)) as dst:
        dst.write(np.full((4, size, size), 120, dtype=np.uint8))
    old = SimpleNamespace(datetime=datetime(2021, 6, 1, tzinfo=timezone.utc), assets={})
    new = SimpleNamespace(datetime=datetime(2023, 7, 9, tzinfo=timezone.utc),
                          assets={"image": SimpleNamespace(href=str(tif))})
    search = SimpleNamespace(items=lambda: iter([old, new]))
    monkeypatch.setattr(imagery.Client, "open", lambda *a, **kw: SimpleNamespace(search=lambda **kw: search))


def test_bounds_include_margin(field_path):
    b = gpd.GeoSeries([box(*imagery._bounds(field_path))], crs=4326).to_crs(UTM).total_bounds
    assert b[0] == pytest.approx(X - imagery.MARGIN_M, abs=2)
    assert b[3] == pytest.approx(Y + 400 + imagery.MARGIN_M, abs=2)


def test_fetch_tile(field_path, naip, tmp_path):
    out = tmp_path / "tiles" / "f.png"
    meta = imagery.fetch_tile(field_path, out)
    assert json.loads(out.with_suffix(".json").read_text()) == meta
    assert meta["date"] == "2023-07-09" and meta["crs"] == f"EPSG:{UTM}"
    # ~700 m window at 1 m is shrunk to fit MAX_PX, so pixels grow past 1 m
    assert max(meta["width"], meta["height"]) <= imagery.MAX_PX
    a, _, c, _, e, f = meta["transform"]
    assert a == pytest.approx(-e) and a > 0.5
    assert c == pytest.approx(X - imagery.MARGIN_M, abs=3)
    assert f == pytest.approx(Y + 400 + imagery.MARGIN_M, abs=3)
    # the far corner pixel lands at the far corner of the bounds
    assert c + a * meta["width"] == pytest.approx(X + 400 + imagery.MARGIN_M, abs=3)
    assert Image.open(out).size == (meta["width"], meta["height"])


def test_fetch_tile_no_imagery(field_path, monkeypatch):
    empty = SimpleNamespace(items=lambda: iter([]))
    monkeypatch.setattr(imagery.Client, "open", lambda *a, **kw: SimpleNamespace(search=lambda **kw: empty))
    with pytest.raises(LookupError):
        imagery.fetch_tile(field_path, "unused.png")


def test_fetch_tile_max_px_and_skip(field_path, naip, tmp_path, monkeypatch):
    out = tmp_path / "f.png"
    meta = imagery.fetch_tile(field_path, out, max_px=200)
    assert max(meta["width"], meta["height"]) == 200
    monkeypatch.setattr(imagery.Client, "open", lambda *a, **kw: pytest.fail("refetched"))
    assert imagery.fetch_tile(field_path, out) == meta


POND = box(-93.0, 42.0, -92.999, 42.001)
CREEK = LineString([(-93.0, 42.0), (-92.99, 42.01)])


def fc(*geoms, more=False):
    out = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": mapping(g) if g else None,
                                                      "properties": {}} for g in geoms]}
    if more:
        out["properties"] = {"exceededTransferLimit": True}
    return out


def fake_nhd(monkeypatch, results):
    """results: layer name -> list of pages (dict = JSON body, int = HTTP status, Exception = raised)."""
    calls = []

    def get(url, params=None, timeout=None):
        layer = next(k for k, v in imagery.NHD_LAYERS.items() if url.endswith(f"/{v}/query"))
        calls.append((layer, params["resultOffset"]))
        pages = results[layer]
        r = pages[min(len([c for c in calls if c[0] == layer]) - 1, len(pages) - 1)]
        if isinstance(r, Exception):
            raise r
        req = httpx.Request("GET", url)
        return httpx.Response(r, request=req) if isinstance(r, int) else httpx.Response(200, json=r, request=req)

    monkeypatch.setattr(imagery.httpx, "get", get)
    return calls


def test_usgs_water(field_path, monkeypatch):
    calls = fake_nhd(monkeypatch, {"waterbody_hr": [fc(POND, None)], "flowline_hr": [fc()]})
    assert imagery.usgs_water(field_path) == [POND]
    assert calls == [("waterbody_hr", 0), ("flowline_hr", 0)]


def test_usgs_water_streams_become_areas(field_path, monkeypatch):
    fake_nhd(monkeypatch, {"waterbody_hr": [fc(POND)], "flowline_hr": [fc(CREEK)]})
    pond, creek = imagery.usgs_water(field_path)
    assert pond == POND
    assert creek.geom_type == "Polygon" and creek.contains(CREEK.interpolate(0.5, normalized=True))
    utm = gpd.GeoSeries([creek, CREEK], crs=4326).to_crs(gpd.GeoSeries([CREEK], crs=4326).estimate_utm_crs())
    assert utm[0].area / utm[1].length == pytest.approx(2 * imagery.STREAM_BUFFER_M, rel=0.05)


def test_usgs_water_pages(field_path, monkeypatch):
    calls = fake_nhd(monkeypatch, {"waterbody_hr": [fc(POND, more=True), fc(POND)], "flowline_hr": [fc()]})
    assert len(imagery.usgs_water(field_path)) == 2
    assert calls == [("waterbody_hr", 0), ("waterbody_hr", 1), ("flowline_hr", 0)]


@pytest.mark.parametrize("down", [httpx.ConnectError("no route"), 503, {"error": {"code": 400, "message": "bad"}}])
def test_usgs_water_one_layer_down(field_path, monkeypatch, down):
    fake_nhd(monkeypatch, {"waterbody_hr": [down], "flowline_hr": [fc(CREEK)]})
    failed = []
    [creek] = imagery.usgs_water(field_path, failed)
    assert creek.geom_type == "Polygon" and failed == ["waterbody_hr"]
    assert len(imagery.usgs_water(field_path)) == 1  # failed is optional


def test_usgs_water_both_down_raises(field_path, monkeypatch):
    fake_nhd(monkeypatch, {"waterbody_hr": [503], "flowline_hr": [{"error": {"code": 500}}]})
    with pytest.raises(RuntimeError, match=r"(?s)waterbody_hr.*flowline_hr"):
        imagery.usgs_water(field_path)


def test_usgs_water_empty_is_really_empty(field_path, monkeypatch):
    fake_nhd(monkeypatch, {"waterbody_hr": [fc()], "flowline_hr": [fc()]})
    failed = []
    assert imagery.usgs_water(field_path, failed) == [] and failed == []


def serve(monkeypatch, *items):
    search = SimpleNamespace(items=lambda: iter(items))
    monkeypatch.setattr(imagery.Client, "open", lambda *a, **kw: SimpleNamespace(search=lambda **kw: search))


def item(year, href):
    return SimpleNamespace(datetime=datetime(year, 7, 1, tzinfo=timezone.utc),
                           assets={"image": SimpleNamespace(href=str(href))})


@pytest.fixture
def halves(tmp_path):
    """West-only newer image (value 200, UTM) and a whole-area older image (value 50, lon/lat)."""
    west = tmp_path / "west.tif"
    with rasterio.open(west, "w", driver="GTiff", width=600, height=2400, count=4, dtype="uint8", nodata=0,
                       crs=f"EPSG:{UTM}", transform=from_origin(X - 400, Y + 1400, 1, 1)) as dst:
        dst.write(np.full((4, 2400, 600), 200, dtype=np.uint8))  # covers x up to X + 200: the west half
    whole = tmp_path / "whole.tif"
    w, s_, e, n = gpd.GeoSeries([box(X - 1000, Y - 1000, X + 1400, Y + 1400)], crs=UTM).to_crs(4326).total_bounds
    with rasterio.open(whole, "w", driver="GTiff", width=1200, height=1200, count=4, dtype="uint8", nodata=0,
                       crs="EPSG:4326", transform=from_origin(w, n, (e - w) / 1200, (n - s_) / 1200)) as dst:
        dst.write(np.full((4, 1200, 1200), 50, dtype=np.uint8))
    return west, whole


def test_fetch_tile_fills_gaps_from_older_image(field_path, halves, tmp_path, monkeypatch):
    west, whole = halves
    serve(monkeypatch, item(2021, whole), item(2023, west))
    out = tmp_path / "t.png"
    meta = imagery.fetch_tile(field_path, out)
    a = np.asarray(Image.open(out))
    assert meta["empty_fraction"] == 0 and meta["dates"] == ["2023-07-01", "2021-07-01"]
    assert meta["date"] == "2023-07-01" and meta["crs"] == f"EPSG:{UTM}"
    assert a[:, 5, 0].min() == 200 and a[:, -5, 0].max() == 50  # west from the newer, east from the older


def test_fetch_tile_reports_what_no_image_covers(field_path, halves, tmp_path, monkeypatch):
    west, _ = halves
    serve(monkeypatch, item(2023, west))
    meta = imagery.fetch_tile(field_path, tmp_path / "t.png")
    assert meta["dates"] == ["2023-07-01"]
    assert meta["empty_fraction"] == pytest.approx(0.5, abs=0.05)


def test_black_pixels_without_nodata_count_as_gaps(field_path, halves, tmp_path, monkeypatch):
    """Real NAIP: no nodata value; outside the footprint the pixels are simply 0."""
    _, whole = halves
    blackeast = tmp_path / "blackeast.tif"
    data = np.full((4, 2400, 2400), 200, dtype=np.uint8)
    data[:, :, 1200:] = 0  # east of X + 200 is black
    with rasterio.open(blackeast, "w", driver="GTiff", width=2400, height=2400, count=4, dtype="uint8",
                       crs=f"EPSG:{UTM}", transform=from_origin(X - 1000, Y + 1400, 1, 1)) as dst:
        dst.write(data)
    serve(monkeypatch, item(2023, blackeast))
    assert imagery.fetch_tile(field_path, tmp_path / "a.png")["empty_fraction"] == pytest.approx(0.5, abs=0.05)
    serve(monkeypatch, item(2023, blackeast), item(2021, whole))
    meta = imagery.fetch_tile(field_path, tmp_path / "b.png")
    assert meta["empty_fraction"] == 0 and meta["dates"] == ["2023-07-01", "2021-07-01"]


def test_same_date_prefers_the_image_covering_more(field_path, monkeypatch):
    bounds = imagery._bounds(field_path)
    w, s_, e, n = bounds
    part = SimpleNamespace(datetime=datetime(2022, 8, 3, tzinfo=timezone.utc), id="se",
                           geometry=mapping(box(w, s_, e, (s_ + n) / 2)))
    full = SimpleNamespace(datetime=datetime(2022, 8, 3, tzinfo=timezone.utc), id="ne",
                           geometry=mapping(box(w - 1, s_ - 1, e + 1, n + 1)))
    older = SimpleNamespace(datetime=datetime(2021, 8, 3, tzinfo=timezone.utc), id="old",
                            geometry=mapping(box(w - 1, s_ - 1, e + 1, n + 1)))
    serve(monkeypatch, part, older, full)
    assert [i.id for i in imagery._naip_items(bounds)] == ["ne", "se", "old"]


def test_outbound_imagery_calls_have_timeouts(field_path, monkeypatch):
    import os

    seen = {}
    monkeypatch.setattr(imagery.Client, "open", lambda *a, **kw: seen.update(kw) or SimpleNamespace(
        search=lambda **kw: SimpleNamespace(items=lambda: iter([item(2023, "x.tif")]))))
    imagery._naip_items(imagery._bounds(field_path))
    assert seen["timeout"] == imagery.STAC_TIMEOUT_S
    assert os.environ["GDAL_HTTP_TIMEOUT"] and os.environ["GDAL_HTTP_CONNECTTIMEOUT"]
