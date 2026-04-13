"""Broker-neutral adapter interfaces for source-specific integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, TypeAlias

from packages.contracts.events import CanonicalEvent
from packages.domain.models import (
    InstrumentRef,
    OrderBookSnapshot,
    ProgramTrade,
    Trade,
)


TradeEvent: TypeAlias = CanonicalEvent[Trade]
OrderBookSnapshotEvent: TypeAlias = CanonicalEvent[OrderBookSnapshot]
ProgramTradeEvent: TypeAlias = CanonicalEvent[ProgramTrade]
MarketDataEvent: TypeAlias = TradeEvent | OrderBookSnapshotEvent | ProgramTradeEvent


class MarketDataAdapter(ABC):
    """Broker-neutral collector-facing market data adapter boundary."""

    adapter_id: str

    @abstractmethod
    def healthcheck(self) -> bool:
        """Return whether the adapter is currently healthy enough to run."""

    @abstractmethod
    def stream_trades(self, instrument: InstrumentRef) -> AsyncIterator[TradeEvent]:
        """Yield canonical trade events for an instrument."""

    @abstractmethod
    def stream_order_book_snapshots(
        self,
        instrument: InstrumentRef,
    ) -> AsyncIterator[OrderBookSnapshotEvent]:
        """Yield canonical order book snapshot events for an instrument."""

    @abstractmethod
    def stream_program_trades(
        self,
        instrument: InstrumentRef,
    ) -> AsyncIterator[ProgramTradeEvent]:
        """Yield canonical program trade events for an instrument."""


Adapter = MarketDataAdapter
