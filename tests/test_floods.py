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
