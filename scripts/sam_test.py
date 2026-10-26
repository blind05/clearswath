"""Live SAM check on data/test_fields/*.geojson. Uses the network and your key:
`uv run python scripts/sam_test.py`. Overlays land in data/cache/overlays/<name>.png."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw  # noqa: E402
from rasterio.transform import Affine, array_bounds  # noqa: E402
from rasterio.warp import transform_bounds, transform_geom  # noqa: E402
from shapely.affinity import affine_transform  # noqa: E402
from shapely.geometry import box, mapping, shape  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from app import imagery, segment  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
PHRASES = {"pond": "blue", "creek": "cyan", "water": "deepskyblue", "building": "red", "tree line": "lime"}
WATER = ("pond", "creek", "water")
USGS_COLOR = "yellow"
GO_RECALL = 0.7  # share of USGS water features SAM must touch


def draw(png, meta, layers, out):
    """layers: [(lon/lat polygons, color)] outlined on the tile."""
    inv = ~Affine(*meta["transform"])
    to_px = [inv.a, inv.b, inv.d, inv.e, inv.c, inv.f]
    img = Image.open(png).convert("RGB")
    pen = ImageDraw.Draw(img)
    for polys, color in layers:
        for p in polys:
            p = affine_transform(shape(transform_geom("EPSG:4326", meta["crs"], mapping(p))), to_px)
            for part in getattr(p, "geoms", [p]):
                pen.line(list(part.exterior.coords), fill=color, width=2)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def main():
    fields = sorted((ROOT / "data" / "test_fields").glob("*.geojson"))
    if not fields:
        sys.exit("No fields in data/test_fields/")
    print(f"{'field':<22}{'date':<12}" + "".join(f"{p:>10}" for p in PHRASES) + f"{'usgs hit':>10}{'recall':>8}")
    hit_total = usgs_total = 0
    for field in fields:
        png = CACHE / "sam_test" / field.stem / "tile.png"
        meta = imagery.fetch_tile(field, png)
        found = {p: segment.segment_tile(png, p) for p in PHRASES}
        tile = box(*transform_bounds(meta["crs"], "EPSG:4326", *array_bounds(
            meta["height"], meta["width"], Affine(*meta["transform"]))))
        usgs = [w for w in imagery.usgs_water(field) if w.intersects(tile)]
        sam_water = unary_union([p for name in WATER for p in found[name]])
        hits = sum(w.intersects(sam_water) for w in usgs)
        hit_total, usgs_total = hit_total + hits, usgs_total + len(usgs)
        draw(png, meta, [(usgs, USGS_COLOR)] + [(found[p], c) for p, c in PHRASES.items()],
             CACHE / "overlays" / f"{field.stem}.png")
        recall = f"{hits / len(usgs):.2f}" if usgs else "n/a"
        print(f"{field.stem:<22}{meta['date']:<12}" + "".join(f"{len(found[p]):>10}" for p in PHRASES)
              + f"{f'{hits}/{len(usgs)}':>10}{recall:>8}")
    recall = hit_total / usgs_total if usgs_total else 0
    verdict = "GO" if recall >= GO_RECALL else "PARTIAL" if hit_total else "check-overlays"
    print(f"\nwater recall {hit_total}/{usgs_total} -> {verdict}  (overlays: {CACHE / 'overlays'})")


if __name__ == "__main__":
    main()
