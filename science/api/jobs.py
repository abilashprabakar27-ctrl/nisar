"""In-memory background jobs for /analyses. Finished results are saved via api.cache."""
import json
import threading
import time
import uuid
from pathlib import Path

from . import cache
from .schemas import validate_result

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "samples" / "golden_sample.json"
STEPS = ["checking", "fetching", "preparing", "detecting", "verifying", "explaining"]

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def _new(status: str, step: str, result: dict | None = None, events: list | None = None) -> str:
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {"job_id": job_id, "status": status, "step": step, "error": None,
                         "result": result, "verify": None, "events": events or []}
    return job_id


def _event(job_id: str, **ev) -> None:
    with _lock:
        _jobs[job_id]["events"].append(ev)


def _set(job_id: str, **fields) -> None:
    with _lock:
        _jobs[job_id].update(fields)


def get(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return {**job, "events": list(job["events"])} if job else None


def sample_result(bbox: list[float]) -> dict:
    data = json.loads(SAMPLE_PATH.read_text())
    data["source"] = "sample"
    data["bbox"] = list(bbox)
    return data


def run_analysis(req: dict) -> dict:
    """Real pipeline (workers.pipeline.run) when data covers the area; otherwise the labelled sample.
    Returns a ChangeResult dict (api.schemas.ChangeResult.to_dict()). May include an optional "_verify" dict (per-source overlap)
    which the API serves at /analyses/{id}/agreement and strips from the result."""
    from workers.pipeline import run  # lazy: pulls in h5py/rasterio
    result = run(req)
    return result if result is not None else sample_result(req["bbox"])


def _run(job_id: str, key: str, req: dict) -> None:
    try:
        _set(job_id, status="running")
        result = None
        for step in STEPS:
            _set(job_id, step=step)
            _event(job_id, step=step, message=f"{step.capitalize()}...")
            if step == "detecting":
                result = run_analysis(req)
        verify = result.pop("_verify", None)
        validate_result(result)
        cache.save(key, result)
        if verify:
            cache.save_verify(key, verify)
        _set(job_id, status="done", step="done", result=result, verify=verify)
        _event(job_id, step="done", message="Done", done=True)
    except Exception as exc:  # report any failure to the poller
        _set(job_id, status="error", error=str(exc))
        _event(job_id, step="error", message=str(exc), error=True)


def start_analysis(key: str, req: dict) -> str:
    cached = cache.load(key)
    if cached is not None:
        if cached.get("source") != "sample":
            cached["source"] = "saved"
        job_id = _new("done", "done", cached, [{"step": "done", "message": "Saved result", "done": True}])
        _set(job_id, verify=cache.load_verify(key))
        return job_id
    job_id = _new("queued", "queued")
    threading.Thread(target=_run, args=(job_id, key, req), daemon=True).start()
    return job_id


def stream(job_id: str):
    """Yield SSE frames for each step message until done/error."""
    sent = 0
    while True:
        job = get(job_id)
        for ev in job["events"][sent:]:
            yield f"data: {json.dumps(ev)}\n\n"
        sent = len(job["events"])
        if job["status"] in ("done", "error") and sent >= len(job["events"]):
            return
        time.sleep(0.05)
