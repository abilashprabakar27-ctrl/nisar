"""Settings, read from environment variables (or a .env file)."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # optional
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("NCE_DATA_DIR", BASE_DIR / "data"))
RESULTS_DIR = DATA_DIR / "results"
JOBS_DIR = DATA_DIR / "jobs"
DRIVERS_DIR = DATA_DIR / "drivers"      # rainfall / fire CSVs from the reference team
CACHE_DIR = DATA_DIR / "cache"          # clipped pass arrays
WATCH_FILE = DATA_DIR / "watch.json"
for d in (RESULTS_DIR, JOBS_DIR, DRIVERS_DIR, CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)

# NASA Earthdata Login (for reading NISAR files). Never commit real values.
EARTHDATA_USERNAME = os.getenv("EARTHDATA_USERNAME", "")
EARTHDATA_PASSWORD = os.getenv("EARTHDATA_PASSWORD", "")

PUBLIC_BASE_URL = os.getenv("NCE_PUBLIC_BASE_URL", "")  # e.g. https://api.example.com
CORS_ORIGINS = [o.strip() for o in os.getenv("NCE_CORS_ORIGINS", "*").split(",") if o.strip()]

# Science rules (agreed in the Night Shift 1 pack)
NISAR_START = "2026-06-17"
DATA_GAP = ("2026-07-27", "2026-08-10")
MIN_PASSES_EACH_SIDE = 2
MAX_MASKED_FRACTION = 0.30
CHANGE_DB = 3.0                 # dB drop/rise that counts as change
# Water cut-offs. "fixed" uses values measured on NISAR provisional GCOV over the Gangetic plain
# (Patna, Sep 2026: water HH median -14.7 dB, HV -21.0 dB; land HH -7.1, HV -17.2).
# "otsu" picks them automatically from each image's histogram instead.
THRESHOLD_MODE = os.getenv("NCE_THRESHOLD_MODE", "fixed")
WATER_HH_DB = float(os.getenv("NCE_WATER_HH_DB", "-14.5"))
WATER_HV_DB = float(os.getenv("NCE_WATER_HV_DB", "-20.5"))
MIN_PATCH_HA = 1.0
MAX_AREA_KM2 = float(os.getenv("NCE_MAX_AREA_KM2", "900"))   # about 30 x 30 km
TARGET_RES_M = float(os.getenv("NCE_TARGET_RES_M", "20"))
FOOTBALL_PITCH_HA = 0.714
WATCH_INTERVAL_S = int(os.getenv("NCE_WATCH_INTERVAL_S", "3600"))

# Download estimates before we have measured this computer's connection (they are replaced by
# measured values in data/download_stats.json after the first download).
DL_PRIOR_MB_PER_FRAME = float(os.getenv("NCE_DL_PRIOR_MB_PER_FRAME", "90"))
DL_PRIOR_MBPS = float(os.getenv("NCE_DL_PRIOR_MBPS", "1.5"))
DL_STATS_FILE = DATA_DIR / "download_stats.json"
