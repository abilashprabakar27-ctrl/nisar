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

from workers.check import assess_availability

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


@app.post("/availability")
def availability(req: AvailabilityIn) -> dict:
    _check_area(req.bbox)
    base = {"bbox": req.bbox, "start": req.start, "end": req.end}
    path = catalog_file()
    if not path.exists():
        return {**base, "source": "sample", "passes": 0, "questions": {"water_change": False},
                "message": "No catalog at data/catalog/pass_counts.csv - sample response"}
    with path.open(newline="") as f:
        rows = [r for r in csv.DictReader(f) if _overlaps(r, req.bbox)]
    if req.start:
        rows = [r for r in rows if r.get("date", "") >= req.start.isoformat()]
    if req.end:
        rows = [r for r in rows if r.get("date", "") <= req.end.isoformat()]
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
