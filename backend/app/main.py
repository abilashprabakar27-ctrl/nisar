"""NISAR Change Explorer API.

Run:  uvicorn app.main:app --reload --port 8000     (from the backend/ folder)
Docs: http://localhost:8000/docs
"""
import asyncio
import json
import os
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import assistant, catalog, config, downloads, events, partners, pipeline, resources, sample, store, watch
from .models import AnalysisRequest, AvailabilityRequest, DownloadRequest, WatchRequest

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app):
    if os.getenv("NCE_WATCH_CHECKER", "1") == "1":
        watch.start_background_checker()
    yield


app = FastAPI(lifespan=lifespan, title="NISAR Change Explorer API", version="1.0.0",
              description="Find NISAR passes, run change analyses, compare with NASA OPERA, explain causes, watch places.")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

executor = ThreadPoolExecutor(max_workers=int(os.getenv("NCE_WORKERS", "2")))
dl_executor = ThreadPoolExecutor(max_workers=1)   # one area downloads at a time; others wait in line
_places_cache: dict[str, list] = {}
_active_downloads: dict[str, str] = {}


WEB_DIR = config.BASE_DIR / "web"
if WEB_DIR.exists():
    app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/app/")


@app.get("/demo-areas")
def demo_areas():
    p = config.BASE_DIR / "demo_areas.json"
    return json.loads(p.read_text()) if p.exists() else []


@app.get("/health")
def health():
    return {"ok": True, "version": app.version, "earthdata_login": bool(config.EARTHDATA_USERNAME)}


@app.get("/places")
def places(q: str = Query(..., min_length=2)):
    """Place search through OpenStreetMap Nominatim (cached)."""
    key = q.strip().lower()
    if key in _places_cache:
        return _places_cache[key]
    import requests
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search", timeout=8,
                         params={"q": q, "format": "json", "limit": 5},
                         headers={"User-Agent": "NISAR-Change-Explorer/1.0 (Space Apps 2026)"})
        r.raise_for_status()
    except Exception:
        raise HTTPException(503, "Place search is not reachable right now. Try again in a moment.")
    out = [{"name": p["display_name"], "lat": float(p["lat"]), "lon": float(p["lon"]),
            "bbox": [float(p["boundingbox"][2]), float(p["boundingbox"][0]),
                     float(p["boundingbox"][3]), float(p["boundingbox"][1])]} for p in r.json()]
    _places_cache[key] = out
    return out


EVENT_NOTE = ("Events are reported by the named source. The box is a default 25 km box around the "
              "reported point, not a flood footprint; this tool does not claim any flood extent.")


def _event_out(e):
    return {**e, "reported_by": e["source"], "bbox_note": "default 25 km box around the reported point"}


@app.get("/events/recent")
def events_recent(days: int = Query(45, ge=1, le=180),
                  category: str = Query("all", pattern="^(all|flood|storm|earthquake|landslide)$")):
    evs, sources = events.recent_events(days, category)
    return {"days": days, "category": category, "note": EVENT_NOTE, "sources": sources,
            "events": [_event_out(e) for e in evs]}


class EventCoverageRequest(BaseModel):
    bbox: list[float]
    start_date: str
    title: str = "Reported event"


def _coverage_response(ev):
    try:
        cov = events.coverage_for(ev)
    except Exception as e:
        raise HTTPException(503, f"NASA's data search is not reachable right now ({e.__class__.__name__}).")
    return {"event": _event_out(ev), "coverage": cov, "verdict": cov["verdict"], "message": cov.get("message"),
            "analysis_request": events.analysis_request(ev), "note": EVENT_NOTE}


@app.get("/events/coverage")
def events_coverage(id: str):
    ev = events.find_event(id)
    if not ev:
        raise HTTPException(404, "No recent event with that id (it may be older than 90 days).")
    return _coverage_response(ev)


@app.post("/events/coverage")
def events_coverage_post(req: EventCoverageRequest):
    from .models import check_bbox
    try:
        check_bbox(req.bbox)
        datetime.strptime(req.start_date[:10], "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(422, str(e))
    ev = {"id": None, "source": "user", "title": req.title, "start_date": req.start_date[:10] + "T00:00:00Z",
          "bbox": req.bbox}
    return _coverage_response(ev)


@app.post("/availability")
def availability(req: AvailabilityRequest):
    try:
        passes = catalog.search_passes(req.bbox, req.start, req.end)
    except Exception as e:
        raise HTTPException(503, f"NASA's data search is not reachable right now ({e.__class__.__name__}).")
    return catalog.availability(passes)


@app.post("/analyses", status_code=202)
def create_analysis(req: AnalysisRequest):
    body = req.model_dump()
    key = store.result_key(body)
    if store.load_result(key):  # already computed: answer at once
        job = store.new_job(uuid.uuid4().hex[:12], key, body)
        store.update_job(job["id"], status="done", progress=100, step="done", result_key=key,
                         event={"step": "done", "label": "Saved result"})
        return {"id": job["id"], "status": "done", "result_key": key}
    job = store.new_job(uuid.uuid4().hex[:12], key, body)
    executor.submit(pipeline.run_job, job["id"], body)
    return {"id": job["id"], "status": "queued"}


def _job_or_404(job_id):
    job = store.load_job(job_id)
    if not job:
        raise HTTPException(404, "No analysis with that id")
    return job


@app.get("/analyses/{job_id}")
def get_analysis(job_id: str):
    job = _job_or_404(job_id)
    out = {k: job.get(k) for k in ("id", "status", "step", "progress", "error", "detail", "download")}
    out["steps"] = [{"id": s, "label": l} for s, l in pipeline.STEPS]
    if job["status"] == "done":
        out["result"] = store.load_result(job.get("result_key") or job["key"])
    return out


@app.get("/analyses/{job_id}/events")
async def analysis_events(job_id: str):
    """Server-Sent Events: one message per progress step until the job ends."""
    _job_or_404(job_id)

    async def stream():
        sent = 0
        while True:
            job = store.load_job(job_id)
            for ev in job["events"][sent:]:
                yield f"data: {json.dumps(ev | {'progress': job['progress']})}\n\n"
            sent = len(job["events"])
            if job["status"] in ("done", "failed", "not_enough_data"):
                yield f"event: end\ndata: {json.dumps({'status': job['status'], 'error': job.get('error')})}\n\n"
                return
            await asyncio.sleep(1)
    return StreamingResponse(stream(), media_type="text/event-stream")


def _result_for(job_id):
    job = _job_or_404(job_id)
    if job["status"] != "done":
        raise HTTPException(409, f"Analysis is {job['status']}")
    res = store.load_result(job.get("result_key") or job["key"])
    if not res:
        raise HTTPException(404, "Result missing")
    return res


@app.get("/analyses/{job_id}/drivers")
def analysis_drivers(job_id: str):
    res = _result_for(job_id)
    return {"label": "Interpretation, not a measurement.", "drivers": res.get("drivers", []),
            "window": res.get("window")}


@app.get("/analyses/{job_id}/agreement")
def analysis_agreement(job_id: str):
    return _result_for(job_id).get("agreement")


@app.post("/results/{key}/ask")
def ask_result(key: str, body: dict):
    """Answers questions about a result using only its saved facts."""
    res = store.load_result(key)
    if not res:
        raise HTTPException(404, "No saved result with that key")
    return assistant.answer(res, str(body.get("question", ""))[:300])


@app.get("/results/{key}/questions")
def result_questions(key: str):
    """The common questions this result's own data can answer (may be empty)."""
    res = store.load_result(key)
    if not res:
        raise HTTPException(404, "No saved result with that key")
    return assistant.questions(res)


@app.get("/results/{key}")
def get_result(key: str):
    res = store.load_result(key)
    if not res:
        raise HTTPException(404, "No saved result with that key")
    return res


@app.get("/files/{key}/{name}")
def get_file(key: str, name: str):
    if "/" in name or ".." in name or "/" in key or ".." in key:
        raise HTTPException(400, "Bad file name")
    p = config.RESULTS_DIR / key / name
    if not p.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/sample")
def get_sample(rebuild: bool = False):
    """Labelled sample result in the exact live shape - for building screens before real data is ready."""
    key = store.result_key(sample.SAMPLE_REQUEST)
    res = None if rebuild else store.load_result(key)
    return res or sample.build_sample()


@app.get("/learn")
def learn(tag: str | None = None):
    """All challenge resources (NASA data, guides, trainings, partner agencies), optionally by tag:
    learn, polarization, stories, next, partner, verify, drivers, method."""
    return resources.by_tag(tag)


@app.post("/partners")
def partner_radar(req: AvailabilityRequest, name: str = "Study area"):
    """Partner radar availability (RCM, RADARSAT-1 via EODMS; SAOCOM as recorded by the team)."""
    start = req.start
    end = req.end or "2026-12-31"
    return partners.check_all(req.bbox, start, end, config.DRIVERS_DIR / pipeline.slug(name))


# ---------------- Download data for an area (like the terminal scripts) ----------------
@app.post("/downloads/status")
def download_status(req: DownloadRequest):
    """Which pass files for this area are already on this computer, and how long the rest would take."""
    try:
        return downloads.status(req.bbox, req.event_date, req.scope)
    except Exception as e:
        raise HTTPException(503, f"NASA's data search is not reachable right now ({e.__class__.__name__}).")


def _dl_key(req: DownloadRequest):
    return json.dumps([[round(v, 4) for v in req.bbox], req.scope, req.event_date if req.scope == "question" else None])


@app.post("/downloads", status_code=202)
def download_start(req: DownloadRequest):
    """Start downloading the study-area window of every needed pass. Poll GET /downloads/{id}."""
    k = _dl_key(req)
    running = _active_downloads.get(k)
    if running:
        job = store.load_job(running)
        if job and job["status"] in ("queued", "running"):
            return {"id": running, "status": job["status"], "already_running": True}
    job = store.new_job("dl-" + uuid.uuid4().hex[:10], "download", req.model_dump())
    job["kind"] = "download"
    store.save_job(job)
    _active_downloads[k] = job["id"]
    dl_executor.submit(downloads.run_job, job["id"], req.model_dump())
    return {"id": job["id"], "status": "queued"}


@app.get("/downloads/{job_id}")
def download_get(job_id: str):
    job = _job_or_404(job_id)
    out = {k: job.get(k) for k in ("id", "status", "step", "progress", "error", "download", "skipped")}
    out["name"] = (job.get("request") or {}).get("name")
    out["bbox"] = (job.get("request") or {}).get("bbox")
    out["events"] = job.get("events", [])[-6:]
    return out


@app.post("/downloads/{job_id}/cancel")
def download_cancel(job_id: str):
    _job_or_404(job_id)
    downloads.cancel(job_id)
    return {"id": job_id, "status": "cancelling"}


# ---------------- Watch this place ----------------
@app.post("/watch", status_code=201)
def watch_add(req: WatchRequest):
    return watch.add(req.bbox, req.name, req.last_result_date, req.analysis_id)


@app.get("/watch")
def watch_list():
    return watch.list_all()


@app.post("/watch/check")
def watch_check():
    try:
        return watch.check_all()
    except Exception as e:
        raise HTTPException(503, f"Could not check NASA's data search ({e.__class__.__name__}).")


@app.delete("/watch/{item_id}", status_code=204)
def watch_remove(item_id: str):
    if not watch.remove(item_id):
        raise HTTPException(404, "Not in the watch list")
