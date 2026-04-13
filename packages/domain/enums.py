"""Shared broker-agnostic enums for the core domain."""

from __future__ import annotations

from enum import StrEnum


class Venue(StrEnum):
    """Trading venue identifiers used by broker-neutral domain models."""

    KRX = "krx"
    NASDAQ = "nasdaq"
    NYSE = "nyse"
    CME = "cme"
    BINANCE = "binance"
    OTHER = "other"


class AssetClass(StrEnum):
    """Lean asset-class labels for instrument references."""

    EQUITY = "equity"
    ETF = "etf"
    FUTURE = "future"
    OPTION = "option"
    FX = "fx"
    CRYPTO = "crypto"
    INDEX = "index"
    OTHER = "other"


class TradeSide(StrEnum):
    """Optional aggressor or reported trade side when reliably available."""

    BUY = "buy"
    SELL = "sell"
    UNKNOWN = "unknown"


class InstrumentType(StrEnum):
    """Minimal instrument classification scaffold."""

    EQUITY = "equity"
    ETF = "etf"
    FUTURE = "future"
    OPTION = "option"
    FX_PAIR = "fx_pair"
    CRYPTO_PAIR = "crypto_pair"
    INDEX = "index"
    OTHER = "other"


class MarketSide(StrEnum):
    """Side semantics used by trades and book updates."""

    BID = "bid"
    ASK = "ask"
    BUY = "buy"
    SELL = "sell"
    UNKNOWN = "unknown"


class BarInterval(StrEnum):
    """Common bar interval labels for canonical bar events."""

    TICK = "tick"
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    DAY_1 = "1d"


class SessionState(StrEnum):
    """Trading session states when a source can report them."""

    PREOPEN = "preopen"
    OPEN = "open"
    HALTED = "halted"
    CLOSED = "closed"
    UNKNOWN = "unknown"
