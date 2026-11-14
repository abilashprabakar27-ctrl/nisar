"""Watch this place: remember areas and flag them when a newer NISAR pass appears."""
import json
import threading
import time
import uuid
from datetime import datetime, timezone

from . import catalog, config

_lock = threading.Lock()


def _load() -> list[dict]:
    if not config.WATCH_FILE.exists():
        return []
    return json.loads(config.WATCH_FILE.read_text())


def _save(items):
    config.WATCH_FILE.write_text(json.dumps(items, indent=2))


def add(bbox, name, last_result_date=None, analysis_id=None) -> dict:
    with _lock:
        items = _load()
        item = {"id": uuid.uuid4().hex[:10], "name": name, "bbox": bbox, "analysis_id": analysis_id,
                "last_result_date": last_result_date, "newest_pass": None, "new_pass_available": False,
                "checked": None, "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        items.append(item)
        _save(items)
    return item


def list_all() -> list[dict]:
    with _lock:
        return _load()


def remove(item_id: str) -> bool:
    with _lock:
        items = _load()
        kept = [i for i in items if i["id"] != item_id]
        _save(kept)
        return len(kept) != len(items)


def newest_pass(bbox, newest_fn=None) -> str | None:
    if newest_fn:
        return newest_fn(bbox)
    passes = catalog.search_passes(bbox)
    return max((p.date for p in passes), default=None)


def check_all(newest_fn=None) -> list[dict]:
    with _lock:
        items = _load()
    for it in items:
        try:
            newest = newest_pass(it["bbox"], newest_fn)
        except Exception:
            continue
        it["newest_pass"] = newest
        it["new_pass_available"] = bool(newest and (not it.get("last_result_date") or newest > it["last_result_date"]))
        it["checked"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        current = {i["id"]: i for i in _load()}
        for it in items:
            if it["id"] in current:
                current[it["id"]].update({k: it[k] for k in ("newest_pass", "new_pass_available", "checked")})
        _save(list(current.values()))
    return list(current.values())


def start_background_checker():
    def loop():
        while True:
            time.sleep(config.WATCH_INTERVAL_S)
            try:
                check_all()
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True, name="watch-checker").start()
