# Data Inventory

## Purpose

This document lists the minimum data classes the architecture is designed to support. It is intentionally implementation-guiding rather than exhaustive.

## Inventory principles

- define data classes by market meaning, not by one broker's naming
- keep provenance and operational metadata alongside market facts
- allow the same class to appear across raw, canonical, derived, and serving stages with different shapes

## Required data classes

| Data class | Primary layers | Why it matters |
| --- | --- | --- |
| Instrument identity and reference data | Canonical, Serving | anchors symbol mapping, venue context, and stable instrument identity |
| Trade ticks | Raw, Canonical, Derived | supports replay, time-and-sales, and bar construction |
| Order book / quote data | Raw, Canonical, Derived, Serving | supports spread, depth, quote, and liquidity views |
| Program trade data | Raw, Canonical, Derived, Serving | preserves flow signals that should not be collapsed into ordinary trade events |
| Bar data | Canonical, Derived, Serving | supports charting, historical queries, and read-heavy consumers |
| Ingest and operational metadata | Raw, Derived, Serving | supports lineage, latency checks, replay, and operational trust |

## Minimum facts by class

### Instrument identity and reference data

- internal instrument identifier where available
- symbol and venue references
- instrument classification
- core trading constraints when relevant

### Trade ticks

- instrument identity
- event time and ingest time
- price and quantity
- trade identifier or side only when the source provides it reliably

### Order book / quote data

- instrument identity
- event time and ingest time
- best bid/ask or depth levels
- snapshot/delta context when available
- sequencing context when the source provides it

### Program trade data

- instrument or basket identity as available
- event time and ingest time
- direction, quantity, notional, or count fields when supplied
- preserved source classification for later interpretation

### Bar data

- instrument identity
- interval
- start and end time
- open, high, low, close
- volume/notional and completion status when relevant

### Ingest and operational metadata

- source and adapter identity
- raw event or trace identifiers
- ingest, publish, and processing timestamps
- quality or gap signals when available

## Scope note

These classes describe the target architecture. They do not imply that every class is fully implemented in the current runtime.
