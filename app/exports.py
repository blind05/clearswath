"""Sprayer exports from the spot-spray grid. Pure geometry and files, never calls a model.

spot.tif (saved with each run): the cell grid in the field's UTM zone, 1 = spray, 0 = don't, 255 = outside the field.
DJI Agras zip: a boundary shapefile plus a rate GeoTIFF, the layout PIX4Dfields exports for T-series VRA missions.
"""

import io
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin

SPRAY, CLEAN, OUTSIDE = 1, 0, 255


def spot_raster(grid: dict) -> tuple[np.ndarray, object]:
    """(uint8 array, transform) with one pixel per cell of cells.classify's grid, in grid['utm']."""
    size, cells = grid["size_m"], grid["cells"]
    minx = min(c["cell"].bounds[0] for c in cells)  # the field touches its bounding box, so a cell does too
    miny = min(c["cell"].bounds[1] for c in cells)
    where = []
    for c in cells:
        p = c["cell"].representative_point()  # inside the clipped cell, never on its edge
        where.append((int((p.y - miny) // size), int((p.x - minx) // size)))
    rows, cols = max(r for r, _ in where) + 1, max(k for _, k in where) + 1
    out = np.full((rows, cols), OUTSIDE, np.uint8)
    for c, (r, k) in zip(cells, where, strict=True):
        out[rows - 1 - r, k] = SPRAY if c["state"] == "spray" else CLEAN
    return out, from_origin(minx, miny + rows * size, size, size)


def write_spot_tif(grid: dict, path: str | Path) -> None:
    data, transform = spot_raster(grid)
    with rasterio.open(path, "w", driver="GTiff", width=data.shape[1], height=data.shape[0], count=1,
                       dtype="uint8", crs=grid["utm"].to_wkt(), transform=transform, nodata=OUTSIDE,
                       compress="deflate") as dst:
        dst.write(data, 1)


def dji_zip(field, spot_tif: str | Path, rate: float) -> bytes:
    """Boundary shapefile (EPSG:4326) + prescription GeoTIFF: `rate` in spray cells, 0 elsewhere.

    TODO(verify): DJI's import spec isn't public. Folder names follow PIX4Dfields' DJI export and a DJI forum
    report (DJI/ShapeFile, EPSG:4326 polygons with a .dbf); the rate unit (L/ha assumed) and whether the
    controller accepts a UTM GeoTIFF are unconfirmed. Check on a controller before a real job.
    """
    if not rate > 0:
        raise ValueError("rate must be positive")
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        shp = Path(tmp) / "boundary.shp"
        gpd.GeoDataFrame({"name": ["ClearSwath field"]}, geometry=[field], crs=4326).to_file(shp)
        for part in Path(tmp).glob("boundary.*"):
            z.write(part, f"DJI/ShapeFile/{part.name}")
        with rasterio.open(spot_tif) as src:
            mask, profile = src.read(1), src.profile
        rx = np.where(mask == SPRAY, rate, np.where(mask == OUTSIDE, -1, 0)).astype(np.float32)
        profile.update(dtype="float32", nodata=-1)
        with rasterio.open(Path(tmp) / "prescription.tif", "w", **profile) as dst:
            dst.write(rx, 1)
        z.write(Path(tmp) / "prescription.tif", "DJI/Rx/prescription.tif")
    return buf.getvalue()
