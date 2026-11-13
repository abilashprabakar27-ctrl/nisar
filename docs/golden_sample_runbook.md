# Golden sample runbook (real NISAR GCOV, on your laptop)

Goal: replace the placeholder `data/samples/golden_sample.json` with a result computed from
real Tonle Sap passes (track 83, ascending, frame 8) using `workers.fetch.read_window` and
`methods.floods.detect_change`.

`workers/fetch.py` was built against the documented layout and tested only on a synthetic
HDF5 file. Step 2 below is the gate: do not trust any number until every check passes on one
real file.

## 0. Setup

```bash
pip install -e ".[dev]" pyproj fsspec aiohttp   # pyproj is not yet in pyproject.toml
export EARTHDATA_TOKEN='eyJ...'                 # never commit, never paste into a notebook
python3 -m pytest -q tests/test_fetch.py        # 15 passed
```

## 1. Get one real file first, then the rest

```bash
python scripts/download.py --area mekong_tonlesap --track 83 --dry-run   # 11 scenes, ~1.9 GB each
python scripts/download.py --area mekong_tonlesap --track 83             # -> data/raw/
```

Download a single scene (or try the URL route in step 5) and do step 2 before pulling all 11.

## 2. Check the real layout BEFORE anything else

```bash
F=data/raw/NISAR_L2_PR_GCOV_023_083_A_008_2005_DHDH_M_20260619T223637_20260619T223711_P05023_N_F_J_001.h5
python3 - "$F" <<'EOF'
import sys, h5py, numpy as np
f = h5py.File(sys.argv[1], "r")
def show(name, obj):
    if isinstance(obj, h5py.Dataset) and "/grids/" in "/" + name:
        print(name, obj.shape, obj.dtype, "chunks", obj.chunks, dict(obj.attrs))
f.visititems(show)
g = f["/science/LSAR/GCOV/grids/frequencyA"]
x, y = g["xCoordinates"][()], g["yCoordinates"][()]
print("x", x[:2], x[-1], "dx", np.diff(x[:2]), "| y", y[:2], y[-1], "dy", np.diff(y[:2]))
print("projection value", g["projection"][()], "attrs", dict(g["projection"].attrs))
r, c = g["HHHH"].shape[0] // 2, g["HHHH"].shape[1] // 2
a = g["HHHH"][r:r + 512, c:c + 512]
print("HHHH centre: min/median/max", np.nanmin(a), np.nanmedian(a), np.nanmax(a), "nan frac", np.isnan(a).mean())
print("HHHH corner:", g["HHHH"][:3, :3])
if "mask" in g:
    print("mask values:", np.unique(g["mask"][r:r + 512, c:c + 512]), "corner", g["mask"][:2, :2])
EOF
```

What to confirm, in this order (each line says what `fetch.py` assumes and what to change if it is wrong):

| # | Check | Assumed | If different |
|---|-------|---------|--------------|
| 1 | Layout names | `/science/LSAR/GCOV/grids/frequencyA/{HHHH,HVHV,xCoordinates,yCoordinates,projection}`; optional `mask`, `numberOfLooks`, `xCoordinateSpacing`, `yCoordinateSpacing` | edit `GRID_ROOT` / dataset names in `workers/fetch.py` |
| 2 | Units | linear power (gamma0), not dB. Land median about 0.01-0.3, open water about 0.001-0.02, never negative. Values mostly in -30..0 mean dB | `detect_change` applies `10*log10` itself; a dB file must be converted back (`10**(x/10)`) before use |
| 3 | Nodata | NaN outside the swath (corner pixels print `nan`); a non-NaN `_FillValue` attribute is also honoured | if fill is e.g. 0 or -9999 with no attribute, add it in `_read_layer` |
| 4 | Mask | uint8: 0 = invalid, 1-5 = sub-swath, 255 = fill. The corner should print 0 or 255, the centre 1..5 | if the centre shows 0/255, `nodata_fraction` will be near 1.0: call `read_window(..., apply_mask=False)` and fix `MASK_INVALID`/`MASK_FILL` |
| 5 | CRS | `projection` carries `epsg_code` attr (and/or the EPSG as its value); expect EPSG:32648 (UTM 48N) for Tonle Sap | extend `_epsg()` |
| 6 | Posting / orientation | x ascending, y descending, coordinates are pixel centres, dx = 20 m (or 10 m), dy = -dx; all 11 scenes share one grid | either direction is handled; if coordinates are pixel edges, drop the half-pixel shift in the transform |
| 7 | dtype | `HHHH`/`HVHV` real float32 (off-diagonal terms are complex and are rejected) | - |
| 8 | Chunking | chunked (e.g. 512x512 or similar) so a window read touches few chunks | if contiguous/huge chunks, URL reads will be slow; use local files |

Paths in row 1, the `mask`/`numberOfLooks` layers, gamma0 backscatter, UTM/polar EPSG and
10/20/80 m posting are stated in the NISAR GCOV product page (nisar-docs.asf.alaska.edu/gcov,
/projections). Rows 3-8 and the coordinate/projection dataset names are assumptions.

## 3. One window, eyeball it

```bash
python3 - "$F" <<'EOF'
import sys, numpy as np
from workers.fetch import read_window
w = read_window(sys.argv[1], (104.0, 12.8, 104.2, 13.0))      # ~21.7 x 22.1 km around 12.90N 104.10E
print({k: v for k, v in w.items() if not isinstance(v, np.ndarray)})
for k in ("HH", "HV"):
    if w[k] is not None:
        print(k, "median dB", 10 * np.log10(np.nanmedian(w[k])))
EOF
```

Expect: `crs` EPSG:32648, `shape` about (1100, 1085) at 20 m, `pixel_area_ha` 0.04 (0.01 at
10 m), `nodata_fraction` near 0, HH median roughly -12..-6 dB, HV about 6-8 dB lower. The
transform origin must be identical for every pass (step 4 asserts this).

## 4. Produce the golden sample

Save as `/tmp/golden.py` (or run in a notebook from the repo root) and run
`python3 /tmp/golden.py` from the repo root:

```python
import csv, json, time
from pathlib import Path
import numpy as np
from api.schemas import PassRef
from methods.floods import detect_change
from workers.fetch import fetch_passes

AREA, TRACK, FRAME = "mekong_tonlesap", "83", "8"
BBOX = (104.0, 12.8, 104.2, 13.0)          # lon_min, lat_min, lon_max, lat_max
SPLIT = "2026-08-15"                       # split_date_hypothesis in aoi_ranking.csv
RAW, CACHE, OUT = Path("data/raw"), Path("data/cache/passes"), Path("data/samples")
QUALITY = {"BE": "BETA", "PR": "PROVISIONAL", "VA": "VALIDATED"}   # confirm the cfg codes

rows = [r for r in csv.DictReader(open("data/catalog/pass_counts.csv"))
        if r["area"] == AREA and r["track"] == TRACK and r["frame"] == FRAME
        and r["direction"] == "ASCENDING" and r["in_gap"].lower() != "true"]
rows.sort(key=lambda r: r["date"])
before = [r for r in rows if r["date"] < SPLIT][-3:]      # 3 passes nearest the split
after = [r for r in rows if r["date"] > SPLIT][-3:]       # 3 latest passes (peak flood)

def ref(r):   # local file if downloaded, otherwise range-read the URL
    local = RAW / f"{r['scene']}.h5"
    return {"scene": r["scene"], "path": str(local)} if local.exists() else {"scene": r["scene"], "url": r["url"]}

def passref(r):
    return PassRef(scene=r["scene"], date=r["date"], track=int(r["track"]), direction=r["direction"],
                   frame=int(r["frame"]), quality=QUALITY.get(r["quality"].split(";")[0].split("=")[1], "BETA"))

t0 = time.time()
wins = fetch_passes([ref(r) for r in before + after], BBOX, CACHE, workers=4, on_step=print)
print(f"fetch {time.time() - t0:.1f}s")
assert all(w["HH"] is not None for w in wins), "a pass has no HHHH layer"
assert len({(w["shape"], tuple(w["transform"])[:6], w["crs"]) for w in wins}) == 1, "passes are not on one grid"

b, a = wins[:len(before)], wins[len(before):]
res, lab = detect_change([w["HH"] for w in b], [w["HH"] for w in a],
                         pixel_area_ha=wins[0]["pixel_area_ha"], bbox=BBOX,
                         before_refs=[passref(r) for r in before],
                         after_refs=[passref(r) for r in after], source="saved")
OUT.mkdir(parents=True, exist_ok=True)
np.savez_compressed(OUT / "golden_sample_labels.npz", labels=lab,
                    transform=np.array(tuple(wins[0]["transform"])[:6]), crs=wins[0]["crs"])
d = res.to_dict() if hasattr(res, "to_dict") else res.__dict__
(OUT / "golden_sample_real.json").write_text(json.dumps(d, indent=2, default=str))
print(res.status, res.area_ha, res.confidence, res.message, f"total {time.time() - t0:.1f}s")
```

Notes:
- `detect_change` takes one array per pass; this uses HH only. HV is in each window (`w["HV"]`) for later use.
- No `permanent_water` / `steep` masks are passed here, so the permanent lake and steep terrain
  are not excluded; add the reference masks (`scripts/fetch_reference.py`) resampled to the window
  grid before calling this a validated number.
- The 2026-10-29 pass has a different processing version (CRID P05036; the others are P05023).
  Compare its window against 10-17 before keeping it in the composite, or use 09-23/10-05/10-17.
- The output is written to `golden_sample_real.json`, not over `golden_sample.json`. Rename it only
  after step 5, and keep `source: "saved"` and honest `limits`.
- A second run prints `cache hit` for every pass and takes under a second; delete
  `data/cache/passes/` after any change to `workers/fetch.py` reading logic.

## 5. Sanity checks on the result

1. `status == "ok"`; `masked_fraction` < 0.15.
2. Sum of `area_ha` values plus masked area is about 21.7 km x 22.1 km = ~48,000 ha.
3. Sign: wet season (Sep-Oct) vs dry (Jun-Jul) at Tonle Sap should give `likely_became_water`
   much larger than `likely_water_receded`. The reverse means before/after are swapped or the
   data are in dB.
4. Flooded forest brightens in HH (double bounce) and will show as `receded`/no change, not
   water. That is a known limit, not a bug; put it in `limits`.
5. Overlay `labels` (EPSG:32648, saved transform) on a basemap; the new-water edge should follow
   the lake shore, not a straight line (a straight edge means swath boundary or mask problem).

## 6. Optional: skip the download (range reads)

`read_window` accepts the catalog `url` directly and sends `Authorization: Bearer $EARTHDATA_TOKEN`.
Unverified against the real ASF endpoint; check on one scene:

```bash
python3 -c "
import csv, time
from workers.fetch import read_window
r = next(r for r in csv.DictReader(open('data/catalog/pass_counts.csv')) if r['area']=='mekong_tonlesap' and r['track']=='83')
t=time.time(); w = read_window(r['url'], (104.0, 12.8, 104.2, 13.0)); print(w['shape'], w['nodata_fraction'], time.time()-t, 's')"
```

If it fails with an auth error: the ASF URL redirects to a signed URL and the client drops the
header on the cross-host hop (intended); if the first hop itself returns 401, the token is expired
or the EULA for the NISAR collection is not accepted. If it works but takes minutes, HDF5 metadata
is scattered across the file: fall back to local files. Threads give limited speed-up for local
files (h5py holds a global lock); the gain is on network latency.
