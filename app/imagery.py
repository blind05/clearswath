"""Aerial imagery (NAIP via Planetary Computer) and USGS water features around a field."""

import json
from pathlib import Path

import geopandas as gpd
import httpx
import numpy as np
import planetary_computer
import rasterio
from PIL import Image
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry import shape

from app import geo

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
MARGIN_M = 150  # catch hazards just outside the field that a buffer reaches into
MAX_PX = 1024
STREAM_BUFFER_M = 3  # flowlines become areas so they merge with the other water shapes
NHD = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer"
NHD_LAYERS = {"waterbody_hr": 12, "flowline_hr": 6}  # Waterbody / Flowline - Large Scale


class NoImageryError(LookupError):
    """No NAIP tile covers the field; the message is safe to show users."""


def _bounds(field_path, margin_m=MARGIN_M) -> tuple[float, float, float, float]:
    """Field bounds plus margin_m, in lon/lat."""
    s = gpd.GeoSeries([geo.load_field(field_path)], crs=4326)
    utm = s.estimate_utm_crs()
    return tuple(s.to_crs(utm).buffer(margin_m).to_crs(4326).total_bounds)


def _newest_naip(bounds):
    catalog = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = list(catalog.search(collections=["naip"], bbox=bounds).items())
    if not items:
        raise NoImageryError(f"No NAIP imagery covers {bounds}")
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


def _nhd_query(layer: str, bounds) -> list:
    """All features of one NHD layer intersecting bounds, as lon/lat shapes. Raises on any service error."""
    params = {"geometry": ",".join(map(str, bounds)), "geometryType": "esriGeometryEnvelope", "inSR": 4326,
              "spatialRel": "esriSpatialRelIntersects", "outSR": 4326, "outFields": "ftype",
              "returnGeometry": "true", "orderByFields": "OBJECTID", "f": "geojson"}  # stable paging
    shapes, offset = [], 0
    while True:
        r = httpx.get(f"{NHD}/{NHD_LAYERS[layer]}/query", params=params | {"resultOffset": offset},
                      timeout=120)  # cold queries on this USGS server can take ~1 min
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise ValueError(f"NHD error: {data['error']}")
        page = data["features"]
        shapes += [shape(f["geometry"]) for f in page if f.get("geometry")]
        more = data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit")
        if not (more and page):
            return shapes
        offset += len(page)


def usgs_water(field_path, failed: list | None = None) -> list:
    """NHD high-res waterbodies and flowlines near the field, as lon/lat areas (streams buffered).

    One layer failing doesn't stop the other; its name is appended to `failed` so callers can warn.
    Both failing raises, so an outage never reads as "no water".
    """
    bounds = _bounds(field_path)
    shapes, errors = [], []
    for layer in NHD_LAYERS:
        try:
            shapes += _nhd_query(layer, bounds)
        except (httpx.HTTPError, ValueError, KeyError) as e:  # an outage must never read as "no water"
            errors.append(f"{layer}: {e}")
            if failed is not None:
                failed.append(layer)
    if len(errors) == 2:
        raise RuntimeError(f"USGS water lookup failed: {'; '.join(errors)}")
    s = gpd.GeoSeries([g for g in shapes if g is not None and not g.is_empty], crs=4326)
    if s.empty:
        return []
    utm = s.estimate_utm_crs()
    lines = s.geom_type.isin(["LineString", "MultiLineString"])
    s[lines] = s[lines].to_crs(utm).buffer(STREAM_BUFFER_M).to_crs(4326)
    return list(s)
