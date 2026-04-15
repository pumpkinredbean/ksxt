from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from apps.collector.runtime import CollectorRuntime
from packages.contracts import ChannelType, EventType, SubscriptionSpec
from packages.domain.enums import Venue
from packages.domain.models import InstrumentRef
from packages.adapters.kis.mappers import KISSubscriptionBinding
from packages.adapters.kis.realtime import KISRealtimeClient


class _FakeAuthProvider:
    async def issue_realtime_credentials(self) -> object:
        return object()


class _FakeRealtimeClient:
    def __init__(self) -> None:
        self.call_count = 0
        self.max_active_sessions = 0
        self._active_sessions = 0
        self.subscription_batches: list[list[SubscriptionSpec]] = []

    async def stream_subscriptions_rows_until(self, subscriptions, auth, *, until):
        self.call_count += 1
        self._active_sessions += 1
        self.max_active_sessions = max(self.max_active_sessions, self._active_sessions)
        self.subscription_batches.append(list(subscriptions))
        try:
            while not until.is_set():
                await asyncio.sleep(0.01)
            if False:
                yield None
        finally:
            self._active_sessions -= 1


class _FakeAdapter:
    def __init__(self) -> None:
        self.auth = _FakeAuthProvider()
        self.realtime = _FakeRealtimeClient()

    def build_subscription_spec(self, instrument, channel_type, **options):
        return SubscriptionSpec(instrument=instrument, channel_type=channel_type, options=dict(options))

    def map_dashboard_row(self, row):
        return SimpleNamespace(
            event_type=EventType.TRADE,
            raw_payload={"fields": {"STCK_CNTG_HOUR": "090000", "STCK_PRPR": "1000"}},
            occurred_at=datetime.now(timezone.utc),
            received_at=datetime.now(timezone.utc),
        )


class _FakeChartClient:
    async def aclose(self) -> None:
        return None


async def _wait_for(predicate, *, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met before timeout")


class CollectorRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_targets_share_one_upstream_task(self) -> None:
        events: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []
        runtime = CollectorRuntime(
            SimpleNamespace(ws_url="ws://example", rest_url="https://example", app_key="x", app_secret="y"),
            on_event=lambda **payload: _capture(events, payload),
            on_failure=lambda **payload: _capture(failures, payload),
        )
        fake_adapter = _FakeAdapter()
        runtime._adapter = fake_adapter
        runtime._chart_client = _FakeChartClient()

        await runtime.register_target(owner_id="target-1", symbol="005930", market_scope="krx", event_types=["trade"])
        await _wait_for(lambda: fake_adapter.realtime.call_count == 1)
        self.assertEqual(1, len(fake_adapter.realtime.subscription_batches[-1]))

        await runtime.register_target(owner_id="target-2", symbol="000660", market_scope="krx", event_types=["trade"])
        await _wait_for(lambda: fake_adapter.realtime.call_count == 2)
        self.assertEqual(2, len(fake_adapter.realtime.subscription_batches[-1]))
        self.assertEqual(1, fake_adapter.realtime.max_active_sessions)
        self.assertTrue(runtime.is_target_active("target-1"))
        self.assertTrue(runtime.is_target_active("target-2"))

        await runtime.aclose()
        self.assertEqual([], events)
        self.assertEqual([], failures)

    async def test_realtime_rows_bind_by_symbol_with_shared_tr_id(self) -> None:
        client = KISRealtimeClient(SimpleNamespace(ws_url="ws://example"))
        instrument_a = InstrumentRef(symbol="005930", instrument_id="005930", venue=Venue.KRX)
        instrument_b = InstrumentRef(symbol="000660", instrument_id="000660", venue=Venue.KRX)
        binding_a = KISSubscriptionBinding(
            spec=SubscriptionSpec(instrument=instrument_a, channel_type=ChannelType.TRADE, options={"market": "krx"}),
            tr_id="H0STCNT0",
            tr_key="005930",
            market="krx",
        )
        binding_b = KISSubscriptionBinding(
            spec=SubscriptionSpec(instrument=instrument_b, channel_type=ChannelType.TRADE, options={"market": "krx"}),
            tr_id="H0STCNT0",
            tr_key="000660",
            market="krx",
        )

        raw = "0|H0STCNT0|2|005930^090000^1000^0^0^0^0^0^0^0^0^0^10^10^10000^000660^090001^2000^0^0^0^0^0^0^0^0^0^20^20^20000"
        rows = await client._parse_many_message(
            raw=raw,
            bindings_by_subscription_key={("H0STCNT0", "005930"): binding_a, ("H0STCNT0", "000660"): binding_b},
            ws=SimpleNamespace(pong=_noop_pong),
        )

        assert rows is not None
        self.assertEqual(["005930", "000660"], [row.binding.tr_key for row in rows])
        self.assertEqual(["005930", "000660"], [row.fields["MKSC_SHRN_ISCD"] for row in rows])


async def _capture(bucket: list[dict[str, object]], payload: dict[str, object]) -> None:
    bucket.append(payload)


async def _noop_pong(_raw) -> None:
    return None
