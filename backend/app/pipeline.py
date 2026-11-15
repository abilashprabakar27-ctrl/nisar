"""The six-step analysis: Check -> Fetch -> Prepare -> Detect -> Verify -> Explain."""
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np

from . import catalog, config, data_sources, downloads, resources, store
from .catalog import NotEnoughData
from .science import change, drivers, render, verify
from .science import gcov
from .science.gcov import read_window
from .science.grid import make_grid, resample

STEPS = [("check", "Finding NISAR passes"), ("fetch", "Reading the study area from each pass"),
         ("prepare", "Lining up passes and calming radar speckle"), ("detect", "Comparing before and after"),
         ("verify", "Checking against NASA OPERA"), ("explain", "Writing the answer")]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "area"


def area_km2(bbox) -> float:
    w, s, e, n = bbox
    lat = np.radians((s + n) / 2)
    return abs(e - w) * 111.32 * np.cos(lat) * abs(n - s) * 110.57


def file_url(key: str, name: str) -> str:
    return f"{config.PUBLIC_BASE_URL}/files/{key}/{name}"


class Progress:
    def __init__(self, job_id):
        self.job_id = job_id
        self.t = time.time()
        self.last = None
        self.timings = {}

    def _tick(self, sid):
        now = time.time()
        if self.last:
            self.timings[self.last] = round(now - self.t, 1)
            print(f"  [{self.last}] {self.timings[self.last]} s", flush=True)
        self.t, self.last = now, sid

    def step(self, i, note=None, pct=None):
        sid, label = STEPS[i]
        self._tick(sid)
        pct = pct if pct is not None else int(100 * i / len(STEPS))
        if self.job_id:
            store.update_job(self.job_id, status="running", step=sid, progress=pct,
                             event={"step": sid, "label": label, "note": note})

    def note(self, text, pct):
        if self.job_id:
            store.update_job(self.job_id, progress=pct, event={"step": "fetch", "label": text})


def run_analysis(req: dict, job_id: str | None = None, *, passes=None, reader=read_window, online=True) -> dict:
    """Run the full analysis and return the result dict (also saved to disk)."""
    key = store.result_key(req)
    prog = Progress(job_id)
    t0 = time.time()
    bbox = req["bbox"]
    if area_km2(bbox) > config.MAX_AREA_KM2:
        raise NotEnoughData(f"The area is about {area_km2(bbox):.0f} km². Please choose an area under "
                            f"{config.MAX_AREA_KM2:.0f} km² (about 30 x 30 km).", detail={"reason": "area_too_large"})

    # 1. Check
    prog.step(0)
    if passes is None:
        passes = catalog.search_passes(bbox)
    (trk, direction), before, after, track_passes = catalog.choose_groups(
        passes, req.get("event_date"), req.get("before"), req.get("after"))
    qualities = sorted({p.quality for p in before + after})

    # 2. Fetch (in parallel, only the study-area window)
    prog.step(1, pct=15)
    # every frame of the chosen dates on this track (an area can span two frames)
    wanted = {p.date for p in before + after}
    todo = [p for p in passes if p.track == trk and p.direction == direction and p.date in wanted and p.url]
    wins = {}
    if reader is read_window:   # real NASA files: download with % done and time left
        need = [p for p in todo if not gcov.is_cached(p.url, bbox)]
        tr = downloads.Tracker(len(need), job_id, base_pct=15, span_pct=40)
        prog.note(f"Downloading {len(need)} file(s) from NASA; {len(todo) - len(need)} already on this computer"
                  if need else "All files already on this computer", 15)
        if job_id:
            store.update_job(job_id, download=tr.snapshot())

        def keep(p, w):
            wins.setdefault(p.date, []).append(w)
            print(f"    read {p.date} frame {p.frame}", flush=True)
        downloads.fetch_frames(todo, bbox, tr, on_window=keep)
        tr.finish()
        if job_id:
            store.update_job(job_id, download=tr.snapshot())
    else:
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(reader, p.url, bbox, p.date): p for p in todo}
            for i, fut in enumerate(futs):
                p = futs[fut]
                try:
                    wins.setdefault(p.date, []).append(fut.result())
                except ValueError:  # this frame does not touch the area
                    pass
                prog.note(f"Read pass {p.date} frame {p.frame}", 15 + int(40 * (i + 1) / len(todo)))
    missing = sorted(wanted - set(wins))
    if missing:
        raise NotEnoughData(f"No NISAR frame on {', '.join(missing)} covers this area.", detail={"missing": missing})

    # 3. Prepare: one common grid; frames of the same date are merged
    prog.step(2, pct=58)
    res = 40.0 if req.get("quick") else config.TARGET_RES_M
    grid = make_grid(bbox, wins[before[0].date][0].epsg, res)

    def merged(date, band):
        out = None
        for w in wins[date]:
            a = resample(w, grid, band)
            out = a if out is None else np.where(np.isfinite(out), out, a)
        return out

    hh = {d: merged(d, "hh") for d in wins}
    hv = {d: merged(d, "hv") for d in wins}
    coverage = {d: round(float(np.isfinite(a).mean()), 3) for d, a in hh.items()}

    folder = config.DRIVERS_DIR / slug(req.get("name", "area"))
    dem = data_sources.dem_on_grid(folder, grid)
    steep = data_sources.slope_mask(dem, grid.res) if dem is not None else None

    # 4. Detect
    prog.step(3, pct=68)
    r = change.detect_water_change([hh[p.date] for p in before], [hh[p.date] for p in after], grid.pixel_ha,
                                   extra_mask=steep,
                                   before_hv=[hv[p.date] for p in before], after_hv=[hv[p.date] for p in after])
    if r.masked_fraction > config.MAX_MASKED_FRACTION:
        raise NotEnoughData(f"{r.masked_fraction:.0%} of the area could not be read (radar shadow, steep slopes "
                            f"or outside the swath), so we won't guess. Coverage by date: {coverage}",
                            detail={"reason": "masked", "coverage": coverage})

    # 5. Verify
    prog.step(4, pct=80)
    agreement = verify.run(r.classes, grid, bbox, after[-1].date, folder, online=online,   # OPERA nearest the LAST after pass (the water must persist to it)
                           ours_water=r.first_after_water)

    # 6. Explain
    prog.step(5, pct=90)
    out = store.result_dir(key)
    images = {"bounds": None}
    images["bounds"] = render.classes_png(r.classes, grid, out / "result.png")
    images["result"] = file_url(key, "result.png")
    render.gray_png(r.after_db, grid, out / "after_hh.png", -25, 0)
    render.gray_png(r.before_db, grid, out / "before_hh.png", -25, 0)
    images["hh"], images["before_hh"] = file_url(key, "after_hh.png"), file_url(key, "before_hh.png")
    images["photo"] = data_sources.photo_url(bbox, after[0].date)
    images["passes"] = []
    for p_ in before + after:   # one HH image per pass, for the time-lapse view
        nm = f"pass_{p_.date}.png"
        render.gray_png(change.lee_filter(change.to_db(hh[p_.date])), grid, out / nm, -25, 0)
        images["passes"].append({"date": p_.date, "url": file_url(key, nm),
                                 "group": "before" if p_ in before else "after"})
    hv_after = change.composite([change.lee_filter(change.to_db(hv[p.date])) for p in after])
    if np.isfinite(hv_after).any():
        render.gray_png(hv_after, grid, out / "after_hv.png", -32, -8)
        render.mix_png(r.after_db, hv_after, grid, out / "after_mix.png")
        images["hv"], images["mix"] = file_url(key, "after_hv.png"), file_url(key, "after_mix.png")
    else:
        images["hv"] = images["mix"] = None

    overlap = None
    agree_out = None
    if agreement and "map" in agreement:
        amap = agreement.pop("map")
        coded = amap.copy()
        from PIL import Image
        ll, _ = render.to_lonlat(coded, grid, nearest=True)
        rgba = np.zeros(ll.shape + (4,), "uint8")
        rgba[ll == 1] = (29, 78, 216, 215)
        rgba[ll == 2] = (147, 197, 253, 200)
        rgba[ll == 3] = (245, 158, 11, 200)
        Image.fromarray(rgba, "RGBA").save(out / "agreement.png", optimize=True)
        agreement["map_url"] = file_url(key, "agreement.png")
        overlap = agreement["overlap_pct"]
        agree_out = agreement
    elif agreement:
        agree_out = agreement

    all_dates = [p.date for p in before + after]
    db_all = [change.lee_filter(change.to_db(hh[d])) for d in all_dates]
    series = change.water_area_series(db_all, r.threshold_db, grid.pixel_ha)

    # Reliability checks (each fail-soft: data missing -> "not checked")
    stab = change.radiometric_stability(all_dates, db_all, r.classes, r.threshold_db)
    wc = data_sources.worldcover_on_grid(bbox, grid) if online else None
    lc = change.landcover_shares(r.classes, wc)
    validation = change.validation_status(bbox, [p.date for p in before + after], trk)
    unstable = [f["date"] for f in stab.get("flagged", [])]
    level, reason = change.confidence(len(before), len(after), r.persistence, overlap, r.masked_fraction, qualities,
                                       new_water_ha=r.areas_ha.get("became_water"),
                                       unstable_passes=unstable if stab.get("checked") else None,
                                       cropland_share=lc.get("cropland_share") if r.areas_ha["became_water"] >= 5 else None,
                                       place_validated=validation["this_place_validated"])

    per_pass = [{"date": d, "water_ha": w, "change_ha": None if i == 0 else round(w - series[i - 1], 1)}
                for i, (d, w) in enumerate(zip(all_dates, series))]

    became, receded = r.areas_ha["became_water"], r.areas_ha["water_receded"]
    if became >= 5 and became >= 0.3 * receded:
        label, hect = ("Likely flooding" if level == "High" else "Possible new water"), became
        measured = (f"Radar brightness dropped sharply over {became:,.0f} ha between "
                    f"{before[-1].date} and {after[0].date}" +
                    (" and stayed low on the next pass." if r.persistence >= 0.8 else "."))
        interpreted = ("New water, most likely flooding. A drop like this can also come from very wet soil." if level == "High"
                       else "Radar suggests new water; this has not been checked here.")
    elif receded >= 5:
        label, hect = "Water likely receded", receded
        measured = f"Radar brightness rose over {receded:,.0f} ha that was dark (water) before."
        interpreted = "Water has drained away from these areas."
    else:
        label, hect = "No clear change", 0.0
        measured = "No area larger than 1 hectare changed beyond the 3 dB threshold."
        interpreted = "The surface looks about the same in both groups of passes."
        if level == "High":   # a High reason about new water makes no sense when nothing changed
            level, reason = "Medium", (f"We did not find any change bigger than 1 hectare, using {len(before)} passes before and "
                                       f"{len(after)} after. Very small or short-lived changes could still be missed.")

    drv = drivers.all_drivers(folder, bbox, r.classes, grid.res, [p.date for p in before],
                              [p.date for p in after], dem=dem, online=online)

    limits = ["These are estimates. Very wet fields can sometimes look like water.",
              "Some spots, like steep hillsides, can't be seen clearly and are left out."]
    if any(q != "Validated" for q in qualities):
        limits.append("Some NISAR data used is " + "/".join(q for q in qualities if q != "Validated") +
                      " quality; numbers may change when reprocessed.")
    limits += change.stability_limits(stab)
    if not stab.get("checked"):
        limits.append(f"Pass-to-pass brightness was not checked ({stab.get('note')}).")
    if not lc.get("checked"):
        limits.append("Land cover (ESA WorldCover) was not checked, so we cannot say whether new water lies on cropland.")
    elif lc.get("cropland_share") is not None and lc["cropland_share"] > change.CROPLAND_SHARE_MAX:
        limits.append("Most detected new water lies on cropland, where radar cannot separate a flood from irrigated or "
                      "flooded paddies; on one cropland window our map and OPERA disagreed almost completely.")
    if not validation["this_place_validated"]:
        limits.append("This place and these dates have not been compared with OPERA: the method was compared on one lake window (Jul to Oct 2026, track 83) only.")
    if before[-1].date <= config.DATA_GAP[1] and after[0].date >= config.DATA_GAP[0]:
        limits.append("There are no satellite images from 27 Jul to 10 Aug 2026, and we don't guess what's missing.")

    result = {
        "id": key, "status": "done", "source": "live",
        "area": {"name": req.get("name", "Study area"), "bbox": bbox,
                 "hectares": round(area_km2(bbox) * 100, 0)},
        "question": req.get("question", "change"),
        "window": {"before": [p.date for p in before], "after": [p.date for p in after]},
        "track": {"track": trk, "direction": direction},
        "passes": [{"date": p.date, "track": p.track, "direction": p.direction, "quality": p.quality,
                    "used": p in before + after, "file": p.name} for p in track_passes],
        "images": images,
        "areas_ha": r.areas_ha,
        "water_ha": {"before": r.water_before_ha, "after": r.water_after_ha},
        "headline": {"label": label, "hectares": round(hect, 0),
                     "football_pitches": int(round(hect / config.FOOTBALL_PITCH_HA)),
                     "share_of_area_pct": round(100 * hect / max(area_km2(bbox) * 100, 1), 1)},
        "confidence": {"level": level, "reason": reason},
        "validation": validation,
        "measured": measured, "interpreted": interpreted,
        "agreement": agree_out,
        "per_pass": per_pass,
        "drivers": drv,
        "impact": {"people_1km": None, "roads": None},
        "limits": limits,
        "credits": resources.credits(["asf-vertex", "nisar-guide"] + (["opera"] if overlap is not None else [])
                                     + ["power", "usgs", "worldview"] + (["cop-dem"] if dem is not None else [])
                                     + (["firms"] if (folder / "fires.csv").exists() else [])),
        "watch": {"watched": False, "newest_pass": track_passes[-1].date, "new_pass_available": False},
        "share_url": None,
        "provenance": {"method": store.METHOD_VERSION, "threshold_mode": config.THRESHOLD_MODE, "threshold_db": round(r.threshold_db, 2),
                       "threshold_hv_db": None if r.threshold_hv_db is None else round(r.threshold_hv_db, 2),
                       "change_db": config.CHANGE_DB, "resolution_m": res, "epsg": grid.epsg,
                       "masked_fraction": round(r.masked_fraction, 3), "coverage_by_date": coverage, "persistence": round(r.persistence, 3),
                       "radiometric_stability": stab, "landcover": lc,
                       "polarization_used": "HH + HV" if r.threshold_hv_db is not None else "HH",
                       "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "seconds": round(time.time() - t0, 1), "step_seconds": prog.timings},
    }
    prog._tick("done")
    result["provenance"]["step_seconds"] = prog.timings
    store.save_result(key, result)
    return result


def run_job(job_id: str, req: dict, **kw):
    try:
        res = run_analysis(req, job_id, **kw)
        store.update_job(job_id, status="done", progress=100, step="done",
                         event={"step": "done", "label": "Answer ready"}, result_key=res["id"])
    except NotEnoughData as e:
        store.update_job(job_id, status="not_enough_data", error=str(e), detail=e.detail,
                         event={"step": "stopped", "label": str(e)})
    except Exception as e:  # keep the stage, show a plain message
        traceback.print_exc()
        job = store.load_job(job_id) or {}
        store.update_job(job_id, status="failed", error=f"Something went wrong at step '{job.get('step')}': "
                                                        f"{e.__class__.__name__}: {e}",
                         event={"step": "failed", "label": str(e)})
