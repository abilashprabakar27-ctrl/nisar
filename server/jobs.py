"""In-memory background jobs for /analyze. Finished results are saved via server.cache."""
import json
import threading
import uuid
from pathlib import Path

from . import cache

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "samples" / "golden_sample.json"

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def _set(job_id: str, **fields) -> None:
    with _lock:
        _jobs[job_id].update(fields)


def _new(status: str, step: str, result: dict | None = None) -> str:
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {"job_id": job_id, "status": status, "step": step, "error": None, "result": result}
    return job_id


def get(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def sample_result(bbox: list[float]) -> dict:
    """Placeholder until the science function is wired in. Always source 'sample'."""
    data = json.loads(SAMPLE_PATH.read_text())
    data["source"] = "sample"
    data["bbox"] = list(bbox)
    return data


def _run(job_id: str, key: str, bbox: list[float]) -> None:
    try:
        _set(job_id, status="running", step="finding passes")
        _set(job_id, step="fetching")
        _set(job_id, step="comparing")
        result = sample_result(bbox)  # TODO: replace with the real science call
        _set(job_id, step="saving")
        cache.save(key, result)
        _set(job_id, status="done", result=result)
    except Exception as exc:  # report any failure to the poller
        _set(job_id, status="error", error=str(exc))


def start_analysis(key: str, bbox: list[float]) -> str:
    cached = cache.load(key)
    if cached is not None:
        if cached.get("source") != "sample":
            cached["source"] = "saved"
        return _new("done", "saved", cached)
    job_id = _new("queued", "queued")
    threading.Thread(target=_run, args=(job_id, key, bbox), daemon=True).start()
    return job_id
