"""Adapter layer entrypoints for broker or venue integrations."""

from .base import (
    Adapter,
    MarketDataAdapter,
    MarketDataEvent,
    OrderBookSnapshotEvent,
    ProgramTradeEvent,
    TradeEvent,
)
from .ccxt import CCXTAdapterStub, CCXTProAdapterStub
from .kxt import KXTAdapterStub
from .registry import ProviderRegistration, ProviderRegistry, build_default_registry

__all__ = [
    "Adapter",
    "CCXTAdapterStub",
    "CCXTProAdapterStub",
    "KXTAdapterStub",
    "MarketDataAdapter",
    "MarketDataEvent",
    "OrderBookSnapshotEvent",
    "ProgramTradeEvent",
    "ProviderRegistration",
    "ProviderRegistry",
    "TradeEvent",
    "build_default_registry",
]
