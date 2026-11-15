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
    # no independent reference backs the new water: the cropland cap applies
    lvl, why = change.confidence(2, 2, 1.0, None, 0.05, ["Provisional"], cropland_share=lc["cropland_share"])
    assert lvl == "Lower" and "farmland" in why and "disagreed almost completely" in why
    # OPERA also shows water on 87% of the new water: a flooded paddy floodplain is real flooding, no cap
    assert conf(cropland_share=lc["cropland_share"])[0] != "Lower"
    # OPERA weak (<75%) on cropland: cap still applies
    assert change.confidence(2, 2, 1.0, 60, 0.05, ["Provisional"], cropland_share=0.9)[0] == "Lower"
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
DATES_IN = ["2026-08-30", "2026-09-11", "2026-09-23", "2026-10-05"]


def test_validation_block():
    v = change.validation_status([80.25, 26.35, 80.5, 26.6], DATES_IN, "083")
    assert v["this_place"] == "not compared here" and v["human_labelled_accuracy"] == "not measured"
    txt = " ".join(v["compared_with_opera"])
    assert "IoU 0.68 [0.64-0.72]" in txt and "precision 0.88" in txt and "recall 0.75" in txt and "not validated" in txt
    assert "validated_against_opera" not in v
    assert any("0.04" in x for x in v["known_failures"]) and any("2 of 2" in x for x in v["known_failures"])
    box = [103.95, 13.10, 104.05, 13.20]
    inside = change.validation_status(box, DATES_IN, "083")
    assert inside["this_place"] == "compared with OPERA here for Jul to Oct 2026, track 83; other dates are not checked"
    assert inside["this_place_validated"] is True and change.validation_status(box, DATES_IN, 83)["this_place_validated"]
    assert change.validation_status([103.9, 12.83, 104.12, 13.05], DATES_IN, "083")["this_place"] == "not compared here"   # south neighbour
    # right box, wrong dates or wrong track or no dates: not compared here
    assert not change.validation_status(box, ["2027-02-01", "2027-02-13"], "083")["this_place_validated"]
    assert not change.validation_status(box, DATES_IN, "098")["this_place_validated"]
    assert not change.validation_status(box)["this_place_validated"]


def test_honest_wording():
    import re
    from pathlib import Path
    ok = change.confidence(2, 2, 1.0, 87, 0.05, ["Provisional"], new_water_ha=3000.0, place_validated=True)
    assert ok[0] == "High"
    assert "about 87% of the area we mark as new water is also water in another satellite's water map" in ok[1]
    assert "does not tell us whether the water is new" in ok[1]
    assert "both later passes" not in ok[1]
    texts = [ok[1], conf(overlap_pct=60)[1], conf(overlap_pct=None)[1], conf(cropland_share=0.9, overlap_pct=60)[1]]
    texts += [x for x in change.validation_status([0, 0, 1, 1])["compared_with_opera"]]
    for t in texts:
        assert not re.search(r"confirm|independent|VALIDATED METHOD", t, re.I), t
    from app.science import verify
    assert not re.search(r"confirm|independent", Path(verify.__file__).read_text().split('"""', 2)[1], re.I)
    ui = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text()
    assert "VALIDATED METHOD" not in ui and "Confirmed" not in ui and "confirms" not in ui and "INDEPENDENT" not in ui


def test_labels_not_high_are_cautious():
    from app import pipeline
    src = open(pipeline.__file__).read()
    assert "Possible new water" in src and "Radar suggests new water; this has not been checked here." in src
    assert "numbers may change when reprocessed" in src and "shift slightly" not in src


def test_unvalidated_place_capped_at_medium():
    lvl, why = conf(place_validated=False)
    assert lvl == "Medium" and "not checked this place" in why
    assert conf(place_validated=True)[0] == "High"


def test_existing_rules_still_win():
    assert conf(qualities=["Beta"], place_validated=False)[0] == "Lower"
    assert conf(overlap_pct=40, place_validated=True)[0] == "Lower"
    lvl, why = conf(new_water_ha=68.0, place_validated=False, unstable_passes=["x"])
    assert lvl == "Medium" and "too little" in why and "not checked this place" in why


def test_accuracy_is_shown_only_for_story_places():
    from app.science import change
    for sid, st in change.STORIES.items():
        w, so, e, n = st["bbox"]
        v = change.validation_status((w + 0.05, so + 0.05, e - 0.05, n - 0.05))
        assert v["story"] == sid and v["story_name"] == st["name"]
        assert v["human_labelled_accuracy"] == "not measured"
        assert v["reference_note"] == "OPERA and Sentinel-2 are other satellite products, not ground truth"
    assert change.validation_status((92.2, 26.2, 92.3, 26.3))["measured"] == []      # Morigaon: nothing measured
    assert "monsoon cloud" in change.validation_status((92.2, 26.2, 92.3, 26.3))["measured_note"]
    k = change.validation_status((80.3, 26.4, 80.45, 26.55))["measured"]
    assert {r["reference"] for r in k} == {"NASA OPERA", "Sentinel-2"}
    # a place that is not a story shows no numbers and says so
    far = change.validation_status((103.9, 13.05, 104.12, 13.27))
    assert far["story"] is None and far["measured"] == [] and "only for the three story places" in far["measured_note"]
    text = " ".join(str(x) for st in change.STORIES.values() for r in st["rows"] for x in r.values()).lower()
    for bad in ("confirmed", "validated", "independent", "beats", "sen1floods11"):
        assert bad not in text


def test_assistant_answers_accuracy_from_the_story_rows():
    from app import assistant
    from app.science import change
    res = {"confidence": {"level": "Medium", "reason": "x"}, "validation": change.validation_status((80.3, 26.4, 80.45, 26.55))}
    a = assistant.answer(res, "what is the precision and recall?")
    assert "Sentinel-2" in a["answer"] and "0.14" in a["answer"] and "not ground truth" in a["answer"]
    none = assistant.answer({"validation": change.validation_status((103.9, 13.05, 104.12, 13.27))}, "how accurate is it?")
    assert "No accuracy has been measured" in none["answer"]
