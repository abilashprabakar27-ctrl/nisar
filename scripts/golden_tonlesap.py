# Golden sample: Tonle Sap north shore, real NISAR GCOV. Run from repo root: python scripts/golden_tonlesap.py
# Needs data/reference/tonlesap/{dem_copernicus30,jrc_occurrence}.tif and the t83 files in $NISAR_DATA.
import csv, json, os, time
from pathlib import Path
import numpy as np, rasterio
from rasterio.warp import reproject, Resampling
from api.schemas import PassRef
from methods.floods import detect_change
from workers.fetch import fetch_passes

AREA, TRACK, FRAME = "mekong_tonlesap", "83", "8"
BBOX = (103.90, 13.05, 104.12, 13.27)
RAW = Path(os.environ.get("NISAR_DATA", os.path.expanduser("~/nisar_data"))); CACHE = Path("data/cache/passes"); OUT = Path("data/samples")
REF = Path("data/reference/tonlesap")
BEFORE_D = ["2026-07-01", "2026-07-13", "2026-07-25"]
AFTER_D = ["2026-09-11", "2026-09-23", "2026-10-05"]
QUALITY = {"BE": "BETA", "PR": "PROVISIONAL", "VA": "VALIDATED"}
rows = {r["date"]: r for r in csv.DictReader(open("data/catalog/pass_counts.csv"))
        if r["area"] == AREA and r["track"] == TRACK and r["frame"] == FRAME}
sel = [rows[d] for d in BEFORE_D + AFTER_D]
def ref(r): return {"scene": r["scene"], "path": str(RAW / f"{r['scene']}.h5")}
def passref(r):
    q = QUALITY[r["quality"].split(";")[0].split("=")[1]]
    return PassRef(scene=r["scene"], date=r["date"], track=int(r["track"]), direction=r["direction"], frame=int(r["frame"]), quality=q)
t0 = time.time()
wins = fetch_passes([ref(r) for r in sel], BBOX, CACHE, workers=4, on_step=print)
print(f"fetch {time.time()-t0:.1f}s")
assert len({(w["shape"], tuple(w["transform"])[:6], w["crs"]) for w in wins}) == 1, "grid mismatch"
w0 = wins[0]; shape = w0["shape"]
def onto_grid(tif, resamp):
    with rasterio.open(tif) as s:
        dst = np.full(shape, np.nan, np.float32)
        reproject(rasterio.band(s, 1), dst, dst_transform=w0["transform"], dst_crs=w0["crs"], resampling=resamp)
    return dst
dem = onto_grid(REF/"dem_copernicus30.tif", Resampling.bilinear)
gy, gx = np.gradient(dem, 20.0)
slope = np.degrees(np.arctan(np.hypot(gx, gy)))
jrc = onto_grid(REF/"jrc_occurrence.tif", Resampling.nearest)
perm = np.nan_to_num(jrc, nan=0) >= 90
print("permanent water frac", perm.mean().round(3), "steep frac", (slope > 10).mean().round(4))
b, a = wins[:3], wins[3:]
res, lab = detect_change([w["HH"] for w in b], [w["HH"] for w in a], pixel_area_ha=w0["pixel_area_ha"], bbox=BBOX,
    before_refs=[passref(r) for r in sel[:3]], after_refs=[passref(r) for r in sel[3:]],
    permanent_water=perm, dem_slope_deg=slope, before_hv=[w["HV"] for w in b], after_hv=[w["HV"] for w in a], source="saved")
OUT.mkdir(parents=True, exist_ok=True)
np.savez_compressed(OUT/"golden_sample_labels.npz", labels=lab, transform=np.array(tuple(w0["transform"])[:6]), crs=w0["crs"])
d = res.to_dict() if hasattr(res, "to_dict") else res.__dict__
(OUT/"golden_sample_real.json").write_text(json.dumps(d, indent=2, default=str))
print(res.status, res.area_ha, res.confidence, res.message, f"total {time.time()-t0:.1f}s")
print("labels:", dict(zip(*np.unique(lab, return_counts=True))), "limits:", res.limits)
for k, w in (("b", b), ("a", a)):
    for p in ("HH","HV"):
        print(k, p, "median dB", round(float(10*np.log10(np.nanmedian(np.stack([x[p] for x in w])))),1))
