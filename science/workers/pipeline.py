"""Real analysis pipeline behind api.jobs.run_analysis: catalogue -> window read -> detect_change -> OPERA check.

Returns None when no real data covers the request, so the caller can fall back to the labelled sample.
"""
from __future__ import annotations

import csv
import glob
import math
import os
from pathlib import Path

import numpy as np

from api.schemas import PassRef
from methods.floods import detect_change
from workers.fetch import fetch_passes

ROOT = Path(__file__).resolve().parents[1]
QUALITY = {"BE": "BETA", "PR": "PROVISIONAL", "VA": "VALIDATED"}
MAX_AOI_KM = 60.0
SLOPE_MAX_NOTE = "Terrain slope and permanent-water masks were applied."
TUNING_NOTE = ("Water threshold was tuned on Tonle Sap (Oct 2026, against OPERA); accuracy in other areas is unknown. "
               "Edge pixels shrink by about 2 px; flooded forest can look like no change.")


def _km(lat0, lon0, lat1, lon1):
    return math.hypot((lat1 - lat0) * 111.32, (lon1 - lon0) * 111.32 * math.cos(math.radians((lat0 + lat1) / 2)))


def nearest_area(bbox, centres=None):
    path = ROOT / "data" / "catalog" / "aoi_centres.csv"
    if centres is None:
        if not path.exists():
            return None
        centres = [(r["area"], float(r["lat"]), float(r["lon"])) for r in csv.DictReader(path.open())]
    lat, lon = (bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2
    best = min(((_km(lat, lon, a, o), n) for n, a, o in centres), default=None)
    return best[1] if best and best[0] <= MAX_AOI_KM else None


def _rows(area):
    with (ROOT / "data" / "catalog" / "pass_counts.csv").open(newline="") as f:
        return [r for r in csv.DictReader(f) if r["area"] == area and r.get("in_gap", "").lower() != "true"]


def _passref(r):
    q = QUALITY.get(r["quality"].split(";")[0].split("=")[-1], "BETA")
    return PassRef(r["scene"], r["date"], int(r["track"]), r["direction"], int(r["frame"]), q)


def pick_passes(rows, b0, b1, a0, a1, n=3):
    """Best single geometry: most passes on the thinner side. Latest n passes in each range."""
    groups = {}
    for r in rows:
        groups.setdefault((r["track"], r["direction"], r["frame"]), []).append(r)
    best, score = None, -1
    for g in groups.values():
        g.sort(key=lambda r: r["date"])
        bef = [r for r in g if b0 <= r["date"] <= b1][-n:]
        aft = [r for r in g if a0 <= r["date"] <= a1][-n:]
        s = min(len(bef), len(aft))
        if s > score:
            best, score = (bef, aft), s
    return best


def _ref(r, data_dir):
    local = Path(data_dir) / f"{r['scene']}.h5"
    return {"scene": r["scene"], "path": str(local)} if local.exists() else {"scene": r["scene"], "url": r["url"]}


def _onto(tif, win, resampling):
    import rasterio
    from rasterio.warp import reproject
    dst = np.full(win["shape"], np.nan, np.float32)
    with rasterio.open(tif) as s:
        reproject(rasterio.band(s, 1), dst, dst_transform=win["transform"], dst_crs=win["crs"], resampling=resampling)
    return dst


def _masks(area, win):
    """(permanent_water, slope_deg) from data/reference/<name>/ if present, else (None, None)."""
    from rasterio.enums import Resampling
    d = ROOT / "data" / "reference" / area.split("_", 1)[-1]
    jrc, dem = d / "jrc_occurrence.tif", d / "dem_copernicus30.tif"
    if not (jrc.exists() and dem.exists()):
        return None, None
    z = _onto(dem, win, Resampling.bilinear)
    gy, gx = np.gradient(z, abs(win["transform"].a))
    return np.nan_to_num(_onto(jrc, win, Resampling.nearest)) >= 90, np.degrees(np.arctan(np.hypot(gx, gy)))


def _opera_grid(patterns, win):
    import rasterio
    from rasterio.warp import reproject
    from rasterio.enums import Resampling
    out = np.full(win["shape"], 255, np.uint8)
    for f in sorted(p for pat in patterns for p in glob.glob(pat)):
        tmp = np.full(win["shape"], 255, np.uint8)
        with rasterio.open(f) as s:
            reproject(rasterio.band(s, 1), tmp, dst_transform=win["transform"], dst_crs=win["crs"],
                      resampling=Resampling.nearest, dst_nodata=255)
        out = np.where(out == 255, tmp, out)
    return out


def opera_agreement(labels, win, area, before_date, after_date):
    """Agreement of 'likely_became_water' with OPERA new water (water after, not water before). None if no reference."""
    d = ROOT / "data" / "reference" / area.split("_", 1)[-1]
    s1 = [str(d / f"OPERA_L3_DSWx-S1_*_{after_date.replace('-', '')}T*")]
    hls = sorted(glob.glob(str(d / "OPERA_L3_DSWx-HLS_*")))
    if not glob.glob(s1[0]) or not hls:
        return None
    after = _opera_grid(s1, win)
    near = min(hls, key=lambda f: abs(int(os.path.basename(f).split("_")[4][:8]) - int(before_date.replace("-", ""))))
    before = _opera_grid([near], win)
    valid = np.isin(before, (0, 1, 2)) & np.isin(after, (0, 1)) & (labels != 255)
    ref, pred = (after == 1) & (before != 1) & valid, (labels == 1) & valid
    i = int((ref & pred).sum())
    ratio = lambda n, m: round(n / m, 3) if m else None
    return {"source": "OPERA DSWx", "overlap": ratio(i, int((ref | pred).sum())), "precision": ratio(i, int(pred.sum())),
            "recall": ratio(i, int(ref.sum())), "compared_fraction": round(float(valid.mean()), 3),
            "opera_files": [os.path.basename(near)] + [os.path.basename(p) for p in glob.glob(s1[0])]}


def run(req, data_dir=None, cache_dir=None):
    bbox = tuple(req["bbox"])
    area = nearest_area(bbox)
    if area is None:
        return None
    picked = pick_passes(_rows(area), req["before_start"], req["before_end"], req["after_start"], req["after_end"])
    if picked is None:
        return None
    bef, aft = picked
    data_dir = data_dir or os.environ.get("NISAR_DATA", os.path.expanduser("~/nisar_data"))
    cache_dir = cache_dir or ROOT / "data" / "cache" / "passes"
    brefs, arefs = [_passref(r) for r in bef], [_passref(r) for r in aft]
    if min(len(bef), len(aft)) < 2:   # let detect_change/assess_availability explain it
        res, _ = detect_change([], [], pixel_area_ha=0.04, bbox=bbox, before_refs=brefs, after_refs=arefs, source="live")
        return res.to_dict()
    wins = fetch_passes([_ref(r, data_dir) for r in bef + aft], bbox, cache_dir, workers=4)
    b, a = wins[:len(bef)], wins[len(bef):]
    perm, slope = _masks(area, wins[0])
    hv = all(w["HV"] is not None for w in wins)
    res, lab = detect_change([w["HH"] for w in b], [w["HH"] for w in a], pixel_area_ha=wins[0]["pixel_area_ha"],
                             bbox=bbox, before_refs=brefs, after_refs=arefs, permanent_water=perm, dem_slope_deg=slope,
                             before_hv=[w["HV"] for w in b] if hv else None, after_hv=[w["HV"] for w in a] if hv else None,
                             source="live")
    out = res.to_dict()
    if res.status != "ok":
        return out
    out["limits"] = list(out.get("limits", [])) + [TUNING_NOTE]
    out["limits"].append(SLOPE_MAX_NOTE if perm is not None else
                         "No terrain or permanent-water reference was available for this area; rivers and steep slopes are not masked.")
    out["measured"] = "Radar backscatter change (L-band HH" + ("/HV" if hv else "") + ")"
    v = opera_agreement(lab, wins[0], area, bef[-1]["date"], aft[-1]["date"])
    if v:
        out["_verify"] = v
        out["referee_files"] = v["opera_files"]
    return out
