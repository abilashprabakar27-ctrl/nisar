# Data runbook (Abilash)

Do these in order. Each step says what "done" looks like.

1. **Set up** (10 min)
   - `pip install -r requirements.txt`, `cp .env.example .env`
   - Fill `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` (urs.earthdata.nasa.gov)
   - Optional: free FIRMS key from firms.modaps.eosdis.nasa.gov/api/map_key -> `FIRMS_MAP_KEY`
   - Done when `python scripts/run_area.py --sample` prints "Likely flooding".

2. **Pass table** (5 min)
   - `python scripts/run_area.py --name "Patna, Bihar" --bbox 85.00 25.35 85.25 25.60 --passes-only`
   - Repeat for Morigaon and Kanpur (boxes in `demo_areas.json`).
   - Done when you know which areas have 2+ passes before and 2+ after the event on one track. Edit `demo_areas.json` to keep only those (adjust `event_date` if needed).

3. **Collect supporting data** (10 min)
   - `python scripts/prepare_demo.py --skip-analysis`
   - Done when each `data/drivers/<area>/` has `rain.csv`, `dem.tif` (and `fires.csv` if you set the key).

4. **Run the analyses** (5-20 min per area, first time)
   - `python scripts/prepare_demo.py`
   - Done when `data/demo_summary.md` shows "done" with hectares and confidence. If a row says "failed", paste the traceback to Claude.

5. **Accuracy** (30 min, can hand to Nevedha)
   - `python scripts/make_checkpoints.py --key <id from summary> --name "Patna, Bihar"`
   - Open `data/drivers/patna-bihar/checkpoints.csv` in QGIS over the OPERA map or a clear photo; fill `label` with `water` / `not water`. Do not look at the `ours` column while labelling.
   - `python scripts/score.py --key <id> --points data/drivers/patna-bihar/checkpoints.csv`
   - Done when you have precision and recall: these go on slide 12 and the How we know screen.

6. **Share**
   - Post `data/demo_summary.md` in the team chat.
   - Start the API (`uvicorn app.main:app --port 8000`) on the demo machine; results load instantly from the cache.
