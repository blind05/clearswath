"""Aerial imagery (NAIP via Planetary Computer) and USGS water features around a field."""

import json
import os
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
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry import box, shape

from app import geo

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
STAC_TIMEOUT_S = 30
# GDAL reads NAIP over HTTP; without these a stalled read has no time limit. Defaults only: env can override.
for _k, _v in {"GDAL_HTTP_TIMEOUT": "60", "GDAL_HTTP_CONNECTTIMEOUT": "15", "GDAL_HTTP_MAX_RETRY": "2",
               "GDAL_HTTP_RETRY_DELAY": "1"}.items():
    os.environ.setdefault(_k, _v)
MARGIN_M = 150  # catch hazards just outside the field that a buffer reaches into
MAX_PX = 1024
MAX_ITEMS = 8  # NAIP images tried when filling gaps (newest first)
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


def _naip_items(bounds) -> list:
    """NAIP images touching bounds: newest first, and on the same date the one covering more of bounds."""
    catalog = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace, timeout=STAC_TIMEOUT_S)
    items = list(catalog.search(collections=["naip"], bbox=bounds).items())
    if not items:
        raise NoImageryError(f"No NAIP imagery covers {bounds}")
    area = box(*bounds)

    def cover(i):
        return shape(i.geometry).intersection(area).area if getattr(i, "geometry", None) else 0

    return sorted(items, key=lambda i: (i.datetime, cover(i)), reverse=True)


def fetch_tile(field_path, out_png, margin_m=MARGIN_M, max_px=MAX_PX) -> dict:
    """Writes out_png (RGB) and its .json sidecar (crs, transform, date, dates, empty_fraction, width, height).

    The grid comes from the newest NAIP image; gaps (a field across an image edge) are filled from the
    next images, newest first. empty_fraction is what no image covered. Skips the download when cached."""
    out_png = Path(out_png)
    sidecar = out_png.with_suffix(".json")
    if out_png.exists() and sidecar.exists():
        return json.loads(sidecar.read_text())
    bounds = _bounds(field_path, margin_m)
    items = _naip_items(bounds)[:MAX_ITEMS]
    with rasterio.open(items[0].assets["image"].href) as src:
        crs = src.crs
        window = from_bounds(*transform_bounds(4326, crs, *bounds), src.transform)
        window = window.round_offsets().round_lengths()
        scale = min(1.0, max_px / max(window.width, window.height))
        width, height = max(1, round(window.width * scale)), max(1, round(window.height * scale))
        transform = src.window_transform(window) @ Affine.scale(window.width / width, window.height / height)

    rgb = np.zeros((3, height, width), dtype=np.uint8)
    filled = np.zeros((height, width), dtype=bool)
    dates = []
    for item in items:
        with rasterio.open(item.assets["image"].href) as src, \
                WarpedVRT(src, crs=crs, transform=transform, width=width, height=height,
                          resampling=Resampling.average) as vrt:
            data = vrt.read([1, 2, 3])
            # NAIP marks nothing as nodata; outside an image's footprint the pixels are just black
            valid = (vrt.dataset_mask() > 0) & (data.max(axis=0) > 0) & ~filled
            if not valid.any():
                continue
            rgb[:, valid] = data[:, valid]
            filled |= valid
            dates.append(item.datetime.date().isoformat())
        if filled.all():
            break

    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.moveaxis(rgb, 0, -1)).save(out_png)
    meta = {"crs": crs.to_string(), "transform": list(transform)[:6], "date": dates[0] if dates else None,
            "dates": dates, "empty_fraction": round(float(1 - filled.mean()), 4), "width": width, "height": height}
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
