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
STREAM_BUFFER_M = 3  # flowlines become areas so they merge with the other water shapes


def _bounds(field_path, margin_m=MARGIN_M) -> tuple[float, float, float, float]:
    """Field bounds plus margin_m, in lon/lat."""
    s = gpd.GeoSeries([geo.load_field(field_path)], crs=4326)
    utm = s.estimate_utm_crs()
    return tuple(s.to_crs(utm).buffer(margin_m).to_crs(4326).total_bounds)


def _newest_naip(bounds):
    catalog = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = list(catalog.search(collections=["naip"], bbox=bounds).items())
    if not items:
        raise LookupError(f"No NAIP imagery covers {bounds}")
    # ponytail: newest single tile; fields straddling two NAIP tiles get clipped, mosaic if that bites
    return max(items, key=lambda i: i.datetime)


def fetch_tile(field_path, out_png, margin_m=MARGIN_M, max_px=MAX_PX) -> dict:
    """Writes out_png (RGB) and its .json sidecar (crs, transform, date, width, height). Returns the sidecar.

    Skips the download when both files already exist."""
    out_png = Path(out_png)
    sidecar = out_png.with_suffix(".json")
    if out_png.exists() and sidecar.exists():
        return json.loads(sidecar.read_text())
    bounds = _bounds(field_path, margin_m)
    item = _newest_naip(bounds)
    with rasterio.open(item.assets["image"].href) as src:
        window = from_bounds(*transform_bounds(4326, src.crs, *bounds), src.transform)
        window = window.round_offsets().round_lengths()
        scale = min(1.0, max_px / max(window.width, window.height))
        width, height = max(1, round(window.width * scale)), max(1, round(window.height * scale))
        rgb = src.read([1, 2, 3], window=window, out_shape=(3, height, width),
                       boundless=True, resampling=Resampling.average)
        transform = src.window_transform(window) * Affine.scale(window.width / width,
                                                                window.height / height)
        crs = src.crs.to_string()

    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.moveaxis(rgb, 0, -1).astype(np.uint8)).save(out_png)
    meta = {"crs": crs, "transform": list(transform)[:6], "date": item.datetime.date().isoformat(),
            "width": width, "height": height}
    sidecar.write_text(json.dumps(meta))
    return meta


def usgs_water(field_path) -> list:
    """NHD high-res waterbodies and flowlines near the field, as lon/lat areas (streams buffered).

    One layer failing doesn't stop the other; both failing raises, so an outage never reads as "no water".
    """
    bounds = _bounds(field_path)
    shapes, errors = [], []
    for layer in ("waterbody_hr", "flowline_hr"):
        try:
            shapes += list(pynhd.NHD(layer).bygeom(bounds).to_crs(4326).geometry)
        except pygeoogc.exceptions.ZeroMatchedError:  # pynhd's own subclasses this
            pass  # nothing of that kind nearby
        except Exception as e:
            errors.append(f"{layer}: {e}")
    if len(errors) == 2:
        raise RuntimeError(f"USGS water lookup failed: {'; '.join(errors)}")
    s = gpd.GeoSeries([g for g in shapes if g is not None and not g.is_empty], crs=4326)
    if s.empty:
        return []
    utm = s.estimate_utm_crs()
    lines = s.geom_type.isin(["LineString", "MultiLineString"])
    s[lines] = s[lines].to_crs(utm).buffer(STREAM_BUFFER_M).to_crs(4326)
    return list(s)
