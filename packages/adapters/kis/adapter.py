"""KIS market-data adapter with a first-pass domestic stock trade stream path."""

from __future__ import annotations

from typing import AsyncIterator

from packages.adapters.base import MarketDataAdapter, MarketDataEvent, OrderBookSnapshotEvent, ProgramTradeEvent, TradeEvent
from packages.contracts import ChannelType, SubscriptionSpec
from packages.domain.enums import Venue
from packages.domain.models import InstrumentRef

from .auth import KISAuthProvider
from .config import KISSettings
from .mappers import map_order_book_event, map_program_trade_event, map_trade_event
from .realtime import KISRealtimeClient


class KISMarketDataAdapter(MarketDataAdapter):
    """First-pass adapter with only domestic stock KRX trade streaming wired live."""

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

    async def stream_trades(self, instrument: InstrumentRef) -> AsyncIterator[TradeEvent]:
        subscription = self.build_subscription_spec(
            instrument=instrument,
            channel_type=ChannelType.TRADE,
            market=self._resolve_trade_market(instrument),
        )
        if subscription.options["market"] != "krx":
            raise NotImplementedError("KIS trade adapter runtime currently supports only domestic stock KRX trades")

        auth = await self.auth.issue_realtime_credentials()
        async for row in self.realtime.stream_subscription_rows(subscription, auth):
            yield map_trade_event(row)

    async def stream_order_book_snapshots(
        self,
        instrument: InstrumentRef,
    ) -> AsyncIterator[OrderBookSnapshotEvent]:
        subscription = self.build_subscription_spec(
            instrument=instrument,
            channel_type=ChannelType.ORDER_BOOK_SNAPSHOT,
            market=self._resolve_trade_market(instrument),
        )
        if subscription.options["market"] != "krx":
            raise NotImplementedError(
                "KIS order book adapter runtime currently supports only domestic stock KRX order books"
            )

        auth = await self.auth.issue_realtime_credentials()
        async for row in self.realtime.stream_subscription_rows(subscription, auth):
            yield map_order_book_event(row)

    async def stream_program_trades(
        self,
        instrument: InstrumentRef,
    ) -> AsyncIterator[ProgramTradeEvent]:
        subscription = self.build_subscription_spec(
            instrument=instrument,
            channel_type=ChannelType.PROGRAM_TRADE,
            market=self._resolve_trade_market(instrument),
        )
        if subscription.options["market"] != "krx":
            raise NotImplementedError(
                "KIS program trade adapter runtime currently supports only domestic stock KRX program trades"
            )

        auth = await self.auth.issue_realtime_credentials()
        async for row in self.realtime.stream_subscription_rows(subscription, auth):
            yield map_program_trade_event(row)

    async def stream_dashboard_events(self, instrument: InstrumentRef) -> AsyncIterator[MarketDataEvent]:
        market = self._resolve_trade_market(instrument)
        if market != "krx":
            raise NotImplementedError("KIS dashboard adapter runtime currently supports only domestic stock KRX streams")

        subscriptions = [
            self.build_subscription_spec(
                instrument=instrument,
                channel_type=ChannelType.TRADE,
                market=market,
            ),
            self.build_subscription_spec(
                instrument=instrument,
                channel_type=ChannelType.ORDER_BOOK_SNAPSHOT,
                market=market,
            ),
            self.build_subscription_spec(
                instrument=instrument,
                channel_type=ChannelType.PROGRAM_TRADE,
                market=market,
            ),
        ]

        auth = await self.auth.issue_realtime_credentials()
        async for row in self.realtime.stream_subscriptions_rows(subscriptions, auth):
            channel_type = row.binding.spec.channel_type
            if channel_type == ChannelType.TRADE:
                yield map_trade_event(row)
                continue
            if channel_type == ChannelType.ORDER_BOOK_SNAPSHOT:
                yield map_order_book_event(row)
                continue
            if channel_type == ChannelType.PROGRAM_TRADE:
                yield map_program_trade_event(row)

    def _resolve_trade_market(self, instrument: InstrumentRef) -> str:
        if instrument.venue == Venue.KRX:
            return "krx"
        return "krx"
