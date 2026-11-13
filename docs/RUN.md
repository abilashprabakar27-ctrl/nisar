# Run the server

1. Install: `pip install -e .[dev]`
2. Config is env-only: `NISAR_CACHE_DIR`, `NISAR_CATALOG_DIR`, `EARTHDATA_TOKEN` (not used by the sample stub yet). Never commit secrets.
3. Start: `uvicorn api.app:app --reload --port 8000`
4. Check: `curl http://localhost:8000/health` returns `{"status":"ok"}`.

## Endpoints
- `GET /places?q=Baton+Rouge`: OpenStreetMap Nominatim search (User-Agent `nisar-change-explorer`, recent queries cached in memory). Returns 502 with a plain message if the lookup fails.
- `POST /availability` `{bbox, start?, end?}`: which question types the catalog can answer (`questions`, `answerable`, `notes`). Uses `workers.check` on `data/catalog/pass_counts.csv`; falls back to a sample response if no catalog.
- `POST /analyses` `{bbox, before_start, before_end, after_start, after_end, question}`: returns `{"job_id": ...}` at once. Steps: checking, fetching, preparing, detecting, verifying, explaining.
- `GET /analyses/{id}`: the result (validated by `api.schemas.validate_result`); 409 with the current `step` while running; 404 for unknown id.
- `GET /analyses/{id}/events`: Server-Sent Events, one `data: {"step","message"}` frame per step until `done` or `error`.
- `GET /analyses/{id}/agreement`: per-source overlap, or `{"available": false, "reason": ...}`.

Areas must be 25 x 25 km or smaller (HTTP 422). Results are cached in `data/cache/` (gitignored), keyed by sha1 of the request plus `METHOD_VERSION` (`floods-0.2.0`).

## Science seam
`api/jobs.py: run_analysis(req) -> ChangeResult dict` is the single TODO. It currently returns `data/samples/golden_sample.json` (source `sample`, limits "Sample data - not live"). Return an optional `"_verify"` dict to feed `/agreement`.
