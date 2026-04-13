"""Broker-neutral subscription contracts for upstream streaming sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from packages.domain.models import InstrumentRef


class ChannelType(StrEnum):
    """Canonical channel labels independent from any single broker."""

    TRADE = "trade"
    ORDER_BOOK_SNAPSHOT = "order_book_snapshot"
    PROGRAM_TRADE = "program_trade"


@dataclass(frozen=True, slots=True)
class SubscriptionSpec:
    """Minimal broker-neutral subscription request for one instrument/channel."""

    instrument: InstrumentRef
    channel_type: ChannelType
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def subscription_key(self) -> str:
        """Stable key useful for local dedupe and registry scaffolding."""

        return f"{self.channel_type}:{self.instrument.symbol}"
