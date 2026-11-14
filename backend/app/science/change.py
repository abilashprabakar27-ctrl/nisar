"""Water-change detection on NISAR HH backscatter.

Method (explainable, no trained model):
1. linear power -> decibels; Lee speckle filter
2. median composite of the before passes and of the after passes
3. water threshold from Otsu on the after image (clamped to a physical range)
4. classes: became water / water receded / permanent water / no change / masked
5. drop patches smaller than 1 hectare

v4 accuracy rules (docs/accuracy_log.md): a pixel counts as water BEFORE only if clearly dark (cut-off minus
WATER_BEFORE_MARGIN_DB), so borderline-dark land is not locked in as 'permanent'; new water must be water on
every after pass.
"""
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from .. import config

NO_CHANGE, BECAME_WATER, RECEDED, PERMANENT, MASKED = 0, 1, 2, 3, 255


def to_db(power: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 10.0 * np.log10(power)
    out[~np.isfinite(out)] = np.nan
    return out.astype("float32")


def lee_filter(db: np.ndarray, size: int = 5) -> np.ndarray:
    """Classic Lee filter on dB values, NaN-aware."""
    valid = np.isfinite(db)
    x = np.where(valid, db, 0.0).astype("float64")
    w = valid.astype("float64")
    n = np.maximum(ndimage.uniform_filter(w, size), 1e-6)
    mean = ndimage.uniform_filter(x, size) / n
    sq = ndimage.uniform_filter(x * x, size) / n
    var = np.maximum(sq - mean * mean, 0.0)
    noise = np.nanmedian(var[valid]) if valid.any() else 0.0
    gain = var / np.maximum(var + noise, 1e-6)
    out = mean + gain * (x - mean)
    out[~valid] = np.nan
    return out.astype("float32")


def composite(stack: list[np.ndarray]) -> np.ndarray:
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            return np.nanmedian(np.stack(stack), axis=0).astype("float32")


def otsu_threshold(db: np.ndarray, lo: float = -24.0, hi: float = -15.0) -> float:
    v = db[np.isfinite(db)]
    v = v[(v > -35) & (v < 5)]
    if v.size < 100:
        return -18.0
    hist, edges = np.histogram(v, bins=256)
    mids = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * mids) / np.maximum(w0, 1)
    m1 = (np.sum(hist * mids) - np.cumsum(hist * mids)) / np.maximum(w1, 1)
    between = w0 * w1 * (m0 - m1) ** 2
    t = float(mids[np.argmax(between)])
    return float(np.clip(t, lo, hi))


@dataclass
class ChangeResult:
    classes: np.ndarray
    before_db: np.ndarray
    after_db: np.ndarray
    diff_db: np.ndarray
    threshold_db: float
    pixel_ha: float
    areas_ha: dict = field(default_factory=dict)
    water_before_ha: float = 0.0
    water_after_ha: float = 0.0
    masked_fraction: float = 0.0
    persistence: float = 1.0        # share of new water also seen on every after pass
    threshold_hv_db: float | None = None
    first_after_water: np.ndarray | None = None


def remove_small(mask: np.ndarray, min_pixels: int) -> np.ndarray:
    if min_pixels <= 1:
        return mask
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, lab, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, bool)
    keep[1:] = sizes >= min_pixels
    return keep[lab]


def detect_water_change(before: list[np.ndarray], after: list[np.ndarray], pixel_ha: float,
                        extra_mask: np.ndarray | None = None,
                        before_hv: list[np.ndarray] | None = None, after_hv: list[np.ndarray] | None = None,
                        lee_size: int = 7) -> ChangeResult:
    """before/after: lists of HH linear-power arrays on the same grid (HV optional but recommended).

    Water must be dark in HH AND in HV: open water is dark in both, while wet or flooded rice fields
    are dark-ish in HH but moderately bright in HV (leaves scatter the cross-polarised signal).
    """
    b_db = [lee_filter(to_db(a), lee_size) for a in before]
    a_db = [lee_filter(to_db(a), lee_size) for a in after]
    bc, ac = composite(b_db), composite(a_db)
    fixed = config.THRESHOLD_MODE == "fixed"
    thr = config.WATER_HH_DB if fixed else otsu_threshold(ac, lo=-20.0, hi=-11.0)
    diff = ac - bc

    use_hv = bool(before_hv and after_hv) and all(np.isfinite(x).any() for x in after_hv)
    if use_hv:
        bhv_db = [lee_filter(to_db(a), lee_size) for a in before_hv]
        ahv_db = [lee_filter(to_db(a), lee_size) for a in after_hv]
        bhv, ahv = composite(bhv_db), composite(ahv_db)
        thr_hv = config.WATER_HV_DB if fixed else otsu_threshold(ahv, lo=-26.0, hi=-17.0)
    else:
        bhv = ahv = None
        thr_hv = None

    invalid = ~np.isfinite(bc) | ~np.isfinite(ac)
    if extra_mask is not None:
        invalid |= extra_mask

    def is_water(hh, hv, margin_hh=0.0, margin_hv=None):
        """margin > 0 demands darker pixels (stricter); margin < 0 allows brighter ones (looser)."""
        margin_hv = margin_hh if margin_hv is None else margin_hv
        w = hh < thr - margin_hh
        if hv is not None:
            w &= np.where(np.isfinite(hv), hv < thr_hv - margin_hv, True)
        return w

    water_b = is_water(bc, bhv, config.WATER_BEFORE_MARGIN_DB) & ~invalid
    water_a = is_water(ac, ahv) & ~invalid
    if config.HYST_HH_EXTRA_DB > 0 or config.HYST_HV_EXTRA_DB > 0:
        # hysteresis: keep strict water as seeds, add looser-water pixels within a few pixels of a seed
        loose = is_water(ac, ahv, -config.HYST_HH_EXTRA_DB, -config.HYST_HV_EXTRA_DB) & ~invalid
        water_a = ndimage.binary_dilation(water_a, iterations=max(config.HYST_MAX_PX, 1), mask=loose) | water_a

    # every after pass must agree, so one odd pass (wind, rain, crop growth) cannot create change
    each_after_water = [is_water(a_db[i], ahv_db[i] if use_hv else None) for i in range(len(a_db))]
    each_after_dry = [~w for w in each_after_water]
    all_after_water = np.logical_and.reduce(each_after_water)
    all_after_dry = np.logical_and.reduce(each_after_dry)

    min_px = int(np.ceil(config.MIN_PATCH_HA / pixel_ha))
    cand = water_a & ~water_b & (diff < -config.CHANGE_DB)
    if config.REQUIRE_PERSISTENT:
        cand &= all_after_water
    if config.AFTER_VAR_MAX_DB > 0 and len(a_db) > 1:
        spread = np.nanmax(np.stack(a_db), axis=0) - np.nanmin(np.stack(a_db), axis=0)
        cand &= ~(spread > config.AFTER_VAR_MAX_DB)
    became = remove_small(cand, min_px)
    receded = remove_small(water_b & ~water_a & (diff > config.CHANGE_DB) & all_after_dry, 2 * min_px)
    permanent = water_b & water_a

    classes = np.full(bc.shape, NO_CHANGE, "uint8")
    classes[permanent] = PERMANENT
    classes[became] = BECAME_WATER
    classes[receded] = RECEDED
    classes[invalid] = MASKED

    persistence = float(all_after_water[became].mean()) if became.any() else 1.0
    first_after = each_after_water[0] & ~invalid

    total = classes.size
    r = ChangeResult(classes=classes, before_db=bc, after_db=ac, diff_db=diff, threshold_db=thr,
                     pixel_ha=pixel_ha, masked_fraction=float(invalid.sum()) / max(total, 1),
                     persistence=persistence)
    r.threshold_hv_db = thr_hv
    r.first_after_water = first_after
    r.areas_ha = {
        "became_water": round(float(became.sum()) * pixel_ha, 1),
        "water_receded": round(float(receded.sum()) * pixel_ha, 1),
        "permanent_water": round(float(permanent.sum()) * pixel_ha, 1),
        "veg_lost": None, "structures": None,
    }
    r.water_before_ha = round(float(water_b.sum()) * pixel_ha, 1)
    r.water_after_ha = round(float(water_a.sum()) * pixel_ha, 1)
    return r


def water_area_series(passes_db: list[np.ndarray], threshold_db: float, pixel_ha: float,
                      mask: np.ndarray | None = None) -> list[float]:
    """Water area (ha) in each pass, for the per-pass chart."""
    out = []
    for d in passes_db:
        w = (d < threshold_db) & np.isfinite(d)
        if mask is not None:
            w &= ~mask
        out.append(round(float(w.sum()) * pixel_ha, 1))
    return out


# Provisional reliability limits. They come from 2 observed failures (docs/accuracy_log.md "Reliability checks"), not from tuning:
# do not adjust them to make outputs look better.
PASS_DRIFT_DB = 1.5          # a pass this far from the median of all passes is not comparable (Kanpur 23 Sep was ~3 dB brighter)
CROPLAND_SHARE_MAX = 0.50    # more new water than this on cropland -> not above Lower (cropland plains south of Tonle Sap, IoU 0.04)
WC_CROPLAND, WC_BUILT = 40, 50

# Tonle Sap lake window: the only place scored against OPERA (strict became-water score), see docs/accuracy_log.md
TONLE_SAP_VALIDATED_BBOX = (103.90, 13.05, 104.12, 13.27)
VALIDATED_AGAINST_OPERA = [
    "Tonle Sap lake window (103.90-104.12 E, 13.05-13.27 N), one season and one NISAR track: IoU 0.68, precision 0.88, "
    "recall 0.74 against OPERA new water, compared on 51% of the window (docs/accuracy_log.md). OPERA is a second opinion, not ground truth.",
]
KNOWN_FAILURES = [
    "cropland plains: IoU 0.04 on one window south of Tonle Sap, 301k px predicted as new water vs 15k in OPERA (docs/GENERALISATION.md)",
    "Sentinel-2 check disagreed on 2 of 2 scored areas: south of Tonle Sap precision 0.15, Kanpur recall 0.03 (docs/accuracy_log.md)",
]


def validation_status(bbox) -> dict:
    """What has really been measured about this method, and whether this place is covered. Only measured numbers, with sources."""
    w, s, e, n = bbox
    bw, bs, be, bn = TONLE_SAP_VALIDATED_BBOX
    inside = w >= bw - 1e-6 and s >= bs - 1e-6 and e <= be + 1e-6 and n <= bn + 1e-6
    return {
        "validated_against_opera": list(VALIDATED_AGAINST_OPERA),
        "known_failures": list(KNOWN_FAILURES),
        "this_place": "validated against OPERA on one window and season" if inside else "not validated",
        "this_place_validated": inside,
        "human_labelled_accuracy": "not measured",
    }


def radiometric_stability(dates: list[str], dbs: list[np.ndarray], classes: np.ndarray, thr_db: float,
                          tol_db: float = PASS_DRIFT_DB) -> dict:
    """Median HH (dB) of each pass over pixels that are land in every pass (not masked, never classed as water,
    never darker than the water cut-off). A pass far from the others is not comparable with them."""
    if len(dates) < 2 or len(dbs) != len(dates):
        return {"checked": False, "note": "needs at least 2 passes"}
    st = np.stack(dbs)
    land = np.isfinite(st).all(axis=0) & (st > thr_db).all(axis=0) & (classes == NO_CHANGE)
    n = int(land.sum())
    if n < 1000:
        return {"checked": False, "note": f"only {n} stable land pixels"}
    med = {d: float(np.median(db[land])) for d, db in zip(dates, dbs)}
    ref = float(np.median(list(med.values())))
    dev = {d: round(m - ref, 2) for d, m in med.items()}
    flagged = [{"date": d, "offset_db": v} for d, v in dev.items() if abs(v) > tol_db]
    return {"checked": True, "land_pixels": n, "median_hh_db": {d: round(m, 2) for d, m in med.items()},
            "median_of_passes_db": round(ref, 2), "offset_db": dev, "tolerance_db": tol_db, "flagged": flagged}


def stability_limits(stab: dict) -> list[str]:
    out = []
    for f in stab.get("flagged", []):
        v = f["offset_db"]
        out.append(f"Pass {f['date']} is {abs(v):.1f} dB {'brighter' if v > 0 else 'darker'} than the others, likely wind, "
                   f"rain or wet soil, so open water may be missed on that date.")
    return out


def landcover_shares(classes: np.ndarray, wc: np.ndarray | None) -> dict:
    """Share of 'became water' pixels on cropland / built-up (ESA WorldCover). wc None -> not checked."""
    if wc is None:
        return {"checked": False, "note": "ESA WorldCover not available, not checked"}
    m = classes == BECAME_WATER
    n = int(m.sum())
    if n == 0:
        return {"checked": True, "became_water_px": 0, "cropland_share": None, "builtup_share": None}
    return {"checked": True, "became_water_px": n,
            "cropland_share": round(float((wc[m] == WC_CROPLAND).mean()), 3),
            "builtup_share": round(float((wc[m] == WC_BUILT).mean()), 3)}


def confidence(n_before: int, n_after: int, persistence: float, overlap_pct: float | None,
               masked_fraction: float, qualities: list[str], new_water_ha: float | None = None,
               unstable_passes: list[str] | None = None, cropland_share: float | None = None,
               place_validated: bool | None = None) -> tuple[str, str]:
    """Rules from the Night Shift 1 pack plus three reliability checks (docs/accuracy_log.md "Reliability checks").

    overlap_pct must be the STRICT figure (share of our *new* water that OPERA confirms, verify.compare), never
    one that counts permanent water. Without it (no OPERA check, or no new water) the level cannot be High.
    Reliability inputs (None = not checked, rule skipped): unstable_passes (dates whose land brightness differs from
    the others), cropland_share (share of new water on cropland), place_validated (bbox inside a validated window).
    """
    reasons = []
    if "Beta" in qualities:
        return "Lower", "Uses Beta-quality NISAR data, which is still being calibrated."
    if masked_fraction > 0.15:
        return "Lower", f"{masked_fraction:.0%} of the area could not be read (radar shadow, steep slopes or no data)."
    if overlap_pct is not None and overlap_pct < 50:
        return "Lower", f"Only {overlap_pct:.0f}% overlap with NASA's OPERA water map."
    if cropland_share is not None and cropland_share > CROPLAND_SHARE_MAX:
        return "Lower", ("Most detected new water lies on cropland, where radar cannot separate a flood from irrigated or "
                         f"flooded paddies; this kind of place failed validation ({cropland_share:.0%} of the new water is on cropland).")
    high = n_before >= 2 and n_after >= 2 and persistence >= 0.8 and overlap_pct is not None and overlap_pct >= 75
    if high:
        caps = []
        if new_water_ha is not None and new_water_ha < config.MIN_HIGH_CONF_HA:
            caps.append(f"Only {new_water_ha:.0f} ha of new water was found, too little to call High: agreement with "
                        f"OPERA on a small area says what we found is probably right, not that the whole change was mapped.")
        if unstable_passes:
            caps.append("Pass " + ", ".join(unstable_passes) + " differs by more than "
                        f"{PASS_DRIFT_DB:g} dB from the others (wind, rain or wet soil), so open water may be missed on that date.")
        if place_validated is False:
            caps.append("This place has not been validated: the method has been scored against OPERA only on one lake window, "
                        "and failed on other kinds of place.")
        if caps:
            return "Medium", " ".join(caps)
        reasons.append("the change shows on both later passes")
        reasons.append(f"NASA's OPERA water map confirms {overlap_pct:.0f}% of the new water")
        return "High", "Why high: " + " and ".join(reasons) + "."
    if persistence < 0.8:
        return "Medium", "Part of the new water appears on only one of the later passes."
    if overlap_pct is None:
        return "Medium", "The new water was not checked against NASA's OPERA water map, so this cannot be High."
    return "Medium", f"Moderate agreement with NASA's OPERA water map ({overlap_pct:.0f}% of our new water confirmed)."
