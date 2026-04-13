# AGENTS.md

## Commands
- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Web app: `uvicorn apps.api_web.app:app --reload`
- Dashboard path: `python web.py`
- CLI path: `python main.py --symbol 005930 --market krx`
- Compose check: `docker compose config`

## Scope
- Treat this repo as a small monorepo with three working units: `apps/`, `packages/`, and `src/`.
- Keep AGENTS guidance at monorepo-unit level only. Do not add new per-app or per-package AGENTS files unless the repo structure changes materially.
- `src/` holds the real dashboard and KIS integration logic.
- `apps/` holds runtime entrypoints and placeholder services.
- `packages/` holds reusable shared code and deeper package layers.

## Always
- Read the nearest retained AGENTS file before changing files in `apps/`, `packages/`, or `src/`.
- Keep guidance accurate to current repo reality; do not describe unfinished parts as mature systems.
- Keep examples and docs public-safe; never copy local secrets or `.env` values.

## Ask First
- Adding a new top-level monorepo unit.
- Reintroducing nested AGENTS files below `apps/`, `packages/`, or `src/`.
- Breaking compatibility paths such as `web.py`, `main.py`, `apps.api_web.app:app`, or `src/config.py` re-exports.

## Never
- Scatter AGENTS.md files across individual apps or subpackages.
- Claim collector/processor are production-ready pipelines when they are still placeholder services.
- Treat thin entrypoints as the source of business logic when the implementation lives elsewhere.
