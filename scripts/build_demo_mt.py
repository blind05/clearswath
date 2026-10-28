"""Builds the Montana demo cache: a ~10 ha block of the MPG Ranch drone orthomosaic, Tordon 22K, USGS water and a
leafy spurge map from the DINOv3/DINOv2 probe. Live: Modal GPU, one label read (cached), EPA BLT and USGS queries.

uv run --with modal python scripts/build_demo_mt.py --backbone facebook/dinov2-base --view full --window 1.6
Imagery and survey plots: Leafy Spurge Dataset (MPG Ranch), CC BY 4.0, doi:10.57967/hf/2508.
"""

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from shapely.geometry import box, mapping, shape

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "train")]

from app import bulletins, geo, imagery, label_reader, pipeline  # noqa: E402

OUT = ROOT / "data" / "demo" / "mt"
TILE_M, X0, Y0 = 52.02, 726737.2 - 16 * 52.02, 5177123.6 + 52.02  # orthomosaic tile grid, EPSG:32611
ROWS, COLS = list(range(10, 16)), list(range(6, 12))  # the 6 x 6 tiles with the most surveyed spurge plots
HOLDOUT = [1, 6, 7, 8]  # every cluster with plots inside the block: never trained on
CREDIT = "Drone imagery: Leafy Spurge Dataset, MPG Ranch, CC BY 4.0"
CATCH_RATES = (0.95, 0.9, 0.85, 0.8, 0.7, 0.6)
MONTH = "2026-06"  # leafy spurge in bloom, as when the block was flown (2023-06-12)


def block_utm():
    left, top = X0 + COLS[0] * TILE_M, Y0 - ROWS[0] * TILE_M
    return box(left, top - len(ROWS) * TILE_M, left + len(COLS) * TILE_M, top)


def overlay() -> None:
    """block.jpg (UTM-aligned) -> block.webp in lon/lat with transparent corners, for a Leaflet image overlay."""
    import numpy as np
    from PIL import Image
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    src = np.asarray(Image.open(OUT / "block.jpg").convert("RGB")).transpose(2, 0, 1)
    b = block_utm().bounds
    tf = from_origin(b[0], b[3], (b[2] - b[0]) / src.shape[2], (b[3] - b[1]) / src.shape[1])
    dst_tf, w, h = calculate_default_transform(32611, 4326, src.shape[2], src.shape[1], *b)
    dst = np.zeros((4, h, w), np.uint8)
    bands = [(b_, Resampling.bilinear) for b_ in src] + [(np.full(src.shape[1:], 255, np.uint8), Resampling.nearest)]
    for i, (band, method) in enumerate(bands):  # RGB, then an all-opaque band that becomes the alpha
        reproject(band, dst[i], src_transform=tf, src_crs=32611, dst_transform=dst_tf, dst_crs=4326,
                  resampling=method)
    Image.fromarray(dst.transpose(1, 2, 0), "RGBA").save(OUT / "block.webp", quality=80)
    west, north = dst_tf.c, dst_tf.f
    bounds = [west, north + h * dst_tf.e, west + w * dst_tf.a, north]  # west, south, east, north
    (OUT / "block_bounds.json").write_text(json.dumps({"crs": "EPSG:4326", "bounds": bounds, "credit": CREDIT}))


def weeds_at(catch: float) -> tuple[list, dict]:
    """Spurge polygons (lon/lat) at the threshold that catches `catch` of the training clusters' spurge plots,
    and how that threshold does on the held-out plots and the block."""
    import numpy as np
    import rasterio
    from rasterio.features import shapes

    m = json.loads((OUT / "weed_map.json").read_text())
    t = float(np.quantile(m["fit_present_probs"], 1 - catch))
    hp, hy = np.array(m["holdout_probs"]), np.array(m["holdout_y"])
    with rasterio.open(OUT / "prob.tif") as src:
        p, tf = src.read(1), src.transform
    ok = p != 255
    weed = ok & (p >= round(t * 254))
    # Polygonized in 5 m windows: one field-sized polygon would make every cell's intersection with it slow.
    w = 25
    polys = [shape(g) for y in range(0, weed.shape[0], w) for x in range(0, weed.shape[1], w)
             for g, v in shapes(weed[y:y + w, x:x + w].astype(np.uint8), mask=weed[y:y + w, x:x + w],
                                transform=tf * tf.translation(x, y)) if v]
    # 5 cm simplification (a quarter pixel) drops the pixel stair-steps that make the demo cache large
    return list(gpd.GeoSeries(polys, crs=32611).simplify(0.05).to_crs(4326)), {
        "catch_target": catch, "threshold": t, "holdout_recall": float((hp[hy == 1] >= t).mean()),
        "holdout_absent_flagged": float((hp[hy == 0] >= t).mean()), "block_flagged": float(weed.sum() / ok.sum())}


def main(backbone: str, view: str, window: float, provider: str, catch: float, reuse_map: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    utm = block_utm()
    field = gpd.GeoSeries([utm], crs=32611).to_crs(4326).iloc[0]
    field_path = OUT / "block.geojson"
    field_path.write_text(json.dumps(mapping(field)))

    if not reuse_map:  # the map is saved before anything else can fail: it is the 25-minute GPU step
        import spurge_modal

        m = spurge_modal.run_map(backbone=backbone, view=view, window_m=window, rows_=ROWS, cols=COLS,
                                 holdout=HOLDOUT)
        (OUT / "block.jpg").write_bytes(m["jpeg"])
        (OUT / "prob.tif").write_bytes(m["prob_tif"])
        (OUT / "weed_map.json").write_text(json.dumps({k: v for k, v in m.items() if k not in ("jpeg", "prob_tif")}))
        overlay()
    curve = [weeds_at(c)[1] for c in CATCH_RATES]
    (OUT / "weed_curve.json").write_text(json.dumps(curve, indent=1))
    weeds, check = weeds_at(catch)
    weeds = [w for w in shapely.set_precision(np.array(weeds, dtype=object), 1e-7) if not w.is_empty]  # ~1 cm
    name = json.loads((OUT / "weed_map.json").read_text())["backbone"].split("/")[1]

    label_raw = label_reader.read_raw(ROOT / "data" / "labels" / "tordon_22k.pdf", provider)
    water_path = OUT / "water.geojson"  # USGS NHD for the block, kept once fetched: the service often times out
    if not water_path.exists():
        failed = []
        water = imagery.usgs_water(field_path, failed)
        if failed:
            raise SystemExit(f"USGS layers failed: {failed}; not caching a partial answer")
        geo.save_shapes(water, water_path)
    water = geo.load_shapes(water_path)
    import rasterio

    with rasterio.open(OUT / "prob.tif") as src:
        missing = float((src.read(1) == 255).mean())
    gaps = [f"Drone imagery is missing for {missing:.0%} of the block, so spurge there is unmapped and those cells "
            "are not sprayed. Scout them before the job."] if missing > 0.005 else []
    hazards = {"water": water, "building": [], "habitat": [], "water_source": "usgs", "water_warnings": [],
               "imagery_date": "2023-06-12", "imagery_warnings": gaps, "weeds": weeds,
               "weed_source": f"{name} probe set to catch {catch:.0%} of spurge plots: on held-out plots it found "
                              f"{check['holdout_recall']:.0%} and also flagged {check['holdout_absent_flagged']:.0%} "
                              "of clean ones"}
    bulletin = bulletins.check_bulletin(field_path, MONTH, "62719-6")
    if not bulletin["checked"]:
        raise SystemExit(f"bulletin check failed ({bulletin['citation']}); not caching a failed check")
    pipeline.save_inputs(ROOT / "data" / "demo" / "cache" / "mt", field, label_raw, hazards, bulletin, MONTH)
    result = pipeline.assemble(field, label_reader.verify(label_raw), hazards, bulletin, MONTH, "drone")
    print(json.dumps(curve, indent=1))
    print(json.dumps(check | {"weed_polygons": len(weeds), "water_features": len(water),
                              "plan": {k: result["plan"][k] for k in ("status", "spray_acres", "field_acres")},
                              "spot": pipeline.cells.summary(result["cells"])}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlay-only", action="store_true", help="redo block.webp from block.jpg")
    ap.add_argument("--reuse-map", action="store_true", help="use the saved prob.tif and weed_map.json; skip the GPU step")
    ap.add_argument("--backbone")
    ap.add_argument("--view", choices=["full", "zoom"])
    ap.add_argument("--window", type=float)
    ap.add_argument("--provider", default="fireworks")
    ap.add_argument("--catch", type=float, default=0.95, help="share of spurge plots the map must catch")
    a = ap.parse_args()
    if a.overlay_only:
        overlay()
    elif a.reuse_map:
        main(None, None, None, a.provider, a.catch, reuse_map=True)
    elif not (a.backbone and a.view and a.window):
        ap.error("--backbone, --view and --window are required")
    else:
        main(a.backbone, a.view, a.window, a.provider, a.catch)
