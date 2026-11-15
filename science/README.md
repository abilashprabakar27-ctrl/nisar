# science/

The NISAR science pipeline and its saved results, built alongside `backend/` and `web/`.
It was built in a separate repo first and is brought in here unchanged.

- `methods/floods.py`: water-change detection (Lee filter, log-ratio, Otsu, minimum patch)
- `workers/`: window reads, masks, per-pass series, rain and terrain drivers, OPERA check
- `api/`: a FastAPI app with the same ideas as `backend/app/` (a candidate to merge, not yet merged)
- `data/catalog/`: pass tables, IMERG rain series, per-pass series; `data/demo_results/`: saved Tonle Sap and Nile Sudd results
- `docs/`: abstract, form answers, 7-slide deck, plan and handoff notes
- `tests/`: 83 tests on synthetic and fixture data

Results on file: the saved demo results come from this older pipeline, whose water threshold was tuned on Tonle Sap against OPERA, so its old scores (0.72 / 0.90 / 0.79) are not the app's numbers and are not quoted. For the app (`backend/`), on the half of the Tonle Sap main window not used for parameter sweeps, our new-water map overlaps OPERA with IoU 0.68 (roughly 0.64 to 0.72), precision 0.88, recall 0.75; that half adjoins the tuned half and was seen when the final setting was picked, so it is not an independent test. The method does not transfer reliably: 0.04 on a window 50 km south, 0.01 to 0.78 by half on the window in between, and a Sentinel-2 check there agrees with only 15% of our new water. OPERA is another radar-based model, not ground truth, and there is no human-labelled accuracy yet. The Nile Sudd has not been checked. See docs/ACCURACY_FINAL.md.
