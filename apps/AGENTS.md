# AGENTS.md

## Commands
- Web app: `uvicorn apps.api_web.app:app --reload`
- Collector: `python -m apps.collector.service`
- Processor: `python -m apps.processor.service`

## Scope
- `apps/` is for runtime entrypoints and service wrappers.
- `apps/api_web/app.py` should stay a thin web entrypoint.
- `apps/collector` and `apps/processor` are still placeholder heartbeat services, not full pipeline implementations.

## Always
- Keep entrypoints small; move real shared logic into `src/` or `packages/`.
- Preserve stable import and launch paths used by the repo.
- Describe collector and processor honestly as placeholders unless the code actually changes.

## Ask First
- Adding another app.
- Turning placeholder services into real ingestion, processing, or persistence services.
- Moving dashboard or shared contract logic into `apps/`.

## Never
- Copy dashboard business logic into `apps/api_web`.
- Duplicate shared config or event helpers inside app folders.
