"""GeoJSON <-> shapely. Everything is EPSG:4326 (lon/lat)."""

import json
from pathlib import Path

from shapely.geometry import MultiPolygon, Polygon, mapping, shape


def _geometries(gj: dict) -> list[dict]:
    if gj.get("type") == "FeatureCollection":
        return [f["geometry"] for f in gj["features"] if f.get("geometry")]
    if gj.get("type") == "Feature":
        return [gj["geometry"]] if gj.get("geometry") else []
    return [gj]


def load_field(path: str | Path) -> Polygon:
    """First polygon in a FeatureCollection, Feature or bare geometry."""
    for g in _geometries(json.loads(Path(path).read_text())):
        geom = shape(g)
        if isinstance(geom, Polygon):
            return geom
        if isinstance(geom, MultiPolygon):
            return geom.geoms[0]
    raise ValueError(f"No polygon found in {path}")


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
