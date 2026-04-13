# Package Layout

## Goal

Package boundaries should follow stable responsibilities, not the current adapter implementation.

## Current top-level layout

```text
apps/
  api_web/
  collector/
  processor/
packages/
  shared/
  domain/
  contracts/
  adapters/
  infrastructure/
src/
```

## Intended package roles

### `packages/domain`

- broker-neutral market-data concepts
- instrument identity
- semantic event types and value objects

### `packages/contracts`

- shared raw/canonical envelopes and schemas
- topic or channel contracts
- schema versioning helpers

### `packages/adapters`

- one subpackage per provider or venue
- auth, protocol clients, parsers, and mappers
- source-specific constraints and translation helpers

### `packages/infrastructure`

- stream and storage integrations
- runtime wiring, observability, and materialization plumbing

### `packages/shared`

- current shared settings and minimal service event helpers used across apps
- transitional shared utilities that support the monorepo runtime today

## App roles

- `apps/collector`: collector-stage FastAPI runtime entrypoint with `/health` and `/stream`; owns live upstream subscriptions for the current dashboard path
- `apps/processor`: processor-stage runtime entrypoint; currently placeholder
- `apps/api_web`: API/dashboard entrypoint that relays collector SSE for browser clients

## Dependency direction

- adapters may depend on domain and contracts
- infrastructure may depend on domain and contracts
- domain should not depend on adapters or infrastructure
- contracts should not import adapter implementations

## Migration note

The repository still contains a compatibility-heavy `src/` layer with active KIS-backed behavior. The current dashboard runtime is collector-owned streaming plus web-side SSE relay, while broader processor/storage architecture remains intentionally incomplete.
