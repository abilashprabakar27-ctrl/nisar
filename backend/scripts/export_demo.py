"""Build the online demo (a static site for Vercel) from the answers already made on this computer.

    python scripts/export_demo.py                  # writes ../vercel-demo next to the backend folder
    python scripts/export_demo.py --only Patna       # just one place
    python scripts/export_demo.py --only Patna,Kanpur,Morigaon   # several places
    python scripts/export_demo.py --out C:\\some\\folder

What it does
  * copies the web app (web/) and switches it to demo mode (no Python server needed),
  * picks the newest finished answer for every place you have run, plus the example result,
  * copies their map images, pre-writes the "Common questions" answers and the learning links,
  * writes vercel.json.

Run every place you want in the demo first (in the app, or with scripts/prepare_demo.py).
Only places with a finished answer can be shown online.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import assistant, config, resources, sample, store  # noqa: E402

FAQ = ["Could rain have caused this?", "How sure can we be?", "What could be wrong?", "Did the water go down anywhere?"]


def load_results():
    out = []
    for p in sorted(config.RESULTS_DIR.glob("*/result.json")):
        try:
            r = json.loads(p.read_text())
        except Exception:
            continue
        if r.get("status") == "done" and r.get("area") and r.get("images"):
            out.append(r)
    return out


def newest_per_place(results):
    """One answer per place: prefer the current method, then the most recent."""
    best = {}
    for r in results:
        if r.get("source") == "sample":
            continue
        b = r["area"]["bbox"]
        k = tuple(round(v, 2) for v in b)
        cur = (r["provenance"].get("method") == store.METHOD_VERSION, r["provenance"].get("created", ""))
        if k not in best or cur > best[k][0]:
            best[k] = (cur, r)
    return [v[1] for v in best.values()]


def availability_from(r):
    """What the Check screen needs, rebuilt from the saved answer (no internet needed)."""
    passes = r.get("passes", [])
    dates = sorted({p["date"] for p in passes})
    q = sorted({p["quality"] for p in passes})
    best = {"track": r["track"]["track"], "direction": r["track"]["direction"], "passes": len(dates), "dates": dates,
            "quality": q, "polarizations": ["HH", "HV"]}
    return {"enough_data": True, "verdict": "Enough data", "best_track": best, "tracks": [best], "total_passes": len(dates),
            "gap": {"start": config.DATA_GAP[0], "end": config.DATA_GAP[1]},
            "can_answer": {"now": True, "change": True, "diff": True, "much": True, "why": True},
            "newest_pass": dates[-1] if dates else None}


def event_date_of(r):
    return (r.get("window", {}).get("after") or [None])[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT.parent / "vercel-demo"))
    ap.add_argument("--only", help='keep only places whose name contains this text; several comma-separated, e.g. --only Patna,Kanpur,Morigaon')
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "web", out)
    data = out / "content"   # not "data": .gitignore excludes data/ folders
    (data / "results").mkdir(parents=True)
    (data / "ask").mkdir()

    # 1. switch the page to demo mode
    idx = out / "index.html"
    html = idx.read_text(encoding="utf-8")
    html = html.replace('<script src="app.js"></script>', '<script>window.NCE_DEMO = true;</script>\n<script src="app.js"></script>')
    idx.write_text(html, encoding="utf-8")

    # 2. answers to include
    results = newest_per_place(load_results())
    if a.only:
        wanted = [w.strip().lower() for w in a.only.split(",") if w.strip()]
        results = [r for r in results if any(w in r["area"]["name"].lower() for w in wanted)]
    smp = store.load_result(store.result_key(sample.SAMPLE_REQUEST)) or sample.build_sample()
    stories_src = json.loads((ROOT / "demo_areas.json").read_text()) if (ROOT / "demo_areas.json").exists() else []

    places = []
    for r in results + [smp]:
        key = r["id"]
        (data / "results" / f"{key}.json").write_text(json.dumps(r))
        src = config.RESULTS_DIR / key
        if src.exists():
            dst = out / "files" / key
            dst.mkdir(parents=True, exist_ok=True)
            for png in src.glob("*.png"):
                shutil.copy2(png, dst / png.name)
        answers = {q: assistant.answer(r, q)["answer"] for q in FAQ}
        (data / "ask" / f"{key}.json").write_text(json.dumps(answers))
        if r is smp:
            continue
        name = r["area"]["name"]
        story = next((s for s in stories_src if [round(v, 2) for v in s["bbox"]] == [round(v, 2) for v in r["area"]["bbox"]]), None)
        w = r.get("window", {})
        places.append({"key": key, "name": name, "bbox": r["area"]["bbox"],
                       "event_date": (story or {}).get("event_date") or event_date_of(r),
                       "window": [(w.get("before") or [None])[-1], (w.get("after") or [None])[0]],
                       "story": (story or {}).get("story", ""), "availability": availability_from(r)})

    if not places:   # nothing run yet: the example still makes a working demo
        places.append({"key": smp["id"], "name": smp["area"]["name"], "bbox": smp["area"]["bbox"],
                       "event_date": event_date_of(smp), "window": [smp["window"]["before"][-1], smp["window"]["after"][0]],
                       "story": "Example result", "availability": availability_from(smp)})

    stories = [{"name": p["name"], "bbox": p["bbox"], "event_date": p["event_date"], "story": p["story"]} for p in places]
    (data / "prepared.json").write_text(json.dumps({"places": places, "stories": stories, "sample": smp["id"]}, indent=1))

    # 3. learning links (About the data / Why pages)
    for tag in ("learn", "next", "all"):
        (data / f"learn-{tag}.json").write_text(json.dumps(resources.by_tag(None if tag == "all" else tag)))

    # 4. Vercel settings: plain static site, cache images, never cache the data lists
    (out / "vercel.json").write_text(json.dumps({
        "cleanUrls": False,
        "headers": [
            {"source": "/files/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=86400"}]},
            {"source": "/content/(.*)", "headers": [{"key": "Cache-Control", "value": "no-cache"}]},
        ],
    }, indent=1))

    # 5. short README so anyone opening the folder knows what it is and which places it holds
    (out / "README.md").write_text(
        "# NISAR Change Explorer: online demo\n\n"
        "Static build of the web app, generated by `backend/scripts/export_demo.py`. Do not edit by hand.\n\n"
        f"Places with a prepared answer (currently: {'; '.join(p['name'] for p in places)}).\n"
        "Any other place shows \"This place isn't in the online demo\"; the full app runs any place locally.\n",
        encoding="utf-8")

    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    print(f"Demo written to {out}  ({size:.1f} MB)")
    print("Places in the demo:")
    for p in places:
        print(f"  - {p['name']}  (answer {p['key']}, change date {p['event_date']})")
    print("Next: deploy this folder to Vercel (see HANDOFF or the steps you were given).")


if __name__ == "__main__":
    main()
