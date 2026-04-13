# Architecture Overview

## Purpose

This repository is evolving into a reusable real-time market data stack for Korean equities and related workflows. The current live integration is KIS, but the long-term architecture is broker-agnostic.

## Current direction

- treat broker integrations as edge adapters, not as the system identity
- keep shared domain concepts, contracts, and downstream pipelines broker-neutral where practical
- separate ingress, normalization, processing, storage, and serving responsibilities
- document current committed direction only; exploratory notes stay outside this repo

## High-level flow

```text
collector -> broker adapter -> processor -> analytical storage -> api/web
```

Today, the repo already contains the monorepo skeleton for that shape:

- `apps/collector`: placeholder service for ingress-stage runtime wiring
- `apps/processor`: placeholder service for downstream processing-stage wiring
- `apps/api_web`: API and dashboard entrypoint
- `packages/shared`: current shared config and minimal event helpers
- `packages/domain`, `packages/contracts`, `packages/adapters`, `packages/infrastructure`: emerging broker-agnostic package boundaries
- `src/`: compatibility-heavy implementation layer, including current KIS-backed behavior

## Current reality

- KIS is the active adapter today
- `collector` and `processor` are still placeholder heartbeat services, not full production data pipeline components
- the repo already contains early broker-neutral scaffolding such as domain models and canonical event/topic packages
- compose wiring already reflects the intended platform shape with collector, processor, Redpanda, ClickHouse, and API/web services
- KRX dashboard live streaming now uses a collector-owned in-process runtime that keeps one upstream KIS subscription per active subscription spec and fans out locally to web consumers

## Design rules

- broker-specific auth, protocol details, and source quirks stay in adapter packages
- canonical event meaning should not depend on one provider's field names
- raw, canonical, and derived data should remain distinct
- serving models may optimize for query and UI needs, but should not redefine core event semantics

## Related docs

- `data-inventory.md`
- `adapter-boundary.md`
- `raw-canonical-derived.md`
- `package-layout.md`
- `../adr/ADR-001-broker-agnostic-core.md`
