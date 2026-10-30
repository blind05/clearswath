"""Scout eval: what each method finds on NAIP tiles, scored against ground truth no Meta model made.

uv run python evals/scout_eval.py [--tiles 20]

Live and paid (cached per tile after the first run): the Meta API (Muse Wonder, SAM 3.1), the Planetary Computer
(NAIP, ESA WorldCover) and Microsoft's building footprints.
Methods: SAM 3.1 with the fixed text prompts (segment.PHRASES); Muse Wonder + SAM 3.1 boxes before Wonder's review
("draft"); and after it (what the app uses).
Truth: trees, shrubs and water from ESA WorldCover 2021 v200 (10 m, CC BY 4.0); buildings from Microsoft Global ML Building
Footprints (ODbL). Both are coarser or older than the 2022-2023 NAIP the models see; see the results file.
"""

import argparse
import csv
import gzip
import io
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import planetary_computer
import pystac_client
import rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject, transform_bounds, transform_geom
from shapely.geometry import box, mapping, shape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import geo, imagery, scout, segment  # noqa: E402

CACHE = ROOT / "data" / "cache" / "scout_eval"
OUT = ROOT / "evals" / "results_scout.md"
CELL_M = 10.0  # the truth grid: WorldCover's resolution
HABITAT, WATER = {10, 20}, {80, 90}  # WorldCover: tree cover and shrubland; permanent water and herbaceous wetland
FIELD_M = 400  # each sample is a 400 m square "field"; fetch_tile adds its margin around it
LINKS = "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
PC = "https://planetarycomputer.microsoft.com/api/stac/v1"
KINDS = ("habitat", "building", "water")


def fields(n: int) -> list[Path]:
    """The two demo fields, then squares around them at fixed random offsets (seed 7): 70% near South Dakota."""
    rng = np.random.default_rng(7)
    demos = [ROOT / "data" / "demo" / "field.geojson", ROOT / "data" / "demo" / "mt" / "block.geojson"]
    sd, mt = (geo.load_field(p).centroid for p in demos)
    out = list(demos)
    for i in range(n - len(demos)):
        c, spread = (sd, (0.25, 0.18)) if i < round(0.7 * (n - 2)) else (mt, (0.08, 0.06))
        lon, lat = c.x + rng.uniform(-1, 1) * spread[0], c.y + rng.uniform(-1, 1) * spread[1]
        dlon, dlat = FIELD_M / 2 / (111_320 * math.cos(math.radians(lat))), FIELD_M / 2 / 110_540
        path = CACHE / f"field_{i:02d}.geojson"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(mapping(box(lon - dlon, lat - dlat, lon + dlon, lat + dlat))))
        out.append(path)
    return out


def _cached(path: Path, compute):
    if path.exists():
        return json.loads(path.read_text())
    value = compute()
    path.write_text(json.dumps(value))
    return value


def methods(field: Path, png: Path) -> dict:
    """{method: {kind: [geojson]}} for one tile; each model step cached, so a rerun costs nothing."""
    def baseline():
        found = {k: [] for k in KINDS}
        for kind, phrases in segment.PHRASES.items():
            for phrase in phrases:
                found[kind] += [mapping(p) for p in segment.segment_tile(png, phrase)]
        return found

    def scouted():
        out = scout.scout(png)
        as_json = lambda d: {k: [mapping(p) for p in d[k]] for k in KINDS}  # noqa: E731
        return {"draft": as_json(out["draft"]), "reviewed": as_json(out), "trace": out["trace"]}

    s = _cached(png.with_name("scout_eval.json"), scouted)
    return {"SAM 3.1, text prompts": _cached(png.with_name("baseline.json"), baseline),
            "Wonder + SAM, before review": s["draft"], "Wonder + SAM, after review": s["reviewed"]}


def grid(meta: dict) -> tuple[Affine, int, int]:
    """A 10 m grid over the tile, in the tile's CRS."""
    t = Affine(*meta["transform"])
    left, top = t.c, t.f
    w_m, h_m = meta["width"] * t.a, meta["height"] * -t.e
    return Affine(CELL_M, 0, left, 0, -CELL_M, top), int(w_m // CELL_M), int(h_m // CELL_M)


def worldcover(meta: dict, catalog) -> np.ndarray:
    transform, w, h = grid(meta)
    bounds = transform_bounds(meta["crs"], 4326, transform.c, transform.f - h * CELL_M, transform.c + w * CELL_M,
                              transform.f)
    item = next(i for i in catalog.search(collections=["esa-worldcover"], bbox=bounds).items()
                if i.properties.get("esa_worldcover:product_version") == "2.0.0" or "v200" in i.id)
    out = np.zeros((h, w), dtype=np.uint8)
    with rasterio.open(item.assets["map"].href) as src:
        reproject(rasterio.band(src, 1), out, dst_transform=transform, dst_crs=meta["crs"],
                  resampling=Resampling.mode)
    return out


def _quadkey(lon: float, lat: float, level: int = 9) -> str:
    n = 2 ** level
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return "".join(str(((x >> i) & 1) + 2 * ((y >> i) & 1)) for i in range(level - 1, -1, -1))


def footprints(meta: dict, links: dict) -> list:
    """Microsoft building footprints on the tile, in the tile's CRS."""
    transform, w, h = grid(meta)
    tile = box(transform.c, transform.f - h * CELL_M, transform.c + w * CELL_M, transform.f)
    lon0, lat0, lon1, lat1 = transform_bounds(meta["crs"], 4326, *tile.bounds)
    keys = {_quadkey(lo, la) for lo in (lon0, lon1) for la in (lat0, lat1)}
    polys = []
    for key in keys:
        path = CACHE / f"buildings_{key}.geojsonl.gz"
        if not path.exists():
            path.write_bytes(httpx.get(links[key], timeout=300, follow_redirects=True).content)
        for line in gzip.open(path, "rt"):
            g = shape(transform_geom("EPSG:4326", meta["crs"], json.loads(line)["geometry"]))
            if g.intersects(tile):
                polys.append(g)
    return polys


def burn(shapes: list, meta: dict) -> np.ndarray:
    transform, w, h = grid(meta)
    geoms = [transform_geom("EPSG:4326", meta["crs"], g) for g in shapes]
    return rasterize(geoms, (h, w), transform=transform, dtype=np.uint8) > 0 if geoms else np.zeros((h, w), bool)


def score(field: Path, catalog, links: dict) -> dict:
    png = CACHE / field.stem / "tile.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    meta = imagery.fetch_tile(field, png)
    found = methods(field, png)
    cover = worldcover(meta, catalog)
    truth = {"habitat": np.isin(cover, list(HABITAT)), "water": np.isin(cover, list(WATER))}
    buildings = [b for b in footprints(meta, links) if b.area >= 40]
    row = {"tile": field.stem, "date": meta.get("date"), "buildings": len(buildings),
           "tree_cells": int(truth["habitat"].sum()), "water_cells": int(truth["water"].sum())}
    for name, f in found.items():
        for kind in ("habitat", "water"):
            pred = burn(f[kind], meta)
            row[(name, kind)] = (int((pred & truth[kind]).sum()), int((pred & ~truth[kind]).sum()),
                                 int((~pred & truth[kind]).sum()))
        pred = [shape(transform_geom("EPSG:4326", meta["crs"], g)).buffer(3) for g in f["building"]]
        hit = sum(any(p.intersects(b) for p in pred) for b in buildings)
        right = sum(any(p.intersects(b) for b in buildings) for p in pred)
        row[(name, "building")] = (hit, len(buildings), right, len(pred))
    return row


def pct(a: int, b: int) -> str:
    return f"{a / b:.0%}" if b else "n/a"


def report(rows: list[dict], failed: list[str]) -> str:
    names = [k[0] for k in rows[0] if isinstance(k, tuple) and k[1] == "habitat"]
    lines = [f"# Hazard scout eval ({date.today().isoformat()})", "",
             f"{len(rows)} NAIP tiles (about 0.6 km across each): the 2 demo fields and {len(rows) - 2} squares at "
             "fixed random offsets around them, eastern South Dakota and western Montana. Made by "
             "`evals/scout_eval.py`." + (f" Failed tiles, not scored: {', '.join(failed)}." if failed else ""), "",
             "Truth, which no Meta model made: trees and shrubs (the app's tree lines and woods) and water from ESA "
             "WorldCover 2021 v200 (10 m cells, CC BY 4.0); "
             "buildings from Microsoft Global ML Building Footprints (ODbL), 40 m2 and up. A building counts as found "
             "if an outline touches it (3 m tolerance).", "",
             "| Method | Trees and shrubs: precision / recall | Water: precision / recall | Buildings found | Building outlines on a building |",
             "|---|---|---|---|---|"]
    for name in names:
        tp, fp, fn = (sum(r[(name, "habitat")][i] for r in rows) for i in range(3))
        wtp, wfp, wfn = (sum(r[(name, "water")][i] for r in rows) for i in range(3))
        hit, total, right, outlines = (sum(r[(name, "building")][i] for r in rows) for i in range(4))
        lines.append(f"| {name} | {pct(tp, tp + fp)} / {pct(tp, tp + fn)} | {pct(wtp, wtp + wfp)} / "
                     f"{pct(wtp, wtp + wfn)} | {hit} of {total} ({pct(hit, total)}) | {right} of {outlines} |")
    lines += ["", "Per tile (trees and shrubs: true positive / false positive / missed 10 m cells, after review):", "",
              "| Tile | NAIP date | Tree and shrub cells | Water cells | Buildings | After review |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['tile']} | {r['date']} | {r['tree_cells']} | {r['water_cells']} | {r['buildings']} | "
                     f"{' / '.join(map(str, r[(names[-1], 'habitat')]))} |")
    lines += ["", "Limits: WorldCover is 10 m and from 2021, so a 15 m shelterbelt may fill only part of a cell, and "
              "trees planted or cut since then count against the models. Footprints miss some farm buildings and "
              "include some that are gone. Water here is the scout's possible water, which the app never cuts out."]
    return "\n".join(lines) + "\n"


def main(n: int) -> None:
    catalog = pystac_client.Client.open(PC, modifier=planetary_computer.sign_inplace)
    CACHE.mkdir(parents=True, exist_ok=True)
    index = CACHE / "dataset-links.csv"
    if not index.exists():
        index.write_text(httpx.get(LINKS, timeout=120).text)
    links = {r["QuadKey"]: r["Url"] for r in csv.DictReader(io.StringIO(index.read_text()))
             if r["Location"] == "UnitedStates"}
    rows, failed = [], []

    def one(field):
        try:
            return score(field, catalog, links)
        except Exception as e:  # one bad tile shouldn't sink the run; it's listed in the results
            print(f"{field.stem}: {type(e).__name__}: {e}")
            failed.append(field.stem)

    with ThreadPoolExecutor(4) as pool:
        rows = [r for r in pool.map(one, fields(n)) if r]
    text = report(rows, failed)
    OUT.write_text(text)
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", type=int, default=20)
    main(ap.parse_args().tiles)
