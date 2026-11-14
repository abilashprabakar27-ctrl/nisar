# NISAR Change Explorer

**NASA Space Apps Challenge 2026: "Dancing with the SARs"**

A web app that shows how any place on Earth is changing, using NASA–ISRO NISAR radar.

## Where to start

- **Running the app:** see [backend/README.md](backend/README.md)
- **Teammates joining the project:** see [backend/HANDOFF.md](backend/HANDOFF.md)

```powershell
git clone https://github.com/abilashprabakar27-ctrl/nisar-change-explorer.git
cd nisar-change-explorer\backend
```

You need your own free NASA Earthdata account. Copy `backend/.env.example` to `backend/.env` and fill in your own credentials; `.env` is never committed.

## Folders

- `backend/` – FastAPI server with its own web frontend (`backend/web/`), science pipeline, scripts and tests
- `web/` – React + MapLibre web app (map, place search, availability card, NASA GIBS layer)

Planned as we build:
- `workers/` – science processing
- `notebooks/` – reproducible analysis
- `docs/` – architecture, data sources, licences

## Note on AI assistance

Parts of this code were written with help from Claude (Anthropic), a generative AI tool, and reviewed and tested by the team.
