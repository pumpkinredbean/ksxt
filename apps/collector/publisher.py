"""Collector-side dashboard publisher helpers."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from packages.contracts.events import DashboardEventEnvelope
from packages.contracts.topics import DASHBOARD_EVENTS_TOPIC
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
    """Publish collector dashboard events to the broker."""

    def __init__(self, broker: Any):
        self._broker = broker

    async def publish_dashboard_event(
        self,
        *,
        symbol: str,
        market: str,
        event_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        message = _to_transport_value(
            DashboardEventEnvelope(
                symbol=symbol,
                market=market.lower(),
                event_name=event_name,
                payload=payload,
                published_at=datetime.utcnow(),
            )
        )
        await self._broker.publish(topic=DASHBOARD_EVENTS_TOPIC, value=message, key=f"{market.lower()}:{symbol}")
        return message
