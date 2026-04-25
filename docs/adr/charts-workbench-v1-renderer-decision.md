# Charts Workbench V1 renderer decision evidence

Date: 2026-04-26
Branch: `fix/binance-raw-only-events`
Decision: `MIGRATE_TO_ECHARTS`

## Current `/admin/charts` browser E2E evidence

Fresh browser E2E was run against the served Docker app at `http://127.0.0.1:8000/admin/charts` after rebuilding `collector` and `api-web`.

Evidence artifact: `docs/verification/admin-charts-e2e-2026-04-26/admin-charts-e2e-evidence.json`
Screenshot: `docs/verification/admin-charts-e2e-2026-04-26/admin-charts-e2e.png`

Observed current asset: `/admin/assets/index-pZ9yLrVJ.js`

Checks recorded in the evidence JSON:

- Current built asset pattern: PASS
- Targetless disabled state covered before selecting a target: PASS
- Target/event/x/y raw-path flow: PASS (`binance-spot-BTCUSDT`, `trade`, `raw.info.E`, `raw.price`)
- Save/reload retained: PASS
- Canvas rendered: PASS
- Series sample count: 24
- Full-width/tiny regression absent: PASS
- `normalized.*` option count: 0

## ECharts renderer prototype evidence

The prototype is a real, inspectable browser artifact backed by the repo dependency `echarts` in `apps/admin_web/package.json`.

Prototype HTML: `docs/prototypes/echarts-renderer-prototype.html`
Runner: `tools/verify_echarts_renderer_prototype.py`
Evidence artifact: `docs/verification/echarts-renderer-prototype-2026-04-26/echarts-prototype-evidence.json`
Screenshot: `docs/verification/echarts-renderer-prototype-2026-04-26/echarts-prototype.png`

Prototype coverage:

- Line renderer from raw dotted paths: PASS (`raw.info.E` → `raw.info.nested.arbitrary.y`)
- Candle renderer from raw dotted paths: PASS (`raw.k.t/o/h/l/c`)
- Candle + line overlay: PASS
- Tooltip support: PASS (`tooltip.trigger = axis`)
- DataZoom support: PASS (`inside` + `slider`)
- Arbitrary x/y path mapping: PASS (`rawPathCanMove.x` → `rawPathCanMove.y`)
- Resize/full-width validation: PASS (width updated from 1386px to 926px, resize events 1 → 3)
- 10k point feasibility: PASS (10,000 line points + 10,000 candles; render ~142ms in Chromium run)

## Renderer comparison and decision

`MIGRATE_TO_ECHARTS`

Rationale:

- Workbench V1 requires arbitrary x/y path mapping from raw payloads. The ECharts prototype demonstrates this directly with line, candle, and overlay series from the same raw-path model.
- Tooltip and dataZoom are first-class in ECharts and verified in the prototype. The current Lightweight Charts implementation renders the current flow, but adding equivalent interactive data exploration would require more custom work.
- The 10k-point browser prototype remained feasible and resize/full-width behavior was validated.
- Because line, candle, overlay, tooltip, dataZoom, arbitrary paths, and 10k data are all covered by one renderer, a split renderer is not justified by current evidence.

Implementation note: the production `ChartsView` still uses Lightweight Charts. This decision records the renderer direction and provides inspectable evidence; it does not yet migrate production rendering.

## Commands run

- `npm --prefix apps/admin_web install echarts@^5.6.0`
- `npm --prefix apps/admin_web run build`
- `python3 tools/verify_echarts_renderer_prototype.py --out docs/verification/echarts-renderer-prototype-2026-04-26`
- `docker compose build collector api-web`
- `docker compose up -d collector api-web`
- `python3 tools/verify_admin_charts_e2e.py --base-url http://127.0.0.1:8000 --out docs/verification/admin-charts-e2e-2026-04-26`
- `PYTHONPATH=. pytest tests/ -q`

## Vault report status

The requested external vault path could not be modified from this execution context because external-directory tool access was denied. This repo-local ADR and evidence directory are the canonical inspectable artifacts for verification.
