"""Minimal compile-level tests for the KSXT-backed CollectorRuntime.

The legacy WS-managed runtime tests were removed as part of hub-B (collector
migration to KSXT ``KISRealtimeSession``).  Deep behavioural coverage of the
KSXT session is owned by the ksxt repo; here we only assert that the hub
module still imports and exposes the public surface the service layer needs.

hub-E will re-introduce integration-level coverage against the KSXT session.

One behavioural regression probe is retained (restored under hub-B H4): the
session-recovery path — when KSXT's ``on_recovery`` callback fires, the
control plane must clear transient publication errors and broadcast a
``session_recovered`` meta event to SSE subscribers.
"""
from __future__ import annotations

import asyncio
import unittest


class CollectorRuntimeImportTests(unittest.TestCase):
    def test_runtime_module_imports_ksxt_session(self) -> None:
        # Bare import — the runtime module should not pull the legacy
        # packages.adapters.kis websocket adapter anymore.
        from apps.collector import runtime as runtime_module

        self.assertTrue(hasattr(runtime_module, "CollectorRuntime"))
        self.assertTrue(hasattr(runtime_module, "SUPPORTED_MARKET_SCOPES"))
        # Confirm the legacy WS supervisor symbols have been removed — these
        # are exit criteria from the hub-B migration packet.
        for removed in (
            "_run_upstream_session",
            "_BASE_RECONNECT_DELAY",
            "_MAX_RECONNECT_DELAY",
            "_broadcast_recovery",
            "_broadcast_failure",
        ):
            self.assertFalse(
                hasattr(runtime_module, removed),
                f"{removed} must be removed from collector runtime (hub-B exit criteria)",
            )

    def test_runtime_uses_ksxt_session(self) -> None:
        from ksxt import KISRealtimeSession, RealtimeState

        # Sanity: public exports referenced by the runtime exist.
        self.assertTrue(hasattr(KISRealtimeSession, "subscribe"))
        self.assertTrue(hasattr(RealtimeState, "HEALTHY"))


class SessionRecoveryPropagationTests(unittest.IsolatedAsyncioTestCase):
    """Restored hub-B regression probe (H4 decision).

    Original name (pre-hub-B):
      ``test_session_failure_broadcasts_to_all_targets_and_recovery_clears_errors``

    This rewrite targets the KSXT ``KISRealtimeSession`` state transitions
    HEALTHY → DEGRADED → HEALTHY and the ``on_recovery`` hook. We stub the
    session so no network / private ``_registry`` access is required; the
    goal is to pin the contract that ``CollectorControlPlaneService``'s
    publication-error state is cleared when ``on_recovery`` fires and that
    a ``session_recovered`` meta event is delivered to subscribers.
    """

    async def test_session_failure_broadcasts_to_all_targets_and_recovery_clears_errors(self) -> None:
        from datetime import datetime
        from types import SimpleNamespace

        from src.collector_control_plane import CollectorControlPlaneService

        started: list[dict[str, object]] = []
        stopped: list[dict[str, object]] = []
        active_owners: set[str] = set()

        async def fake_start(**kwargs: object) -> dict[str, object]:
            started.append(kwargs)
            active_owners.add(str(kwargs["owner_id"]))
            return {"subscription_id": kwargs["owner_id"], "status": "started"}

        async def fake_stop(*, subscription_id: str) -> dict[str, object]:
            stopped.append({"subscription_id": subscription_id})
            active_owners.discard(subscription_id)
            return {"subscription_id": subscription_id, "status": "stopped"}

        service = CollectorControlPlaneService(
            service_name="collector",
            default_symbol="005930",
            default_market_scope="krx",
            start_publication=fake_start,
            stop_publication=fake_stop,
            is_publication_active=lambda owner_id: owner_id in active_owners,
        )

        # Seed two targets (HEALTHY baseline, like KSXT session state HEALTHY).
        upsert_a = await service.upsert_target(
            target_id=None,
            symbol="005930",
            market_scope="krx",
            event_types=["trade"],
            enabled=True,
        )
        upsert_b = await service.upsert_target(
            target_id=None,
            symbol="000660",
            market_scope="krx",
            event_types=["trade"],
            enabled=True,
        )
        target_id_a = upsert_a["target"].target_id  # type: ignore[attr-defined]
        target_id_b = upsert_b["target"].target_id  # type: ignore[attr-defined]

        # Simulate KSXT session HEALTHY → DEGRADED: the runtime fans a
        # publication failure out to each (symbol, market_scope) pair, as
        # would happen when the upstream session errors mid-stream.
        await service.record_publication_failure(
            symbol="005930", market_scope="krx", error="upstream disconnected"
        )
        await service.record_publication_failure(
            symbol="000660", market_scope="krx", error="upstream disconnected"
        )
        snapshot_degraded = await service.snapshot()
        statuses_degraded = {s.target_id: s for s in snapshot_degraded.collection_target_status}
        self.assertEqual(statuses_degraded[target_id_a].last_error, "upstream disconnected")
        self.assertEqual(statuses_degraded[target_id_b].last_error, "upstream disconnected")

        # Now simulate KSXT session DEGRADED → HEALTHY via on_recovery
        # callback path: CollectorDashboardService._handle_runtime_recovery
        # calls clear_all_publication_errors() + broadcast_session_recovered().
        async with service.subscribe_meta_events() as meta_queue:
            await service.clear_all_publication_errors()
            await service.broadcast_session_recovered()

            # Recovery must be delivered as a `session_recovered` meta SSE
            # event and MUST NOT pollute the market-data events feed.
            meta_event = await asyncio.wait_for(meta_queue.get(), timeout=1.0)

        self.assertEqual(meta_event[0], "session_recovered")
        self.assertIn("observed_at", meta_event[1])

        snapshot_recovered = await service.snapshot()
        statuses_recovered = {s.target_id: s for s in snapshot_recovered.collection_target_status}
        self.assertIsNone(statuses_recovered[target_id_a].last_error)
        self.assertIsNone(statuses_recovered[target_id_b].last_error)

        # Recent events queue must NOT have the meta event — it travels
        # exclusively on the meta channel.
        events_snapshot = await service.recent_events(limit=50)
        self.assertEqual(events_snapshot["recent_events"], ())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
