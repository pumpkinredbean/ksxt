"""KIS market-data adapter with domestic stock live stream support."""

from __future__ import annotations

from typing import AsyncIterator

from packages.adapters.base import MarketDataAdapter, MarketDataEvent, OrderBookSnapshotEvent, ProgramTradeEvent, TradeEvent
from packages.contracts import ChannelType, SubscriptionSpec
from packages.domain.enums import Venue
from packages.domain.models import InstrumentRef

from .auth import KISAuthProvider
from .config import KISSettings
from .mappers import KISRealtimeRow, map_order_book_event, map_program_trade_event, map_trade_event
from .realtime import KISRealtimeClient


class KISMarketDataAdapter(MarketDataAdapter):
    """Domestic stock adapter for KIS live trade, order book, and program streams."""

    adapter_id = "kis"

    def __init__(self, settings: KISSettings):
        self._settings = settings
        self.auth = KISAuthProvider(settings)
        self.realtime = KISRealtimeClient(settings)

    def healthcheck(self) -> bool:
        return bool(self._settings.ws_url)

    def build_subscription_spec(
        self,
        instrument: InstrumentRef,
        channel_type: ChannelType,
        **options: object,
    ) -> SubscriptionSpec:
        return SubscriptionSpec(
            instrument=instrument,
            channel_type=channel_type,
            options=dict(options),
        )

    async def stream_trades(self, instrument: InstrumentRef, *, market: str | None = None) -> AsyncIterator[TradeEvent]:
        subscription = self.build_subscription_spec(
            instrument=instrument,
            channel_type=ChannelType.TRADE,
            market=self._resolve_trade_market(instrument, market=market),
        )

        auth = await self.auth.issue_realtime_credentials()
        async for row in self.realtime.stream_subscription_rows(subscription, auth):
            yield map_trade_event(row)

    async def stream_order_book_snapshots(
        self,
        instrument: InstrumentRef,
        *,
        market: str | None = None,
    ) -> AsyncIterator[OrderBookSnapshotEvent]:
        subscription = self.build_subscription_spec(
            instrument=instrument,
            channel_type=ChannelType.ORDER_BOOK_SNAPSHOT,
            market=self._resolve_trade_market(instrument, market=market),
        )

        auth = await self.auth.issue_realtime_credentials()
        async for row in self.realtime.stream_subscription_rows(subscription, auth):
            yield map_order_book_event(row)

    async def stream_program_trades(
        self,
        instrument: InstrumentRef,
        *,
        market: str | None = None,
    ) -> AsyncIterator[ProgramTradeEvent]:
        subscription = self.build_subscription_spec(
            instrument=instrument,
            channel_type=ChannelType.PROGRAM_TRADE,
            market=self._resolve_trade_market(instrument, market=market),
        )

        auth = await self.auth.issue_realtime_credentials()
        async for row in self.realtime.stream_subscription_rows(subscription, auth):
            yield map_program_trade_event(row)

    async def stream_dashboard_events(
        self,
        instrument: InstrumentRef,
        *,
        market: str | None = None,
    ) -> AsyncIterator[MarketDataEvent]:
        subscriptions = self.build_dashboard_subscriptions(instrument, market=market)

        auth = await self.auth.issue_realtime_credentials()
        async for row in self.realtime.stream_subscriptions_rows(subscriptions, auth):
            yield self.map_dashboard_row(row)

    def build_dashboard_subscriptions(
        self,
        instrument: InstrumentRef,
        *,
        market: str | None = None,
    ) -> list[SubscriptionSpec]:
        resolved_market = self._resolve_trade_market(instrument, market=market)
        return [
            self.build_subscription_spec(
                instrument=instrument,
                channel_type=ChannelType.TRADE,
                market=resolved_market,
            ),
            self.build_subscription_spec(
                instrument=instrument,
                channel_type=ChannelType.ORDER_BOOK_SNAPSHOT,
                market=resolved_market,
            ),
            self.build_subscription_spec(
                instrument=instrument,
                channel_type=ChannelType.PROGRAM_TRADE,
                market=resolved_market,
            ),
        ]

    def map_dashboard_row(self, row: KISRealtimeRow) -> MarketDataEvent:
        channel_type = row.binding.spec.channel_type
        if channel_type == ChannelType.TRADE:
            return map_trade_event(row)
        if channel_type == ChannelType.ORDER_BOOK_SNAPSHOT:
            return map_order_book_event(row)
        if channel_type == ChannelType.PROGRAM_TRADE:
            return map_program_trade_event(row)
        raise ValueError(f"unsupported dashboard channel type: {channel_type}")

    def _resolve_trade_market(self, instrument: InstrumentRef, *, market: str | None = None) -> str:
        if market is not None:
            normalized_market = market.strip().lower()
            if normalized_market in {"krx", "nxt", "total"}:
                return normalized_market
            raise ValueError(f"unsupported KIS live market: {market}")
        if instrument.venue == Venue.KRX:
            return "krx"
        return "krx"
