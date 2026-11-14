"""Saved results and job records on disk (simple, no database needed)."""
import hashlib
import json
import threading
import time
from pathlib import Path

from . import config

_lock = threading.Lock()
METHOD_VERSION = "water-change-v3e-calibrated"


def result_key(req: dict) -> str:
    """Same area + dates + question + method -> same key, so nothing is computed twice."""
    keep = {k: req.get(k) for k in ("bbox", "question", "event_date", "before", "after", "looking_for", "quick")}
    keep["bbox"] = [round(v, 4) for v in keep["bbox"]]
    keep["method"] = METHOD_VERSION
    return hashlib.sha1(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:16]


def result_dir(key: str) -> Path:
    d = config.RESULTS_DIR / key
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_result(key: str) -> dict | None:
    p = config.RESULTS_DIR / key / "result.json"
    return json.loads(p.read_text()) if p.exists() else None


def save_result(key: str, result: dict):
    p = result_dir(key) / "result.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=2))
    tmp.replace(p)


# ---------------- jobs ----------------
def _job_path(job_id: str) -> Path:
    return config.JOBS_DIR / f"{job_id}.json"


def new_job(job_id: str, key: str, request: dict) -> dict:
    job = {"id": job_id, "key": key, "status": "queued", "step": None, "progress": 0,
           "events": [], "error": None, "request": request, "created": time.time()}
    save_job(job)
    return job


def save_job(job: dict):
    with _lock:
        _job_path(job["id"]).write_text(json.dumps(job))


def load_job(job_id: str) -> dict | None:
    p = _job_path(job_id)
    if not p.exists():
        return None
    with _lock:
        return json.loads(p.read_text())


def update_job(job_id: str, **changes):
    job = load_job(job_id)
    if job is None:
        return None
    if "event" in changes:
        ev = changes.pop("event")
        ev["t"] = round(time.time(), 1)
        job["events"].append(ev)
    job.update(changes)
    save_job(job)
    return job
