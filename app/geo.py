"""GeoJSON <-> shapely. Everything is EPSG:4326 (lon/lat)."""

import json
import os
from pathlib import Path

import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.validation import explain_validity

MAX_FIELD_ACRES = float(os.getenv("MAX_FIELD_ACRES", "640"))  # one square mile; larger jobs get split
MAX_VERTICES = 2000
# NAIP imagery covers the contiguous US
CONUS = (-125.0, 24.4, -66.9, 49.5)
SQM_PER_ACRE = 4046.8564224


class FieldError(ValueError):
    """A field outline we won't plan for; the message is safe to show users."""


def _geometries(gj: dict) -> list[dict]:
    if gj.get("type") == "FeatureCollection":
        return [f["geometry"] for f in gj["features"] if f.get("geometry")]
    if gj.get("type") == "Feature":
        return [gj["geometry"]] if gj.get("geometry") else []
    return [gj]


def load_field(path: str | Path) -> Polygon:
    """First polygon in a FeatureCollection, Feature or bare geometry, checked before any paid call."""
    for g in _geometries(json.loads(Path(path).read_text())):
        geom = shape(g)
        if isinstance(geom, MultiPolygon):
            geom = geom.geoms[0]
        if isinstance(geom, Polygon):
            check_field(geom)
            return geom
    raise FieldError("The file has no field outline (polygon).")


def check_field(field: Polygon) -> None:
    """Raises FieldError unless field is a valid polygon in the contiguous US, <= MAX_FIELD_ACRES."""
    if field.is_empty:
        raise FieldError("The field outline is empty.")
    points = len(field.exterior.coords) + sum(len(r.coords) for r in field.interiors)
    if points > MAX_VERTICES:
        raise FieldError(f"The field outline has {points:,} points; the limit is {MAX_VERTICES:,}.")
    w, s, e, n = field.bounds
    if not (-180 <= w <= e <= 180 and -90 <= s <= n <= 90):
        raise FieldError("The field's coordinates aren't longitude/latitude (EPSG:4326).")
    if not (CONUS[0] <= w and e <= CONUS[2] and CONUS[1] <= s and n <= CONUS[3]):
        raise FieldError("The field is outside the contiguous US, where aerial imagery (NAIP) is available.")
    if not field.is_valid:
        raise FieldError(f"The field outline isn't a valid shape ({explain_validity(field)}). Redraw it.")
    s_ = gpd.GeoSeries([field], crs=4326)
    acres = s_.to_crs(s_.estimate_utm_crs()).area.iloc[0] / SQM_PER_ACRE
    if acres > MAX_FIELD_ACRES:
        raise FieldError(f"The field is {acres:,.0f} acres; the limit is {MAX_FIELD_ACRES:,.0f}. Split it up.")


def to_feature_collection(shapes, props: list[dict] | None = None) -> dict:
    props = props or [{} for _ in shapes]
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": mapping(s), "properties": p}
                         for s, p in zip(shapes, props, strict=True)]}


def save_shapes(shapes, path: str | Path, props: list[dict] | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_feature_collection(shapes, props)))


def load_shapes(path: str | Path) -> list:
    return [shape(g) for g in _geometries(json.loads(Path(path).read_text()))]
