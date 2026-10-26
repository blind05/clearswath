"""Field -> hazard shapes (water, building, habitat) from SAM on aerial imagery plus USGS water."""

import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
from meta_sam_parser import decode_mask_to_raster
from rasterio.features import shapes
from rasterio.transform import Affine
from shapely.geometry import shape

from app import geo, imagery, llm

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
PHRASES = {
    "water": "pond, lake, stream or river",
    "building": "house or building",
    "habitat": "forest or wetland",
}


def _polygons(masks: list, meta: dict) -> list:
    """SAM mask records (pixel coords on the tile) -> polygons in lon/lat."""
    tile = Affine(*meta["transform"])
    polys = []
    for rec in masks:
        m = rec.mask
        raster = np.frombuffer(decode_mask_to_raster(m), dtype=np.uint8).reshape(m.height, m.width)
        # Masks are cropped to their box; place them at the box corner.
        # TODO(verify): assumes SAM reports pixels of the PNG as sent, not a resized frame
        t = tile * Affine.translation(rec.bounds.left, rec.bounds.top)
        polys += [shape(g) for g, _ in shapes(raster, mask=raster == 1, transform=t)]
    if not polys:
        return []
    return list(gpd.GeoSeries(polys, crs=meta["crs"]).to_crs(4326))


def find_hazards(field_path) -> dict:
    """Hazard shapes near the field. Cached per field and hazard in data/cache/<field hash>/."""
    key = hashlib.sha1(Path(field_path).read_bytes()).hexdigest()[:12]
    cache = CACHE / key
    png = cache / "tile.png"

    def cached(name, compute):
        path = cache / f"{name}.geojson"
        if not path.exists():
            geo.save_shapes(compute(), path)
        return geo.load_shapes(path)

    def sam(hazard):
        if not png.exists():
            imagery.fetch_tile(field_path, png)
        meta = json.loads(png.with_suffix(".json").read_text())
        return _polygons(llm.segment(png, PHRASES[hazard], purpose=f"segment:{hazard}"), meta)

    out = {h: cached(h, lambda h=h: sam(h)) for h in PHRASES}
    usgs = cached("water_usgs", lambda: imagery.usgs_water(field_path))
    out["water_source"] = "+".join(n for n, s in (("usgs", usgs), ("sam", out["water"])) if s) or "none"
    out["water"] = usgs + out["water"]
    sidecar = png.with_suffix(".json")
    out["imagery_date"] = json.loads(sidecar.read_text())["date"] if sidecar.exists() else None
    return out
