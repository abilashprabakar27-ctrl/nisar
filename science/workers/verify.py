import numpy as np


def _ratio(n, d):
    return float(n / d) if d else None


def validate(pred, opera_water_after, opera_water_before, opera_date_gap_days, checkpoints=None) -> dict:
    p = np.asarray(pred) == 1
    o = np.asarray(opera_water_after).astype(bool)
    if opera_water_before is not None:
        o = o & ~np.asarray(opera_water_before).astype(bool)
    inter = int((p & o).sum())
    acc, cps = None, checkpoints or []
    ok = [(r, c, t) for r, c, t in cps if 0 <= r < p.shape[0] and 0 <= c < p.shape[1]]
    if ok:
        acc = float(np.mean([bool(p[r, c]) == bool(t) for r, c, t in ok]))
    return {
        "overlap": _ratio(inter, int((p | o).sum())),
        "precision": _ratio(inter, int(p.sum())),
        "recall": _ratio(inter, int(o.sum())),
        "n_pixels": int(p.size),
        "n_checkpoints": len(cps),
        "checkpoint_accuracy": acc,
        "opera_date_gap_days": opera_date_gap_days,
    }
