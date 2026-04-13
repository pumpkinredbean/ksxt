"""Minimal domain models for broker-neutral market data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime

from .enums import AssetClass, InstrumentType, TradeSide, Venue


@dataclass(frozen=True, slots=True)
class InstrumentRef:
    """Stable instrument reference independent from adapter-specific symbols."""

    symbol: str
    instrument_id: str | None = None
    venue: Venue | None = None
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None


@dataclass(frozen=True, slots=True)
class Trade:
    """Individual execution fact without cumulative, book, or transport metadata."""

    instrument: InstrumentRef
    occurred_at: datetime
    price: Decimal
    quantity: Decimal
    side: TradeSide | None = None
    trade_id: str | None = None
    sequence: int | str | None = None


@dataclass(frozen=True, slots=True)
class QuoteLevel:
    """Single price level with only the facts required for broker-neutral depth."""

    price: Decimal
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    """Snapshot-only order book state without source-specific totals or deltas."""

    instrument: InstrumentRef
    occurred_at: datetime
    asks: tuple[QuoteLevel, ...] = ()
    bids: tuple[QuoteLevel, ...] = ()


@dataclass(frozen=True, slots=True)
class ProgramTrade:
    """Program trading flow facts kept separate from ordinary trade executions."""

    instrument: InstrumentRef
    occurred_at: datetime
    sell_quantity: Decimal
    buy_quantity: Decimal
    net_buy_quantity: Decimal
    sell_notional: Decimal
    buy_notional: Decimal
    net_buy_notional: Decimal
    program_sell_depth: Decimal | None = None
    program_buy_depth: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Provenance:
    """Source metadata that keeps adapter details outside the core payload."""

    source_id: str
    adapter_id: str
    raw_event_id: str | None = None
    trace_id: str | None = None

