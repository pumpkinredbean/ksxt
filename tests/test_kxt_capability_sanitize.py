"""Tests for H32 — KXT capability/runtime alignment.

Pins the behavior that:

1. KXT KRX spot ``upsert_target`` silently drops ``program_trade`` from
   event_types and surfaces a warning, because the kxt runtime does not
   implement a program_trade StreamKind.
2. Other providers (binance/ccxt) retain strict ValueError gating for
   ungated events — the sanitize path is scope-limited.
"""
from __future__ import annotations

import unittest
from typing import Any


class KxtCapabilitySanitizeTests(unittest.IsolatedAsyncioTestCase):
    async def _make_service(self):
        from src.collector_control_plane import CollectorControlPlaneService

        async def _noop(**_: Any) -> dict[str, object]:
            return {}

        return CollectorControlPlaneService(
            service_name="test",
            default_symbol="005930",
            default_market_scope="krx",
            start_publication=_noop,
            stop_publication=_noop,
            is_publication_active=lambda _o: False,
        )

    async def test_kxt_spot_drops_program_trade_with_warning(self) -> None:
        svc = await self._make_service()
        result = await svc.upsert_target(
            target_id=None,
            symbol="005930",
            market_scope="krx",
            event_types=["trade", "program_trade"],
            enabled=False,
            provider="kxt",
            instrument_type="spot",
        )

        self.assertTrue(result["applied"])
        target = result["target"]
        stored = tuple(target.event_types)
        self.assertIn("trade", stored)
        self.assertNotIn("program_trade", stored)
        # All stored events must be runtime-supported.
        self.assertTrue(set(stored) <= {"trade", "order_book_snapshot"})

        warning = result.get("warning")
        self.assertIsNotNone(warning)
        self.assertIn("program_trade", str(warning))

    async def test_binance_spot_still_rejects_ungated_event(self) -> None:
        """Regression pin: scope-limited sanitize must not soften Binance."""
        svc = await self._make_service()
        with self.assertRaises(ValueError) as cm:
            await svc.upsert_target(
                target_id=None,
                symbol="BTC/USDT",
                market_scope="",
                event_types=["trade", "mark_price"],
                enabled=False,
                provider="ccxt",
                instrument_type="spot",
            )
        # mark_price is not supported by Binance spot → strict ValueError.
        self.assertIn("mark_price", str(cm.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
