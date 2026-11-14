"""Reliability checks: pass-to-pass brightness, land cover, validation status. All offline, synthetic inputs."""
import numpy as np

from app import data_sources
from app.science import change
from app.science.grid import Grid

OK = dict(n_before=2, n_after=2, persistence=1.0, overlap_pct=87, masked_fraction=0.05,
          qualities=["Provisional"], new_water_ha=3000.0)


def conf(**kw):
    a = {**OK, **kw}
    return change.confidence(a["n_before"], a["n_after"], a["persistence"], a["overlap_pct"], a["masked_fraction"],
                             a["qualities"], new_water_ha=a["new_water_ha"],
                             **{k: v for k, v in kw.items() if k in ("unstable_passes", "cropland_share", "place_validated")})


# ---- A. radiometric stability
def _passes(offsets, n=4000, seed=0):
    rng = np.random.default_rng(seed)
    base = rng.normal(-8.0, 0.5, (100, n // 100)).astype("float32")
    return [base + o for o in offsets]


def test_stability_flags_bright_pass():
    dates = ["2026-08-30", "2026-09-11", "2026-09-23", "2026-10-05"]
    classes = np.zeros((100, 40), "uint8")
    st = change.radiometric_stability(dates, _passes([0, 0.2, 3.0, -0.1]), classes, -14.5)
    assert st["checked"] and [f["date"] for f in st["flagged"]] == ["2026-09-23"]
    assert st["flagged"][0]["offset_db"] > 2.5
    text = change.stability_limits(st)[0]
    assert "2026-09-23" in text and "brighter" in text and "open water may be missed" in text
    assert st["median_hh_db"]["2026-09-23"] > st["median_hh_db"]["2026-08-30"] + 2.5


def test_stability_ok_and_darker_and_not_checked():
    dates = ["a", "b", "c", "d"]
    classes = np.zeros((100, 40), "uint8")
    assert change.radiometric_stability(dates, _passes([0, 0.3, -0.4, 0.1]), classes, -14.5)["flagged"] == []
    st = change.radiometric_stability(dates, _passes([0, 0, 0, -2.0]), classes, -14.5)
    assert "darker" in change.stability_limits(st)[0]
    assert change.radiometric_stability(["a"], _passes([0]), classes, -14.5)["checked"] is False
    allwater = np.full((100, 40), change.PERMANENT, "uint8")   # no land pixels at all -> not checked, not a crash
    assert change.radiometric_stability(dates, _passes([0, 0, 0, 0]), allwater, -14.5)["checked"] is False


def test_unstable_pass_blocks_high():
    assert conf()[0] == "High"
    lvl, why = conf(unstable_passes=["2026-09-23"])
    assert lvl == "Medium" and "2026-09-23" in why and "1.5 dB" in why
    assert conf(unstable_passes=[])[0] == "High"


# ---- B. land cover
def test_landcover_shares_and_lower():
    classes = np.zeros((10, 10), "uint8")
    classes[:, :4] = change.BECAME_WATER            # 40 px
    wc = np.full((10, 10), 10, "uint8")
    wc[:, :3] = 40                                  # 30 cropland
    wc[:, 3] = 50                                   # 10 built-up
    lc = change.landcover_shares(classes, wc)
    assert lc["checked"] and lc["cropland_share"] == 0.75 and lc["builtup_share"] == 0.25
    lvl, why = conf(cropland_share=lc["cropland_share"])
    assert lvl == "Lower" and "cropland" in why and "failed validation" in why
    assert conf(cropland_share=0.5)[0] == "High"    # not above 50%


def test_landcover_not_checked_offline_and_no_new_water():
    classes = np.full((5, 5), change.BECAME_WATER, "uint8")
    assert change.landcover_shares(classes, None)["checked"] is False
    assert change.landcover_shares(np.zeros((5, 5), "uint8"), np.zeros((5, 5), "uint8"))["cropland_share"] is None
    assert conf(cropland_share=None)[0] == "High"   # unknown share must not penalise


def test_worldcover_tile_names_and_failsoft(monkeypatch):
    assert data_sources.worldcover_tiles([103.9, 13.05, 104.12, 13.27]) == ["N12E102"]
    assert data_sources.worldcover_tiles([80.25, 26.35, 80.5, 26.6]) == ["N24E078"]
    assert data_sources.worldcover_tiles([-60.5, -3.5, -59.5, -2.5]) == ["S06W063", "S06W060", "S03W063", "S03W060"]
    import rasterio

    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(rasterio, "open", boom)
    grid = Grid(32648, np.arange(10) * 20.0 + 1e5, np.arange(10)[::-1] * 20.0 + 1e6, 20.0)
    assert data_sources.worldcover_on_grid([103.9, 13.05, 104.12, 13.27], grid) is None


# ---- C. validation status
def test_validation_block():
    v = change.validation_status([80.25, 26.35, 80.5, 26.6])
    assert v["this_place"] == "not validated" and v["human_labelled_accuracy"] == "not measured"
    assert any("IoU 0.68" in x and "precision 0.88" in x and "recall 0.74" in x for x in v["validated_against_opera"])
    assert any("0.04" in x for x in v["known_failures"]) and any("2 of 2" in x for x in v["known_failures"])
    inside = change.validation_status([103.95, 13.10, 104.05, 13.20])
    assert inside["this_place"] == "validated against OPERA on one window and season"
    assert change.validation_status([103.9, 12.83, 104.12, 13.05])["this_place"] == "not validated"   # south neighbour


def test_unvalidated_place_capped_at_medium():
    lvl, why = conf(place_validated=False)
    assert lvl == "Medium" and "not been validated" in why
    assert conf(place_validated=True)[0] == "High"


def test_existing_rules_still_win():
    assert conf(qualities=["Beta"], place_validated=False)[0] == "Lower"
    assert conf(overlap_pct=40, place_validated=True)[0] == "Lower"
    lvl, why = conf(new_water_ha=68.0, place_validated=False, unstable_passes=["x"])
    assert lvl == "Medium" and "too little" in why and "not been validated" in why
