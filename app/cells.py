"""Spot-spray grid: weed patches -> cells to spray, cells left clean, and cells a buffer rules out.

Pure geometry, never calls a model. Works in the field's UTM zone (metres), like buffers.py.
"""

import hashlib

import geopandas as gpd
from shapely import STRtree, union_all
from shapely.geometry import Polygon, box
from shapely.wkt import dumps as wkt

SQM_PER_ACRE = 4046.8564224
MIN_CELL_M2 = 0.01  # slivers from clipping to the field edge are dropped
DEFAULT_THRESHOLD = 0.01  # a cell is sprayed at >= 1% weed cover


def _utm(field: Polygon):
    return gpd.GeoSeries([field], crs=4326).estimate_utm_crs()


def _to(shapes, src, dst) -> list:
    return list(gpd.GeoSeries(list(shapes), crs=src).to_crs(dst)) if shapes else []


def grid(field_m: Polygon, size_m: float) -> list[Polygon]:
    """Square cells of size_m, aligned to the field's bounding box, clipped to the field (metres)."""
    if size_m <= 0:
        raise ValueError("cell size must be positive")
    minx, miny, maxx, maxy = field_m.bounds
    cells = []
    y = miny
    while y < maxy:
        x = minx
        while x < maxx:
            cell = box(x, y, x + size_m, y + size_m).intersection(field_m)
            if not cell.is_empty and cell.area >= MIN_CELL_M2:
                cells.append(cell)
            x += size_m
        y += size_m
    return cells


def classify(field: Polygon, weeds: list, no_spray, size_m: float, threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Cells over the field (EPSG:4326 in and out). no_spray is the union of every buffer the label requires.

    A cell touching no_spray is 'buffered' (always beats 'spray'); else 'spray' when weed cover >= threshold;
    else 'clean'.
    """
    utm = _utm(field)
    field_m = _to([field], 4326, utm)[0]
    weeds_m = union_all(_to(weeds, 4326, utm)) if weeds else Polygon()
    blocked = _to([no_spray], 4326, utm)[0] if no_spray is not None and not no_spray.is_empty else Polygon()
    cells_m = grid(field_m, size_m)
    tree = STRtree(cells_m)

    weedy = {int(i) for i in tree.query(weeds_m, predicate="intersects")} if not weeds_m.is_empty else set()
    near_buffer = set()
    if not blocked.is_empty:
        for i in tree.query(blocked, predicate="intersects"):
            if cells_m[int(i)].intersection(blocked).area > 0:  # a shared edge is not a touch
                near_buffer.add(int(i))
    out = []
    for i, cell in enumerate(cells_m):
        cover = cell.intersection(weeds_m).area / cell.area if i in weedy else 0.0
        state = "buffered" if i in near_buffer else ("spray" if cover >= threshold else "clean")
        out.append({"cell": cell, "cover": cover, "state": state})
    cells_wgs = _to([c["cell"] for c in out], utm, 4326)
    for c, g in zip(out, cells_wgs, strict=True):
        c["geometry"] = g
    return {"utm": utm, "size_m": size_m, "threshold": threshold, "cells": out,
            "hash": input_hash(field, weeds, no_spray, size_m, threshold)}


def input_hash(field, weeds, no_spray, size_m, threshold) -> str:
    """Same inputs, same plan ID. Coordinates are rounded to ~1 cm so float noise doesn't change it."""
    h = hashlib.sha256()
    for g in [field, *weeds, no_spray if no_spray is not None else Polygon()]:
        h.update(wkt(g, rounding_precision=7, trim=True).encode())
    h.update(f"{size_m}|{threshold}".encode())
    return h.hexdigest()


def summary(result: dict) -> dict:
    """Acres by state, plus the plan hash."""
    acres = {"spray": 0.0, "clean": 0.0, "buffered": 0.0}
    for c in result["cells"]:
        acres[c["state"]] += c["cell"].area / SQM_PER_ACRE
    total = sum(acres.values())
    return {"field_acres": round(total, 2), "treated_acres": round(acres["spray"], 2),
            "clean_acres": round(acres["clean"], 2), "buffered_acres": round(acres["buffered"], 2),
            "cells": len(result["cells"]), "cell_size_m": result["size_m"], "hash": result["hash"]}
