"""Put every pass on one common grid so pixels line up."""
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import uniform_filter

from .gcov import Window, bbox_to_utm


@dataclass
class Grid:
    epsg: int
    x: np.ndarray   # pixel-centre eastings (ascending)
    y: np.ndarray   # pixel-centre northings (descending, north-up)
    res: float

    @property
    def shape(self):
        return (self.y.size, self.x.size)

    @property
    def pixel_ha(self):
        return self.res * self.res / 10_000.0


def make_grid(bbox, epsg: int, res: float) -> Grid:
    x0, y0, x1, y1 = bbox_to_utm(bbox, epsg)
    x0, y0 = np.floor(x0 / res) * res, np.floor(y0 / res) * res
    x1, y1 = np.ceil(x1 / res) * res, np.ceil(y1 / res) * res
    x = np.arange(x0 + res / 2, x1, res)
    y = np.arange(y1 - res / 2, y0, -res)
    return Grid(epsg=epsg, x=x, y=y, res=res)


def _nearest_index(src: np.ndarray, targets: np.ndarray):
    """Index of the nearest source coordinate for each target; -1 when outside."""
    asc = src[0] <= src[-1]
    s = src if asc else src[::-1]
    i = np.clip(np.searchsorted(s, targets), 1, len(s) - 1)
    left, right = s[i - 1], s[i]
    i = np.where(np.abs(targets - left) <= np.abs(targets - right), i - 1, i)
    step = abs(s[1] - s[0]) if len(s) > 1 else 1.0
    outside = (targets < s[0] - step) | (targets > s[-1] + step)
    if not asc:
        i = len(s) - 1 - i
    i[outside] = -1
    return i


def resample(win: Window, grid: Grid, band: str = "hh") -> np.ndarray:
    arr = getattr(win, band)
    if arr is None:
        return np.full(grid.shape, np.nan, "float32")
    src_res = abs(float(win.x[1] - win.x[0])) if win.x.size > 1 else grid.res
    k = int(round(grid.res / src_res)) if src_res > 0 else 1
    if k > 1:  # average source pixels inside each target pixel (also calms speckle)
        valid = np.isfinite(arr).astype("float32")
        num = uniform_filter(np.nan_to_num(arr), size=k, mode="nearest")
        den = uniform_filter(valid, size=k, mode="nearest")
        with np.errstate(invalid="ignore", divide="ignore"):
            arr = np.where(den > 0.5, num / np.maximum(den, 1e-6), np.nan).astype("float32")
    if win.epsg == grid.epsg:
        xi = _nearest_index(win.x, grid.x)
        yi = _nearest_index(win.y, grid.y)
        out = arr[np.clip(yi, 0, None)[:, None], np.clip(xi, 0, None)[None, :]]
        out = out.astype("float32")
        out[(yi < 0)[:, None] | (xi < 0)[None, :]] = np.nan
        return out
    from pyproj import Transformer
    t = Transformer.from_crs(grid.epsg, win.epsg, always_xy=True)
    gx, gy = np.meshgrid(grid.x, grid.y)
    sx, sy = t.transform(gx, gy)
    xi = _nearest_index(win.x, sx.ravel()).reshape(gx.shape)
    yi = _nearest_index(win.y, sy.ravel()).reshape(gx.shape)
    out = arr[np.clip(yi, 0, None), np.clip(xi, 0, None)].astype("float32")
    out[(xi < 0) | (yi < 0)] = np.nan
    return out
