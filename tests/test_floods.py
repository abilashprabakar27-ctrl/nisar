import numpy as np
from api.schemas import PassRef
from methods.floods import detect_change

HA = 0.1  # pixel area; 10 px = 1 ha
BBOX = (0.0, 0.0, 1.0, 1.0)


def refs(dates, q="VALIDATED"):
    return [PassRef("s" + d, d, 1, "ASCENDING", 1, q) for d in dates]


BR = refs(["2026-06-01", "2026-06-13", "2026-06-25"])
AR = refs(["2026-07-01", "2026-07-07", "2026-07-13"])


def scene(rng, flood=None, n=3, land=0.1, wet=0.004):
    out = []
    for _ in range(n):
        p = np.full((100, 100), land)
        if flood:
            r0, r1, c0, c1 = flood
            p[r0:r1, c0:c1] = wet
        out.append(p * rng.exponential(1.0, p.shape))
    return out


def run(before, after, **kw):
    kw.setdefault("before_refs", BR[:len(before)])
    kw.setdefault("after_refs", AR[:len(after)])
    return detect_change(before, after, pixel_area_ha=HA, bbox=BBOX, **kw)


def test_planted_flood_recovered():
    rng = np.random.default_rng(0)
    res, lab = run(scene(rng), scene(rng, (30, 50, 30, 60)))
    assert res.status == "ok" and lab.dtype == np.uint8
    assert 35 < res.area_ha["likely_became_water"] <= 65  # edges erode via smoothing
    assert res.area_ha["likely_water_receded"] < 1.0
    assert res.confidence == "High"
    assert lab[40, 45] == 1 and lab[5, 5] == 0


def test_receded():
    rng = np.random.default_rng(1)
    res, lab = run(scene(rng, (30, 50, 30, 60)), scene(rng))
    assert res.area_ha["likely_water_receded"] > 35 and lab[40, 45] == 2


def test_noise_only():
    rng = np.random.default_rng(2)
    res, lab = run(scene(rng), scene(rng))
    assert res.area_ha["likely_became_water"] < 1.0
    assert (lab == 1).mean() < 0.001


def test_small_patch_dropped():
    rng = np.random.default_rng(3)
    res, lab = run(scene(rng), scene(rng, (50, 53, 50, 53)))  # 9 px < 1 ha
    assert res.area_ha["likely_became_water"] == 0 and not (lab == 1).any()


def test_one_pass_insufficient():
    rng = np.random.default_rng(4)
    res, lab = run(scene(rng, n=1), scene(rng, (30, 50, 30, 60)))
    assert res.status == "insufficient_data" and res.area_ha == {} and res.message


def test_masked_over_30_insufficient():
    rng = np.random.default_rng(5)
    w = np.zeros((100, 100), bool)
    w[:, :40] = True
    res, _ = run(scene(rng), scene(rng, (30, 50, 50, 80)), permanent_water=w)
    assert res.status == "insufficient_data"


def test_masks_excluded():
    rng = np.random.default_rng(6)
    w = np.zeros((100, 100), bool)
    w[30:50, 30:45] = True
    res, lab = run(scene(rng), scene(rng, (30, 50, 30, 60)), permanent_water=w)
    assert lab[40, 35] == 255 and lab[40, 55] == 1
    assert 0 < res.masked_fraction < 0.3


def test_mixed_beta_warning():
    rng = np.random.default_rng(7)
    br = refs(["2026-06-01", "2026-06-13", "2026-06-25"], "BETA")
    res, _ = run(scene(rng), scene(rng, (30, 50, 30, 60)), before_refs=br)
    assert any("BETA" in x for x in res.limits)


def test_gap_warning():
    rng = np.random.default_rng(8)
    ar = refs(["2026-08-15", "2026-08-21", "2026-08-27"])
    res, _ = run(scene(rng), scene(rng, (30, 50, 30, 60)), after_refs=ar)
    assert any("gap" in x.lower() for x in res.limits)


def test_single_after_never_high():
    rng = np.random.default_rng(9)
    res, _ = run(scene(rng), scene(rng, (30, 50, 30, 60), n=1))
    assert res.status == "insufficient_data" or res.confidence != "High"


# ---- s5: Lee + Otsu + HV flooded vegetation + provenance ----
import methods.floods as floods
from api.schemas import validate_result


def hv_scene(rng, n=3, level=0.02, patch=None, patch_level=None):
    out = []
    for _ in range(n):
        p = np.full((100, 100), level)
        if patch:
            r0, r1, c0, c1 = patch
            p[r0:r1, c0:c1] = patch_level
        out.append(p * rng.exponential(1.0, p.shape))
    return out


def bright_scene(rng, patch, n=3, land=0.1, gain_db=6.0):
    out = []
    for _ in range(n):
        p = np.full((100, 100), land)
        r0, r1, c0, c1 = patch
        p[r0:r1, c0:c1] = land * 10 ** (gain_db / 10)
        out.append(p * rng.exponential(1.0, p.shape))
    return out


FOREST = (30, 50, 30, 60)


def test_flood_recovered_by_otsu_not_fixed_threshold(monkeypatch):
    monkeypatch.setattr(floods, "CHANGE_DB", 99.0)  # fixed threshold unusable -> must be Otsu
    rng = np.random.default_rng(10)
    res, lab = run(scene(rng), scene(rng, (30, 50, 30, 60)))
    assert 35 < res.area_ha["likely_became_water"] <= 65 and lab[40, 45] == 1
    assert not any("became water" in x and "fixed" in x for x in res.limits)


def test_flooded_vegetation_only_with_hv():
    rng = np.random.default_rng(11)
    b, a = scene(rng), bright_scene(rng, FOREST)
    bhv, ahv = hv_scene(rng), hv_scene(rng)
    res, lab = run(b, a, before_hv=bhv, after_hv=ahv)
    assert lab[40, 45] == 3 and lab[5, 5] == 0
    assert 35 < res.area_ha["likely_flooded_vegetation"] <= 65
    assert res.polarization == "HH+HV"
    res2, lab2 = run(b, a)
    assert not (lab2 == 3).any() and "likely_flooded_vegetation" not in res2.area_ha
    assert res2.polarization == "HH"
    assert "HV not provided: flooded vegetation not assessed" in res2.limits


def test_hv_drop_not_flooded_vegetation():
    rng = np.random.default_rng(12)
    b, a = scene(rng), bright_scene(rng, FOREST)
    res, lab = run(b, a, before_hv=hv_scene(rng), after_hv=hv_scene(rng, patch=FOREST, patch_level=0.005))
    assert not (lab == 3).any() and res.area_ha["likely_flooded_vegetation"] == 0


def test_mixed_beta_provisional_reports_beta():
    rng = np.random.default_rng(13)
    br = refs(["2026-06-01", "2026-06-13", "2026-06-25"], "BETA")
    ar = refs(["2026-07-01", "2026-07-07", "2026-07-13"], "PROVISIONAL")
    res, _ = run(scene(rng), scene(rng, (30, 50, 30, 60)), before_refs=br, after_refs=ar)
    assert res.quality_level == "BETA" and any("lowest" in x.lower() for x in res.limits)


def test_degenerate_no_change_falls_back():
    rng = np.random.default_rng(14)
    res, lab = run(scene(rng), scene(rng))
    assert res.status == "ok" and not np.isin(lab, [1, 2, 3]).any()
    assert any("fixed 3 dB" in x for x in res.limits)
    validate_result(res.to_dict())


def test_ok_result_has_provenance():
    rng = np.random.default_rng(15)
    res, _ = run(scene(rng), scene(rng, (30, 50, 30, 60)))
    validate_result(res.to_dict())
    assert res.method_version == "floods-0.3.0" and res.quality_level == "VALIDATED"
    assert "HH" in res.measured and " ha" in res.measured
    assert res.interpreted.startswith("Likely") and "not confirmed" in res.interpreted


def test_shadow_and_slope_masked():
    rng = np.random.default_rng(16)
    sh = np.zeros((100, 100), bool); sh[30:50, 30:40] = True
    sl = np.zeros((100, 100)); sl[30:50, 50:60] = 30.0
    _, lab = run(scene(rng), scene(rng, (30, 50, 30, 60)), shadow=sh, dem_slope_deg=sl)
    assert lab[40, 35] == 255 and lab[40, 55] == 255 and lab[40, 45] == 1
