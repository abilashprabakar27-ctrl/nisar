"""Per-pass change series for the timeline chart (task #12).

One fixed BEFORE composite (first N usable passes of one geometry) is compared with each
later pass on its own, using the same detector, masks and thresholds as the golden sample
(methods.floods.detect_change; WATER_DB is NOT retuned here).

Honesty rules: every row is ONE after-pass, so persistence cannot be checked. detect_change needs
>=2 after passes (plan rule: High needs >=2), so the single pass is passed in twice and the row is
then forced to confidence "Lower" with single_pass=True. The series is context for the timeline,
not an accuracy claim. Passes inside the permanent data gap are skipped, never filled.
"""
from __future__ import annotations

import csv
import os
from datetime import date
from pathlib import Path

from api.schemas import PassRef
from methods.floods import detect_change
from workers.check import GAP_END, GAP_START

ROOT = Path(__file__).resolve().parents[1]
QUALITY = {"BE": "BETA", "PR": "PROVISIONAL", "VA": "VALIDATED"}
SINGLE_PASS_NOTE = ("Single after-pass: persistence across passes cannot be checked, so confidence is capped "
                    "at Lower. Context for the timeline, not an accuracy claim; areas are likely, not confirmed.")
VERSION_NOTE = "Processing version differs from the before composite; backscatter may not be directly comparable."
NO_OPERA_NOTE = "Single-pass rows are not checked against OPERA."
UNVALIDATED_NOTE = "No permanent-water/terrain masks and no OPERA check for this area: unvalidated."
FIELDS = ["date", "scene", "became_water_ha", "receded_ha", "masked_fraction", "n_passes_used",
          "n_before_passes", "quality_flag", "single_pass", "confidence", "masks_applied", "validated", "note"]


def in_gap(d: str) -> bool:
    return GAP_START <= date.fromisoformat(d) <= GAP_END


def _ref(p) -> PassRef:
    return PassRef(p["scene"], p["date"], int(p["track"]), p["direction"], int(p["frame"]), p.get("quality", "PROVISIONAL"))


def change_series(before: list[dict], after: list[dict], *, bbox, permanent_water=None, dem_slope_deg=None,
                  use_hv=True, masks_applied=False, source="live") -> list[dict]:
    """before/after: pass dicts = read_window output (HH, HV, pixel_area_ha) plus scene, date, track,
    direction, frame, quality and optionally version. Returns one row per usable after-pass, date-sorted."""
    before = sorted((p for p in before if not in_gap(p["date"])), key=lambda p: p["date"])
    after = sorted((p for p in after if not in_gap(p["date"])), key=lambda p: p["date"])
    if len(before) < 2:
        raise ValueError(f"need >=2 usable before passes for the composite, got {len(before)}")
    hv = use_hv and all(p.get("HV") is not None for p in before + after)
    bversions = {p.get("version") for p in before} - {None}
    brefs = [_ref(p) for p in before]
    rows = []
    for p in after:
        r = _ref(p)
        res, _ = detect_change(
            [q["HH"] for q in before], [p["HH"]] * 2, pixel_area_ha=before[0]["pixel_area_ha"], bbox=bbox,
            before_refs=brefs, after_refs=[r, r], permanent_water=permanent_water, dem_slope_deg=dem_slope_deg,
            before_hv=[q["HV"] for q in before] if hv else None, after_hv=[p["HV"]] * 2 if hv else None, source=source)
        flags, notes = [], [SINGLE_PASS_NOTE]
        if res.status != "ok":
            flags.append("insufficient_data")
            notes.append(res.message)
        if p.get("version") and bversions and p["version"] not in bversions:
            flags.append("version_mismatch")
            notes.append(VERSION_NOTE)
        if any("fixed" in s and "threshold" in s for s in res.limits):
            flags.append("threshold_fallback")
            notes.append("A change threshold fell back to the fixed value.")
        if not masks_applied:
            notes.append(UNVALIDATED_NOTE)
        notes.append(NO_OPERA_NOTE)
        ok = res.status == "ok"
        rows.append({
            "date": p["date"], "scene": p["scene"],
            "became_water_ha": round(res.area_ha["likely_became_water"], 1) if ok else None,
            "receded_ha": round(res.area_ha["likely_water_receded"], 1) if ok else None,
            "masked_fraction": round(res.masked_fraction, 3), "n_passes_used": 1, "n_before_passes": len(before),
            "quality_flag": "+".join(flags) if flags else "ok", "single_pass": True,
            "confidence": "Lower", "masks_applied": bool(masks_applied), "validated": False, "note": " ".join(notes)})
    return rows


def _catalog_rows(area, track, frame, catalog=None):
    path = Path(catalog) if catalog else ROOT / "data" / "catalog" / "pass_counts.csv"
    with path.open(newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["area"] == area and r["track"] == str(track)
                and r["frame"] == str(frame) and r.get("in_gap", "").lower() != "true"]
    return sorted(rows, key=lambda r: r["date"])


def _meta(r):
    q = QUALITY.get(r["quality"].split(";")[0].split("=")[-1], "BETA")
    ver = dict(kv.split("=", 1) for kv in r["quality"].split(";") if "=" in kv).get("crid")
    return {"scene": r["scene"], "date": r["date"], "track": r["track"], "direction": r["direction"],
            "frame": r["frame"], "quality": q, "version": ver}


def series_for_area(area, bbox, track, frame, *, n_before=3, data_dir=None, cache_dir=None, pols=("HHHH", "HVHV"),
                    workers=4, on_step=None, catalog=None):
    """Read windows (cached) for one geometry and compute the series. Returns (rows, info)."""
    from workers.fetch import fetch_passes
    from workers.pipeline import _masks
    rows = _catalog_rows(area, track, frame, catalog)
    data_dir = Path(data_dir or os.environ.get("NISAR_DATA", os.path.expanduser("~/nisar_data")))
    cache_dir = cache_dir or ROOT / "data" / "cache" / "passes"
    refs = [{"scene": r["scene"], "path": str(data_dir / f"{r['scene']}.h5")} if (data_dir / f"{r['scene']}.h5").exists()
            else {"scene": r["scene"], "url": r["url"]} for r in rows]
    wins = fetch_passes(refs, bbox, cache_dir, workers=workers, on_step=on_step, pols=pols)
    passes = [{**w, **_meta(r)} for w, r in zip(wins, rows)]
    perm = slope = None
    for cand in dict.fromkeys((area, area.split("_", 1)[-1])):   # data/reference/<area>/ or <name>/ (tonlesap)
        perm, slope = _masks("x_" + cand, wins[0])               # _masks takes the part after the first '_'
        if perm is not None:
            break
    usable = [p for p in passes if not in_gap(p["date"])]
    out = change_series(usable[:n_before], usable[n_before:], bbox=bbox, permanent_water=perm, dem_slope_deg=slope,
                        use_hv="HVHV" in pols, masks_applied=perm is not None, source="saved")
    info = {"area": area, "bbox": list(bbox), "track": int(track), "frame": int(frame),
            "before_dates": [p["date"] for p in usable[:n_before]], "masks": perm is not None,
            "polarization": "HH+HV" if "HVHV" in pols and all(p.get("HV") is not None for p in usable) else "HH"}
    return out, info
