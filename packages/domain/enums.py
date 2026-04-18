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
    """Instrument type classification supporting multiprovider semantics.

    Includes both legacy labels (equity/etf/fx_pair/crypto_pair) and
    multiprovider-ready semantics (spot/future/perpetual/option) so crypto
    venues can distinguish spot vs USDT-perpetual from day 1 while KRX
    equity defaults keep their existing ``equity`` label.
    """

    EQUITY = "equity"
    ETF = "etf"
    SPOT = "spot"
    FUTURE = "future"
    PERPETUAL = "perpetual"
    OPTION = "option"
    FX_PAIR = "fx_pair"
    CRYPTO_PAIR = "crypto_pair"
    INDEX = "index"
    OTHER = "other"


class Provider(StrEnum):
    """First-class provider/hub axis for multiprovider targets.

    ``KXT`` covers the KSXT-backed KIS integration (KRX equity today).
    ``CCXT`` and ``CCXT_PRO`` cover the crypto integration boundary and
    are introduced as a skeleton in step 1 of the multiprovider plan.
    """

    KXT = "kxt"
    CCXT = "ccxt"
    CCXT_PRO = "ccxt_pro"
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


class RuntimeState(StrEnum):
    """Lifecycle states for collector/admin control-plane runtime reporting."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    ERROR = "error"


class StorageBindingScope(StrEnum):
    """Scope labels for mapping incoming events into storage destinations."""

    ALL_TARGETS = "all_targets"
    COLLECTION_TARGET = "collection_target"
