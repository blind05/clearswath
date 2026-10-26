"""Aerial imagery (NAIP via Planetary Computer) and USGS water features around a field."""

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import planetary_computer
import pygeoogc.exceptions
import pynhd
import rasterio
from PIL import Image
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

from app import geo

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
MARGIN_M = 150  # catch hazards just outside the field that a buffer reaches into
MAX_PX = 1024


def _bounds(field_path) -> tuple[float, float, float, float]:
    """Field bounds plus MARGIN_M, in lon/lat."""
    s = gpd.GeoSeries([geo.load_field(field_path)], crs=4326)
    utm = s.estimate_utm_crs()
    return tuple(s.to_crs(utm).buffer(MARGIN_M).to_crs(4326).total_bounds)


def _newest_naip(bounds):
    catalog = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = list(catalog.search(collections=["naip"], bbox=bounds).items())
    if not items:
        raise LookupError(f"No NAIP imagery covers {bounds}")
    # ponytail: newest single tile; fields straddling two NAIP tiles get clipped, mosaic if that bites
    return max(items, key=lambda i: i.datetime)


def fetch_tile(field_path, out_png) -> dict:
    """Writes out_png (RGB) and out_png.json (crs, transform, date, width, height). Returns the sidecar."""
    bounds = _bounds(field_path)
    item = _newest_naip(bounds)
    with rasterio.open(item.assets["image"].href) as src:
        window = from_bounds(*transform_bounds(4326, src.crs, *bounds), src.transform)
        window = window.round_offsets().round_lengths()
        scale = min(1.0, MAX_PX / max(window.width, window.height))
        width, height = max(1, round(window.width * scale)), max(1, round(window.height * scale))
        rgb = src.read([1, 2, 3], window=window, out_shape=(3, height, width),
                       boundless=True, resampling=Resampling.average)
        transform = src.window_transform(window) * Affine.scale(window.width / width,
                                                                window.height / height)
        crs = src.crs.to_string()

    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.moveaxis(rgb, 0, -1).astype(np.uint8)).save(out_png)
    meta = {"crs": crs, "transform": list(transform)[:6], "date": item.datetime.date().isoformat(),
            "width": width, "height": height}
    out_png.with_suffix(".json").write_text(json.dumps(meta))
    return meta


def usgs_water(field_path) -> list:
    """NHD high-res waterbodies (polygons) and flowlines (lines) near the field, in lon/lat."""
    bounds = _bounds(field_path)
    shapes = []
    for layer in ("waterbody_hr", "flowline_hr"):
        try:
            shapes += list(pynhd.NHD(layer).bygeom(bounds).geometry)
        except pygeoogc.exceptions.ZeroMatchedError:  # pynhd's own subclasses this
            pass  # nothing of that kind nearby
    return [s for s in shapes if s is not None and not s.is_empty]
