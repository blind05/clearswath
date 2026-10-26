"""Field -> hazard shapes (water, building, habitat) from SAM on aerial imagery plus USGS water."""

import hashlib
import json
from pathlib import Path

import numpy as np
from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, image_segmentation_format
from rasterio.features import shapes
from rasterio.transform import Affine
from rasterio.warp import transform_geom
from shapely.geometry import mapping, shape

from app import geo, imagery, llm

USGS_LAYERS = {"waterbody_hr": "pond and lake", "flowline_hr": "stream"}
CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
# One noun phrase per SAM request; a list in one phrase matches nothing.
PHRASES = {
    "water": ["pond", "creek", "river"],
    "building": ["building"],
    "habitat": ["tree line"],
}


def masks_to_polygons(text: str, width: int, height: int, transform, crs, min_area=50,
                      simplify=0.5, min_confidence=0.0) -> list:
    """SAM output text (pixel coords on the tile) -> polygons in lon/lat.

    min_area and simplify are in tile CRS units (square meters / meters for NAIP in UTM).
    """
    parser = image_segmentation_format().create_parser()
    parser.push(text)
    tile = Affine(*transform)
    polys = []
    for rec in parser.finish(CompletedOutcome()).result.records:
        if rec.kind != "mask" or (rec.confidence is not None and rec.confidence < min_confidence):
            continue
        m, top, left = rec.mask, rec.bounds.top, rec.bounds.left
        # TODO(verify): assumes SAM reports pixels of the PNG as sent, not a resized frame
        crop = np.frombuffer(decode_mask_to_raster(m), dtype=np.uint8).reshape(m.height, m.width)
        canvas = np.zeros((height, width), dtype=np.uint8)
        r0, c0 = max(top, 0), max(left, 0)
        r1, c1 = min(top + m.height, height), min(left + m.width, width)
        if r1 <= r0 or c1 <= c0:
            continue
        canvas[r0:r1, c0:c1] = crop[r0 - top:r1 - top, c0 - left:c1 - left]
        for g, _ in shapes(canvas, mask=canvas == 1, transform=tile):
            p = shape(g)
            if p.area >= min_area:
                polys.append(shape(transform_geom(crs, "EPSG:4326", mapping(p.simplify(simplify)))))
    return polys


def segment_tile(png, phrase: str, **kw) -> list:
    """One SAM call for one phrase on a tile from imagery.fetch_tile -> lon/lat polygons."""
    meta = json.loads(Path(png).with_suffix(".json").read_text())
    text = llm.sam_raw(png, phrase, purpose=f"segment:{phrase}")
    return masks_to_polygons(text, meta["width"], meta["height"], meta["transform"], meta["crs"], **kw)


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
        return [p for phrase in PHRASES[hazard] for p in segment_tile(png, phrase)]

    out = {h: cached(h, lambda h=h: sam(h)) for h in PHRASES}
    usgs_path, failed = cache / "water_usgs.geojson", []
    if usgs_path.exists():
        usgs = geo.load_shapes(usgs_path)
    else:
        usgs = imagery.usgs_water(field_path, failed)
        if not failed:  # a partial answer is not cached, so the next run retries it
            geo.save_shapes(usgs, usgs_path)
    out["water_warnings"] = [f"USGS {USGS_LAYERS[layer]} data was unavailable, so {USGS_LAYERS[layer]} "
                             "may be missing from the map. Check the field before spraying."
                             for layer in failed]
    out["water_source"] = "+".join(n for n, s in (("usgs", usgs), ("sam", out["water"])) if s) or "none"
    out["water"] = usgs + out["water"]
    sidecar = png.with_suffix(".json")
    out["imagery_date"] = json.loads(sidecar.read_text())["date"] if sidecar.exists() else None
    return out
