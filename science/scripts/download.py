"""Download full NISAR GCOV files listed in data/catalog/pass_counts.csv.

Run on your own machine. The token is read from the EARTHDATA_TOKEN env var
(never put it in the repo):  export EARTHDATA_TOKEN='eyJ...'
Examples:
  python scripts/download.py --list
  python scripts/download.py --area mekong_tonlesap --track 83 --dry-run
  python scripts/download.py --area mekong_tonlesap --area bd_sylhet_haor --out /big/disk/nisar
Resumable: finished files (matching size_bytes) are skipped.
"""
import argparse, csv, os, sys
from pathlib import Path

CATALOG = Path(__file__).resolve().parent.parent / "data/catalog/pass_counts.csv"


def load(areas, track=None):
    rows = [r for r in csv.DictReader(open(CATALOG)) if (not areas or r["area"] in areas) and (track is None or r["track"] == str(track))]
    seen, out = set(), []
    for r in rows:  # same scene can cover several areas
        if r["scene"] not in seen and r.get("in_gap", "").lower() not in ("true", "1"):
            seen.add(r["scene"]); out.append(r)
    return sorted(out, key=lambda r: (r["area"], r["date"]))


def gb(rows):
    return sum(float(r.get("size_bytes") or 0) for r in rows) / 1e9


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", action="append", default=[])
    ap.add_argument("--track", type=int, help="only this track (one geometry per demo)")
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.list:
        for ar in sorted({r["area"] for r in load([])}):
            rs = load([ar]); print(f"{ar:28s} {len(rs):3d} scenes {gb(rs):8.1f} GB")
        return
    rows = load(a.area, a.track)
    print(f"{len(rows)} scenes, {gb(rows):.1f} GB -> {a.out}")
    if a.dry_run:
        for r in rows: print(r["area"], r["date"], r["scene"][-40:]); return
    tok = os.environ.get("EARTHDATA_TOKEN")
    if not tok: sys.exit("Set EARTHDATA_TOKEN first (see docstring).")
    import asf_search as asf
    s = asf.ASFSession(); s.auth_with_token(tok)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    for r in rows:
        dest = Path(a.out) / (r["scene"] + ".h5")
        want = int(float(r.get("size_bytes") or 0))
        if dest.exists() and want and dest.stat().st_size == want:
            print("skip", dest.name); continue
        print("get ", dest.name, f"{want/1e9:.1f} GB", flush=True)
        asf.download_url(r["url"], path=a.out, filename=dest.name, session=s)


if __name__ == "__main__":
    main()
