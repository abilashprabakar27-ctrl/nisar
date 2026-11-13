import warnings
import numpy as np
from scipy import ndimage
from science.schema import ChangeResult, PassRef
from science.availability import assess_availability

SMOOTH_SIZE = 5
CHANGE_DB = 3.0
WATER_DB = -18.0
MIN_PATCH_HA = 1.0
HIGH_PERSISTENCE, MED_PERSISTENCE, HIGH_MAX_MASKED = 0.7, 0.5, 0.15
NONE, BECAME, RECEDED, MASKED = 0, 1, 2, 255


def _smooth(a):
    v = np.isfinite(a)
    num = ndimage.uniform_filter(np.where(v, a, 0.0), SMOOTH_SIZE)
    den = ndimage.uniform_filter(v.astype(float), SMOOTH_SIZE)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den
    out[~v] = np.nan
    return out


def _db(x):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(x)


def _median(stack):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(stack, axis=0)


def _classes(b_db, a_db):
    d = a_db - b_db
    with np.errstate(invalid="ignore"):
        return (d <= -CHANGE_DB) & (a_db < WATER_DB), (d >= CHANGE_DB) & (b_db < WATER_DB)


def _drop_small(m, pixel_area_ha):
    lab, n = ndimage.label(m)
    if n == 0:
        return m
    sizes = ndimage.sum(m, lab, index=np.arange(1, n + 1))
    keep = np.concatenate([[False], sizes * pixel_area_ha >= MIN_PATCH_HA])
    return keep[lab]


def detect_change(before, after, *, pixel_area_ha, bbox, before_refs, after_refs,
                  permanent_water=None, steep=None, source="sample"):
    shape = (before or after)[0].shape if (before or after) else (0, 0)
    mask = np.zeros(shape, bool)
    for s in (before, after):
        if s:
            mask |= np.all(np.isnan(np.stack(s)), axis=0)
    for m in (permanent_water, steep):
        if m is not None:
            mask |= np.asarray(m).astype(bool)
    mfrac = float(mask.mean()) if mask.size else 0.0
    status, notes = assess_availability(before_refs, after_refs, mfrac)
    res = ChangeResult(status=status, source=source, bbox=tuple(bbox), before=before_refs,
                       after=after_refs, masked_fraction=mfrac)
    if status != "ok":
        res.message = "Insufficient data: " + " ".join(notes)
        return res, np.full(shape, MASKED, np.uint8)
    res.limits = notes

    sb = [_smooth(x) for x in before]
    sa = [_smooth(x) for x in after]
    b_db, a_db = _db(_median(np.stack(sb))), _db(_median(np.stack(sa)))
    became, receded = _classes(b_db, a_db)
    became = _drop_small(became & ~mask, pixel_area_ha)
    receded = _drop_small(receded & ~mask, pixel_area_ha)
    lab = np.zeros(shape, np.uint8)
    lab[became], lab[receded], lab[mask] = BECAME, RECEDED, MASKED
    res.area_ha = {"likely_became_water": float(became.sum() * pixel_area_ha),
                   "likely_water_receded": float(receded.sum() * pixel_area_ha),
                   "no_change": float(((lab == NONE).sum()) * pixel_area_ha)}

    changed = became | receded
    pers = 0.0
    if changed.any():
        agree = np.zeros(shape)
        for x in sa:
            bq, rq = _classes(b_db, _db(x))
            agree += np.where(became, bq, rq)
        pers = float((agree[changed] / len(sa)).mean())
    n_after = len(after)
    if n_after >= 2 and pers >= HIGH_PERSISTENCE and mfrac < HIGH_MAX_MASKED:
        res.confidence, why = "High", "changed pixels persist"
    elif n_after >= 2 and pers >= MED_PERSISTENCE:
        res.confidence, why = "Medium", "changed pixels persist in only some passes or masking is high"
    else:
        res.confidence, why = "Lower", "weak persistence across after-passes or too few passes"
    res.confidence_reason = f"{why} ({pers:.0%} of {n_after} after-passes agree; {mfrac:.0%} masked)."
    res.message = "Likely changes only; not confirmed."
    return res, lab
