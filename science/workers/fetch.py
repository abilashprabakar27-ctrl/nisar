"""Windowed reads of NISAR L2 GCOV HDF5 files (local path or https URL).

Never downloads a whole product: reads the two 1-D coordinate vectors, works
out the row/col slice for the requested lon/lat box, then slices the 2-D
datasets so HDF5 (and, for URLs, HTTP range requests) touch only that window.

Layout (paths confirmed against nisar-docs.asf.alaska.edu/gcov; the coordinate,
projection, fill and mask conventions are assumptions -- see
docs/golden_sample_runbook.md):
  /science/LSAR/GCOV/grids/frequencyA/{HHHH,HVHV,...}  2-D real, linear gamma0 power
  .../xCoordinates, .../yCoordinates                    1-D pixel-centre metres
  .../projection                                        EPSG in attr `epsg_code` (or value)
  .../mask, .../numberOfLooks                           optional 2-D layers
"""
from __future__ import annotations

import hashlib
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import h5py
import numpy as np
from affine import Affine
from pyproj import Geod, Transformer

GRID_ROOT = "/science/LSAR/GCOV/grids"
MAX_WINDOW_M = 25_000.0
HTTP_BLOCK_BYTES = 4 * 1024 * 1024
MASK_INVALID = 0          # assumed: 0 = no valid radar samples, 1..5 = sub-swath id
MASK_FILL = 255           # assumed mask _FillValue when the attribute is absent
_GEOD = Geod(ellps="WGS84")
_CACHE_VERSION = "v1"


def _open(path_or_url: str, token_env: str = "EARTHDATA_TOKEN"):
    """Return (h5py.File, closer). URLs go through fsspec so reads are ranged."""
    if "://" not in str(path_or_url):
        f = h5py.File(path_or_url, "r")
        return f, f.close
    import fsspec

    kwargs = {}
    if str(path_or_url).startswith(("http://", "https://")):
        kwargs = {"block_size": HTTP_BLOCK_BYTES, "cache_type": "blockcache"}
        token = os.environ.get(token_env or "", "")
        if token:  # the token is only ever placed in the request header
            kwargs["headers"] = {"Authorization": f"Bearer {token}"}
    of = fsspec.open(path_or_url, "rb", **kwargs)
    fobj = of.open()
    try:
        f = h5py.File(fobj, "r")
    except Exception as e:
        of.close()
        # Do not chain the original: its text can carry a signed redirect URL.
        raise OSError(f"could not open remote HDF5 ({type(e).__name__}); "
                      f"check the URL and ${token_env}") from None

    def close():
        try:
            f.close()
        finally:
            of.close()

    return f, close


def _epsg(grid) -> int:
    if "projection" not in grid:
        raise ValueError("file has no `projection` dataset; cannot determine CRS")
    p = grid["projection"]
    for k in ("epsg_code", "epsg", "EPSG"):
        if k in p.attrs:
            return int(np.asarray(p.attrs[k]).ravel()[0])
    try:
        v = int(np.asarray(p[()]).ravel()[0])
        if v > 1000:
            return v
    except (TypeError, ValueError):
        pass
    raise ValueError("`projection` dataset has no EPSG attribute or value")


def _spacing(grid, name, coords) -> float:
    if name in grid:
        return float(np.asarray(grid[name][()]).ravel()[0])
    if coords.size < 2:
        raise ValueError(f"cannot derive {name}: coordinate vector has < 2 samples")
    return float((coords[-1] - coords[0]) / (coords.size - 1))


def _slice(coords, lo, hi) -> slice | None:
    """Contiguous index range of pixel centres within [lo, hi]; None if empty."""
    idx = np.flatnonzero((coords >= lo) & (coords <= hi))
    if idx.size == 0:
        return None
    return slice(int(idx[0]), int(idx[-1]) + 1)


def _bbox_size_m(bbox):
    w, s, e, n = bbox
    mid = 0.5 * (s + n)
    width = _GEOD.line_length([w, e], [mid, mid])
    height = _GEOD.line_length([w, w], [s, n])
    return width, height


def _read_layer(ds, rows, cols) -> np.ndarray:
    a = ds[rows, cols]
    if np.iscomplexobj(a):
        raise ValueError(f"{ds.name} is complex; only real diagonal terms (HHHH, HVHV, ...) are supported")
    a = np.asarray(a, dtype=np.float32)
    fill = ds.attrs.get("_FillValue")
    if fill is not None:
        fill = float(np.asarray(fill).ravel()[0])
        if not math.isnan(fill):
            a[a == np.float32(fill)] = np.nan
    a[~np.isfinite(a)] = np.nan
    return a


def read_window(path_or_url: str, bbox_lonlat: tuple[float, float, float, float],
                pols=("HHHH", "HVHV"), token_env="EARTHDATA_TOKEN", *,
                frequency: str = "A", apply_mask: bool = True) -> dict:
    """Read a <=25x25 km window of GCOV backscatter (linear power, NaN = nodata).

    bbox_lonlat is (west, south, east, north) in degrees. Returns a dict with one
    key per requested pol (first two letters, e.g. "HH"; None when the file lacks
    it), plus transform, crs, pixel_area_ha, shape, nodata_fraction.
    """
    w, s, e, n = (float(v) for v in bbox_lonlat)
    if not (w < e and s < n):
        raise ValueError(f"bbox must be (west, south, east, north) with west<east and south<north, got {bbox_lonlat}")
    width_m, height_m = _bbox_size_m((w, s, e, n))
    if max(width_m, height_m) > MAX_WINDOW_M * (1 + 1e-6):
        raise ValueError(f"bbox is {width_m / 1000:.1f} x {height_m / 1000:.1f} km; "
                         f"the limit is {MAX_WINDOW_M / 1000:.0f} x {MAX_WINDOW_M / 1000:.0f} km")

    f, close = _open(path_or_url, token_env)
    try:
        gpath = f"{GRID_ROOT}/frequency{frequency}"
        if gpath not in f:
            raise ValueError(f"file has no {gpath} group (not a GCOV product, or frequency{frequency} absent)")
        grid = f[gpath]
        epsg = _epsg(grid)
        x = np.asarray(grid["xCoordinates"][()], dtype=np.float64)
        y = np.asarray(grid["yCoordinates"][()], dtype=np.float64)
        dx = _spacing(grid, "xCoordinateSpacing", x)
        dy = _spacing(grid, "yCoordinateSpacing", y)

        tf = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        xmin, ymin, xmax, ymax = tf.transform_bounds(w, s, e, n, densify_pts=21)
        cols, rows = _slice(x, xmin, xmax), _slice(y, ymin, ymax)
        if cols is None or rows is None:
            hx, hy = abs(dx) / 2, abs(dy) / 2
            raise ValueError(
                f"bbox {(w, s, e, n)} does not intersect the file: bbox in EPSG:{epsg} is "
                f"x[{xmin:.0f},{xmax:.0f}] y[{ymin:.0f},{ymax:.0f}], file covers "
                f"x[{x.min() - hx:.0f},{x.max() + hx:.0f}] y[{y.min() - hy:.0f},{y.max() + hy:.0f}]")
        # Hard clip (grid convergence can inflate the projected envelope slightly).
        max_c = max(1, int(MAX_WINDOW_M // abs(dx)))
        max_r = max(1, int(MAX_WINDOW_M // abs(dy)))
        cols = slice(cols.start, min(cols.stop, cols.start + max_c))
        rows = slice(rows.start, min(rows.stop, rows.start + max_r))
        shape = (rows.stop - rows.start, cols.stop - cols.start)

        invalid = np.zeros(shape, bool)
        if apply_mask and "mask" in grid:
            m = grid["mask"]
            mw = np.asarray(m[rows, cols])
            fill = m.attrs.get("_FillValue", MASK_FILL)
            invalid = (mw == MASK_INVALID) | (mw == np.asarray(fill).ravel()[0])

        out: dict = {}
        nodata = invalid.copy()
        for pol in pols:
            key = pol[:2]
            if pol in grid:
                a = _read_layer(grid[pol], rows, cols)
                a[invalid] = np.nan
                nodata |= np.isnan(a)
                out[key] = a
            else:
                out[key] = None
        if all(out[p[:2]] is None for p in pols):
            nodata[:] = True

        x0 = x[cols.start] - dx / 2          # coordinates are pixel centres
        y0 = y[rows.start] - dy / 2
        out.update(
            transform=Affine(dx, 0.0, x0, 0.0, dy, y0),
            crs=f"EPSG:{epsg}",
            pixel_area_ha=abs(dx * dy) / 10_000.0,
            shape=shape,
            nodata_fraction=float(nodata.mean()) if nodata.size else 1.0,
        )
        return out
    finally:
        close()


def window_key(scene: str, bbox) -> str:
    """Stable sha1 cache key for (pass id, area)."""
    b = ",".join(f"{float(v):.6f}" for v in bbox)
    return hashlib.sha1(f"{_CACHE_VERSION}|{scene}|{b}".encode()).hexdigest()


def _ref_parts(ref):
    """A ref is a path/URL string or a dict with scene/id and url/path."""
    if isinstance(ref, (str, os.PathLike)):
        src = str(ref)
        return Path(src.split("?")[0]).stem, src
    src = ref.get("path") or ref.get("url")
    if not src:
        raise ValueError("pass ref needs a 'path' or 'url'")
    scene = ref.get("scene") or ref.get("id") or Path(str(src).split("?")[0]).stem
    return str(scene), str(src)


_ARRAYS = ("HH", "HV", "VV", "VH")


def _save(path: Path, win: dict) -> None:
    data = {k: v for k, v in win.items() if isinstance(v, np.ndarray)}
    data["_none"] = np.array([k for k, v in win.items() if v is None], dtype="U8")
    data["_transform"] = np.array(tuple(win["transform"])[:6], dtype=np.float64)
    data["_crs"] = np.array(win["crs"])
    data["_scalars"] = np.array([win["pixel_area_ha"], win["nodata_fraction"]], dtype=np.float64)
    data["_shape"] = np.array(win["shape"], dtype=np.int64)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with open(tmp, "wb") as fh:
        np.savez(fh, **data)
    os.replace(tmp, path)


def _load(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as z:
        win = {k: z[k] for k in z.files if not k.startswith("_")}
        win.update({str(k): None for k in z["_none"]})
        win.update(
            transform=Affine(*z["_transform"].tolist()),
            crs=str(z["_crs"]),
            pixel_area_ha=float(z["_scalars"][0]),
            shape=tuple(int(v) for v in z["_shape"]),
            nodata_fraction=float(z["_scalars"][1]),
        )
    return win


def fetch_passes(refs, bbox, cache_dir, workers: int = 4, on_step=None, *,
                 pols=("HHHH", "HVHV"), token_env="EARTHDATA_TOKEN") -> list[dict]:
    """Read the same window from several passes in parallel, in input order.

    Each result is the read_window dict plus "scene", "ref" and "cached".
    Windows are cached as <cache_dir>/<window_key>.npz. Step messages carry the
    scene id only (never the URL or token).
    """
    refs = list(refs)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    total = len(refs)

    def step(msg):
        if on_step is not None:
            with lock:
                on_step(msg)

    def one(item):
        i, ref = item
        scene, src = _ref_parts(ref)
        key = window_key(scene + "|" + ",".join(pols), bbox)
        fp = cache / f"{key}.npz"
        win, cached = None, False
        if fp.exists():
            try:
                win, cached = _load(fp), True
            except Exception:
                win = None  # corrupt/partial cache entry: reread
        if win is None:
            step(f"fetching pass {i + 1}/{total}: {scene}")
            win = read_window(src, bbox, pols=pols, token_env=token_env)
            _save(fp, win)
        else:
            step(f"cache hit pass {i + 1}/{total}: {scene}")
        win.update(scene=scene, ref=ref, cached=cached)
        return win

    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
        return list(ex.map(one, enumerate(refs)))
