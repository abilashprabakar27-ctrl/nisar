# NISAR Change Explorer - Backend

FastAPI server that finds NISAR passes, reads only the study-area window from each GCOV file,
detects water change, checks it against NASA OPERA, explains likely causes, and watches places
for new passes.

## Run it (5 minutes)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then add your NASA Earthdata username and password
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs for the interactive API.
`GET /sample` works with no login and returns a labelled sample result in the exact live shape.

Tests: `python -m pytest -q tests` (offline, uses the sample scene).

Command line, no server:

```bash
python scripts/run_area.py --name "Patna, Bihar" --bbox 85.00 25.35 85.25 25.60 --passes-only
python scripts/run_area.py --name "Patna, Bihar" --bbox 85.00 25.35 85.25 25.60 --event 2026-09-07
```

## Endpoints

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/health` | server status, whether an Earthdata login is set |
| GET | `/places?q=patna` | place matches (OpenStreetMap Nominatim, cached) |
| GET | `/events/recent?days=45&category=flood\|storm\|earthquake\|all` | recent events reported by GDACS, EONET, USGS, Copernicus EMS (de-duplicated) plus a `sources` list; a source that is down is skipped, not an error. Boxes are a default 25 km box, not a flood footprint |
| GET/POST | `/events/coverage?id=...` (or POST `{bbox, start_date, title}`) | NISAR passes before/after the event: verdict `enough` / `waiting` / `none`, and a ready `analysis_request` for `POST /analyses` |
| POST | `/availability` | `{bbox}` -> passes per track, quality, data gap, which questions can be answered |
| POST | `/analyses` | `{bbox, name, question, event_date \| before+after, quick}` -> `{id, status}` at once |
| GET | `/analyses/{id}` | status, step, progress; `result` when done; `error` when stopped |
| GET | `/analyses/{id}/events` | live progress (Server-Sent Events) |
| GET | `/analyses/{id}/drivers` | causes for the Why screen, labelled "Interpretation, not a measurement." |
| GET | `/analyses/{id}/agreement` | NISAR vs NASA OPERA areas, overlap, verdict, agreement map |
| GET | `/results/{key}` | a saved result |
| GET | `/files/{key}/{name}` | PNGs: `result.png`, `after_hh.png`, `before_hh.png`, `after_hv.png`, `after_mix.png`, `agreement.png` |
| GET | `/sample` | labelled sample result |
| POST/GET/DELETE | `/watch`, `/watch/{id}` | Watch this place |
| POST | `/watch/check` | check every watched place for a newer pass now (also runs hourly) |

Job `status` is one of `queued`, `running`, `done`, `not_enough_data`, `failed`.
`not_enough_data` carries a plain message for the screen (e.g. "Not enough NISAR data here yet... so we won't guess.").

### Putting images on the map (MapLibre)

Every PNG is in EPSG:4326 and shares `result.images.bounds = [west, south, east, north]`:

```js
const [w, s, e, n] = result.images.bounds;
map.addSource("nisar", { type: "image", url: result.images.hh,   // or .hv / .mix / .result
  coordinates: [[w, n], [e, n], [e, s], [w, s]] });
map.addLayer({ id: "nisar", type: "raster", source: "nisar" });
```

The polarization switch only swaps `url` between `images.hh`, `images.hv` and `images.mix`.

## How the analysis works

1. **Check** - ASF search for NISAR GCOV passes; keep one track and direction; need at least 2 passes before and 2 after the change date, else stop with "not enough data".
2. **Fetch** - open each GCOV over HTTPS (Earthdata login) and read only the study-area rows and columns of `HHHH`, `HVHV` and `mask` from `/science/LSAR/GCOV/grids/frequencyA`.
3. **Prepare** - put every pass on one 20 m UTM grid; average finer pixels; decibels; Lee speckle filter.
4. **Detect** - median of the before passes vs median of the after passes; water threshold by Otsu (clamped -24 to -12 dB); new water = below threshold after, above before, and at least 3 dB darker; patches under 1 ha dropped; permanent water kept separate so rivers are not called floods.
5. **Verify** - compare with NASA OPERA DSWx-S1 (searched automatically, or `data/drivers/<area-slug>/opera.tif`).
6. **Explain** - headline number, football pitches, confidence (rules below), measured vs interpreted text, per-pass water areas, causes, limits, PNGs.

Confidence: **High** = 2+ passes each side, change seen on both later passes, OPERA overlap >= 75%, masked area <= 15%.
**Lower** = any Beta-quality pass, overlap < 50% or masked area > 15%. Otherwise **Medium**.

### Cause evidence (Why screen)

Drop files in `data/drivers/<area-slug>/` (slug of the area name, e.g. `patna-bihar`):

- `rain.csv` - `date,mm` daily NASA GPM IMERG rainfall
- `fires.csv` - `date,lat,lon` NASA FIRMS hotspots
- `opera.tif` - optional local OPERA DSWx-S1 tile

River overflow is measured from the change map itself; earthquakes come from the public USGS feed.

## Deploy

`docker build -t nce-api . && docker run -p 8000:8000 --env-file .env -v $PWD/data:/data nce-api`
Set `NCE_PUBLIC_BASE_URL` to the public address so image links are absolute.

## Data toolkit

| Command | What it does |
| --- | --- |
| `python scripts/prepare_demo.py` | For every area in `demo_areas.json`: pass table, rainfall (NASA POWER), fire hotspots (NASA FIRMS, needs `FIRMS_MAP_KEY`), Copernicus DEM 30 m, full analysis, OPERA check, accuracy if check points exist. Writes `data/demo_summary.md`. |
| `python scripts/prepare_demo.py --only Patna --skip-analysis` | Only collect supporting data for one area |
| `python scripts/make_checkpoints.py --key <id> --name "Patna, Bihar"` | 100 random points (50 our-water, 50 our-dry) to label by hand |
| `python scripts/score.py --key <id> --points data/drivers/patna-bihar/checkpoints.csv` | Precision, recall, confusion matrix; saved into the result as `accuracy` |

With `dem.tif` present, slopes over 10 degrees are masked and the "flat, low-lying land" cause is checked.
`result.images.photo` is a NASA Worldview true-colour snapshot for the date after the change (expect cloud).


## Download data from the app

On **Check data** the app shows how many NISAR passes for the area are already on this computer, how
many MB are left and roughly how long they will take. **Download** fetches them in the background
(the same as `scripts/run_area.py` in the terminal) with a panel showing % done, MB, speed and time
left; you can minimise it, keep exploring, or cancel (files already downloaded are kept). Running an
analysis on an area that is not downloaded shows the same progress on the Analysing screen.

Time left is worked out from the speed of the download in progress. Before it starts, the app uses the
speed and file size measured on this computer last time (`data/download_stats.json`), or a cautious
default (`NCE_DL_PRIOR_MB_PER_FRAME`, `NCE_DL_PRIOR_MBPS`) the very first time.

API: `POST /downloads/status`, `POST /downloads`, `GET /downloads/{id}`, `POST /downloads/{id}/cancel`.
