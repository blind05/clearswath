"""Field -> hazard shapes (water, building, habitat): USGS water plus Muse Wonder and SAM 3.1 on aerial imagery."""

import hashlib
import json
import logging
from pathlib import Path

import numpy as np
from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, image_segmentation_format
from rasterio.features import shapes
from rasterio.transform import Affine
from rasterio.warp import transform_geom
from shapely.geometry import mapping, shape

from app import geo, imagery, llm, scout

USGS_LAYERS = {"waterbody_hr": "pond and lake", "flowline_hr": "stream"}
CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
log = logging.getLogger(__name__)
# SAM text prompts, one noun phrase per request. scout.py uses the building and water ones (77% of buildings, open
# water at 95% precision on 20 NAIP tiles); "tree line" finds 8% of trees, so Wonder's boxes do that job and it
# stays only as the eval's baseline (evals/results_scout.md).
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
    return [p for rec in parser.finish(CompletedOutcome()).result.records
            if rec.kind == "mask" and (rec.confidence is None or rec.confidence >= min_confidence)
            for p in record_polygons(rec, width, height, transform, crs, min_area, simplify)]


def record_polygons(rec, width: int, height: int, transform, crs, min_area=50, simplify=0.5) -> list:
    """One parsed SAM mask record -> polygons in lon/lat (min_area and simplify in tile CRS units)."""
    m, top, left = rec.mask, rec.bounds.top, rec.bounds.left
    # SAM reports pixels of the image as sent (checked 2026-10-29: box prompts come back at the same coordinates)
    crop = np.frombuffer(decode_mask_to_raster(m), dtype=np.uint8).reshape(m.height, m.width)
    canvas = np.zeros((height, width), dtype=np.uint8)
    r0, c0 = max(top, 0), max(left, 0)
    r1, c1 = min(top + m.height, height), min(left + m.width, width)
    if r1 <= r0 or c1 <= c0:
        return []
    canvas[r0:r1, c0:c1] = crop[r0 - top:r1 - top, c0 - left:c1 - left]
    polys = []
    for g, _ in shapes(canvas, mask=canvas == 1, transform=Affine(*transform)):
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
    """Hazard shapes near the field: USGS water, plus what Muse Wonder and SAM 3.1 find on the aerial tile.

    Cached per field in data/cache/<field hash>/. A failed scout or a partial USGS answer is not cached, so the next
    run retries it.
    """
    cache = _cache_dir(field_path)
    png = cache / "tile.png"
    out, scout_warnings = scout_field(field_path)
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
    out["water_source"] = "usgs" if usgs else "none"
    out["water"] = usgs  # water the scout saw is out["possible_water"]: checked by a person, not cut out
    meta = json.loads(png.with_suffix(".json").read_text()) if png.with_suffix(".json").exists() else {}
    out["imagery_date"] = meta.get("date")
    empty = meta.get("empty_fraction", 0)
    out["imagery_warnings"] = [f"Aerial imagery is missing for {empty:.0%} of the area around the field, so SAM "
                               "may have missed water, buildings or tree lines there. Check the map."] if empty > 0.01 else []
    out["imagery_warnings"] += scout_warnings
    return out


SCOUTED = ("water", "building", "habitat")


def _cache_dir(field_path) -> Path:
    return CACHE / hashlib.sha1(Path(field_path).read_bytes()).hexdigest()[:12]


def scout_field(field_path) -> tuple[dict, list[str]]:
    """scout.scout on the field's aerial tile, cached -> (possible_water/building/habitat shapes and scout_trace,
    warnings).

    A failure comes back as a warning, never as "nothing found", and is not cached.
    """
    cache = _cache_dir(field_path)
    png, path = cache / "tile.png", cache / "scout.json"
    if path.exists():
        saved = json.loads(path.read_text())
        return _named({k: [shape(g) for g in saved[k]] for k in SCOUTED}, saved["trace"]), []
    try:
        if not png.exists():
            imagery.fetch_tile(field_path, png)
        found = scout.scout(png)
    except Exception:  # any model, imagery or parse failure: say so on the plan instead of passing it
        log.exception("hazard scout failed for %s", png.parent.name)
        return _named({k: [] for k in SCOUTED}, []), [
            "Muse Wonder and SAM 3.1 couldn't check the aerial imagery, so tree lines, buildings and ponds may be "
            "missing from the map. Check the field before spraying."]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: [mapping(p) for p in found[k]] for k in SCOUTED} | {"trace": found["trace"]}))
    return _named(found, found["trace"]), []


def _named(found: dict, trace: list) -> dict:
    """The scout's water is only possible water: the national water map is the one source of water geometry."""
    return {"possible_water": found["water"], "building": found["building"], "habitat": found["habitat"],
            "scout_trace": trace}
