"""Download NISAR pass data for an area from inside the app, with % done, speed and time left.

The same thing `scripts/run_area.py` / `prepare_demo.py` do in the terminal: for every pass file
needed, read only the study-area window from NASA and keep it in data/cache. Later analyses of the
same area then load from the cache in seconds.

Time left is estimated from what has really arrived so far. Before anything has arrived it uses the
speed and file sizes measured on this computer last time (data/download_stats.json), or a cautious
default the very first time.
"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from . import catalog, config, data_sources, store
from .science import gcov

MB = 1024 * 1024
_cancel = set()
_cancel_lock = threading.Lock()


# ---------------------------------------------------------------- learned speed / size
def _stats() -> dict:
    try:
        return json.loads(config.DL_STATS_FILE.read_text())
    except Exception:
        return {}


def _save_stats(mb_per_frame: float, mbps: float):
    old = _stats()
    n = old.get("downloads", 0)
    # running average, newer downloads count a little more
    w = 0.6 if n else 1.0
    new = {"mb_per_frame": round(w * mb_per_frame + (1 - w) * old.get("mb_per_frame", mb_per_frame), 1),
           "mbps": round(w * mbps + (1 - w) * old.get("mbps", mbps), 2),
           "downloads": n + 1, "updated": time.strftime("%Y-%m-%d %H:%M")}
    config.DL_STATS_FILE.write_text(json.dumps(new, indent=2))


def expected() -> dict:
    s = _stats()
    return {"mb_per_frame": s.get("mb_per_frame", config.DL_PRIOR_MB_PER_FRAME),
            "mbps": s.get("mbps", config.DL_PRIOR_MBPS),
            "measured": bool(s)}


# ---------------------------------------------------------------- what needs downloading
def _shift(d, days):
    return (date.fromisoformat(d) + timedelta(days=days)).isoformat()


def plan(bbox, event_date=None, scope="all", passes=None):
    """Pick the pass files to download.

    scope "all": every pass on the best track (what Check data shows).
    scope "question": only the 2 before + 2 after passes an analysis around event_date will use.
    """
    if passes is None:
        passes = catalog.search_passes(bbox)
    if not passes:
        return None, []
    if scope == "question" and event_date:
        try:
            (trk, d), b, a, _ = catalog.choose_groups(passes, event_date)
            dates = {p.date for p in b + a}
        except catalog.NotEnoughData:
            return None, []
    else:
        best = catalog.availability(passes)["best_track"]
        trk, d, dates = best["track"], best["direction"], set(best["dates"])
    frames = [p for p in passes if p.track == trk and p.direction == d and p.date in dates and p.url]
    return {"track": trk, "direction": d}, sorted(frames, key=lambda p: (p.date, str(p.frame)))


def status(bbox, event_date=None, scope="all", passes=None) -> dict:
    track, frames = plan(bbox, event_date, scope, passes)
    exp = expected()
    by_date = {}
    for p in frames:
        x = by_date.setdefault(p.date, {"date": p.date, "frames": 0, "cached": 0})
        x["frames"] += 1
        x["cached"] += int(gcov.is_cached(p.url, bbox))
    todo = sum(x["frames"] - x["cached"] for x in by_date.values())
    est_mb = todo * exp["mb_per_frame"]
    dates = sorted(by_date.values(), key=lambda x: x["date"])
    return {
        "scope": scope, "track": track,
        "dates": dates,
        "passes_total": len(dates), "passes_ready": sum(1 for x in dates if x["cached"] == x["frames"]),
        "frames_total": len(frames), "frames_to_download": todo,
        "all_downloaded": bool(frames) and todo == 0,
        "estimate": {"mb": round(est_mb), "seconds": round(est_mb / max(exp["mbps"], 0.05)),
                     "mbps": exp["mbps"], "measured": exp["measured"]},
    }


# ---------------------------------------------------------------- progress tracking
class Tracker:
    """Counts bytes as they arrive and works out % done, speed and time left."""

    def __init__(self, frames_total: int, job_id: str | None = None, base_pct=0, span_pct=100, every_s=1.0):
        exp = expected()
        self.frames_total = max(frames_total, 0)
        self.frames_done = 0
        self.frame_bytes = []          # sizes of finished frames
        self.prior = exp["mb_per_frame"] * MB
        self.prior_mbps = exp["mbps"]
        self.bytes = 0
        self.t0 = time.time()
        self.job_id, self.base, self.span, self.every = job_id, base_pct, span_pct, every_s
        self._last_push = 0.0
        self._lock = threading.Lock()
        self._push_lock = threading.Lock()
        self.current = []
        self.samples = []              # (time, bytes) for a smoothed speed

    # -- called from the reader threads
    def add(self, n: int):
        with self._lock:
            self.bytes += n
        if self.job_id and self.job_id in _cancel:
            raise gcov.Cancelled()
        self.push()

    def frame_done(self, nbytes: int):
        if not nbytes:      # came from this computer's cache: nothing was downloaded
            return
        with self._lock:
            self.frames_done += 1
            if nbytes:
                self.frame_bytes.append(nbytes)
        self.push(force=True)

    # -- numbers
    def per_frame(self):
        return (sum(self.frame_bytes) / len(self.frame_bytes)) if self.frame_bytes else self.prior

    def total_estimate(self):
        est = self.per_frame() * self.frames_total
        return max(est, self.bytes * 1.02)       # never below what already arrived

    def speed(self):
        now = time.time()
        self.samples.append((now, self.bytes))
        self.samples = [s for s in self.samples if now - s[0] <= 20] or [(now, self.bytes)]
        t, b = self.samples[0]
        if now - t >= 3 and self.bytes > b:
            return (self.bytes - b) / (now - t)
        el = now - self.t0
        return self.bytes / el if el > 3 and self.bytes else self.prior_mbps * MB

    def snapshot(self) -> dict:
        with self._lock:
            done = self.frames_done >= self.frames_total
            total = self.total_estimate()
            pct = 100.0 if done else min(99.0, 100.0 * self.bytes / total) if total else 0.0
            sp = self.speed()
            left = 0 if done else max(0.0, total - self.bytes) / max(sp, 1)
            return {"pct": round(pct, 1), "mb_done": round(self.bytes / MB, 1), "mb_total": round(total / MB),
                    "mbps": round(sp / MB, 2), "eta_s": round(left), "elapsed_s": round(time.time() - self.t0),
                    "frames_done": self.frames_done, "frames_total": self.frames_total,
                    "estimated_from": "this download" if self.frame_bytes else ("last download" if expected()["measured"] else "a rough default"),
                    "current": list(self.current)}

    def push(self, force=False):
        if not self.job_id:
            return
        now = time.time()
        if not force and now - self._last_push < self.every:
            return
        if not self._push_lock.acquire(blocking=force):
            return
        try:
            self._last_push = now
            snap = self.snapshot()
            store.update_job(self.job_id, download=snap, progress=int(self.base + self.span * snap["pct"] / 100))
        finally:
            self._push_lock.release()

    def finish(self):
        el = time.time() - self.t0
        if self.frame_bytes and el > 0.2 and self.bytes > 0:
            _save_stats(self.per_frame() / MB, self.bytes / MB / el)


def fetch_frames(frames, bbox, tracker: Tracker, workers=4, on_window=None):
    """Read each frame's study-area window (from cache if present), reporting bytes to tracker."""
    def one(p):
        n0 = [0]

        def cb(n):
            n0[0] += n
            tracker.add(n)
        with tracker._lock:
            tracker.current.append(p.date)
        try:
            w = gcov.read_window(p.url, bbox, p.date, progress=cb)
        finally:
            with tracker._lock:
                if p.date in tracker.current:
                    tracker.current.remove(p.date)
        tracker.frame_done(n0[0])
        if on_window:
            on_window(p, w)
        return w

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, p) for p in frames]
        errors = []
        for f in futs:
            try:
                f.result()
            except gcov.Cancelled:
                raise
            except ValueError:   # frame does not touch the area
                pass
            except Exception as e:
                errors.append(e)
        if errors and len(errors) == len(frames):
            raise errors[0]


# ---------------------------------------------------------------- download job
def run_job(job_id: str, req: dict):
    bbox, scope, ev = req["bbox"], req.get("scope", "all"), req.get("event_date")
    try:
        if job_id in _cancel:
            raise gcov.Cancelled()
        store.update_job(job_id, status="running", step="plan", progress=0,
                         event={"step": "plan", "label": "Finding the NISAR files for this area"})
        _, frames = plan(bbox, ev, scope)
        todo = [p for p in frames if not gcov.is_cached(p.url, bbox)]
        if not frames:
            store.update_job(job_id, status="failed", error="No NISAR files cover this area yet.")
            return
        tr = Tracker(len(todo), job_id, base_pct=0, span_pct=92)
        store.update_job(job_id, step="radar", download=tr.snapshot(), skipped=len(frames) - len(todo),
                         event={"step": "radar", "label": f"Downloading {len(todo)} file(s); {len(frames) - len(todo)} already on this computer"})
        if todo:
            gcov._login()
            fetch_frames(todo, bbox, tr)
            tr.finish()
        store.update_job(job_id, download=tr.snapshot(), progress=92, step="extras",
                         event={"step": "extras", "label": "Rain, land height and fires for the 'Why' screen"})
        if req.get("extras", True):
            dates = sorted({p.date for p in frames})
            folder = config.DRIVERS_DIR / _slug(req.get("name", "area"))
            start, end = _shift(dates[0], -20), _shift(dates[-1], 10)
            for fn in (lambda: data_sources.fetch_rain(bbox, start, end, folder),
                       lambda: data_sources.fetch_dem(bbox, folder),
                       lambda: data_sources.fetch_fires(bbox, start, end, folder)):
                try:
                    fn()
                except Exception:
                    pass   # optional; the app says "not checked" for anything missing
        store.update_job(job_id, status="done", step="done", progress=100, download=tr.snapshot(),
                         event={"step": "done", "label": "Download complete"})
    except gcov.Cancelled:
        store.update_job(job_id, status="cancelled", step="cancelled",
                         event={"step": "cancelled", "label": "Stopped. Files already downloaded are kept."})
    except gcov.LoginFailed as e:
        store.update_job(job_id, status="failed", error=f"NASA Earthdata login failed: {e}. Check EARTHDATA_USERNAME and EARTHDATA_PASSWORD in .env.")
    except Exception as e:
        store.update_job(job_id, status="failed", error=f"Download stopped: {e.__class__.__name__}: {e}"[:300])
    finally:
        with _cancel_lock:
            _cancel.discard(job_id)


def cancel(job_id: str):
    with _cancel_lock:
        _cancel.add(job_id)


def _slug(s):
    import re
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "area"
