# NISAR Change Explorer

NASA Space Apps Challenge 2026, "Dancing with the SARs".

**Try it online: https://nisar-vercel-demo.vercel.app**
The online demo has the prepared flood stories (currently: Patna and Kanpur); the full app below runs any place locally.

- A web app that shows where water has newly appeared (or gone) in a place you pick, using NASA-ISRO NISAR radar.
- It writes the answer in plain words, with a confidence label and the reasons for it.
- It is honest about what it has and has not checked: see the accuracy summary below.

## Run it (3 commands)

```bash
git clone https://github.com/abilashprabakar27-ctrl/nisar.git
cd nisar/backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000. Sample mode (`GET /sample`, and the example result in the app) needs no login. Live NISAR data needs a free NASA Earthdata account: copy `backend/.env.example` to `backend/.env` and add your own credentials (never commit `.env`). More in [backend/README.md](backend/README.md) and [backend/HANDOFF.md](backend/HANDOFF.md).

## Where things are

- `backend/` : FastAPI server, API, tests and scripts (`backend/app/`, `backend/scripts/`, `backend/tests/`).
- `backend/web/` : the web UI the backend serves (plain JavaScript); `export_demo.py` builds the demo from it.
- `backend/app/science/` : the radar water-change method, confidence rules and the comparison with OPERA.
- `web/` : copy of the plain-JavaScript UI kept in step with `backend/web/`, next to the earlier React + MapLibre files.
- `vercel-demo/` : generated static demo for Vercel. Do not edit by hand; rebuild with `backend/scripts/export_demo.py`.
- `docs/` : accuracy results, review, plans and data notes. Start at [docs/README.md](docs/README.md).

## Accuracy in 5 lines

- We compare our new-water map with NASA OPERA (a different radar-based map), not with ground truth.
- On the east half of the Tonle Sap window: IoU 0.68, precision 0.88, recall 0.75. This place was used to tune the method.
- On a fresh window 0.44 degrees south it fails: IoU 0.04. Accuracy varies a lot between places.
- No score against hand-labelled points yet; confidence labels are rules, not probabilities, and most places are "not checked".
- Full numbers and limits: [docs/ACCURACY_FINAL.md](docs/ACCURACY_FINAL.md). Independent review of the claims: [docs/REVIEW.md](docs/REVIEW.md).

## Tests

```bash
cd backend && python -m pytest -q tests
```

Tests run offline on the sample scene (about 2 minutes).

## Contributing

- Keep pull requests small and focused.
- Tests must pass before you ask for review; add a test for new logic.
- Do not make claims the numbers do not support (no "confirmed", "validated" or "independent" for OPERA agreement; see docs/REVIEW.md section 4.2).
- Say in the PR how AI tools were used.

## AI assistance

Parts of this code and documentation were written with Claude (Anthropic), a generative AI tool, and reviewed and tested by the team.
