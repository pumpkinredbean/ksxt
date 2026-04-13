# AGENTS.md

## Commands
- Shared settings check: `python -c "from packages.shared.config import load_service_settings; print(load_service_settings('collector'))"`
- Shared event check: `python -c "from packages.shared.events import build_service_event; print(build_service_event(event_type='x', source='y', payload={}))"`

## Scope
- `packages/` is for reusable code, shared contracts, and deeper package layers.
- Put code here only when it is shared across more than one app or runtime path.
- `packages/shared` currently owns shared env loading and event helpers.

## Always
- Keep shared modules small, importable, and public-safe.
- Add shared settings and contracts through existing package patterns instead of app-local copies.
- Keep wording honest about current implementation depth.

## Ask First
- Renaming shared env keys, topic names, or default ports.
- Moving app-specific behavior into `packages/`.
- Adding a new AGENTS file under an individual subpackage.

## Never
- Store real credentials or copied local env values in package code or docs.
- Add one-off app knobs to shared modules without true cross-app use.
