"""Spot-spray grid: weed patches -> cells to spray, cells left clean, and cells a buffer rules out.

Pure geometry, never calls a model. Works in the field's UTM zone (metres), like buffers.py.
"""

import hashlib

import geopandas as gpd
import numpy as np
import shapely
from shapely import STRtree
from shapely.geometry import Polygon
from shapely.wkt import dumps as wkt

SQM_PER_ACRE = 4046.8564224
MIN_CELL_M2 = 0.01  # slivers from clipping to the field edge are dropped
DEFAULT_THRESHOLD = 0.01  # a cell is sprayed at >= 1% weed cover


def _utm(field: Polygon):
    return gpd.GeoSeries([field], crs=4326).estimate_utm_crs()


def _to(shapes, src, dst) -> list:
    return list(gpd.GeoSeries(list(shapes), crs=src).to_crs(dst)) if len(shapes) else []


def grid(field_m: Polygon, size_m: float) -> list[Polygon]:
    """Square cells of size_m, aligned to the field's bounding box, clipped to the field (metres)."""
    if size_m <= 0:
        raise ValueError("cell size must be positive")
    minx, miny, maxx, maxy = field_m.bounds
    x, y = np.meshgrid(minx + size_m * np.arange(np.ceil((maxx - minx) / size_m)),
                       miny + size_m * np.arange(np.ceil((maxy - miny) / size_m)))  # rows of y, x within a row
    cells = shapely.intersection(shapely.box(x.ravel(), y.ravel(), x.ravel() + size_m, y.ravel() + size_m), field_m)
    return list(cells[~shapely.is_empty(cells) & (shapely.area(cells) >= MIN_CELL_M2)])


def classify(field: Polygon, weeds: list, no_spray, size_m: float, threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Cells over the field (EPSG:4326 in and out). no_spray is the union of every buffer the label requires.

    A cell touching no_spray is 'buffered' (always beats 'spray'); else 'spray' when weed cover >= threshold;
    else 'clean'.
    """
    utm = _utm(field)
    field_m = _to([field], 4326, utm)[0]
    blocked = _to([no_spray], 4326, utm)[0] if no_spray is not None and not no_spray.is_empty else Polygon()
    cells_m = np.array(grid(field_m, size_m), dtype=object)

    # Weed area per cell, summed over the weed polygons each cell meets (vectorised: a drone map has ~10^4-10^5).
    # ponytail: overlapping weed polygons are counted twice, which can only raise cover (more spraying, never
    # less, and never inside a buffer); union them first if a source ever overlaps heavily.
    parts = shapely.get_parts(np.array(_to(weeds, 4326, utm), dtype=object)) if weeds else np.array([], object)
    weed_area = np.zeros(len(cells_m))
    if len(parts):
        ci, wi = STRtree(parts).query(cells_m, predicate="intersects")
        np.add.at(weed_area, ci, shapely.area(shapely.intersection(cells_m[ci], parts[wi])))
    cover = np.minimum(weed_area / shapely.area(cells_m), 1.0)
    near_buffer = np.zeros(len(cells_m), bool)
    if not blocked.is_empty:
        cand = STRtree(cells_m).query(blocked, predicate="intersects")
        near_buffer[cand] = shapely.area(shapely.intersection(cells_m[cand], blocked)) > 0  # an edge is no touch
    states = np.where(near_buffer, "buffered", np.where(cover >= threshold, "spray", "clean"))
    cells_wgs = _to(cells_m, utm, 4326)
    out = [{"cell": c, "cover": float(v), "state": str(st), "geometry": g}
           for c, v, st, g in zip(cells_m, cover, states, cells_wgs, strict=True)]
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
