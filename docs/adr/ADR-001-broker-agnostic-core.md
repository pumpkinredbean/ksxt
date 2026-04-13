# ADR-001: Broker-Agnostic Core

- Status: Accepted
- Date: 2026-04-11

## Context

This repository currently uses KIS as the active market-data integration. At the same time, the project goal is broader than one broker: it aims to become a reusable real-time market-data stack.

Without an explicit decision, provider-specific field names, protocol constraints, and storage shortcuts could become permanent core architecture choices.

## Decision

The core architecture is broker-agnostic.

- provider-specific concerns stay in adapter packages at the ingestion edge
- shared domain models, contracts, processing stages, and serving layers use broker-neutral language where practical
- raw, canonical, and derived layers remain separate
- KIS is treated as the current adapter implementation, not as the system identity

## Consequences

### Positive

- future providers can be added with less impact on the core model
- storage, APIs, and dashboards can evolve around stable market-data semantics
- provider quirks remain isolated and easier to replace or extend

### Trade-offs

- explicit translation boundaries must be maintained
- some early implementation paths may feel indirect compared with coding directly to one provider
- provider-specific features may require careful mapping or explicit non-core extensions

## Implementation guidance

- place provider auth, protocol, and parsing logic under `packages/adapters/<source>`
- keep shared event meaning in `packages/domain` and `packages/contracts`
- avoid using provider-branded names for long-lived core event and topic contracts
- document provider limitations as adapter behavior, not as universal platform rules
