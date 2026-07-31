# AGENTS.md

## Cursor Cloud specific instructions

DeathOvers is a cricket analytics platform with two runtime services:

| Service | Command | Port |
|---|---|---|
| **Astro frontend** | `npm run dev -- --host 0.0.0.0 --port 4321` | 4321 |
| **Flask backend** | `source .venv/bin/activate && python app.py` | 5000 |

See `DEPLOY_INSTRUCTIONS.md` for frontend-only local preview; `ARCHITECTURE.md` for full system design.

### Startup notes

- **Frontend API target:** `LiveCarousel.jsx` and `MatchRoom.jsx` fetch the deployed Render API (`https://deathovers-ai-engine.onrender.com`), not localhost. The Astro dev server works out of the box for UI + live-data E2E without running Flask locally.
- **Local full-stack:** To point the frontend at the local Flask API, temporarily change fetch URLs in those components to `http://localhost:5000`, or use a dev proxy.
- **Flask env vars:** `RAPIDAPI_KEY` is required for live Cricbuzz data. Without it, `/api/health` still returns `status: ok` but the live-scores cache stays empty. Optional: `CRICKETDATA_API_KEY`.
- **Intelligence engine:** Pre-built context JSON under `intelligence/output/context/` loads at Flask startup; no separate process or database is needed.
- **Python venv:** The repo pins Python 3.11 in `.python-version` but runs on 3.12 in this environment. If `python3 -m venv .venv` fails on a fresh VM, install `python3.12-venv` once via apt (not in the update script).

### Lint / test / build

There is no ESLint, pytest, or other automated test suite in this repo.

| Task | Command |
|---|---|
| Production build | `npm run build` |
| Backend health check | `curl http://localhost:5000/api/health` |
| Frontend smoke test | `curl -o /dev/null -w "%{http_code}" http://localhost:4321/` |

### Long-running processes

Use tmux for dev servers (example):

```bash
tmux -f /exec-daemon/tmux.portal.conf new-session -d -s flask-backend -c /workspace -- zsh -l
tmux -f /exec-daemon/tmux.portal.conf send-keys -t flask-backend:0.0 'source .venv/bin/activate && python app.py' C-m

tmux -f /exec-daemon/tmux.portal.conf new-session -d -s astro-dev-server -c /workspace -- zsh -l
tmux -f /exec-daemon/tmux.portal.conf send-keys -t astro-dev-server:0.0 'npm run dev -- --host 0.0.0.0 --port 4321' C-m
```

### Optional / out of scope for routine dev

- **Cricsheet data pipeline** (`intelligence/raw_data/`, `batch_parse.py`) — offline only; context JSON is committed.
- **GitHub Actions + Groq** — article generation pipeline; existing markdown posts work without it.
