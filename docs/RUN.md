# Run the server

1. Install: `pip install -e .[dev]`
2. Optional config: copy `.env.example` to `.env` and fill in values (never commit it).
3. Export any vars you need, e.g. `export EARTHDATA_TOKEN=...` (not used by the sample stub yet).
4. Start: `uvicorn server.app:app --reload --port 8000`
5. Check: `curl http://localhost:8000/health` returns `{"status":"ok"}`.
6. Analyze: `POST /analyze` with bbox, before/after dates and a question; returns `{"job_id": ...}`.
7. Poll: `GET /jobs/{job_id}` until status is `done` (or `error`).
8. Result: `GET /results/{job_id}` returns the ChangeResult JSON.
9. Areas must be 25 x 25 km or smaller (HTTP 422 otherwise).
10. Cached results live in `data/cache/` (gitignored). Set `NISAR_CACHE_DIR` to move them.
