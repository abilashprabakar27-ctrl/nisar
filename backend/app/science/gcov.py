"""Read only the study-area window of a NISAR GCOV file (HH and HV power).

GCOV layout (NISAR L2): /science/LSAR/GCOV/grids/frequencyA/{HHHH,HVHV,mask,xCoordinates,yCoordinates,projection}
Values are linear gamma-0 power on a UTM grid.
"""
from dataclasses import dataclass

import numpy as np

from .. import config

GRID = "/science/LSAR/GCOV/grids/frequencyA"


@dataclass
class Window:
    hh: np.ndarray            # linear power, NaN where invalid
    hv: np.ndarray | None
    x: np.ndarray             # pixel-centre eastings
    y: np.ndarray             # pixel-centre northings
    epsg: int
    date: str


_session = None
_login_lock = __import__("threading").Lock()
_login_error = None


class LoginFailed(RuntimeError):
    pass


def _login():
    """Log in to NASA Earthdata once (shared by all download threads). Never retries a bad password."""
    global _session, _login_error
    with _login_lock:
        if _session is not None:
            return
        if _login_error:
            raise LoginFailed(_login_error)
        import os
        import earthaccess
        try:
            if config.EARTHDATA_USERNAME:
                os.environ["EARTHDATA_USERNAME"] = config.EARTHDATA_USERNAME
                os.environ["EARTHDATA_PASSWORD"] = config.EARTHDATA_PASSWORD
                _session = earthaccess.login(strategy="environment")
            else:
                _session = earthaccess.login(strategy="netrc")
        except Exception as e:
            _login_error = ("NASA Earthdata login failed. Check EARTHDATA_USERNAME and EARTHDATA_PASSWORD in .env "
                            "(username, not email; put the password in double quotes if it contains # or spaces). "
                            f"Details: {e}")
            raise LoginFailed(_login_error) from None


_fs = None


def _open(url: str):
    """Open an HTTPS GCOV file for reading slices.

    HDF5 makes many small reads; over a long-distance link each costs ~0.3 s. Large blocks (8 MB)
    with a block cache turn hundreds of tiny requests into a handful of big ones.
    """
    global _fs
    if not url.startswith("http"):
        return url
    _login()
    import earthaccess
    if _fs is None:
        _fs = earthaccess.get_fsspec_https_session()
    return _fs.open(url, "rb", block_size=8 * 2**20, cache_type="blockcache")


class Cancelled(Exception):
    """The user stopped a download."""


class CountingFile:
    """Wraps a remote file so every byte read is reported (for download % and time left)."""

    def __init__(self, f, on_bytes=None):
        self._f, self._cb = f, on_bytes

    def _count(self, n):
        if self._cb and n:
            self._cb(n)   # may raise Cancelled
        return n

    def read(self, size=-1):
        data = self._f.read(size)
        self._count(len(data))
        return data

    def readinto(self, b):
        if hasattr(self._f, "readinto"):
            return self._count(self._f.readinto(b))
        data = self._f.read(len(b))
        b[:len(data)] = data
        return self._count(len(data))

    def seek(self, *a):
        return self._f.seek(*a)

    def tell(self):
        return self._f.tell()

    def seekable(self):
        return True

    def readable(self):
        return True

    def close(self):
        return self._f.close()

    def flush(self):
        pass

    def __getattr__(self, name):
        return getattr(self._f, name)


def is_cached(url: str, bbox) -> bool:
    return bool(url) and url.startswith("http") and _cache_path(url, bbox).exists()


def _find(f, names):
    for n in names:
        if n in f:
            return f[n]
    return None


def _epsg(f) -> int:
    proj = _find(f, [f"{GRID}/projection", f"{GRID}/listOfPolarizations/../projection"])
    if proj is not None:
        for key in ("epsg_code", "epsg"):
            if key in proj.attrs:
                return int(np.atleast_1d(proj.attrs[key])[0])
        try:
            return int(proj[()])
        except Exception:
            pass
    raise ValueError("Could not find the EPSG code in the GCOV file")


def bbox_to_utm(bbox, epsg):
    from pyproj import Transformer
    t = Transformer.from_crs(4326, epsg, always_xy=True)
    w, s, e, n = bbox
    xs, ys = zip(*[t.transform(x, y) for x, y in [(w, s), (e, s), (e, n), (w, n)]])
    return min(xs), min(ys), max(xs), max(ys)


def _cache_path(url, bbox):
    import hashlib
    key = hashlib.sha1(f"{url}|{[round(v, 4) for v in bbox]}".encode()).hexdigest()[:20]
    return config.CACHE_DIR / f"{key}.npz"


def read_window(url: str, bbox, date: str, pad_m: float = 200.0, progress=None) -> Window:
    """Read the study-area window, using the local cache when this pass was read before.
    progress(nbytes) is called as bytes arrive from NASA (used for download % and time left)."""
    cp = _cache_path(url, bbox) if url.startswith("http") else None
    if cp is not None and cp.exists():
        z = np.load(cp)
        hv = z["hv"] if z["has_hv"] else None
        return Window(hh=z["hh"], hv=hv, x=z["x"], y=z["y"], epsg=int(z["epsg"]), date=date)
    w = _read_window_remote(url, bbox, date, pad_m, progress)
    if cp is not None:
        np.savez_compressed(cp, hh=w.hh, hv=w.hv if w.hv is not None else np.zeros(1, "float32"),
                            has_hv=w.hv is not None, x=w.x, y=w.y, epsg=w.epsg)
    return w


def _read_window_remote(url: str, bbox, date: str, pad_m: float, progress=None) -> Window:
    import h5py
    src = _open(url)
    if progress is not None and not isinstance(src, str):
        src = CountingFile(src, progress)
    with h5py.File(src, "r", rdcc_nbytes=64 * 2**20) as f:
        x = f[f"{GRID}/xCoordinates"][()]
        y = f[f"{GRID}/yCoordinates"][()]
        epsg = _epsg(f)
        x0, y0, x1, y1 = bbox_to_utm(bbox, epsg)
        xi = np.where((x >= x0 - pad_m) & (x <= x1 + pad_m))[0]
        yi = np.where((y >= y0 - pad_m) & (y <= y1 + pad_m))[0]
        if xi.size == 0 or yi.size == 0:
            raise ValueError("This file does not cover the study area")
        cs, ce, rs, re_ = xi.min(), xi.max() + 1, yi.min(), yi.max() + 1
        hh = f[f"{GRID}/HHHH"][rs:re_, cs:ce].astype("float32")
        hv = f[f"{GRID}/HVHV"][rs:re_, cs:ce].astype("float32") if f"{GRID}/HVHV" in f else None
        mask = f[f"{GRID}/mask"][rs:re_, cs:ce] if f"{GRID}/mask" in f else None
    # Calm water is so dark that thermal-noise correction can clip it to exactly 0, so a zero is NOT
    # automatically "no data". Only NaN, the fill value 255, or zero with no valid subswath (mask 0) are invalid.
    floor = 1e-4  # -40 dB
    bad = ~np.isfinite(hh)
    if mask is not None:
        bad |= (mask == 255) | ((mask == 0) & ~(hh > 0))
    else:
        bad |= hh < 0
    hh = np.where(bad, np.nan, np.maximum(hh, floor)).astype("float32")
    if hv is not None:
        hv = np.where(bad | ~np.isfinite(hv), np.nan, np.maximum(hv, floor * 0.1)).astype("float32")
    return Window(hh=hh, hv=hv, x=x[cs:ce], y=y[rs:re_], epsg=epsg, date=date)
