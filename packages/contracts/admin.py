"""Shared admin/control-plane contracts for catalog, targeting, and runtime views."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from packages.domain.models import (
    CollectionTarget,
    CollectionTargetStatus,
    InstrumentSearchResult,
    RuntimeStatus,
    StorageBinding,
)

from .events import EventType


@dataclass(frozen=True, slots=True)
class EventTypeCatalogEntry:
    """Catalog entry describing one supported canonical event type."""

    event_type: EventType
    topic_name: str
    description: str
    owner_service: str = "collector"


@dataclass(frozen=True, slots=True)
class ControlPlaneSnapshot:
    """API- or Kafka-ready snapshot of the first admin/control-plane surface."""

    captured_at: datetime
    source_service: str
    event_type_catalog: tuple[EventTypeCatalogEntry, ...] = ()
    instrument_results: tuple[InstrumentSearchResult, ...] = ()
    collection_targets: tuple[CollectionTarget, ...] = ()
    storage_bindings: tuple[StorageBinding, ...] = ()
    runtime_status: tuple[RuntimeStatus, ...] = ()
    collection_target_status: tuple[CollectionTargetStatus, ...] = ()
    # KSXT realtime session-level state (IDLE/CONNECTING/HEALTHY/DEGRADED/CLOSED).
    # Surfaces a separate admin-UI banner from the collector_offline state.
    session_state: str | None = None
    schema_version: str = "v1"


@dataclass(frozen=True, slots=True)
class RecentRuntimeEvent:
    """Bounded operator-facing event sample from current runtime activity."""

    event_id: str
    topic_name: str
    event_name: str
    symbol: str
    market_scope: str
    published_at: datetime
    matched_target_ids: tuple[str, ...] = ()
    payload: dict[str, Any] | None = None
    schema_version: str = "v1"
