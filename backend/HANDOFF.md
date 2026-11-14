# NISAR Change Explorer: handoff

**From:** Abilash (team lead, built the app)
**For:** the teammate taking over accuracy, data visuals and resource testing
**Challenge:** NASA Space Apps 2026, "Dancing with the SARs"
**Deadline:** submission **Sunday 2:30 PM IST**. Code freeze **Sunday 12:30 PM IST** (after that, only fixes for things that are broken).

---

## 1. What this is, in two minutes

A web app where anyone picks a place on a globe, checks whether NASA–ISRO **NISAR** radar has covered it,
asks "what changed?", and gets a plain-language answer:
- how many hectares turned to water;
- a before/after radar swipe;
- whether NASA's own OPERA water map agrees;
- likely causes (rain, river, flat land, quakes, fires);
- an honest confidence level.

It runs as **one Python server** (FastAPI). The server also hosts the web app (plain JavaScript, no build step).

**What works today:**
- all screens;
- in-app data download with % done and time left;
- watch list;
- PDF report;
- share links;
- 20 passing tests.

**What needs you:**
1. **Accuracy.** Water detection is calibrated on Patna only and has not been checked against independent ground truth yet.
2. **Visual presentation of the data.** The charts and maps work but can be clearer and more striking.
3. **Resource exploration and testing.** Every challenge resource needs to be tried, tested and written up.

---

## 2. Get it running (about 15 minutes)

You need: Python 3.11+, Git, Chrome, and **your own** free NASA Earthdata account (https://urs.earthdata.nasa.gov).

```powershell
git clone https://github.com/abilashprabakar27-ctrl/nisar-change-explorer.git
cd nisar-change-explorer\backend
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass        # Windows PowerShell only
.\.venv\Scripts\Activate.ps1                      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                            # then edit .env, see below
python -m pytest -q                               # should say "20 passed"
python -m uvicorn app.main:app --port 8000
```

Open **http://localhost:8000**. API docs are at http://localhost:8000/docs.

**`.env`** (never commit this file; it is already in `.gitignore`):
```
EARTHDATA_USERNAME=your_username          # the username, NOT your email
EARTHDATA_PASSWORD="your password"        # keep the double quotes
FIRMS_MAP_KEY=                            # optional, free from https://firms.modaps.eosdis.nasa.gov/api/map_key/
EODMS_USERNAME=                           # optional, for RADARSAT checks
EODMS_PASSWORD=
```

**No login? Use sample mode.** Open http://localhost:8000/sample once. Then in the app, choose **Patna** under "Or try a story". You get a labelled sample result in exactly the real shape, so you can work on visuals with no NASA access at all.

**First real run of an area is slow:**
- About 1–2 minutes per pass file from India, because NASA's archive is in the US.
- Use the app's **Download** button on Check data, or run `python scripts/prepare_demo.py --only "Patna"`.
- After that, the area loads from `data/cache` in seconds.
- The `data/` folder is NOT in git. Ask Abilash for a zip of `data/cache` if you want Patna without downloading.

---

## 3. Where everything is

```
backend/
  app/
    main.py            API: every endpoint the app calls; also serves web/ at /app
    pipeline.py        the 6 steps: Check, Fetch, Prepare, Detect, Verify, Explain (start here)
    catalog.py         finds NISAR passes (asf_search), picks one track, splits before/after
    downloads.py       in-app download: status, % done, time left, cancel, learned speed
    store.py           saved results + job files; METHOD_VERSION lives here
    config.py          every threshold and setting (most can be overridden in .env)
    assistant.py       the "Ask about this result" answers (rule-based, from result facts only)
    accuracy.py        precision / recall from hand-labelled check points
    data_sources.py    NASA POWER rain, FIRMS fires, Copernicus DEM, Worldview photo URL
    partners.py        RCM / RADARSAT-1 (EODMS API) and SAOCOM (recorded by hand)
    resources.py       every challenge resource with tags + credits shown in the app
    watch.py           "Watch this place" + hourly new-pass check
    sample.py          the labelled sample result
    science/
      gcov.py          reads only the study-area window from a NISAR GCOV .h5 file (+ cache)
      grid.py          common 20 m UTM grid, averaging resample
      change.py        THE WATER METHOD: dB, Lee filter, composites, thresholds, change, confidence
      verify.py        comparison with NASA OPERA DSWx-S1 + agreement map
      drivers.py       likely causes: rain, river connection, flat land, quakes, fires
      render.py        PNG images for the map (result colours, HH/HV greys, colour mix)
  web/
    index.html         page shell
    style.css          the whole design system (colours, fonts, every screen)
    app.js             every screen (one render function per screen, see list below)
    vendor/            MapLibre GL (globe/map) and Chart.js, stored locally
  scripts/             terminal tools (each has usage at the top of the file)
    run_area.py        one area end to end
    prepare_demo.py    all demo areas: data + analysis + accuracy -> data/demo_summary.md
    calibrate.py       measures real water/land dB values against OPERA
    diagnose.py        per-pass coverage and dB statistics for given dates
    make_checkpoints.py  50 "water" + 50 "dry" random points to label by hand
    score.py           precision / recall from a labelled checkpoints.csv
  tests/               pytest; run before every push
  demo_areas.json      the story areas (Patna, Morigaon, Kanpur) and their event dates
  DATA_RUNBOOK.md      step-by-step data runbook
```

**Screens in `web/app.js`:**

| Screen | Function |
|---|---|
| Find | `renderFind` |
| Check data | `renderCheck` |
| Ask | `renderAsk` |
| Analysing | `renderAnalysing` / `pollJob` |
| Answer | `renderAnswer` |
| Answer: viewer | `initViewer`, `applyView`, `startLapse` |
| Answer: per-pass chart | `passChartSVG` |
| Answer: plain-words box | `plainStory` |
| Do sources agree? | `renderSources` |
| How we know | `renderEvidence` |
| Why | `renderWhy` |
| Stories | `renderStories` |
| Watch list | `openWatch` |
| PDF report | `printReport` |
| Welcome animation | `runIntro` |
| Download panel | `renderDock` |

**The result JSON** (`data/results/<id>/result.json`, or GET `/results/<id>`) is the contract between backend and frontend. Look at one before you change either side. Key fields:
- `headline`
- `areas_ha` (`became_water`, `water_receded`, `permanent_water`)
- `water_ha`
- `per_pass`
- `confidence`
- `agreement` (OPERA)
- `drivers`
- `images`
- `provenance` (thresholds, grid, masked share, timings)
- `limits`
- `credits`

---

## 4. How the water method works now (read before changing it)

All in `app/science/change.py`, called from `pipeline.py`:

1. **Read** HH and HV power for the study area from each GCOV pass (`gcov.py`). Calm water can be clipped to exactly 0 by noise correction, so 0 is floored to −40 dB, **not** treated as missing.
2. **Grid:** all passes go on one 20 m UTM grid (40 m in "quick" mode). Frames from the same date are merged.
3. **dB + Lee speckle filter**, then a **median composite** of the 2 passes before and the 2 after the change date.
4. **Water** = HH < **−14.5 dB** AND HV < **−20.5 dB**.
   - These are fixed values, measured on Patna with `calibrate.py`.
   - `THRESHOLD_MODE=otsu` is an alternative that clamps HH to −20…−11 and HV to −26…−17.
5. **Became water** = water after, not water before, and HH dropped by more than 3 dB.
   - **Receded** = the reverse, only if dry on *all* after passes, and at least 2 ha.
   - Water present both times is **permanent** and is not counted as change.
   - Patches under 1 ha are removed.
6. **Persistence** = share of new water still seen on every after pass.
7. **Confidence:**
   - **High:** persistence ≥ 0.8, OPERA overlap ≥ 75% and 2+ passes on each side.
   - **Lower:** any Beta-quality pass, more than 15% unreadable, or overlap under 50%.
   - **Medium:** everything else.
8. **OPERA check** (`verify.py`): the share of *our* water that OPERA DSWx-S1 also marks as water (its classes 1–3).
   - ≥ 75% → Confirmed
   - ≥ 50% → Partly confirmed
   - otherwise → Sources disagree

**Last real Patna run** (track 98 ascending; before 19 Aug + 31 Aug, after 12 Sep + 24 Sep):
- became water 802 ha, receded 678 ha, permanent 932 ha;
- confidence Lower;
- OPERA overlap 17.9%. That figure was measured against a single pass; the code now compares against the after composite, so re-run to get the current number.
- Earlier runs over-detected water. Rice paddies and wet fields look like water in HH, which is why HV was added.

---

## 5. Workstream A: improve accuracy

**Golden rule: never tune the method to match OPERA and then use OPERA to prove it is right.** That is circular, and judges and mentors will ask about it. OPERA is a *second opinion*. Accuracy must come from **independent hand-labelled check points**.

### A1. Freeze a baseline first (30 min)
- Run `python scripts/prepare_demo.py` for all demo areas.
- Save `data/demo_summary.md` as `docs/baseline.md` in a branch: hectares, confidence, OPERA overlap, masked % per area.
- Every change you make is compared against this table.

### A2. Build independent ground truth (most important, about 1–2 h per area)
1. Run `python scripts/make_checkpoints.py --key <result id> --name "Patna, Bihar"`. This writes `data/drivers/patna-bihar/checkpoints.csv` with 100 random points.
2. Open the CSV in QGIS (or Google Earth) over a **clear-sky optical image close to the after date**, such as Sentinel-2 via Copernicus Browser or NASA Worldview.
3. Fill the `label` column with `water` / `not water` **without looking at the `ours` column**. Get a second person to label 20 of the same points to check agreement.
4. Run `python scripts/score.py --key <id> --points data/drivers/patna-bihar/checkpoints.csv`. It reports precision and recall, and the app's "How we know" screen shows them automatically.
5. Keep **half** the points for tuning and **half** untouched for the final number you report.

### A3. Ideas to try, in rough order of value

| Idea | Where | Why |
|---|---|---|
| Rice / wet-field filter: HV/HH ratio or a temporal-variance test | `change.py` | biggest false-positive source in Bihar |
| Height-above-river (HAND) or DEM mask: water can't be 30 m above the river | `data_sources.py` + `change.py` | removes hill shadows and false water |
| JRC Global Surface Water as "permanent water" instead of our own before-composite | new module | cleaner permanent-vs-new split |
| Tune the change dB (3 dB) and minimum patch (1 ha) on the tuning half of the points | `config.py` | quick wins |
| Per-area thresholds with `calibrate.py`, then check they generalise to the other areas | `scripts/calibrate.py` | Patna values may not fit Assam |
| Incidence-angle normalisation across the swath | `change.py` | near/far range brightness differences |
| Use all after passes for persistence, not just 2 | `catalog.choose_groups` | more stable "stayed flooded" |

### A4. Rules when you change the method
- **Bump `METHOD_VERSION` in `app/store.py`** (for example `water-change-v4-ricefilter`). Otherwise the app serves old cached results.
- Add or adjust a test in `tests/` and keep `python -m pytest -q` green.
- Record before/after numbers in `docs/accuracy_log.md`: date, change, precision, recall, OPERA overlap, hectares.
- If an idea doesn't beat the baseline on the held-out points, don't merge it.

---

## 6. Workstream B: more visually appealing presentation of data

The visual design is fixed. Keep the colours, fonts and corner-handle frames from `style.css`:
- background `#05080D`;
- cyan accent `#7DD3FC`;
- became water `#1D4ED8`, receded `#60A5FA`;
- fonts Michroma (headings), Inter (text) and JetBrains Mono (labels).

The original designs are on the team design canvas; ask Abilash for the link. Use `?r=<result id>` or the sample to work quickly.

**Not built yet from the designs (good first tasks):**
- **Side by side** viewer mode, next to Swipe (the tabs are in `renderAnswer`).
- The "≈ people live within 1 km · roads cross the area" line on the answer card. It needs a population source such as WorldPop or GHSL, and roads from OpenStreetMap.
- A dropdown on **Export report** (PDF / PNG of the map / CSV of numbers).
- A green "Validated method" chip, once accuracy is measured.

**Improvements to make:**
- **Per-pass chart** (`passChartSVG`): hover tooltips with date, quality and hectares; mark which passes were used.
- **Hotspot list:** the 3–5 biggest new-water patches with "zoom here" buttons. Compute them in `pipeline.py` from the classes array and add them to the result JSON.
- **Animated numbers and bars** on first view. Respect `prefers-reduced-motion`.
- **Colour-blind check** of blue / light blue / amber. Test at https://www.color-blindness.com/coblis-color-blindness-simulator/
- **Rain chart on Why:** show the pass dates as vertical lines and shade the change window.
- **Agreement map legend** and a clearer explanation when the sources disagree.
- **Phone layout** (≤ 900 px): check every screen.
- Every chart needs an `aria-label` summary (most have one; keep it that way).

**Submission rules that apply to visuals:**
- No NASA logos or insignia anywhere.
- Any AI-generated image must carry a visible "AI-generated" watermark.
- Credit every data source; the app's credits come from `resources.py`.

---

## 7. Workstream C: explore and test every resource

For each resource below:
1. Open it and try it by hand.
2. Check how the app uses it, or could use it.
3. Fill one row in `docs/resources_tested.md`.

**Row format:** resource · works? (Y/N/partly) · what we use it for · what we tested (area + dates) · result / screenshot · limits found · idea for the app.

| # | Resource | Used in app? | What to test |
|---|---|---|---|
| 1 | ASF Data Search **Vertex** (NISAR GCOV) | Yes: `catalog.py` | Search Patna, Morigaon and Kanpur by hand. Do the pass dates match the app's Check data screen? Any passes the app misses (different track, frames)? |
| 2 | **NISAR Data User Guide** (ASF) | Method | Confirm the GCOV layers, the mask values (255 = fill) and the Beta/Provisional/Validated meaning. List any known-issue notes that affect our dates. |
| 3 | **NASA Earthdata Search** | OPERA lookup | Find OPERA DSWx-S1 tiles for each demo area and date. Do they exist within ±6 days of our after pass? |
| 4 | **NASA OPERA DSWx-S1** | Yes: `verify.py` | Download one tile and open it in QGIS. Check the class values we use (1–3 = water, 250+ = invalid). |
| 5 | **NASA POWER** rainfall | Yes: Why screen | Do the rain totals for the Patna window look realistic against news reports? |
| 6 | **NASA FIRMS** fires | Yes, needs `FIRMS_MAP_KEY` | Get a key and test a fire area. Does the Why screen show fires? |
| 7 | **USGS earthquakes** | Yes: Why screen | Test an area with a known 2026 M4+ quake. |
| 8 | **Copernicus DEM GLO-30** | Yes: slope mask, flat land | Check that the tiles download for each area; look at the slope mask (`diagnose.py`). |
| 9 | **NASA Worldview** snapshots | Yes: photo tab | Do the photo-tab URLs load? Are the after dates cloudy? Find clear days for labelling (A2). |
| 10 | **RCM** (CSA) via EODMS | Yes: `POST /partners` | Make an EODMS account, put it in `.env`, and check scene counts for Patna. |
| 11 | **RADARSAT-1** (open licence) | Availability only | Find historic scenes over Patna (1995–2013) for a "has this happened before?" feature. |
| 12 | **SAOCOM** (CONAE) catalogue | Recorded by hand | Register (one click), search Patna for L-band scenes near our dates, and record them in `data/drivers/<area>/partners_found.json`. |
| 13 | **CSA SAR Python tutorial** | Learning | Run it once; note anything (filters, calibration) we could reuse. |
| 14 | **UAVSAR postcards** | Colour-mix idea | Compare their polarization colour scheme with our HH/HV mix and suggest improvements. |
| 15 | **Intro to Remote Sensing / Intro to SAR / ARSET** | Learning | Pick 3 facts we should state on the "How we know" page, with links. |
| 16 | **NISAR StoryMaps / Applications White Papers** | Stories / next steps | Find 1–2 more story areas with a 2026 event we could add to `demo_areas.json`. |

The links to all of these are in `app/resources.py` and on the app's "How we know" page.

**Also test the app itself** and log bugs as GitHub issues with screenshots:
- every screen at desktop and phone width;
- Download, Cancel and Resume;
- an area with no data (the ocean) and an area that is too large;
- share link, PDF report and watch list;
- server stopped while the app is open (it should offer the saved sample).

---

## 8. Working together on GitHub

- **Never commit:** `.env`, `.venv/`, `data/`. They are already in `.gitignore`; run `git status` before every commit anyway.
- **Branches:**
  - `accuracy/<idea>`, for example `accuracy/rice-filter`;
  - `visual/<thing>`;
  - `docs/resources`.
- Open a pull request into `main`. Abilash reviews.
- Before every push: `python -m pytest -q` passes, the app opens, and Patna still runs.
- Small commits with clear messages: "Add rice filter using HV/HH ratio (+6% precision on held-out points)".
- **AI disclosure (submission rule):** if you use an AI tool to write code or text, say so in the commit message or a code comment. Abilash will also list it in the "Use of SI" field of the submission form.

**Schedule:**

| When | What |
|---|---|
| Sat night | Setup, baseline (A1), label Patna check points (A2), resource table rows 1–9 |
| Sun 8 AM | First accuracy change + visual quick wins (side by side, hotspots, tooltips) |
| **Sun 12:30 PM** | **Code freeze**: merge only what is tested; final `prepare_demo.py` run |
| Sun 2:30 PM | Submission |

Questions: message Abilash. If something is broken and you are stuck for more than 20 minutes, ask; don't lose the evening.
