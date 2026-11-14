"""Driver evidence (interpretation only, never causal claims).

Rainfall comes from NASA GPM IMERG daily files (3B-DAY-L.MS.MRG.3IMERG, V07C).
Layout of each file: `precipitation` (time, lon, lat) mm/day, `lon`, `lat`
(0.1 deg cell centres), fill -9999.9.  bbox everywhere = (west, south, east, north).
"""
from __future__ import annotations

import datetime as dt
import statistics
from pathlib import Path

import numpy as np

# --- explicit rule constants -------------------------------------------------
ANTECEDENT_DAYS = 14
TOTAL_RATIO_LIKELY = 1.5   # antecedent total >= 1.5 x series-median 14-day total
MAX_DAILY_MM_HEAVY = 25.0  # a single day >= 25 mm
WET_DAY_MM = 1.0
BBOX_PAD_DEG = 0.2
LOW_SHARE_LIKELY = 0.6     # terrain: share of low+flat pixels
LOW_SHARE_POSSIBLE = 0.3
FLAT_SLOPE_DEG = 2.0
LOW_HEIGHT_M = 15.0
IMERG_RES = 0.1
IMERG_PATTERN = "3B-DAY-L.MS.MRG.3IMERG.{ymd}-S000000-E235959.V07C.nc4"


def _daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def read_rain_series(bbox, start, end, imerg_dir, return_missing=False):
    """Mean mm/day over bbox (padded 0.2 deg, >=1 cell) for each available date."""
    import h5py

    w, s, e, n = bbox
    w, s, e, n = w - BBOX_PAD_DEG, s - BBOX_PAD_DEG, e + BBOX_PAD_DEG, n + BBOX_PAD_DEG
    i0 = int(np.floor((w + 180.0) / IMERG_RES))
    i1 = max(int(np.ceil((e + 180.0) / IMERG_RES)), i0 + 1)
    j0 = int(np.floor((s + 90.0) / IMERG_RES))
    j1 = max(int(np.ceil((n + 90.0) / IMERG_RES)), j0 + 1)
    i0, j0 = max(i0, 0), max(j0, 0)
    series, missing = [], []
    for d in _daterange(start, end):
        p = Path(imerg_dir) / IMERG_PATTERN.format(ymd=d.strftime("%Y%m%d"))
        if not p.exists():
            missing.append(d)
            continue
        with h5py.File(p, "r") as f:
            ds = f["precipitation"]
            a = np.asarray(ds[0, i0:i1, j0:j1], dtype="float64")
        a[a < 0] = np.nan
        series.append((d, float(np.nanmean(a)) if np.isfinite(a).any() else float("nan")))
    return (series, missing) if return_missing else series


def _label(n_true: int) -> str:
    return {2: "Likely", 1: "Possible"}.get(n_true, "Not supported")


def rain_driver(series, change_date_range, antecedent_days=ANTECEDENT_DAYS):
    """Heavy-rain driver from the antecedent window before the change period.

    Window = the `antecedent_days` days ending at the change range start (inclusive).
    """
    base = {"driver": "heavy_rain", "interpretation": True}
    clean = [(d, v) for d, v in series if v is not None and np.isfinite(v)]
    if not clean:
        return {**base, "label": "Not supported", "evidence": {},
                "note": "No rainfall data for this window."}
    cstart = change_date_range[0]
    wstart = cstart - dt.timedelta(days=antecedent_days - 1)
    win = [v for d, v in clean if wstart <= d <= cstart]
    if not win:
        return {**base, "label": "Not supported", "evidence": {},
                "note": "No rainfall data in the antecedent window."}
    vals = [v for _, v in clean]
    # the series' own season: every rolling window of the same length
    roll = [sum(vals[i:i + antecedent_days]) for i in range(max(len(vals) - antecedent_days + 1, 1))]
    median = statistics.median(roll)
    total, mx = sum(win), max(win)
    pct = 100.0 * sum(r <= total for r in roll) / len(roll)
    wet = sum(v >= WET_DAY_MM for v in win)
    total_hit = total >= TOTAL_RATIO_LIKELY * median and median > 0
    heavy_hit = mx >= MAX_DAILY_MM_HEAVY
    label = _label(int(total_hit) + int(heavy_hit))
    ev = {"antecedent_total_mm": round(total, 1), "max_daily_mm": round(mx, 1),
          "wet_days": wet, "window_days": len(win),
          "series_median_total_mm": round(median, 1),
          "percentile_vs_series": round(pct, 0),
          "rule": f"total>={TOTAL_RATIO_LIKELY}x median and max daily>={MAX_DAILY_MM_HEAVY} mm"}
    note = {"Likely": "Rainfall in the weeks before the change was unusually heavy for this series; consistent with rain-driven flooding.",
            "Possible": "Rainfall was elevated on one measure; may have contributed.",
            "Not supported": "Rainfall before the change was not unusual for this series."}[label]
    return {**base, "label": label, "evidence": ev, "note": note + " (IMERG, interpretation only)"}


def terrain_driver(dem_path, bbox=None, max_height_m=LOW_HEIGHT_M, max_slope_deg=FLAT_SLOPE_DEG):
    """Share of DEM pixels that are low-lying (<= max_height_m) and flat (< max_slope_deg)."""
    import rasterio
    from rasterio.windows import from_bounds

    base = {"driver": "low_flat_terrain", "interpretation": True}
    with rasterio.open(dem_path) as ds:
        win = from_bounds(*bbox, transform=ds.transform) if bbox else None
        z = ds.read(1, window=win, masked=True).astype("float64").filled(np.nan)
        tr = ds.window_transform(win) if win else ds.transform
        lat = tr.f + tr.e * z.shape[0] / 2
    if z.size == 0 or not np.isfinite(z).any():
        return {**base, "label": "Not supported", "evidence": {}, "note": "No elevation data."}
    dy = abs(tr.e) * 111320.0
    dx = abs(tr.a) * 111320.0 * np.cos(np.radians(lat))
    gy, gx = np.gradient(z, dy, dx)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    ok = np.isfinite(z) & np.isfinite(slope)
    share = float(np.mean((z[ok] <= max_height_m) & (slope[ok] < max_slope_deg)))
    label = "Likely" if share >= LOW_SHARE_LIKELY else "Possible" if share >= LOW_SHARE_POSSIBLE else "Not supported"
    return {**base, "label": label,
            "evidence": {"low_flat_share": round(share, 3), "max_height_m": max_height_m,
                         "max_slope_deg": max_slope_deg,
                         "median_elevation_m": round(float(np.median(z[ok])), 1)},
            "note": f"{share:.0%} of the area is low-lying and flat; water can pond or spread easily there (interpretation only)."}


def collect_drivers(bbox, change_date_range, imerg_dir=None, dem_path=None,
                    season_start=None, season_end=None):
    """List of driver dicts; sources that are not supplied are skipped."""
    out = []
    if imerg_dir:
        c0, c1 = change_date_range
        s0 = season_start or c0 - dt.timedelta(days=60)
        s1 = season_end or c1
        out.append(rain_driver(read_rain_series(bbox, s0, s1, imerg_dir), change_date_range))
    if dem_path:
        out.append(terrain_driver(dem_path, bbox))
    return out
