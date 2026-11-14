# science/

The NISAR science pipeline and its saved results, built alongside `backend/` and `web/`.
It was built in a separate repo first and is brought in here unchanged.

- `methods/floods.py`: water-change detection (Lee filter, log-ratio, Otsu, minimum patch)
- `workers/`: window reads, masks, per-pass series, rain and terrain drivers, OPERA check
- `api/`: a FastAPI app with the same ideas as `backend/app/` (a candidate to merge, not yet merged)
- `data/catalog/`: pass tables, IMERG rain series, per-pass series; `data/demo_results/`: saved Tonle Sap and Nile Sudd results
- `docs/`: abstract, form answers, 7-slide deck, plan and handoff notes
- `tests/`: 83 tests on synthetic and fixture data

Results on file: Tonle Sap agrees with OPERA at IoU 0.72 (precision 0.90, recall 0.79) on the tuned window and 0.37 on the window to the south. The Nile Sudd is unvalidated.
