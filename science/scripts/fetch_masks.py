"""Download reference masks (Copernicus DEM 30m, JRC water occurrence, ESA WorldCover) for an area.

Usage: python scripts/fetch_masks.py nile_sudd
Only the analysis window (plus a margin) is read from the public COGs via HTTP range requests.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import rasterio
from rasterio.io import MemoryFile
from rasterio.merge import merge
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
MARGIN = 0.02  # degrees around the window

# area -> (west, south, east, north) analysis window (matches the cached pass window)
WINDOWS = {"nile_sudd": (30.4, 7.4, 30.6, 7.6)}

DEM = "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif"
JRC = "https://storage.googleapis.com/global-surface-water/downloads2021/occurrence/occurrence_{lon}{ew}_{lat}{ns}v1_4_2021.tif"
WC = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{ns}{lat:02d}{ew}{lon:03d}_Map.tif"


def _ns(v): return "N" if v >= 0 else "S"
def _ew(v): return "E" if v >= 0 else "W"


def tiles(bbox, step, template):
    """Tile URLs covering bbox for a grid of `step` degrees (tile id = lower-left corner)."""
    w, s, e, n = bbox
    return [template(la, lo)
            for la in range(math.floor(s / step) * step, math.floor(n / step) * step + 1, step)
            for lo in range(math.floor(w / step) * step, math.floor(e / step) * step + 1, step)]


def dem_url(la, lo): return DEM.format(ns=_ns(la), lat=abs(la), ew=_ew(lo), lon=abs(lo))
def wc_url(la, lo): return WC.format(ns=_ns(la), lat=abs(la), ew=_ew(lo), lon=abs(lo))
def jrc_url(la, lo):  # JRC tiles are 10 deg, named by the upper-left corner
    return JRC.format(lon=abs(lo), ew=_ew(lo), lat=abs(la + 10), ns=_ns(la + 10))


def crop(urls, bbox, out):
    parts = []
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        for u in urls:
            with rasterio.open("/vsicurl/" + u) as src:
                win = from_bounds(*bbox, transform=src.transform).round_offsets().round_lengths()
                parts.append((src.read(window=win), src.window_transform(win), src.profile))
    prof = parts[0][2]
    if len(parts) == 1:
        data, tr = parts[0][0], parts[0][1]
    else:  # tile boundary crossed: merge the pieces
        mfs = [MemoryFile() for _ in parts]
        dss = []
        for mf, (d, t, p) in zip(mfs, parts):
            ds = mf.open(driver="GTiff", height=d.shape[1], width=d.shape[2], count=d.shape[0],
                         dtype=d.dtype, crs=p["crs"], transform=t, nodata=p.get("nodata"))
            ds.write(d)
            dss.append(ds)
        data, tr = merge(dss)
    for k in ("blockxsize", "blockysize", "tiled", "interleave"):
        prof.pop(k, None)
    prof.update(driver="GTiff", height=data.shape[1], width=data.shape[2], transform=tr, count=data.shape[0],
                compress="deflate")
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **prof) as dst:
        dst.write(data)
    print(f"{out.name}: {data.shape} {out.stat().st_size / 1e3:.0f} kB")


def main(area):
    w, s, e, n = WINDOWS[area]
    bbox = (w - MARGIN, s - MARGIN, e + MARGIN, n + MARGIN)
    out = ROOT / "data" / "reference" / area
    crop(tiles(bbox, 1, dem_url), bbox, out / "dem_copernicus30.tif")
    crop(tiles(bbox, 10, jrc_url), bbox, out / "jrc_occurrence.tif")
    crop(tiles(bbox, 3, wc_url), bbox, out / "worldcover.tif")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "nile_sudd")
