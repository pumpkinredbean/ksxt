# Adapter Boundary

## Rule

Adapters translate provider-specific behavior into shared ingress contracts. They do not define the core architecture.

## Adapter responsibilities

- authentication and session setup
- REST or websocket protocol handling
- subscription, polling, and request formatting
- source payload parsing
- source-specific symbol, timeframe, pagination, and sequencing logic
- creation of raw envelopes and adapter-edge mapping into canonical candidates

## Shared responsibilities outside adapters

### Collector/runtime layer

- lifecycle management
- scheduling, supervision, and restart behavior
- common ingest metadata and observability hooks
- publishing or routing raw events onward
- ownership of live upstream subscriptions and local fan-out to downstream consumers

### Domain/contracts layer

- broker-neutral event semantics
- instrument identity model
- shared enums, envelopes, and schema/versioning rules

### Downstream processing/storage layer

- canonical-to-derived transformations
- storage writing and materialization
- API-facing read models

## What must not leak inward

- provider-branded event names as permanent domain types
- provider request IDs as system-wide routing primitives
- source-specific timeframe or pagination rules as universal API semantics
- direct coupling from adapter code to storage-engine table shapes

## Current repo interpretation

- KIS is the active adapter today
- the collector service is the current live-runtime owner for dashboard streaming and price-chart fetching, while web consumes collector HTTP/SSE downstream
- broker-neutral scaffolding already exists under `packages/domain`, `packages/contracts`, and `packages/adapters`
- future adapters should be addable mostly under `packages/adapters/<source>` without redefining the core model
