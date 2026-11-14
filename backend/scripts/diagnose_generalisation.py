"""Why does the water-change method over-predict new water on the south neighbour, and what fixes generalise?

Does NOT change the method: it imports app.science.change.detect_water_change (frozen v4b) and applies
post-filters / re-runs with more passes on top of its output. Scoring is the strict score of eval_tonlesap.py
(became-water vs OPERA new water, only where OPERA is valid).

Stages (each reads/writes a cache dir, so heavy steps run once):
    prep NAME      read NISAR passes (4 before + 4 after, track 083), OPERA, DEM, JRC, ESA WorldCover for a window
    diagnose       false/true-positive tables on the neighbour, missed detections on the main window
    candidates     tune each candidate on WEST only, report EAST / neighbour / fresh windows
Windows: main (west/east halves), nbr (0.22 deg south), fresh (0.44 deg south = never tuned on), fresh_e (0.22 deg east).

    PYTHONPATH=/home/sanjayvasudevan/nasa/pydeps:backend \
      /home/sanjayvasudevan/nasa/nasa_project/.venv/bin/python backend/scripts/diagnose_generalisation.py prep main
Dates: before = 2026-06-19, 07-01, 07-13, 07-25; after = 09-23, 10-05, 10-17, 10-29. The frozen method uses
before 07-13/07-25 and after 09-23/10-05 (indices 2,3 / 4,5). Later after-dates are used only by candidates
that say so; no after-date data ever enters a "before" input.
"""
import argparse
import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
from scipy import ndimage

os.environ.setdefault("NCE_DATA_DIR", "/home/sanjayvasudevan/nasa/team_data")   # pipeline cache of NISAR windows (Kanpur)
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import config  # noqa: E402
from app.science import change  # noqa: E402
from app.science.grid import make_grid, resample  # noqa: E402
import eval_tonlesap as ev  # noqa: E402  (imported only for its data helpers and metric; not modified)

CACHE = BACKEND / "data" / "diag_cache"
BEFORE = ["2026-06-19", "2026-07-01", "2026-07-13", "2026-07-25"]
AFTER = ["2026-09-23", "2026-10-05", "2026-10-17", "2026-10-29"]
BI, AI = [2, 3], [0, 1]          # frozen v4b inputs (indices into BEFORE / AFTER)
MAIN = ev.BBOX
SHIFT = {"main": (0.0, 0.0), "nbr": (-0.22, 0.0), "fresh": (-0.44, 0.0), "fresh_e": (0.0, 0.22)}
WC_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{t}_Map.tif"
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N{la:02d}_00_E{lo:03d}_00_DEM/"
           "Copernicus_DSM_COG_10_N{la:02d}_00_E{lo:03d}_00_DEM.tif")
JRC_URL = "https://storage.googleapis.com/global-surface-water/downloads2021/occurrence/occurrence_{lo}{ew}_{la}{ns}v1_4_2021.tif"
WC_NAMES = {10: "tree", 20: "shrub", 30: "grass", 40: "cropland", 50: "built", 60: "bare", 80: "water",
            90: "herb.wetland", 95: "mangrove", 0: "nodata"}


def bbox_of(name):
    dy, dx = SHIFT[name]
    return [MAIN[0] + dx, MAIN[1] + dy, MAIN[2] + dx, MAIN[3] + dy]


# ------------------------------------------------------------------ static layers (window reads only)
def _read_cog(url, grid, bbox, resampling, dtype, nodata):
    import rasterio
    import rasterio.warp as rw
    from rasterio.crs import CRS
    from rasterio.transform import from_origin
    from rasterio.windows import from_bounds
    out = np.full(grid.shape, nodata, dtype)
    with rasterio.open(url) as src:
        b = [bbox[0] - 0.01, bbox[1] - 0.01, bbox[2] + 0.01, bbox[3] + 0.01]
        win = from_bounds(*b, transform=src.transform).round_offsets().round_lengths()
        arr = src.read(1, window=win, boundless=True, fill_value=nodata)
        tr = src.window_transform(win)
        rw.reproject(arr, out, src_transform=tr, src_crs=src.crs,
                     dst_transform=from_origin(grid.x[0] - grid.res / 2, grid.y[0] + grid.res / 2, grid.res, grid.res),
                     dst_crs=CRS.from_epsg(grid.epsg), resampling=resampling, dst_nodata=nodata)
    return out


def jrc_url(bbox):
    lo, la = int(np.floor(bbox[0] / 10) * 10), int(np.floor(bbox[3] / 10) * 10) + 10   # 10 deg tile, named by its top-left corner
    return JRC_URL.format(lo=abs(lo), ew="E" if lo >= 0 else "W", la=abs(la), ns="N" if la >= 0 else "S")


def static_layers(grid, bbox, with_dem=True):
    from rasterio.enums import Resampling
    t = f"N{int(np.floor(bbox[1] / 3) * 3):02d}E{int(np.floor(bbox[0] / 3) * 3):03d}"
    wc = _read_cog(WC_URL.format(t=t), grid, bbox, Resampling.nearest, "uint8", 0)
    dem = np.full(grid.shape, np.nan, "float32")
    for la in (range(int(np.floor(bbox[1])), int(np.floor(bbox[3])) + 1) if with_dem else []):
        for lo in range(int(np.floor(bbox[0])), int(np.floor(bbox[2])) + 1):
            d = _read_cog(DEM_URL.format(la=la, lo=lo), grid, bbox, Resampling.bilinear, "float32", np.nan)
            dem = np.where(np.isfinite(dem), dem, d)
    jrc = _read_cog(jrc_url(bbox), grid, bbox, Resampling.nearest, "uint8", 255)
    return wc, dem, jrc


def prep(name):
    CACHE.mkdir(parents=True, exist_ok=True)
    bbox = bbox_of(name)
    wins = [ev.read_window(ev.pass_file("083", d), bbox, d) for d in BEFORE + AFTER]
    grid = make_grid(bbox, wins[0].epsg, 20.0)
    hh = np.stack([resample(w, grid, "hh") for w in wins]).astype("float32")
    hv = np.stack([resample(w, grid, "hv") for w in wins]).astype("float32")
    del wins
    before_o, after_o, used = ev.opera_layers(grid, BEFORE[-1], AFTER[1])
    wc, dem, jrc = static_layers(grid, bbox)
    np.savez_compressed(CACHE / f"{name}.npz", hh=hh, hv=hv, before_o=before_o, after_o=after_o, wc=wc, dem=dem,
                        jrc=jrc, gx=grid.x, gy=grid.y, epsg=grid.epsg)
    print(f"{name}: shape {grid.shape}, OPERA files {used}")


class Win:
    """Everything for one window, loaded from the cache."""

    def __init__(self, name):
        z = np.load(CACHE / f"{name}.npz")
        self.name = name
        self.hh, self.hv = z["hh"], z["hv"]
        self.before_o, self.after_o = z["before_o"], z["after_o"]
        self.wc, self.dem, self.jrc = z["wc"], z["dem"], z["jrc"]
        self.grid = type("G", (), {})()
        self.grid.x, self.grid.y, self.grid.epsg, self.grid.res = z["gx"], z["gy"], int(z["epsg"]), 20.0
        self.grid.shape = (self.grid.y.size, self.grid.x.size)
        self.grid.pixel_ha = 0.04
        self.shape = self.grid.shape
        self.lee = config_lee = 7
        dem = np.where(np.isfinite(self.dem), self.dem, np.nanmedian(self.dem))
        gy, gx = np.gradient(dem, 20.0)
        self.slope = np.degrees(np.arctan(np.hypot(gx, gy)))
        self.extra = self.slope > 10.0
        # per-pass Lee-filtered dB, the same filter the method applies
        self.hh_db = np.stack([change.lee_filter(change.to_db(a), 7) for a in self.hh])
        self.hv_db = np.stack([change.lee_filter(change.to_db(a), 7) for a in self.hv])
        # valid = where OPERA's two products are usable (the strict-score rule)
        self.valid = np.isin(self.before_o, (0, 1, 2)) & np.isin(self.after_o, (0, 1))
        self.ref = (self.after_o == 1) & (self.before_o != 1)
        self.regions = {"whole": (slice(None), slice(None))}
        if name == "main":
            from pyproj import Transformer
            t = Transformer.from_crs(4326, self.grid.epsg, always_xy=True)
            xmid = t.transform((MAIN[0] + MAIN[2]) / 2, (MAIN[1] + MAIN[3]) / 2)[0]
            k = int(np.searchsorted(self.grid.x, xmid))
            self.regions.update({"west": (slice(None), slice(0, k)), "east": (slice(None), slice(k, None))})
        # distance / height above JRC water (occurrence >= 75 %), general data, no site constants
        water = self.jrc >= 75
        if water.any():
            d, (iy, ix) = ndimage.distance_transform_edt(~water, return_indices=True, sampling=20.0)
            self.dist_jrc = d.astype("float32")
            self.hand = (dem - dem[iy, ix]).astype("float32")
        else:
            self.dist_jrc = np.full(self.shape, np.nan, "float32")
            self.hand = np.full(self.shape, np.nan, "float32")
        self._base = None

    def run(self, bi=BI, ai=AI, thr_hh=None, thr_hv=None):
        """The frozen method (unchanged), on the chosen passes; optional per-scene cut-offs (config set only in this process)."""
        keep = config.WATER_HH_DB, config.WATER_HV_DB
        if thr_hh is not None:
            config.WATER_HH_DB, config.WATER_HV_DB = thr_hh, thr_hv
        try:
            return self._run(bi, ai)
        finally:
            config.WATER_HH_DB, config.WATER_HV_DB = keep

    def _run(self, bi, ai):
        r = change.detect_water_change([self.hh[i] for i in bi], [self.hh[4 + i] for i in ai], 0.04,
                                       extra_mask=self.extra, before_hv=[self.hv[i] for i in bi],
                                       after_hv=[self.hv[4 + i] for i in ai], lee_size=7)
        return r

    @property
    def base(self):
        if self._base is None:
            r = self.run()
            self._base = r
        return self._base

    def score(self, pred, region="whole"):
        sl = self.regions[region]
        valid = self.valid[sl] & np.ones_like(self.valid[sl])
        m = ev.prf(pred[sl], self.ref[sl], valid & (self.base.classes[sl] != change.MASKED))
        return m

    # ---- features of every pixel
    def features(self):
        r = self.base
        thr, thr_hv = r.threshold_db, r.threshold_hv_db
        F = {}
        F["hh_after"] = r.after_db
        F["hv_after"] = change.composite([self.hv_db[4 + i] for i in AI])
        F["hh_before"] = r.before_db
        F["hv_hh_gap"] = F["hv_after"] - F["hh_after"]
        F["change_db"] = r.diff_db
        dark = (self.hh_db[4:] < thr) & (self.hv_db[4:] < thr_hv)
        F["n_dark_of_4_after"] = dark.sum(0).astype("float32")
        F["after_std"] = np.nanstd(self.hh_db[4:], axis=0).astype("float32")
        F["before_std"] = np.nanstd(self.hh_db[:4], axis=0).astype("float32")
        F["slope_deg"] = self.slope
        F["height_above_jrc_water_m"] = self.hand
        F["dist_jrc_water_m"] = self.dist_jrc
        F["worldcover"] = self.wc.astype("float32")
        lab, n = ndimage.label(r.classes == change.BECAME_WATER, structure=np.ones((3, 3)))
        sizes = np.concatenate([[0], ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))])
        F["patch_ha"] = (sizes[lab] * 0.04).astype("float32")
        return F


# ------------------------------------------------------------------ diagnosis
BINS = {
    "hh_after": [-99, -22, -20, -18, -16, -14.5], "hv_after": [-99, -28, -26, -24, -22, -20.5],
    "hh_before": [-99, -16, -14, -12, -10, 99], "hv_hh_gap": [-99, -9, -8, -7, -6, -5, 99],
    "change_db": [-99, -9, -7, -5, -4, -3], "n_dark_of_4_after": [-0.5, 1.5, 2.5, 3.5, 4.5],
    "after_std": [0, 0.5, 1, 1.5, 2, 3, 99], "before_std": [0, 1, 2, 3, 4, 99],
    "slope_deg": [0, 1, 2, 5, 10, 99], "height_above_jrc_water_m": [-99, 0, 1, 2, 4, 8, 999],
    "dist_jrc_water_m": [-1, 100, 500, 1000, 2500, 5000, 1e9], "patch_ha": [0, 2, 5, 20, 100, 1e9],
}


def bin_table(F, groupmasks, feat):
    """Rows: bin label, share of group A (e.g. false positives) and group B (true positives) per bin, and precision."""
    names = list(groupmasks)
    a, b = groupmasks[names[0]], groupmasks[names[1]]
    if feat == "worldcover":
        vals = sorted(set(np.unique(F[feat][a | b]).astype(int)))
        labels = [WC_NAMES.get(v, str(v)) for v in vals]
        idx = [(F[feat] == v) for v in vals]
    else:
        e = BINS[feat]
        labels = [f"[{e[i]:g},{e[i + 1]:g})" for i in range(len(e) - 1)]
        idx = [(F[feat] >= e[i]) & (F[feat] < e[i + 1]) for i in range(len(e) - 1)]
        if feat == "n_dark_of_4_after":
            labels = ["0-1", "2", "3", "4"]
    na, nb = max(int(a.sum()), 1), max(int(b.sum()), 1)
    rows = []
    for lab, m in zip(labels, idx):
        ca, cb = int((a & m).sum()), int((b & m).sum())
        rows.append((lab, ca, cb, ca / na, cb / nb, (cb / (ca + cb)) if ca + cb else None))
    return names, rows


def md_table(names, rows, feat):
    s = [f"| {feat} | {names[0]} px | {names[1]} px | share of {names[0]} | share of {names[1]} | {names[1]} / ({names[0]}+{names[1]}) |",
         "|---|---|---|---|---|---|"]
    for lab, ca, cb, sa, sb, p in rows:
        s.append(f"| {lab} | {ca} | {cb} | {sa:.0%} | {sb:.0%} | {'-' if p is None else format(p, '.2f')} |")
    return "\n".join(s)


def diagnose():
    out = {}
    for title, wname, kind in [("FALSE vs TRUE positives, south neighbour", "nbr", "fp"),
                               ("FALSE vs TRUE positives, main window", "main", "fp"),
                               ("FALSE vs TRUE positives, fresh window (0.44 deg south)", "fresh", "fp"),
                               ("MISSED (false negatives) vs TRUE positives, main window", "main", "fn")]:
        w = Win(wname)
        F = w.features()
        pred = w.base.classes == change.BECAME_WATER
        v = w.valid & (w.base.classes != change.MASKED)
        tp, fp, fn = pred & w.ref & v, pred & ~w.ref & v, ~pred & w.ref & v
        print(f"\n### {title}  (FP {int(fp.sum())}, TP {int(tp.sum())}, FN {int(fn.sum())} px at 20 m)")
        groups = {"FP": fp, "TP": tp} if kind == "fp" else {"FN": fn, "TP": tp}
        res = {}
        for feat in ["worldcover"] + list(BINS):
            names, rows = bin_table(F, groups, feat)
            print(md_table(names, rows, feat) + "\n")
            res[feat] = rows
        if kind == "fn":
            c = w.base.classes
            tot = max(int(fn.sum()), 1)
            print("Method class of missed pixels:", {n: f"{(fn & (c == k)).sum() / tot:.0%}"
                                                     for n, k in [("no change", 0), ("permanent", 3), ("receded", 2)]})
            water_b = F["hh_before"] < config.WATER_HH_DB
            print(f"missed pixels already dark in the before composite: {(fn & water_b).sum() / tot:.0%}; "
                  f"never dark on both after passes: {(fn & (F['n_dark_of_4_after'] < 2)).sum() / tot:.0%}")
        out[title] = {k: [list(map(lambda x: x if x is None or isinstance(x, str) else float(x), r)) for r in v_]
                      for k, v_ in res.items()}
        del w, F
    return out


# ------------------------------------------------------------------ candidates (post-filters on the method output)
def remove_small(mask, min_px):
    return change.remove_small(mask, int(min_px))


def cand_landcover(w, F, base, classes):
    return base & ~np.isin(F["worldcover"], classes)


def cand_gap(w, F, base, t):          # HV much darker than HH (open water), wet vegetation has a smaller gap
    return base & (F["hv_hh_gap"] < t)


def cand_hv(w, F, base, m):
    return base & (F["hv_after"] < config.WATER_HV_DB - m)


def cand_hh(w, F, base, m):
    return base & (F["hh_after"] < config.WATER_HH_DB - m)


def cand_jrc_perm(w, F, base, o):     # JRC permanent water cannot be "new" water
    return base & ~(w.jrc >= o) if w.jrc.shape == base.shape else base


def cand_wc_water(w, F, base, _):
    return base & ~(F["worldcover"] == 80)


def cand_hand(w, F, base, h):
    return base & (F["height_above_jrc_water_m"] < h)


def cand_hand_floor(w, F, base, h):   # a new-water pixel cannot be LOWER than the permanent water it floods from
    return base & ~(F["height_above_jrc_water_m"] < h)


def cand_dist(w, F, base, d):
    return base & (F["dist_jrc_water_m"] < d)


def cand_stable(w, F, base, k):       # dark on >= k of 4 after passes (uses 2 later passes: dates 10-17, 10-29)
    return base & (F["n_dark_of_4_after"] >= k)


def cand_before_std(w, F, base, s):   # before passes (4, all pre-event) very variable = irrigated / rice field
    return base & (F["before_std"] < s)


def cand_patch(w, F, base, ha):
    return remove_small(base, np.ceil(ha / 0.04))


def cand_ratio_change(w, F, base, c):
    return base & (F["change_db"] < -c)


CANDS = [  # name, function, list of (label, param); "none" is always added as the reference
    ("landcover: drop cropland(40)", cand_landcover, [("40", [40])]),
    ("landcover: drop cropland+grass(40,30)", cand_landcover, [("40,30", [40, 30])]),
    ("landcover: drop crop+grass+herb.wetland", cand_landcover, [("40,30,90", [40, 30, 90])]),
    ("landcover: drop built+bare+crop(50,60,40)", cand_landcover, [("50,60,40", [50, 60, 40])]),
    ("HV-HH gap must be < t dB", cand_gap, [(f"t={t}", t) for t in (-5, -6, -7, -8, -9)]),
    ("HV stricter by m dB", cand_hv, [(f"m={m}", m) for m in (0.5, 1, 2, 3, 4, 5, 6)]),
    ("HH stricter by m dB", cand_hh, [(f"m={m}", m) for m in (0.5, 1, 2, 3, 4)]),
    ("exclude JRC water occurrence >= o %", cand_jrc_perm, [(f"o={o}", o) for o in (90, 75, 50)]),
    ("exclude WorldCover water (80)", cand_wc_water, [("wc80", None)]),
    ("height above JRC water < h m", cand_hand, [(f"h={h}", h) for h in (1, 2, 3, 5, 8, 12)]),
    ("not lower than JRC permanent water (height >= h m)", cand_hand_floor, [(f"h={h}", h) for h in (0, 0.5, 1)]),
    ("distance to JRC water < d m", cand_dist, [(f"d={d}", d) for d in (250, 500, 1000, 2000, 5000)]),
    ("dark on >= k of 4 after passes", cand_stable, [(f"k={k}", k) for k in (3, 4)]),
    ("before-pass spread < s dB", cand_before_std, [(f"s={s}", s) for s in (1.0, 1.5, 2.0, 3.0)]),
    ("min patch ha", cand_patch, [(f"{h}", h) for h in (2, 5, 10, 25)]),
    ("change stricter than c dB", cand_ratio_change, [(f"c={c}", c) for c in (4, 5, 6, 8)]),
]


def rerun_variants(w):
    """Method re-runs with more passes per side (no post-filter): 4 before and/or 4 after passes."""
    out = {}
    for lab, bi, ai in [("4 before passes (06-19..07-25)", [0, 1, 2, 3], AI), ("4 after passes (09-23..10-29)", BI, [0, 1, 2, 3]),
                        ("4 before + 4 after", [0, 1, 2, 3], [0, 1, 2, 3]), ("3 after (09-23,10-05,10-17)", BI, [0, 1, 2])]:
        r = w.run(bi, ai)
        out[lab] = r.classes == change.BECAME_WATER
    return out


def fmt(m):
    f = lambda v: "n/a" if v is None else f"{v:.2f}"
    return f"{f(m['iou'])}/{f(m['precision'])}/{f(m['recall'])}"


def candidates(fresh_names):
    W = {n: Win(n) for n in ["main", "nbr"]}
    F = {n: W[n].features() for n in W}
    base = {n: W[n].base.classes == change.BECAME_WATER for n in W}
    evals = [("west", "main", "west"), ("east", "main", "east"), ("nbr", "nbr", "whole")]
    fresh = {}
    for fn in fresh_names:
        fresh[fn] = Win(fn)
        W[fn] = fresh[fn]
        F[fn] = fresh[fn].features()
        base[fn] = fresh[fn].base.classes == change.BECAME_WATER
        evals.append((fn, fn, "whole"))

    def score_all(preds):
        return {lab: W[wn].score(preds[wn], reg) for lab, wn, reg in evals}

    results = []
    ref = score_all(base)
    results.append(("frozen v4b (reference)", "-", ref, None))

    def pick(name, fn, params):
        best = None
        for lab, p in params:
            sw = W["main"].score(fn(W["main"], F["main"], base["main"], p), "west")
            key = (sw["iou"] or 0)
            if best is None or key > best[0] + 1e-9:
                best = (key, lab, p)
        return best

    for name, fn, params in CANDS:
        # show every parameter on WEST only first (this is what selects), then evaluate the selected one everywhere
        tuned = []
        for lab, p in params:
            sw = W["main"].score(fn(W["main"], F["main"], base["main"], p), "west")
            tuned.append((lab, sw))
        key, lab, p = pick(name, fn, params)
        preds = {n: fn(W[n], F[n], base[n], p) for n in W}
        sc = score_all(preds)
        results.append((name, lab, sc, tuned))
    for lab, _ in []:
        pass
    # method re-runs with more passes (parameter-free)
    rr = {n: rerun_variants(W[n]) for n in W}
    for lab in rr["main"]:
        preds = {n: rr[n][lab] for n in W}
        results.append((f"re-run: {lab}", "-", score_all(preds), None))
    lab4 = "4 after passes (09-23..10-29)"
    results.append(("re-run 4 after passes + height >= 0 m above JRC water (pre-specified, not tuned)", "-",
                    score_all({n: rr[n][lab4] & ~(F[n]["height_above_jrc_water_m"] < 0) for n in W}), None))
    # greedy combination chosen on WEST only
    comb_names, comb_pred = [], dict(base)
    chosen_west = ref["west"]["iou"]
    pool = [(n, f, p) for n, f, p in [(c[0], c[1], c[2]) for c in CANDS]]
    for _ in range(3):
        best = None
        for name, fn, params in pool:
            if name in [c[0] for c in comb_names]:
                continue
            for lab, p in params:
                pr = fn(W["main"], F["main"], comb_pred["main"], p)
                s = W["main"].score(pr, "west")["iou"] or 0
                if best is None or s > best[0]:
                    best = (s, name, fn, lab, p)
        if best is None or best[0] < chosen_west + 0.005:
            break
        s, name, fn, lab, p = best
        comb_names.append((name, lab))
        comb_pred = {n: fn(W[n], F[n], comb_pred[n], p) for n in W}
        chosen_west = s
    if comb_names:
        results.append(("greedy combination (west-selected): " + " + ".join(f"{n} [{l}]" for n, l in comb_names), "-",
                        score_all(comb_pred), None))
    return results, evals


def verdict(results, evals):
    ref = results[0][2]
    lines = []
    for name, lab, sc, _ in results[1:]:
        d_nbr = (sc["nbr"]["iou"] or 0) - (ref["nbr"]["iou"] or 0)
        d_east = (sc["east"]["iou"] or 0) - (ref["east"]["iou"] or 0)
        fresh_labels = [e[0] for e in evals if e[0] not in ("west", "east", "nbr")]
        d_fr = {f: (sc[f]["iou"] or 0) - (ref[f]["iou"] or 0) for f in fresh_labels}
        win = d_nbr > 0.005 and d_east >= -0.01 and all(v >= -0.005 for v in d_fr.values())
        lines.append((name, lab, d_nbr, d_east, d_fr, win))
    return lines


def candidates_report(fresh_names):
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    results, evals = candidates(fresh_names)
    labs = [e[0] for e in evals]
    print("\n### Candidates (parameter chosen on WEST IoU only). cells = IoU/precision/recall (strict)\n")
    print("| candidate | param | " + " | ".join(labs) + " | dIoU east | dIoU nbr | " + " | ".join(f"dIoU {f}" for f in labs[3:]) + " | generalises? |")
    print("|---|---|" + "---|" * (len(labs) + 3 + len(labs[3:])))
    ref = results[0][2]
    v = {x[0]: x for x in verdict(results, evals)}
    for name, lab, sc, _ in results:
        cells = " | ".join(fmt(sc[l]) for l in labs)
        if name in v:
            _, _, dn, de, dfr, win = v[name]
            extra = f"{de:+.3f} | {dn:+.3f} | " + " | ".join(f"{dfr[f]:+.3f}" for f in labs[3:]) + f" | {'YES' if win else 'no'}"
        else:
            extra = "- | - | " + " | ".join("-" for _ in labs[3:]) + " | -"
        print(f"| {name} | {lab} | {cells} | {extra} |")
    print("\n### West-only parameter sweeps (IoU/precision/recall on WEST)\n")
    for name, lab, sc, tuned in results:
        if tuned:
            print(f"- {name}: " + "; ".join(f"{l}: {fmt(s)}" for l, s in tuned) + f"  -> chose {lab}")
    return results


# ------------------------------------------------------------------ scene-self-calibrated cut-offs (no OPERA, no S2, no site constants)
LAND_CLASSES = (10, 40, 50, 60)      # WorldCover tree, cropland, built-up, bare = free "not water" pixels
HH_RANGE, HV_RANGE = (-24.0, -8.0), (-32.0, -14.0)   # sanity clamp only (physical range of open-water backscatter)


def _cut(wv, lv, mode):
    if mode == "cfar5":                    # constant false-alarm rate: only 5 % of known land may fall below the cut-off
        return float(np.percentile(lv, 5))
    ts = np.arange(np.percentile(np.r_[wv, lv], 0.5), np.percentile(np.r_[wv, lv], 99.5), 0.1)
    ws, ls = np.sort(wv), np.sort(lv)
    score = np.searchsorted(ws, ts) / ws.size + 1 - np.searchsorted(ls, ts) / ls.size   # TPR + TNR (Youden)
    return float(ts[np.argmax(score)])


def calibrate_cutoffs(hh_db, hv_db, jrc, wc, excl, mode="youden", occ_min=90, seed=0):
    """Per-scene HH/HV water cut-offs from free labels only: JRC occurrence >= 90 % = water, JRC == 0 and a WorldCover
    land class = land. hh_db/hv_db: (passes, H, W) filtered dB of the passes the method uses. Returns (hh, hv, info)."""
    water = (jrc >= occ_min) & (jrc != 255) & ~excl
    land = (jrc == 0) & np.isin(wc, LAND_CLASSES) & ~excl
    info = {"n_water_px": int(water.sum()), "n_land_px": int(land.sum())}
    if (mode != "cfar5" and water.sum() < 2000) or land.sum() < 2000:
        info["fallback"] = "too few free labels, fixed cut-offs kept"
        return config.WATER_HH_DB, config.WATER_HV_DB, info
    rng = np.random.default_rng(seed)
    out = []
    for name, st, (lo, hi) in (("hh", hh_db, HH_RANGE), ("hv", hv_db, HV_RANGE)):
        samp = {}
        for lab, m in (("w", water), ("l", land)):
            v = st[:, m].ravel()
            v = v[np.isfinite(v)]
            samp[lab] = rng.choice(v, min(v.size, 300000), replace=False) if v.size else np.array([np.nan])
        t = _cut(samp["w"], samp["l"], mode)
        info[f"{name}_raw"] = round(t, 2)
        info[f"{name}_water_median"] = round(float(np.median(samp["w"])), 2)
        info[f"{name}_land_median"] = round(float(np.median(samp["l"])), 2)
        out.append(float(np.clip(t, lo, hi)))
    return out[0], out[1], info


def run_scene(hh_b, hh_a, hv_b, hv_a, extra, thr_hh=None, thr_hv=None):
    keep = config.WATER_HH_DB, config.WATER_HV_DB
    if thr_hh is not None:
        config.WATER_HH_DB, config.WATER_HV_DB = thr_hh, thr_hv
    try:
        return change.detect_water_change(hh_b, hh_a, 0.04, extra_mask=extra, before_hv=hv_b, after_hv=hv_a, lee_size=7)
    finally:
        config.WATER_HH_DB, config.WATER_HV_DB = keep


def kanpur_scene():
    """Kanpur (Ganga, track 77) from the pipeline's local NISAR cache, as eval_s2.py loads it."""
    import eval_s2 as es
    from app import catalog
    from app.science import gcov
    a = es.AREAS["kanpur"]
    bbox = a["bbox"]
    by = {p.date: p for p in catalog.search_passes(bbox) if p.track == "77" and gcov.is_cached(p.url, bbox)}
    wins = [gcov.read_window(by[d].url, bbox, d) for d in a["before"] + a["after"]]
    grid = make_grid(bbox, wins[0].epsg, 20.0)
    hh = [resample(w, grid, "hh") for w in wins]
    hv = [resample(w, grid, "hv") for w in wins]
    wc, _, jrc = static_layers(grid, bbox, with_dem=False)
    grid0 = make_grid(bbox, es.utm_epsg(bbox), 20.0)
    rb, ra = es.load_ref("kanpur", "before", grid0), es.load_ref("kanpur", "after", grid0)
    return dict(name="kanpur", hh=hh, hv=hv, wc=wc, jrc=jrc, extra=np.zeros(grid.shape, bool), rb=rb, ra=ra, es=es)


def window_scene(name):
    w = Win(name)
    sc = dict(name=name, hh=[w.hh[i] for i in BI + [4 + i for i in AI]], hv=[w.hv[i] for i in BI + [4 + i for i in AI]],
              wc=w.wc, jrc=w.jrc, extra=w.extra, win=w)
    if name == "nbr":
        import eval_s2 as es
        grid0 = make_grid(bbox_of("nbr"), es.utm_epsg(bbox_of("nbr")), 20.0)
        sc["rb"], sc["ra"], sc["es"] = es.load_ref("tonlesap_south", "before", grid0), es.load_ref("tonlesap_south", "after", grid0), es
    return sc


def calibrate_report(scenes=None):
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    modes = [("fixed", None, 90), ("youden@90", "youden", 90), ("youden@50", "youden", 50), ("cfar5", "cfar5", 90)]
    print("\n### Scene-self-calibrated cut-offs (JRC>=90 water vs WorldCover tree/crop/built/bare with JRC==0 land)\n")
    rows_o, rows_s = [], []
    thr_rows = []
    for name in (scenes or ["main", "nbr", "fresh", "fresh_e", "kanpur"]):
        sc = kanpur_scene() if name == "kanpur" else window_scene(name)
        hh, hv = sc["hh"], sc["hv"]
        hh_b, hh_a, hv_b, hv_a = hh[:2], hh[2:], hv[:2], hv[2:]
        db = lambda L: np.stack([change.lee_filter(change.to_db(a), 7) for a in L])
        hh_db, hv_db = db(hh), db(hv)
        for mname, mode, occ in modes:
            if mode is None:
                t_hh, t_hv, info = config.WATER_HH_DB, config.WATER_HV_DB, {}
            else:
                t_hh, t_hv, info = calibrate_cutoffs(hh_db, hv_db, sc["jrc"], sc["wc"], sc["extra"], mode, occ)
            r = run_scene(hh_b, hh_a, hv_b, hv_a, sc["extra"], t_hh, t_hv)
            pred = r.classes == change.BECAME_WATER
            thr_rows.append((name, mname, t_hh, t_hv, info))
            if "win" in sc:
                w = sc["win"]
                for reg in w.regions:
                    w._base = r if False else w._base
                    valid = w.valid[w.regions[reg]] & (r.classes[w.regions[reg]] != change.MASKED)
                    m = ev.prf(pred[w.regions[reg]], w.ref[w.regions[reg]], valid)
                    rows_o.append((name, reg, mname, m))
            if "rb" in sc and sc["rb"] is not None:
                es = sc["es"]
                ref, v = es.s2_new_water(sc["rb"], sc["ra"], 0.0)
                m = ev.prf(pred, ref, v & (r.classes != change.MASKED))
                m["radar_water_after_px"] = int(round(r.water_after_ha / 0.04))
                m["s2_water_after_px"] = int(((sc["ra"][0] > 0) & sc["ra"][1] & (r.classes != change.MASKED)).sum())
                rows_s.append((name, mname, m))
        if name == "kanpur":
            kanpur_why(sc, hh_db, hv_db, config.WATER_HH_DB, config.WATER_HV_DB, thr_rows)
        del sc
    print("| scene | method | HH cut-off | HV cut-off | free labels (water px / land px) | water median HH/HV | land median HH/HV |\n|---|---|---|---|---|---|---|")
    for name, mname, a, b, info in thr_rows:
        print(f"| {name} | {mname} | {a:.1f} | {b:.1f} | {info.get('n_water_px', '-')}/{info.get('n_land_px', '-')} | "
              f"{info.get('hh_water_median', '-')}/{info.get('hv_water_median', '-')} | {info.get('hh_land_median', '-')}/{info.get('hv_land_median', '-')} |"
              + (f" {info['fallback']}" if "fallback" in info else ""))
    print("\nvs OPERA new water (IoU/prec/recall; strict):\n")
    print("| window | region | fixed v4b | youden@90 | youden@50 | cfar5 |\n|---|---|---|---|---|---|")
    keys = {}
    for name, reg, mname, m in rows_o:
        keys.setdefault((name, reg), {})[mname] = m
    for (name, reg), d in keys.items():
        print(f"| {name} | {reg} | " + " | ".join(f"{fmt(d[k])} (pred {d[k]['pred_px']}, ref {d[k]['ref_px']})" for k in ("fixed", "youden@90", "youden@50", "cfar5")) + " |")
    print("\nvs Sentinel-2 new water (MNDWI>0; IoU/prec/recall):\n")
    print("| scene | fixed v4b | youden@90 | youden@50 | cfar5 |\n|---|---|---|---|---|")
    keys = {}
    for name, mname, m in rows_s:
        keys.setdefault(name, {})[mname] = m
    for name, d in keys.items():
        print(f"| {name} | " + " | ".join(f"{fmt(d[k])} (pred {d[k]['pred_px']}, S2 {d[k]['ref_px']}, comparable {d[k]['comparable']:.0%}; radar water-after px {d[k]['radar_water_after_px']} vs S2 {d[k]['s2_water_after_px']})" for k in ("fixed", "youden@90", "youden@50", "cfar5")) + " |")


def kanpur_why(sc, hh_db, hv_db, thr_hh, thr_hv, thr_rows=None):
    """Why do the fixed cut-offs miss Kanpur's river? Per-pass HH/HV on pixels that Sentinel-2 calls water."""
    es = sc["es"]
    ma, va = sc["ra"]
    s2w = (ma > 0) & va
    jw = sc["jrc"] >= 50
    land = (sc["jrc"] == 0) & np.isin(sc["wc"], LAND_CLASSES)
    d_edge = ndimage.distance_transform_edt(s2w)           # px inside the S2 water body (1 = shoreline pixel)
    print(f"\n### Kanpur: radar values on Sentinel-2-water pixels (n={int(s2w.sum())}; JRC>=50 water n={int(jw.sum())}; land n={int(land.sum())}), fixed cut-offs HH<{thr_hh}, HV<{thr_hv}\n")
    labs = ["before 08-30", "before 09-11", "after 09-23", "after 10-05"]
    print("| pass | S2 water HH p10/p50/p90 | S2 water HV p10/p50/p90 | share HH<-14.5 | share HV<-20.5 | share both | JRC water HH p50 | land HH p50 |\n|---|---|---|---|---|---|---|---|")
    for i, l in enumerate(labs):
        h, v = hh_db[i], hv_db[i]
        ok = s2w & np.isfinite(h) & np.isfinite(v)
        q = lambda x: "/".join(f"{np.percentile(x[ok], p):.1f}" for p in (10, 50, 90))
        print(f"| {l} | {q(h)} | {q(v)} | {(h[ok] < thr_hh).mean():.0%} | {(v[ok] < thr_hv).mean():.0%} | {((h[ok] < thr_hh) & (v[ok] < thr_hv)).mean():.0%} | "
              f"{np.nanmedian(h[jw]):.1f} | {np.nanmedian(h[land]):.1f} |")
    h, v = hh_db[2:].mean(0), hv_db[2:].mean(0)
    ok = s2w & np.isfinite(h) & np.isfinite(v)
    fail_hh, fail_hv = h >= thr_hh, v >= thr_hv
    n = ok.sum()
    print(f"\nafter-pass mean on S2 water: HH fails only {(ok & fail_hh & ~fail_hv).sum() / n:.0%}, HV fails only {(ok & ~fail_hh & fail_hv).sum() / n:.0%}, both fail {(ok & fail_hh & fail_hv).sum() / n:.0%}, both pass {(ok & ~fail_hh & ~fail_hv).sum() / n:.0%}")
    print("share of S2-water pixels passing BOTH fixed cut-offs by depth inside the water body (1 px = shoreline):")
    for lo, hi in ((1, 2), (2, 4), (4, 8), (8, 1e9)):
        m = ok & (d_edge > lo - 1) & (d_edge <= hi - 1 + (0 if hi < 1e9 else 1e9))
        if m.sum():
            print(f"  {lo}-{hi if hi < 1e9 else 'inf'} px from shore: n={int(m.sum())}, pass {((h[m] < thr_hh) & (v[m] < thr_hv)).mean():.0%}, HH p50 {np.median(h[m]):.1f}, HV p50 {np.median(v[m]):.1f}")
    cols = np.indices(h.shape)[1]
    print(f"HH on S2-water vs image column (cross-track proxy): corr {np.corrcoef(cols[ok], h[ok])[0, 1]:.2f}; HV: {np.corrcoef(cols[ok], v[ok])[0, 1]:.2f}")
    sp = np.nanstd(np.stack([hh_db[i][ok] for i in range(4)]), axis=0)
    print(f"pass-to-pass HH std on S2 water: median {np.median(sp):.1f} dB (a calm-water surface would be stable; wind roughening shifts passes differently)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["prep", "diagnose", "candidates", "check", "calibrate"])
    ap.add_argument("name", nargs="?", default="main", choices=list(SHIFT))
    ap.add_argument("--fresh", nargs="*", default=["fresh"], help="fresh windows to use in 'candidates' (never tuned on)")
    ap.add_argument("--scenes", nargs="*", default=None, help="calibrate stage: subset of main nbr fresh fresh_e kanpur")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    if a.stage == "prep":
        prep(a.name)
    elif a.stage == "check":
        for n in ["main", "nbr"] + a.fresh:
            w = Win(n)
            pred = w.base.classes == change.BECAME_WATER
            for reg in w.regions:
                print(n, reg, fmt(w.score(pred, reg)), {k: w.score(pred, reg)[k] for k in ("pred_px", "ref_px", "comparable")})
    elif a.stage == "diagnose":
        res = diagnose()
        if a.json:
            Path(a.json).write_text(json.dumps(res, indent=1, default=float))
    elif a.stage == "calibrate":
        calibrate_report(a.scenes)
    else:
        candidates_report(a.fresh)


if __name__ == "__main__":
    main()
