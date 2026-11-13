"""Flood / wetland change (Final Architecture s5): HH (+HV for flooded vegetation).

Lee-filtered linear power -> median composites -> dB log-ratio -> Otsu thresholds per tail.
"""
import warnings
import numpy as np
from scipy import ndimage
from api.schemas import ChangeResult, PassRef
from workers.check import assess_availability, lowest_quality

METHOD_VERSION = "floods-0.2.0"
LEE_SIZE = 5
ENL = 1.0                  # equivalent number of looks of the input (single-look intensity)
CHANGE_DB = 3.0            # fallback threshold when the Otsu histogram is degenerate
WATER_DB = -18.0           # open-water ceiling
HV_TOL_DB = 1.0            # HV "not decreasing" tolerance (noise)
STEEP_DEG = 10.0           # slope above which pixels are masked
MIN_CHANGED_PX = 50        # fewer tail pixels above Otsu -> degenerate
MIN_SEPARATION_DB = 3.0    # Otsu class means closer than this -> degenerate (unimodal noise)
OTSU_BINS = 256
MIN_PATCH_HA = 1.0
HIGH_PERSISTENCE, MED_PERSISTENCE, HIGH_MAX_MASKED = 0.7, 0.5, 0.15
NONE, BECAME, RECEDED, FLOODED_VEG, MASKED = 0, 1, 2, 3, 255


def _lee(a):
    """NaN-safe 5x5 Lee filter on linear power."""
    v = np.isfinite(a)
    z = np.where(v, a, 0.0)
    n = ndimage.uniform_filter(v.astype(float), LEE_SIZE)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = ndimage.uniform_filter(z, LEE_SIZE) / n
        var = np.maximum(ndimage.uniform_filter(z * z, LEE_SIZE) / n - m * m, 0.0)
        cu2 = 1.0 / ENL
        var_x = np.maximum((var - cu2 * m * m) / (1 + cu2), 0.0)
        k = np.where(var > 0, var_x / var, 0.0)
    out = m + k * (z - m)
    out[~v] = np.nan
    return out


def _db(x):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(x)


def _median(stack):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(stack, axis=0)


def otsu(values, bins=OTSU_BINS):
    """Otsu threshold on finite values. Returns (threshold, lower_mean, upper_mean, n_upper) or None."""
    x = values[np.isfinite(values)]
    if x.size < 2 or x.min() == x.max():
        return None
    hist, edges = np.histogram(x, bins=bins)
    c = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = x.size - w0
    s0 = np.cumsum(hist * c)
    with np.errstate(invalid="ignore", divide="ignore"):
        m0 = s0 / w0
        m1 = (s0[-1] - s0) / w1
        between = w0 * w1 * (m0 - m1) ** 2
    between[~np.isfinite(between)] = -1
    i = int(np.argmax(between))
    return float(edges[i + 1]), float(m0[i]), float(m1[i]), int(w1[i])


def _tail_threshold(tail):
    """Otsu on one tail (positive magnitudes). Returns (threshold_db, used_otsu)."""
    r = otsu(tail)
    if r is None:
        return CHANGE_DB, False
    t, lo, hi, n_up = r
    if n_up < MIN_CHANGED_PX or hi - lo < MIN_SEPARATION_DB:
        return CHANGE_DB, False
    return t, True


def _drop_small(m, pixel_area_ha):
    lab, n = ndimage.label(m)
    if n == 0:
        return m
    sizes = ndimage.sum(m, lab, index=np.arange(1, n + 1))
    keep = np.concatenate([[False], sizes * pixel_area_ha >= MIN_PATCH_HA])
    return keep[lab]


def _classify(b_db, a_db, t_neg, t_pos, hv_ok=None):
    d = a_db - b_db
    with np.errstate(invalid="ignore"):
        became = (d <= -t_neg) & (a_db < WATER_DB)
        receded = (d >= t_pos) & (b_db < WATER_DB)
        veg = ((d >= t_pos) & ~(b_db < WATER_DB) & hv_ok) if hv_ok is not None else np.zeros(d.shape, bool)
    return became, receded, veg


def _hv_ok(b_hv_db, a_hv_db):
    with np.errstate(invalid="ignore"):
        return (a_hv_db - b_hv_db) >= -HV_TOL_DB


def detect_change(before, after, *, pixel_area_ha, bbox, before_refs, after_refs,
                  permanent_water=None, steep=None, source="sample",
                  before_hv=None, after_hv=None, dem_slope_deg=None, shadow=None):
    shape = (before or after)[0].shape if (before or after) else (0, 0)
    mask = np.zeros(shape, bool)
    for s in (before, after):
        if s:
            mask |= np.all(np.isnan(np.stack(s)), axis=0)
    for m in (permanent_water, steep, shadow):
        if m is not None:
            mask |= np.asarray(m).astype(bool)
    if dem_slope_deg is not None:
        with np.errstate(invalid="ignore"):
            mask |= np.asarray(dem_slope_deg, float) > STEEP_DEG
    mfrac = float(mask.mean()) if mask.size else 0.0
    status, notes = assess_availability(before_refs, after_refs, mfrac)
    res = ChangeResult(status=status, source=source, bbox=tuple(bbox), before=before_refs,
                       after=after_refs, masked_fraction=mfrac)
    if status != "ok":
        res.message = "Insufficient data: " + " ".join(notes)
        return res, np.full(shape, MASKED, np.uint8)
    res.limits = list(notes)
    use_hv = bool(before_hv) and bool(after_hv)
    res.quality_level = lowest_quality(before_refs + after_refs)
    res.polarization = "HH+HV" if use_hv else "HH"
    res.method_version = METHOD_VERSION

    sa = [_lee(x) for x in after]
    b_db = _db(_median(np.stack([_lee(x) for x in before])))
    a_db = _db(_median(np.stack(sa)))
    d = a_db - b_db
    dv = d[~mask & np.isfinite(d)]
    t_neg, otsu_neg = _tail_threshold(-dv[dv < 0])
    t_pos, otsu_pos = _tail_threshold(dv[dv > 0])
    for ok, name in ((otsu_neg, "darkening (became water)"),
                     (otsu_pos, "brightening (water receded / flooded vegetation)")):
        if not ok:
            res.limits.append(f"Too few changed pixels for an adaptive {name} threshold; fixed {CHANGE_DB:g} dB used.")

    hv_ok, sa_hv, b_hv_db = None, None, None
    if use_hv:
        sa_hv = [_lee(x) for x in after_hv]
        b_hv_db = _db(_median(np.stack([_lee(x) for x in before_hv])))
        hv_ok = _hv_ok(b_hv_db, _db(_median(np.stack(sa_hv))))
    else:
        res.limits.append("HV not provided: flooded vegetation not assessed")

    became, receded, veg = _classify(b_db, a_db, t_neg, t_pos, hv_ok)
    became = _drop_small(became & ~mask, pixel_area_ha)
    receded = _drop_small(receded & ~mask, pixel_area_ha)
    veg = _drop_small(veg & ~mask, pixel_area_ha)
    lab = np.zeros(shape, np.uint8)
    lab[became], lab[receded], lab[veg], lab[mask] = BECAME, RECEDED, FLOODED_VEG, MASKED

    def ha(m):
        return float(m.sum() * pixel_area_ha)

    res.area_ha = {"likely_became_water": ha(became), "likely_water_receded": ha(receded)}
    if use_hv:
        res.area_ha["likely_flooded_vegetation"] = ha(veg)
    res.area_ha["no_change"] = ha(lab == NONE)

    changed = became | receded | veg
    pers = 0.0
    if changed.any():
        agree = np.zeros(shape)
        for i, x in enumerate(sa):
            hv_i = _hv_ok(b_hv_db, _db(sa_hv[i])) if use_hv and i < len(sa_hv) else hv_ok
            bq, rq, vq = _classify(b_db, _db(x), t_neg, t_pos, hv_i)
            agree += np.where(became, bq, np.where(receded, rq, vq))
        pers = float((agree[changed] / len(sa)).mean())
    n_after = len(after)
    if n_after >= 2 and pers >= HIGH_PERSISTENCE and mfrac < HIGH_MAX_MASKED:
        res.confidence, why = "High", "changed pixels persist"
    elif n_after >= 2 and pers >= MED_PERSISTENCE:
        res.confidence, why = "Medium", "changed pixels persist in only some passes or masking is high"
    else:
        res.confidence, why = "Lower", "weak persistence across after-passes or too few passes"
    res.confidence_reason = f"{why} ({pers:.0%} of {n_after} after-passes agree; {mfrac:.0%} masked)."

    thr = (f"thresholds -{t_neg:.1f}/+{t_pos:.1f} dB "
           f"({'Otsu' if otsu_neg else 'fixed'}/{'Otsu' if otsu_pos else 'fixed'})")
    if changed.any():
        res.measured = (f"Radar backscatter in HH changed by a median {float(np.nanmedian(d[changed])):+.1f} dB "
                        f"over {ha(changed):.1f} ha; {thr}.")
        parts = [f"{v:.1f} ha {k.removeprefix('likely_').replace('_', ' ')}"
                 for k, v in res.area_ha.items() if k != "no_change" and v > 0]
        res.interpreted = "Likely " + ", ".join(parts) + "; not confirmed."
    else:
        res.measured = (f"Radar backscatter in HH changed by less than the {thr} over any patch of "
                        f"{MIN_PATCH_HA:g} ha or more (0.0 ha).")
        res.interpreted = "Likely no flood-related change; not confirmed."
    res.message = "Likely changes only; not confirmed."
    return res, lab
