"""FastAPI server for the NISAR change explorer demo.

Endpoints: /places /availability /analyses (+ /{id}, /events, /agreement). Config comes only from env vars: NISAR_CACHE_DIR, NISAR_CATALOG_DIR, EARTHDATA_TOKEN (read by the science layer later).
"""
import csv
import math
import os
from collections import OrderedDict
from datetime import date
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator

from workers.check import assess_availability, lowest_quality

from . import cache, jobs
from .schemas import PassRef, validate_result

ROOT = Path(__file__).resolve().parents[1]
MAX_KM = 25.0


def catalog_file() -> Path:
    return Path(os.environ.get("NISAR_CATALOG_DIR") or ROOT / "data" / "catalog") / "pass_counts.csv"


def _check_bbox(b: list[float]) -> list[float]:
    lon0, lat0, lon1, lat1 = b
    if not (-180 <= lon0 < lon1 <= 180 and -90 <= lat0 < lat1 <= 90):
        raise ValueError("bbox must be [lon_min, lat_min, lon_max, lat_max] with min < max and valid ranges")
    return b


def _check_area(b: list[float]) -> None:
    lon0, lat0, lon1, lat1 = b
    height = (lat1 - lat0) * 111.32
    width = (lon1 - lon0) * 111.32 * math.cos(math.radians((lat0 + lat1) / 2))
    if width > MAX_KM or height > MAX_KM:
        raise HTTPException(
            422,
            f"Area is {width:.1f} x {height:.1f} km. The limit is {MAX_KM:.0f} x {MAX_KM:.0f} km. Draw a smaller box.",
        )


class BBoxIn(BaseModel):
    bbox: list[float] = Field(description="lon_min, lat_min, lon_max, lat_max")

    @field_validator("bbox")
    @classmethod
    def _valid_bbox(cls, b: list[float]) -> list[float]:
        if len(b) != 4:
            raise ValueError("bbox needs exactly 4 numbers")
        return _check_bbox(b)


class AvailabilityIn(BBoxIn):
    start: date | None = None
    end: date | None = None


class AnalyzeIn(BBoxIn):
    before_start: date
    before_end: date
    after_start: date
    after_end: date
    question: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _ranges(self):
        if self.before_end < self.before_start or self.after_end < self.after_start:
            raise ValueError("each end date must not be before its start date")
        return self


app = FastAPI(title="NISAR Change Explorer", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


USER_AGENT = "nisar-change-explorer"
_places: "OrderedDict[str, list]" = OrderedDict()


def _nominatim(q: str) -> list[dict]:
    r = httpx.get("https://nominatim.openstreetmap.org/search",
                  params={"q": q, "format": "json", "limit": 5},
                  headers={"User-Agent": USER_AGENT}, timeout=10)
    r.raise_for_status()
    return r.json()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/places")
def places(q: str = Query(min_length=2, max_length=200)) -> list[dict]:
    k = q.strip().lower()
    if k in _places:
        return _places[k]
    try:
        raw = _nominatim(q)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Place search is unavailable right now. Try again in a moment.")
    out = []
    for p in raw:
        try:
            bb = p.get("boundingbox") or []
            s, n, w, e = (float(v) for v in bb)
            out.append({"name": p.get("display_name", ""), "lat": float(p["lat"]), "lon": float(p["lon"]),
                        "bbox": [w, s, e, n]})
        except (KeyError, TypeError, ValueError):
            continue
    _places[k] = out
    while len(_places) > 200:
        _places.popitem(last=False)
    return out


def _overlaps(row: dict, b: list[float]) -> bool:
    try:
        r = [float(row[k]) for k in ("lon_min", "lat_min", "lon_max", "lat_max")]
    except (KeyError, TypeError, ValueError):
        return True  # catalog rows carry no footprint: cannot filter, keep
    return r[0] < b[2] and r[2] > b[0] and r[1] < b[3] and r[3] > b[1]


AOI_HALF = 0.1125   # deg; same half-size as scripts/site_check.py HALF
MIN_COVER = 0.9
QUALITY = {"BE": "BETA", "PR": "PROVISIONAL", "VA": "VALIDATED"}
NO_COVERAGE = ("No NISAR catalogue coverage checked here. This area is outside the places whose "
               "passes were counted, so nothing can be promised.")


def _aoi_centres() -> list[tuple[str, float, float]] | None:
    path = catalog_file().parent / "aoi_centres.csv"
    if not path.exists():
        return None
    with path.open(newline="") as f:
        return [(r["area"], float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)]


def _quality(raw: str) -> str:
    return QUALITY.get((raw or "").split(";")[0].split("=")[-1], "BETA")


def _area_report(area: str, lat: float, lon: float, rows: list[dict]) -> dict:
    gap_rows = [r for r in rows if str(r.get("in_gap", "")).lower() == "true"]
    usable = [r for r in rows if str(r.get("in_gap", "")).lower() != "true"
              and float(r.get("aoi_cover") or 1.0) >= MIN_COVER]
    groups: dict[tuple, dict[str, dict]] = {}
    for r in usable:  # one row per date within a stack
        groups.setdefault((r["track"], r["direction"], r["frame"]), {})[r["date"]] = r
    out = {"area": area, "centre": [lat, lon],
           "aoi_bbox": [round(lon - AOI_HALF, 4), round(lat - AOI_HALF, 4),
                        round(lon + AOI_HALF, 4), round(lat + AOI_HALF, 4)],
           "passes": 0, "dates": [], "newest_pass_date": None, "quality": None,
           "gap_flag": bool(gap_rows), "straddles_gap": False, "gap_dates": sorted({r["date"] for r in gap_rows}),
           "answerable": [], "questions": {"water_change": False}, "status": "insufficient_data",
           "notes": ["No usable passes covering this area for these dates."]}
    if not groups:
        return out
    key, best = max(groups.items(), key=lambda kv: len(kv[1]))
    best_rows = [best[d] for d in sorted(best)]
    refs = [PassRef(r["scene"], r["date"], int(r["track"]), r["direction"], int(r["frame"]), _quality(r.get("quality", "")))
            for r in best_rows]
    mid = refs[len(refs) // 2].date
    status, notes = assess_availability([p for p in refs if p.date < mid], [p for p in refs if p.date >= mid], 0.0)
    if len(groups) > 1:
        notes = notes + [f"{len(groups)} track/direction/frame stacks cover this area; the largest is reported."]
    out.update(passes=len(refs), dates=[p.date for p in refs], newest_pass_date=refs[-1].date,
               quality=lowest_quality(refs), straddles_gap=(refs[0].date < "2026-07-27" and refs[-1].date > "2026-08-10"), stack={"track": int(key[0]), "direction": key[1], "frame": int(key[2])},
               status=status, notes=notes, questions={"water_change": status == "ok"},
               answerable=["Where did water appear or recede?"] if status == "ok" else [])
    return out


def _bbox_hits(b: list[float], centres) -> list[tuple[str, float, float]]:
    return [(n, la, lo) for n, la, lo in centres
            if lo - AOI_HALF < b[2] and lo + AOI_HALF > b[0] and la - AOI_HALF < b[3] and la + AOI_HALF > b[1]]


@app.post("/availability")
def availability(req: AvailabilityIn) -> dict:
    _check_area(req.bbox)
    base = {"bbox": req.bbox, "start": req.start, "end": req.end}
    path = catalog_file()
    if not path.exists():
        return {**base, "source": "sample", "passes": 0, "questions": {"water_change": False},
                "message": "No catalog at data/catalog/pass_counts.csv - sample response"}
    with path.open(newline="") as f:
        all_rows = list(csv.DictReader(f))
    if req.start:
        all_rows = [r for r in all_rows if r.get("date", "") >= req.start.isoformat()]
    if req.end:
        all_rows = [r for r in all_rows if r.get("date", "") <= req.end.isoformat()]
    centres = _aoi_centres()
    if centres is not None:
        return _availability_by_aoi(base, req.bbox, all_rows, centres)
    rows = [r for r in all_rows if _overlaps(r, req.bbox)]  # legacy: no AOI centres file, no spatial filter
    refs = [PassRef(r["scene"], r["date"], int(r["track"]), r["direction"], int(r["frame"]), "PROVISIONAL")
            for r in rows]
    groups: dict[tuple, list[PassRef]] = {}
    for p in refs:
        groups.setdefault((p.track, p.direction, p.frame), []).append(p)
    best, status, notes = [], "insufficient_data", ["No passes found for this area and dates."]
    if groups:
        best = max(groups.values(), key=len)
        dates = sorted(p.date for p in best)
        mid = dates[len(dates) // 2]
        before = [p for p in best if p.date < mid]
        after = [p for p in best if p.date >= mid]
        status, notes = assess_availability(before, after, 0.0)
    return {**base, "source": "catalog", "passes": len(refs), "usable_passes": len(best),
            "questions": {"water_change": status == "ok"},
            "answerable": ["Where did water appear or recede?"] if status == "ok" else [],
            "notes": notes,
            "message": f"{len(refs)} passes found; {len(best)} share one geometry."}


def _availability_by_aoi(base: dict, bbox: list[float], rows: list[dict], centres) -> dict:
    hits = _bbox_hits(bbox, centres)
    if not hits:
        return {**base, "source": "catalog", "coverage": "none", "areas": [], "passes": 0, "usable_passes": 0,
                "questions": {"water_change": False}, "answerable": [], "notes": [NO_COVERAGE],
                "message": NO_COVERAGE}
    areas = [_area_report(n, la, lo, [r for r in rows if r.get("area") == n]) for n, la, lo in hits]
    ok = [a for a in areas if a["status"] == "ok"]
    notes = [f"{a['area']}: {n}" for a in areas for n in a["notes"]]
    if any(a["gap_flag"] for a in areas):
        notes.append("Some scenes fall in the permanent data gap 2026-07-27 to 2026-08-10; they are excluded and the gap is not filled.")
    newest = max((a["newest_pass_date"] for a in areas if a["newest_pass_date"]), default=None)
    usable = sum(a["passes"] for a in areas)
    return {**base, "source": "catalog", "coverage": "catalogue", "areas": areas, "passes": usable, "usable_passes": usable,
            "newest_pass_date": newest, "questions": {"water_change": bool(ok)},
            "answerable": ["Where did water appear or recede?"] if ok else [], "notes": notes,
            "message": f"{len(areas)} catalogued area(s) overlap this box; {usable} usable passes in their best stacks."}


@app.post("/analyses")
def start_analysis(req: AnalyzeIn) -> dict:
    _check_area(req.bbox)
    key = cache.make_key(
        req.bbox,
        [req.before_start.isoformat(), req.before_end.isoformat()],
        [req.after_start.isoformat(), req.after_end.isoformat()],
        req.question,
    )
    return {"job_id": jobs.start_analysis(key, req.model_dump(mode="json"))}


def _job_or_404(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"Unknown analysis: {job_id}")
    return job


@app.get("/analyses/{job_id}")
def analysis_result(job_id: str):
    job = _job_or_404(job_id)
    if job["status"] == "error":
        return JSONResponse({"detail": f"Analysis failed: {job['error']}", "status": "error",
                             "step": job["step"]}, 409)
    if job["status"] != "done":
        return JSONResponse({"detail": "Analysis still running.", "status": job["status"],
                             "step": job["step"]}, 409)
    try:
        validate_result(job["result"])
    except ValueError as exc:
        raise HTTPException(500, f"Result rejected: {exc}")
    return job["result"]


@app.get("/analyses/{job_id}/events")
def analysis_events(job_id: str) -> StreamingResponse:
    _job_or_404(job_id)
    return StreamingResponse(jobs.stream(job_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@app.get("/analyses/{job_id}/agreement")
def analysis_agreement(job_id: str) -> dict:
    job = _job_or_404(job_id)
    if job["status"] != "done":
        return {"available": False, "reason": "Analysis has not finished."}
    if not job["verify"]:
        return {"available": False, "reason": "No independent reference comparison was run for this analysis."}
    return {"available": True, "sources": job["verify"]}
