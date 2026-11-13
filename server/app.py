"""FastAPI server for the NISAR change explorer demo.

Config comes only from env vars: NISAR_CACHE_DIR, NISAR_CATALOG_DIR, EARTHDATA_TOKEN (read by the science layer later).
"""
import csv
import math
import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator

from . import cache, jobs

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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/availability")
def availability(req: AvailabilityIn) -> dict:
    _check_area(req.bbox)
    base = {"bbox": req.bbox, "start": req.start, "end": req.end}
    path = catalog_file()
    if not path.exists():
        return {**base, "source": "sample", "passes": 0,
                "message": "No catalog at data/catalog/pass_counts.csv - sample response"}
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return {**base, "source": "catalog", "passes": len(rows),
            "message": f"{len(rows)} rows in pass_counts.csv (stub: not filtered by bbox yet)"}


@app.post("/analyze")
def analyze(req: AnalyzeIn) -> dict:
    _check_area(req.bbox)
    key = cache.make_key(
        req.bbox,
        [req.before_start.isoformat(), req.before_end.isoformat()],
        [req.after_start.isoformat(), req.after_end.isoformat()],
        req.question,
    )
    return {"job_id": jobs.start_analysis(key, req.bbox)}


def _job_or_404(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"Unknown job: {job_id}")
    return job


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = _job_or_404(job_id)
    return {"job_id": job_id, "status": job["status"], "step": job["step"], "error": job["error"]}


@app.get("/results/{job_id}")
def job_result(job_id: str) -> dict:
    job = _job_or_404(job_id)
    if job["status"] == "error":
        raise HTTPException(409, f"Job failed: {job['error']}")
    if job["status"] != "done":
        raise HTTPException(409, "Result not ready. Poll /jobs/{job_id} until status is done.")
    return job["result"]
