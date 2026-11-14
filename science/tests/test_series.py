import numpy as np
import pytest

from workers.series import change_series, in_gap

BBOX = (0.0, 0.0, 0.01, 0.01)
N = 80


def _pass(d, flood_cols=0, version="P1", hv=True, i=0):
    rng = np.random.default_rng(i)
    hh = rng.gamma(20, 0.01, (N, N)).astype("float32")      # ~ -7 dB land
    hvv = hh * 0.2
    hh[:, :flood_cols] = rng.gamma(20, 0.0005, (N, flood_cols))  # ~ -17 dB water
    return {"HH": hh, "HV": hvv if hv else None, "pixel_area_ha": 1.0, "scene": f"S{d}", "date": d, "track": 83,
            "direction": "ASCENDING", "frame": 8, "quality": "PROVISIONAL", "version": version}


def _scene(cols_by_date, **kw):
    before = [_pass("2026-06-19", i=1), _pass("2026-07-01", i=2), _pass("2026-07-13", i=3)]
    after = [_pass(d, c, i=10 + k, **kw) for k, (d, c) in enumerate(cols_by_date)]
    return before, after


def test_flood_grows_over_passes_and_is_single_pass_flagged():
    b, a = _scene([("2026-08-18", 10), ("2026-09-11", 25), ("2026-10-05", 40)])
    rows = change_series(b, a, bbox=BBOX)
    assert [r["date"] for r in rows] == ["2026-08-18", "2026-09-11", "2026-10-05"]
    w = [r["became_water_ha"] for r in rows]
    assert w[0] < w[1] < w[2]
    assert w[2] > 0.6 * 40 * N
    for r in rows:
        assert r["single_pass"] is True and r["n_passes_used"] == 1 and r["n_before_passes"] == 3
        assert r["confidence"] == "Lower" and "Single after-pass" in r["note"]
        assert r["receded_ha"] < 0.1 * r["became_water_ha"]


def test_gap_date_skipped():
    b, a = _scene([("2026-08-01", 30), ("2026-08-18", 30)])
    rows = change_series(b, a, bbox=BBOX)
    assert [r["date"] for r in rows] == ["2026-08-18"]
    assert in_gap("2026-08-01") and not in_gap("2026-08-18")


def test_version_mismatch_flagged_and_unvalidated_note():
    b, a = _scene([("2026-09-11", 20)])
    a.append(_pass("2026-10-29", 20, version="P2", i=99))
    rows = change_series(b, a, bbox=BBOX)
    assert "version_mismatch" in rows[1]["quality_flag"]
    assert "version_mismatch" not in rows[0]["quality_flag"]
    assert all(r["validated"] is False and "unvalidated" in r["note"] for r in rows)


def test_hh_only_and_too_few_before():
    b, a = _scene([("2026-09-11", 20)], hv=False)
    b = [{**p, "HV": None} for p in b]
    assert change_series(b, a, bbox=BBOX)[0]["became_water_ha"] > 0
    with pytest.raises(ValueError):
        change_series(b[:1], a, bbox=BBOX)


def test_masked_fraction_reported():
    b, a = _scene([("2026-09-11", 20)])
    perm = np.zeros((N, N), bool); perm[:, 70:] = True
    r = change_series(b, a, bbox=BBOX, permanent_water=perm, masks_applied=True)[0]
    assert abs(r["masked_fraction"] - 10 / N) < 0.01 and r["masks_applied"] is True and r["validated"] is False
