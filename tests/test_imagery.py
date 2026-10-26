import json
from datetime import datetime, timezone
from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pygeoogc.exceptions
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


def test_usgs_water(field_path, monkeypatch):
    pond = box(-93.0, 42.0, -92.999, 42.001)
    creek = LineString([(-93.0, 42.0), (-92.99, 42.01)])

    class FakeNHD:
        def __init__(self, layer):
            self.layer = layer

        def bygeom(self, bounds):
            if self.layer == "flowline_hr":
                raise pygeoogc.exceptions.ZeroMatchedError("none")
            return gpd.GeoDataFrame(geometry=[pond, None], crs=4326)

    monkeypatch.setattr(imagery.pynhd, "NHD", FakeNHD)
    assert imagery.usgs_water(field_path) == [pond]
    FakeNHD.bygeom = lambda self, b: gpd.GeoDataFrame(geometry=[pond if self.layer == "waterbody_hr" else creek], crs=4326)
    assert imagery.usgs_water(field_path) == [pond, creek]
