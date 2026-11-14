"""Water-change detection on NISAR HH backscatter.

Method (explainable, no trained model):
1. linear power -> decibels; Lee speckle filter
2. median composite of the before passes and of the after passes
3. water threshold from Otsu on the after image (clamped to a physical range)
4. classes: became water / water receded / permanent water / no change / masked
5. drop patches smaller than 1 hectare
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

    def is_water(hh, hv):
        w = hh < thr
        if hv is not None:
            w &= np.where(np.isfinite(hv), hv < thr_hv, True)
        return w

    water_b = is_water(bc, bhv) & ~invalid
    water_a = is_water(ac, ahv) & ~invalid

    # every after pass must agree, so one odd pass (wind, rain, crop growth) cannot create change
    each_after_water = [is_water(a_db[i], ahv_db[i] if use_hv else None) for i in range(len(a_db))]
    each_after_dry = [~w for w in each_after_water]
    all_after_water = np.logical_and.reduce(each_after_water)
    all_after_dry = np.logical_and.reduce(each_after_dry)

    min_px = int(np.ceil(config.MIN_PATCH_HA / pixel_ha))
    became = remove_small(water_a & ~water_b & (diff < -config.CHANGE_DB), min_px)
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


def confidence(n_before: int, n_after: int, persistence: float, overlap_pct: float | None,
               masked_fraction: float, qualities: list[str]) -> tuple[str, str]:
    """Rules from the Night Shift 1 pack.

    overlap_pct must be the STRICT figure (share of our *new* water that OPERA confirms, verify.compare), never
    one that counts permanent water. Without it (no OPERA check, or no new water) the level cannot be High.
    """
    reasons = []
    if "Beta" in qualities:
        return "Lower", "Uses Beta-quality NISAR data, which is still being calibrated."
    if masked_fraction > 0.15:
        return "Lower", f"{masked_fraction:.0%} of the area could not be read (radar shadow, steep slopes or no data)."
    if overlap_pct is not None and overlap_pct < 50:
        return "Lower", f"Only {overlap_pct:.0f}% overlap with NASA's OPERA water map."
    high = n_before >= 2 and n_after >= 2 and persistence >= 0.8 and overlap_pct is not None and overlap_pct >= 75
    if high:
        reasons.append("the change shows on both later passes")
        if overlap_pct is not None:
            reasons.append(f"NASA's OPERA water map confirms {overlap_pct:.0f}% of the new water")
        return "High", "Why high: " + " and ".join(reasons) + "."
    if persistence < 0.8:
        return "Medium", "Part of the new water appears on only one of the later passes."
    if overlap_pct is None:
        return "Medium", "The new water was not checked against NASA's OPERA water map, so this cannot be High."
    return "Medium", f"Moderate agreement with NASA's OPERA water map ({overlap_pct:.0f}% of our new water confirmed)."
