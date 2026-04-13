"""Collector-side publisher scaffolding kept separate from the current runtime loop."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from packages.adapters.base import MarketDataEvent


def _to_transport_value(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_transport_value(item) for key, item in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple):
        return [_to_transport_value(item) for item in value]
    if isinstance(value, list):
        return [_to_transport_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_transport_value(item) for key, item in value.items()}
    return value


class CollectorPublisher:
    """Publisher seam for collector fan-out without committing to Kafka yet."""

    async def publish(self, event: MarketDataEvent) -> dict[str, Any]:
        return _to_transport_value(event)

    async def publish_many(self, events: list[MarketDataEvent]) -> list[dict[str, Any]]:
        return [await self.publish(event) for event in events]
