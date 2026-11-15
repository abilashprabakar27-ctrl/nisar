"""Render the images the app shows next to the change map: after HH, after HV, and the colour mix.

Colour mix: HH red, HV green, HH/HV blue (dB, fixed stretch so images are comparable between runs).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

STRETCH = {"HH": (-25.0, 0.0), "HV": (-32.0, -8.0), "RATIO": (0.0, 12.0)}


def _db(x):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(x)


def _u8(a, lo, hi):
    return (np.clip((np.nan_to_num(a, nan=lo) - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)


def render_after(hh, hv, out_dir, stem="after") -> dict[str, str]:
    """hh, hv: linear-power composites (2-D). hv may be None (HH-only passes). Returns {kind: path}."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    hh_db = _db(hh)
    files = {"hh": out / f"{stem}_hh.png"}
    Image.fromarray(_u8(hh_db, *STRETCH["HH"])).save(files["hh"])
    if hv is not None:
        hv_db = _db(hv)
        Image.fromarray(_u8(hv_db, *STRETCH["HV"])).save(out / f"{stem}_hv.png")
        files["hv"] = out / f"{stem}_hv.png"
        rgb = np.dstack([_u8(hh_db, *STRETCH["HH"]), _u8(hv_db, *STRETCH["HV"]), _u8(hh_db - hv_db, *STRETCH["RATIO"])])
        Image.fromarray(rgb).save(out / f"{stem}_mix.png")
        files["mix"] = out / f"{stem}_mix.png"
    return {k: str(v) for k, v in files.items()}
