from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from packages.adapters.base import MarketDataEvent
from packages.adapters.kis.adapter import KISMarketDataAdapter
from packages.contracts import ChannelType, EventType
from packages.domain.enums import Venue
from packages.domain.models import InstrumentRef
from src.kis_websocket import KISProgramTradeClient


TRADE_PRICE_RENAME_MAP = {
    "STCK_CNTG_HOUR": "체결시각",
    "STCK_PRPR": "현재가",
}

PROGRAM_TRADE_RENAME_MAP = {
    "STCK_CNTG_HOUR": "체결시각",
    "SELN_CNQN": "프로그램매도체결량",
    "SELN_TR_PBMN": "프로그램매도거래대금",
    "SHNU_CNQN": "프로그램매수체결량",
    "SHNU_TR_PBMN": "프로그램매수거래대금",
    "NTBY_CNQN": "프로그램순매수체결량",
    "NTBY_TR_PBMN": "프로그램순매수거래대금",
    "SELN_RSQN": "매도호가잔량",
    "SHNU_RSQN": "매수호가잔량",
    "WHOL_NTBY_QTY": "전체순매수호가잔량",
}

ORDER_BOOK_RENAME_MAP = {
    "BSOP_HOUR": "호가시각",
    **{f"ASKP{level}": f"매도호가{level}" for level in range(1, 11)},
    **{f"BIDP{level}": f"매수호가{level}" for level in range(1, 11)},
    **{f"ASKP_RSQN{level}": f"매도잔량{level}" for level in range(1, 11)},
    **{f"BIDP_RSQN{level}": f"매수잔량{level}" for level in range(1, 11)},
    "TOTAL_ASKP_RSQN": "총매도잔량",
    "TOTAL_BIDP_RSQN": "총매수잔량",
}


SUPPORTED_MARKET_SCOPES = {"krx", "nxt", "total"}


@dataclass(frozen=True, slots=True)
class DashboardStreamKey:
    symbol: str
    market_scope: str


@dataclass(frozen=True, slots=True)
class RuntimeTargetRegistration:
    owner_id: str
    stream_key: DashboardStreamKey
    event_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _DashboardEventContext:
    stream_key: DashboardStreamKey
    event_name: str
    payload: dict[str, Any]


@dataclass(slots=True)
class _UpstreamPlan:
    subscriptions: list[Any]
    requested_event_names_by_key: dict[DashboardStreamKey, set[str]] = field(default_factory=dict)


ALL_EVENT_NAMES: tuple[str, ...] = tuple(event_type.value for event_type in EventType)
CHANNEL_TYPE_BY_EVENT_NAME: dict[str, ChannelType] = {
    EventType.TRADE.value: ChannelType.TRADE,
    EventType.ORDER_BOOK_SNAPSHOT.value: ChannelType.ORDER_BOOK_SNAPSHOT,
    EventType.PROGRAM_TRADE.value: ChannelType.PROGRAM_TRADE,
}


def _to_native_number(value: Any) -> int | float | str | None:
    if value is None:
        return None
    if hasattr(value, "to_integral_value"):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _rename_fields(fields: dict[str, Any], rename_map: dict[str, str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for source_key, target_key in rename_map.items():
        payload[target_key] = _to_native_number(fields.get(source_key))
    return payload


def _format_dashboard_event(event: MarketDataEvent) -> tuple[str, dict[str, Any]]:
    raw_payload = event.raw_payload if isinstance(event.raw_payload, dict) else {}
    fields = raw_payload.get("fields") if isinstance(raw_payload.get("fields"), dict) else {}

    if event.event_type.value == "trade":
        payload = _rename_fields(fields, TRADE_PRICE_RENAME_MAP)
        payload["체결시각"] = event.occurred_at.strftime("%H:%M:%S")
        payload["received_at"] = event.received_at.isoformat()
        return "trade_price", payload

    if event.event_type.value == "order_book_snapshot":
        payload = _rename_fields(fields, ORDER_BOOK_RENAME_MAP)
        payload["received_at"] = event.received_at.isoformat()
        return "order_book", payload

    payload = _rename_fields(fields, PROGRAM_TRADE_RENAME_MAP)
    payload["체결시각"] = event.occurred_at.strftime("%H:%M:%S")
    payload["received_at"] = event.received_at.isoformat()
    return "program_trade", payload


def _parse_session_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if len(text) != 10:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _resolve_row_session_date(row: dict[str, Any], fallback: date) -> date:
    for key in ("stck_bsop_date", "bsop_date", "trade_date"):
        raw = row.get(key)
        text = str(raw or "").strip()
        if len(text) == 8 and text.isdigit():
            try:
                return datetime.strptime(text, "%Y%m%d").date()
            except ValueError:
                continue
    return fallback


def _aggregate_minute_candles(rows: list[dict[str, Any]], interval: int, *, session_date: date) -> list[dict[str, Any]]:
    kst = timezone(timedelta(hours=9))
    normalized_rows: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        time_text = str(row.get("stck_cntg_hour") or "").strip()
        if len(time_text) != 6 or not time_text.isdigit():
            continue

        try:
            point_time = datetime.strptime(time_text, "%H%M%S")
            price = float(row.get("stck_prpr", 0) or 0)
            open_price = float(row.get("stck_oprc", 0) or 0) or price
            high_price = float(row.get("stck_hgpr", 0) or 0) or price
            low_price = float(row.get("stck_lwpr", 0) or 0) or price
            volume = int(float(row.get("cntg_vol", 0) or 0))
        except (TypeError, ValueError):
            continue

        normalized_rows.append(
            {
                "time_text": time_text,
                "point_time": point_time,
                "session_date": _resolve_row_session_date(row, session_date),
                "source_index": index,
                "price": price,
                "open": open_price,
                "high": max(high_price, price, open_price),
                "low": min(low_price, price, open_price),
                "volume": max(volume, 0),
            }
        )

    normalized_rows.sort(key=lambda item: (item["time_text"], item["source_index"]))

    deduped_rows: list[dict[str, Any]] = []
    current_time: str | None = None
    current_row: dict[str, Any] | None = None
    seen_signatures: set[tuple[Any, ...]] = set()

    for row in normalized_rows:
        signature = (row["time_text"], row["open"], row["high"], row["low"], row["price"], row["volume"])
        if row["time_text"] != current_time:
            if current_row is not None:
                deduped_rows.append(current_row)
            current_time = row["time_text"]
            seen_signatures = {signature}
            current_row = dict(row)
            continue

        if signature in seen_signatures:
            continue

        seen_signatures.add(signature)
        assert current_row is not None
        current_row["open"] = current_row["open"] or row["open"]
        current_row["high"] = max(current_row["high"], row["high"], row["price"])
        current_row["low"] = min(current_row["low"], row["low"], row["price"])
        if row["volume"] >= current_row["volume"]:
            current_row["price"] = row["price"]
        current_row["volume"] = max(current_row["volume"], row["volume"])

    if current_row is not None:
        deduped_rows.append(current_row)

    buckets: list[dict[str, Any]] = []
    current_bucket: dict[str, Any] | None = None

    for row in deduped_rows:
        point_time = row["point_time"]
        total_minutes = point_time.hour * 60 + point_time.minute
        bucket_total_minutes = (total_minutes // interval) * interval
        bucket_hour = bucket_total_minutes // 60
        bucket_minute = bucket_total_minutes % 60
        bucket_label = f"{bucket_hour:02d}:{bucket_minute:02d}"
        bucket_session_date = row["session_date"]
        bucket_key = f"{bucket_session_date.isoformat()}-{bucket_hour:02d}{bucket_minute:02d}"
        bucket_dt = datetime(
            bucket_session_date.year,
            bucket_session_date.month,
            bucket_session_date.day,
            bucket_hour,
            bucket_minute,
            tzinfo=kst,
        )

        if current_bucket is None or current_bucket["key"] != bucket_key:
            current_bucket = {
                "key": bucket_key,
                "time": int(bucket_dt.timestamp()),
                "label": bucket_label,
                "session_date": bucket_session_date.isoformat(),
                "source_time": row["time_text"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["price"],
                "volume": row["volume"],
            }
            buckets.append(current_bucket)
            continue

        current_bucket["high"] = max(current_bucket["high"], row["high"], row["price"])
        current_bucket["low"] = min(current_bucket["low"], row["low"], row["price"])
        current_bucket["close"] = row["price"]
        current_bucket["source_time"] = row["time_text"]
        current_bucket["volume"] += row["volume"]

    return buckets[-120:]


class CollectorRuntime:
    """Collector-owned live runtime for dashboard consumers."""

    def __init__(
        self,
        settings: Any,
        *,
        on_event: Callable[..., Awaitable[None]] | None = None,
        on_failure: Callable[..., Awaitable[None]] | None = None,
    ):
        self._adapter = KISMarketDataAdapter(settings)
        self._chart_client = KISProgramTradeClient(settings)
        self._on_event = on_event
        self._on_failure = on_failure
        self._lock = asyncio.Lock()
        self._refresh_event = asyncio.Event()
        self._registrations_by_owner: dict[str, RuntimeTargetRegistration] = {}
        self._upstream_task: asyncio.Task[None] | None = None
        self._closed = False

    async def aclose(self) -> None:
        self._closed = True
        self._refresh_event.set()
        async with self._lock:
            upstream_task = self._upstream_task
            self._upstream_task = None
            self._registrations_by_owner.clear()

        if upstream_task is not None:
            upstream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await upstream_task
        await self._chart_client.aclose()

    async def register_target(
        self,
        *,
        owner_id: str,
        symbol: str,
        market_scope: str,
        event_types: tuple[str, ...] | list[str] | None = None,
    ) -> RuntimeTargetRegistration:
        normalized_owner_id = owner_id.strip()
        if not normalized_owner_id:
            raise ValueError("owner_id is required")

        stream_key = self._build_stream_key(symbol=symbol, market_scope=market_scope)
        normalized_event_types = self._normalize_event_types(event_types)
        registration = RuntimeTargetRegistration(
            owner_id=normalized_owner_id,
            stream_key=stream_key,
            event_types=normalized_event_types,
        )

        async with self._lock:
            self._registrations_by_owner[normalized_owner_id] = registration
            self._ensure_upstream_task_locked()
            self._refresh_event.set()

        return registration

    async def unregister_target(self, *, owner_id: str) -> RuntimeTargetRegistration | None:
        normalized_owner_id = owner_id.strip()
        async with self._lock:
            registration = self._registrations_by_owner.pop(normalized_owner_id, None)
            if registration is not None:
                self._refresh_event.set()
        return registration

    def is_target_active(self, owner_id: str) -> bool:
        registration = self._registrations_by_owner.get(owner_id)
        return registration is not None and self._upstream_task is not None and not self._upstream_task.done()

    def _ensure_upstream_task_locked(self) -> None:
        if self._upstream_task is None or self._upstream_task.done():
            self._upstream_task = asyncio.create_task(self._run_upstream_session())

    async def _run_upstream_session(self) -> None:
        while not self._closed:
            refresh_event = self._refresh_event
            refresh_event.clear()

            plan = await self._build_upstream_plan()
            if not plan.subscriptions:
                await refresh_event.wait()
                continue

            try:
                auth = await self._adapter.auth.issue_realtime_credentials()
                async for row in self._adapter.realtime.stream_subscriptions_rows_until(
                    plan.subscriptions,
                    auth,
                    until=refresh_event,
                ):
                    event = self._adapter.map_dashboard_row(row)
                    published_event_name, payload = _format_dashboard_event(event)
                    event_context = _DashboardEventContext(
                        stream_key=DashboardStreamKey(
                            symbol=row.binding.spec.instrument.symbol,
                            market_scope=row.binding.market,
                        ),
                        event_name=event.event_type.value,
                        payload=payload,
                    )
                    if event_context.event_name not in plan.requested_event_names_by_key.get(event_context.stream_key, set()):
                        continue
                    await self._publish_event(event_context, published_event_name=published_event_name)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._broadcast_failure(exc)
                if self._closed:
                    return
                try:
                    await asyncio.wait_for(refresh_event.wait(), timeout=1)
                except TimeoutError:
                    continue

    async def _build_upstream_plan(self) -> _UpstreamPlan:
        async with self._lock:
            registrations = tuple(self._registrations_by_owner.values())

        requested_event_names_by_key: dict[DashboardStreamKey, set[str]] = {}
        for registration in registrations:
            requested_event_names_by_key.setdefault(registration.stream_key, set()).update(registration.event_types)

        subscriptions: list[Any] = []
        for stream_key, event_names in requested_event_names_by_key.items():
            instrument = InstrumentRef(symbol=stream_key.symbol, instrument_id=stream_key.symbol, venue=Venue.KRX)
            for event_name in sorted(event_names):
                channel_type = CHANNEL_TYPE_BY_EVENT_NAME[event_name]
                subscriptions.append(
                    self._adapter.build_subscription_spec(
                        instrument=instrument,
                        channel_type=channel_type,
                        market=stream_key.market_scope,
                    )
                )

        return _UpstreamPlan(subscriptions=subscriptions, requested_event_names_by_key=requested_event_names_by_key)

    async def _publish_event(self, event_context: _DashboardEventContext, *, published_event_name: str) -> None:
        if self._on_event is None:
            return
        await self._on_event(
            symbol=event_context.stream_key.symbol,
            market_scope=event_context.stream_key.market_scope,
            event_name=published_event_name,
            payload=dict(event_context.payload),
        )

    async def _broadcast_failure(self, exc: BaseException) -> None:
        if self._on_failure is None:
            return
        async with self._lock:
            stream_keys = tuple({registration.stream_key for registration in self._registrations_by_owner.values()})
        for stream_key in stream_keys:
            await self._on_failure(
                symbol=stream_key.symbol,
                market_scope=stream_key.market_scope,
                error=str(exc),
            )

    def _build_stream_key(self, *, symbol: str, market_scope: str) -> DashboardStreamKey:
        normalized_market_scope = market_scope.strip().lower()
        if normalized_market_scope not in SUPPORTED_MARKET_SCOPES:
            raise ValueError(f"unsupported market scope: {market_scope}")
        normalized_symbol = symbol.strip()
        if not normalized_symbol:
            raise ValueError("symbol is required")
        return DashboardStreamKey(symbol=normalized_symbol, market_scope=normalized_market_scope)

    def _normalize_event_types(self, event_types: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
        if event_types is None:
            return ALL_EVENT_NAMES

        normalized = []
        seen: set[str] = set()
        for event_type in event_types:
            candidate = str(event_type or "").strip().lower()
            if candidate not in CHANNEL_TYPE_BY_EVENT_NAME:
                raise ValueError(f"unsupported event type: {event_type}")
            if candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        if not normalized:
            raise ValueError("at least one event type is required")
        return tuple(normalized)

    def fetch_price_chart(self, *, symbol: str, market_scope: str, interval: int) -> dict[str, Any]:
        chart_payload = self._chart_client.fetch_intraday_chart(symbol=symbol, market=market_scope)
        rows = chart_payload.get("rows") if isinstance(chart_payload, dict) else []
        session_date = _parse_session_date(chart_payload.get("session_date")) if isinstance(chart_payload, dict) else None
        resolved_session_date = session_date or datetime.now(timezone(timedelta(hours=9))).date()
        candles = _aggregate_minute_candles(rows, interval, session_date=resolved_session_date)
        return {
            "symbol": symbol,
            "market_scope": market_scope,
            "market": market_scope,
            "interval": interval,
            "candles": candles,
            "session_date": resolved_session_date.isoformat(),
            "source": "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            "tr_id": "FHKST03010200",
        }
