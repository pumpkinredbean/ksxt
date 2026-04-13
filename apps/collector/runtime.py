from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any

from packages.adapters.base import MarketDataEvent
from packages.adapters.kis.adapter import KISMarketDataAdapter
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


def _aggregate_minute_candles(rows: list[dict[str, Any]], interval: int) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for row in rows:
        time_text = str(row.get("stck_cntg_hour") or "").strip()
        if len(time_text) != 6 or not time_text.isdigit():
            continue

        try:
            price = float(row.get("stck_prpr", 0) or 0)
            open_price = float(row.get("stck_oprc", 0) or 0)
            high_price = float(row.get("stck_hgpr", 0) or 0)
            low_price = float(row.get("stck_lwpr", 0) or 0)
            volume = int(float(row.get("cntg_vol", 0) or 0))
        except (TypeError, ValueError):
            continue

        point_time = datetime.strptime(time_text, "%H%M%S")
        bucket_minute = (point_time.minute // interval) * interval
        bucket_time = point_time.replace(minute=bucket_minute, second=0)
        bucket_key = bucket_time.strftime("%H%M")

        if current is None or current["key"] != bucket_key:
            current = {
                "key": bucket_key,
                "label": bucket_time.strftime("%H:%M"),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": price,
                "volume": volume,
            }
            buckets.append(current)
        else:
            current["high"] = max(current["high"], high_price)
            current["low"] = min(current["low"], low_price)
            current["close"] = price
            current["volume"] += volume

    return buckets[-120:]


class CollectorRuntime:
    """Collector-owned live runtime for dashboard consumers."""

    def __init__(self, settings: Any):
        self._adapter = KISMarketDataAdapter(settings)
        self._chart_client = KISProgramTradeClient(settings)

    async def aclose(self) -> None:
        await self._chart_client.aclose()

    async def stream_dashboard(self, *, symbol: str, market: str) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        if market.lower() != "krx":
            raise NotImplementedError("collector-owned live dashboard runtime currently supports only KRX")

        instrument = InstrumentRef(symbol=symbol, instrument_id=symbol, venue=Venue.KRX)
        async for event in self._adapter.stream_dashboard_events(instrument):
            yield _format_dashboard_event(event)

    def fetch_price_chart(self, *, symbol: str, market: str, interval: int) -> dict[str, Any]:
        rows = self._chart_client.fetch_intraday_chart(symbol=symbol, market=market)
        candles = _aggregate_minute_candles(rows, interval)
        return {
            "symbol": symbol,
            "market": market,
            "interval": interval,
            "candles": candles,
            "source": "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            "tr_id": "FHKST03010200",
        }
