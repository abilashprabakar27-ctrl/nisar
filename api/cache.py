"""File cache for analysis results, keyed by sha1 of the request + method version."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHOD_VERSION = "floods-0.2.0"


def cache_dir() -> Path:
    return Path(os.environ.get("NISAR_CACHE_DIR") or ROOT / "data" / "cache")


def make_key(bbox, before, after, question: str) -> str:
    payload = {
        "method_version": METHOD_VERSION,
        "bbox": [float(v) for v in bbox],
        "before": list(before),
        "after": list(after),
        "question": question.strip(),
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def load(key: str) -> dict | None:
    try:
        return json.loads((cache_dir() / f"{key}.json").read_text())
    except (OSError, ValueError):
        return None


def save(key: str, result: dict) -> None:
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{key}.json.tmp"
    tmp.write_text(json.dumps(result, indent=2))
    tmp.replace(d / f"{key}.json")
