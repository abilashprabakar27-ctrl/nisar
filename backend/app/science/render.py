"""Turn grids into map-ready PNGs (EPSG:4326, north-up) with their lon/lat bounds."""
from pathlib import Path

import numpy as np
from PIL import Image

from .change import BECAME_WATER, MASKED, PERMANENT, RECEDED
from .grid import Grid

COLORS = {  # RGBA, matching the design system
    BECAME_WATER: (29, 78, 216, 215),     # #1D4ED8
    RECEDED: (96, 165, 250, 190),         # #60A5FA
    PERMANENT: (10, 12, 16, 110),
    MASKED: (156, 163, 175, 70),
}


def _transform(grid: Grid):
    from rasterio.transform import from_origin
    return from_origin(grid.x[0] - grid.res / 2, grid.y[0] + grid.res / 2, grid.res, grid.res)


def to_lonlat(arr: np.ndarray, grid: Grid, nearest: bool):
    """Reproject a grid array to EPSG:4326. Returns (array, [w, s, e, n])."""
    import rasterio.warp as rw
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    src_t = _transform(grid)
    h, w = arr.shape
    left, top = src_t.c, src_t.f
    right, bottom = left + w * grid.res, top - h * grid.res
    dst_t, dw, dh = rw.calculate_default_transform(CRS.from_epsg(grid.epsg), CRS.from_epsg(4326), w, h,
                                                   left=left, bottom=bottom, right=right, top=top)
    nodata = 0 if arr.dtype == np.uint8 else np.nan
    dst = np.full((dh, dw), nodata, dtype=arr.dtype)
    rw.reproject(arr, dst, src_transform=src_t, src_crs=CRS.from_epsg(grid.epsg), dst_transform=dst_t,
                 dst_crs=CRS.from_epsg(4326), resampling=Resampling.nearest if nearest else Resampling.bilinear,
                 src_nodata=(None if arr.dtype == np.uint8 else np.nan), dst_nodata=nodata)
    bounds = [dst_t.c, dst_t.f + dh * dst_t.e, dst_t.c + dw * dst_t.a, dst_t.f]
    return dst, [round(float(v), 6) for v in bounds]


def classes_png(classes: np.ndarray, grid: Grid, path: Path):
    # shift class codes so 0 means "outside" after reprojection
    coded = np.where(classes == MASKED, 5, classes + 1).astype("uint8")
    ll, bounds = to_lonlat(coded, grid, nearest=True)
    rgba = np.zeros(ll.shape + (4,), "uint8")
    for cls, col in COLORS.items():
        code = 5 if cls == MASKED else cls + 1
        rgba[ll == code] = col
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)
    return bounds


def _stretch(db, lo, hi):
    v = np.clip((db - lo) / (hi - lo), 0, 1)
    return np.where(np.isfinite(db), v, np.nan)


def gray_png(db: np.ndarray, grid: Grid, path: Path, lo: float, hi: float):
    ll, bounds = to_lonlat(_stretch(db, lo, hi).astype("float32"), grid, nearest=False)
    g = np.nan_to_num(ll * 255).astype("uint8")
    a = np.where(np.isfinite(ll), 255, 0).astype("uint8")
    Image.fromarray(np.dstack([g, a]), "LA").save(path, optimize=True)
    return bounds


def mix_png(hh_db: np.ndarray, hv_db: np.ndarray, grid: Grid, path: Path):
    """Colour mix: red = HH, green = HV, blue = HH/HV ratio (HH - HV in dB)."""
    r = _stretch(hh_db, -25, 0)
    g = _stretch(hv_db, -32, -8)
    b = _stretch(hh_db - hv_db, 0, 15)
    chans = []
    bounds = None
    for c in (r, g, b):
        ll, bounds = to_lonlat(c.astype("float32"), grid, nearest=False)
        chans.append(ll)
    alpha = np.where(np.isfinite(chans[0]) & np.isfinite(chans[1]), 255, 0).astype("uint8")
    rgb = [np.nan_to_num(c * 255).astype("uint8") for c in chans]
    Image.fromarray(np.dstack(rgb + [alpha]), "RGBA").save(path, optimize=True)
    return bounds
