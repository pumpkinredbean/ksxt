# Raw, Canonical, and Derived Layers

## Rule

Each layer answers a different question:

- **Raw**: what arrived from the source?
- **Canonical**: what does it mean in shared market-data terms?
- **Derived**: what downstream consumers need after transformation or aggregation?

## Raw

- preserves source payloads as closely as practical
- keeps provenance, transport, and replay/debug context
- may contain adapter-specific metadata
- is produced at the collector/adapter edge

## Canonical

- expresses normalized market facts in broker-neutral language
- removes dependence on source field names and transport quirks
- is the shared contract for processors, storage loaders, and reusable APIs

## Derived

- contains enriched, aggregated, joined, or read-optimized products
- includes examples such as bars, snapshots, summaries, and analytics tables
- should stay reproducible from raw and canonical inputs where feasible

## Transition rules

### Raw -> Canonical

- translation should be explicit
- raw events should remain available for replay or parser fixes
- normalization may remove source noise, but not meaningful market facts

### Canonical -> Derived

- derivation should remain separate from ingress
- downstream tables and APIs may optimize shape, but should not redefine canonical semantics

## Anti-patterns

- using raw topics as the permanent public contract
- pushing derived indicators back into canonical schemas
- letting storage-table columns dictate canonical event design
- making one adapter's optional fields mandatory for the whole system

## Current repo interpretation

- the placeholder collector currently emits runtime heartbeat events, not full raw market records
- the repo already includes canonical-oriented scaffolding in `packages/domain` and `packages/contracts`
- this layering remains the official direction for future implementation work
