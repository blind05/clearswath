import io
import zipfile

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from shapely.geometry import Polygon, box

from app import cells, exports

UTM = 32615
X, Y = 500_000, 4_650_000


def ll(*shapes):
    return list(gpd.GeoSeries(shapes, crs=UTM).to_crs(4326))


# an L-shaped field, 30 x 20 m with the top-right 10 x 10 m missing; one weed near the bottom-left corner
FIELD, WEED = ll(Polygon([(X, Y), (X + 30, Y), (X + 30, Y + 10), (X + 20, Y + 10), (X + 20, Y + 20), (X, Y + 20)]),
                 box(X + 2, Y + 2, X + 6, Y + 6))


def grid():
    return cells.classify(FIELD, [WEED], None, 10.0)


def test_spot_raster_puts_each_cell_in_its_pixel():
    data, transform = exports.spot_raster(grid())
    # rows top to bottom: the missing corner is outside, the weed cell is bottom-left
    assert data.tolist() == [[0, 0, 255], [1, 0, 0]]
    assert transform.a == 10 and transform.e == -10
    assert transform.c == pytest.approx(X, abs=0.5) and transform.f == pytest.approx(Y + 20, abs=0.5)


def test_dji_zip_has_boundary_and_rates(tmp_path):
    g = grid()
    exports.write_spot_tif(g, tmp_path / "spot.tif")
    z = zipfile.ZipFile(io.BytesIO(exports.dji_zip(FIELD, tmp_path / "spot.tif", 19.0)))
    names = set(z.namelist())
    assert {"DJI/ShapeFile/boundary.shp", "DJI/ShapeFile/boundary.dbf", "DJI/Rx/prescription.tif"} <= names
    z.extractall(tmp_path / "out")
    shp = gpd.read_file(tmp_path / "out" / "DJI" / "ShapeFile" / "boundary.shp")
    assert shp.crs.to_epsg() == 4326 and len(shp) == 1
    assert shp.geometry[0].hausdorff_distance(FIELD) < 1e-9  # same shape; shapefiles reorder rings
    with rasterio.open(tmp_path / "out" / "DJI" / "Rx" / "prescription.tif") as src:
        rx = src.read(1)
        assert src.crs.to_epsg() == g["utm"].to_epsg() and src.nodata == -1
    assert np.array_equal(rx, np.array([[0, 0, -1], [19, 0, 0]], np.float32))


def test_dji_zip_refuses_a_bad_rate(tmp_path):
    exports.write_spot_tif(grid(), tmp_path / "spot.tif")
    with pytest.raises(ValueError):
        exports.dji_zip(FIELD, tmp_path / "spot.tif", 0)
