"""Fetch supporting data for an area. Each function saves into data/drivers/<slug>/ and never raises
for a missing source (the app shows "Not checked" instead).

  rain.csv   NASA POWER daily precipitation (area mean of a 3x3 sample, no login)
  fires.csv  NASA FIRMS VIIRS hotspots (needs a free FIRMS MAP_KEY in .env as FIRMS_MAP_KEY)
  dem.tif    Copernicus DEM 30 m clipped to the area (public AWS bucket, no login)
"""
import csv
import math
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import requests

UA = {"User-Agent": "NISAR-Change-Explorer/1.0 (Space Apps 2026)"}


def fetch_rain(bbox, start: str, end: str, folder: Path) -> dict:
    """Daily precipitation (mm/day) averaged over 9 points in the area."""
    w, s, e, n = bbox
    pts = [(s + (n - s) * fy, w + (e - w) * fx) for fy in (0.2, 0.5, 0.8) for fx in (0.2, 0.5, 0.8)]
    series = {}
    for lat, lon in pts:
        r = requests.get("https://power.larc.nasa.gov/api/temporal/daily/point", headers=UA, timeout=30, params={
            "parameters": "PRECTOTCORR", "community": "AG", "latitude": round(lat, 4), "longitude": round(lon, 4),
            "start": start.replace("-", ""), "end": end.replace("-", ""), "format": "JSON"})
        r.raise_for_status()
        for k, v in r.json()["properties"]["parameter"]["PRECTOTCORR"].items():
            if v is not None and v >= 0:
                series.setdefault(k, []).append(v)
    folder.mkdir(parents=True, exist_ok=True)
    rows = [(f"{k[:4]}-{k[4:6]}-{k[6:]}", round(sum(v) / len(v), 2)) for k, v in sorted(series.items())]
    with open(folder / "rain.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["date", "mm"])
        wr.writerows(rows)
    return {"file": str(folder / "rain.csv"), "days": len(rows), "total_mm": round(sum(m for _, m in rows), 1),
            "source": "NASA POWER daily precipitation"}


def fetch_fires(bbox, start: str, end: str, folder: Path) -> dict:
    key = os.getenv("FIRMS_MAP_KEY", "")
    if not key:
        return {"skipped": "Set FIRMS_MAP_KEY in .env (free from firms.modaps.eosdis.nasa.gov/api/map_key)"}
    w, s, e, n = bbox
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    rows = []
    day = d0
    while day <= d1:  # the area API serves up to 10 days per call
        span = min(10, (d1 - day).days + 1)
        url = (f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_SP/"
               f"{w},{s},{e},{n}/{span}/{day.isoformat()}")
        r = requests.get(url, headers=UA, timeout=60)
        r.raise_for_status()
        lines = r.text.strip().splitlines()
        if len(lines) > 1 and "latitude" in lines[0]:
            hdr = lines[0].split(",")
            for ln in lines[1:]:
                rec = dict(zip(hdr, ln.split(",")))
                rows.append((rec.get("acq_date"), rec.get("latitude"), rec.get("longitude")))
        day += timedelta(days=span)
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "fires.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["date", "lat", "lon"])
        wr.writerows(rows)
    return {"file": str(folder / "fires.csv"), "hotspots": len(rows), "source": "NASA FIRMS VIIRS"}


def _dem_tile_urls(bbox):
    w, s, e, n = bbox
    out = []
    for lat in range(math.floor(s), math.floor(n) + 1):
        for lon in range(math.floor(w), math.floor(e) + 1):
            ns = f"N{lat:02d}" if lat >= 0 else f"S{-lat:02d}"
            ew = f"E{lon:03d}" if lon >= 0 else f"W{-lon:03d}"
            name = f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"
            out.append(f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif")
    return out


def fetch_dem(bbox, folder: Path) -> dict:
    """Clip Copernicus DEM 30 m to the area (reads only the needed window over HTTPS)."""
    import rasterio
    from rasterio.merge import merge
    w, s, e, n = bbox
    srcs = []
    try:
        for u in _dem_tile_urls(bbox):
            try:
                srcs.append(rasterio.open("/vsicurl/" + u))
            except Exception:
                pass
        if not srcs:
            return {"skipped": "No Copernicus DEM tile found (ocean or network blocked)"}
        arr, transform = merge(srcs, bounds=(w - 0.01, s - 0.01, e + 0.01, n + 0.01))
        prof = srcs[0].profile.copy()
        prof.update(height=arr.shape[1], width=arr.shape[2], transform=transform, driver="GTiff",
                    compress="deflate", tiled=False, blockxsize=None, blockysize=None)
        folder.mkdir(parents=True, exist_ok=True)
        with rasterio.open(folder / "dem.tif", "w", **{k: v for k, v in prof.items() if v is not None}) as dst:
            dst.write(arr)
    finally:
        for s_ in srcs:
            s_.close()
    return {"file": str(folder / "dem.tif"), "source": "Copernicus DEM GLO-30"}


def dem_on_grid(folder: Path, grid) -> np.ndarray | None:
    p = folder / "dem.tif"
    if not p.exists():
        return None
    import rasterio
    import rasterio.warp as rw
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    dst = np.full(grid.shape, np.nan, "float32")
    with rasterio.open(p) as src:
        rw.reproject(rasterio.band(src, 1), dst,
                     dst_transform=from_origin(grid.x[0] - grid.res / 2, grid.y[0] + grid.res / 2, grid.res, grid.res),
                     dst_crs=CRS.from_epsg(grid.epsg), resampling=Resampling.bilinear, dst_nodata=np.nan)
    return dst


def slope_mask(dem: np.ndarray, res: float, max_deg: float = 10.0) -> np.ndarray:
    gy, gx = np.gradient(np.nan_to_num(dem, nan=np.nanmedian(dem)), res)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    return slope > max_deg


def photo_url(bbox, day: str, width=1024) -> str:
    """NASA Worldview snapshot (true colour) for the context photo tile. Clouds are expected."""
    w, s, e, n = bbox
    h = int(width * (n - s) / max(e - w, 1e-6))
    return ("https://wvs.earthdata.nasa.gov/api/v1/snapshot?REQUEST=GetSnapshot"
            f"&TIME={day}&BBOX={s},{w},{n},{e}&CRS=EPSG:4326"
            "&LAYERS=MODIS_Terra_CorrectedReflectance_TrueColor,Coastlines_15m"
            f"&WRAP=day,x&FORMAT=image/jpeg&WIDTH={width}&HEIGHT={max(h, 64)}")


# ---------------- ESA WorldCover 10 m (land cover), open COG on AWS ----------------
WORLDCOVER_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
                  "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif")


def worldcover_tiles(bbox) -> list[str]:
    """3-degree tile names (south-west corner), e.g. N12E102, S03W060."""
    w, s, e, n = bbox
    out = []
    for la in range(int(math.floor(s / 3)) * 3, int(math.floor((n - 1e-9) / 3)) * 3 + 1, 3):
        for lo in range(int(math.floor(w / 3)) * 3, int(math.floor((e - 1e-9) / 3)) * 3 + 1, 3):
            out.append(f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}")
    return out


def worldcover_on_grid(bbox, grid) -> np.ndarray | None:
    """WorldCover class codes (uint8, 0 = no data) on the analysis grid, window read only. None if unavailable (offline etc.)."""
    try:
        import rasterio
        import rasterio.warp as rw
        from rasterio.crs import CRS
        from rasterio.enums import Resampling
        from rasterio.transform import from_origin
        from rasterio.windows import from_bounds
        out = np.zeros(grid.shape, "uint8")
        got = False
        b = [bbox[0] - 0.01, bbox[1] - 0.01, bbox[2] + 0.01, bbox[3] + 0.01]
        with rasterio.Env(GDAL_HTTP_TIMEOUT="30", GDAL_HTTP_MAX_RETRY="1", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            for t in worldcover_tiles(bbox):
                try:
                    with rasterio.open(WORLDCOVER_URL.format(tile=t)) as src:
                        win = from_bounds(*b, transform=src.transform).round_offsets().round_lengths()
                        arr = src.read(1, window=win, boundless=True, fill_value=0)
                        tmp = np.zeros(grid.shape, "uint8")
                        rw.reproject(arr, tmp, src_transform=src.window_transform(win), src_crs=src.crs,
                                     dst_transform=from_origin(grid.x[0] - grid.res / 2, grid.y[0] + grid.res / 2, grid.res, grid.res),
                                     dst_crs=CRS.from_epsg(grid.epsg), resampling=Resampling.nearest, dst_nodata=0)
                        out = np.where(out == 0, tmp, out)
                        got = True
                except Exception:
                    continue
        return out if got and (out > 0).mean() > 0.5 else None
    except Exception:
        return None
