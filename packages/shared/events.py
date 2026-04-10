from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


RAW_EVENTS_TOPIC = "kis.raw.program-trade.v1"
PROCESSED_EVENTS_TOPIC = "kis.processed.program-trade.v1"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_service_event(*, event_type: str, source: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "source": source,
        "emitted_at": utc_now_iso(),
        "payload": payload,
    }
