"""One-off: fetch OPERA DSWx tiles (T48PUV) that cover the Tonle Sap north-shore window:
S1 after-flood 2026-09-23 / 10-05, and HLS clear before-flood 2026-07-21 (11% cloud) / 06-22 (3%).

  export EARTHDATA_TOKEN=...   # terminal only
  python scripts/dl_opera_puv.py
"""
import earthaccess

BASE = "https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-protected/OPERA_L3_DSWX-S1_V1/"
HLS = "https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-protected/OPERA_L3_DSWX-HLS_V1/"
HLS_NAMES = (
    "OPERA_L3_DSWx-HLS_T48PUV_20260721T032519Z_20260728T040905Z_S2B_30_v1.1_B01_WTR.tif",
    "OPERA_L3_DSWx-HLS_T48PUV_20260622T031854Z_20260624T223322Z_L8_30_v1.1_B01_WTR.tif",
)
NAMES = (
    "OPERA_L3_DSWx-S1_T48PUV_20260923T111121Z_20260924T053833Z_S1C_30_v1.0_B01_WTR.tif",
    "OPERA_L3_DSWx-S1_T48PUV_20261005T111122Z_20261005T155807Z_S1C_30_v1.0_B01_WTR.tif",
)
earthaccess.login(strategy="environment")
print(earthaccess.download([BASE + n for n in NAMES] + [HLS + n for n in HLS_NAMES], "data/reference/tonlesap"))
