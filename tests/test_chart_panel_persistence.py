"""CRUD + JSON snapshot persistence round-trip tests for admin-charts state."""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path


class ChartsStateRoundTripTests(unittest.IsolatedAsyncioTestCase):
    async def test_panels_scripts_instances_round_trip_through_snapshot(self) -> None:
        from packages.contracts.admin import (
            ChartPanelSpec,
            IndicatorInstanceSpec,
            IndicatorScriptSpec,
        )
        from src.indicator_runtime import ChartsStateStore

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "admin_charts.json"
            store = ChartsStateStore(path=path)

            panel = ChartPanelSpec(
                panel_id="p1",
                chart_type="line",
                symbol="005930",
                source="raw_event",
                series_ref="trade",
                x=0, y=0, w=6, h=6,
                title="삼성 trade",
            )
            await store.upsert_panel(panel)

            user_script = IndicatorScriptSpec(
                script_id="u1",
                name="user OBI",
                source=(
                    "class MyInd(HubIndicator):\n"
                    "    name = 'my'\n"
                    "    inputs = ('trade',)\n"
                    "    def on_event(self, event):\n"
                    "        return None\n"
                ),
                class_name="MyInd",
                builtin=False,
            )
            await store.upsert_script(user_script)

            instance = IndicatorInstanceSpec(
                instance_id="i1",
                script_id="builtin.obi",
                symbol="005930",
                market_scope="total",
                params={"top_n": 3},
                enabled=True,
            )
            await store.upsert_instance(instance)

            self.assertTrue(path.exists())

            # Reload into a fresh store and verify identity.
            store2 = ChartsStateStore(path=path)
            store2.load()

            panels = await store2.list_panels()
            self.assertEqual(len(panels), 1)
            self.assertEqual(panels[0].panel_id, "p1")
            self.assertEqual(panels[0].title, "삼성 trade")

            scripts = {s.script_id: s for s in await store2.list_scripts()}
            self.assertIn("u1", scripts)
            self.assertIn("builtin.obi", scripts)  # seeded, not from disk
            self.assertEqual(scripts["u1"].class_name, "MyInd")

            instances = await store2.list_instances()
            self.assertEqual(len(instances), 1)
            self.assertEqual(instances[0].instance_id, "i1")
            self.assertEqual(instances[0].params, {"top_n": 3})

    async def test_delete_cascade_drops_instances_referencing_script(self) -> None:
        from packages.contracts.admin import (
            IndicatorInstanceSpec,
            IndicatorScriptSpec,
        )
        from src.indicator_runtime import ChartsStateStore

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "admin_charts.json"
            store = ChartsStateStore(path=path)

            await store.upsert_script(IndicatorScriptSpec(
                script_id="s1", name="n", source="class X(HubIndicator):\n    name='x'\n    inputs=()\n    def on_event(self, event): return None\n",
                class_name="X",
            ))
            await store.upsert_instance(IndicatorInstanceSpec(
                instance_id="i1", script_id="s1", symbol="T",
            ))
            removed = await store.delete_script("s1")
            self.assertTrue(removed)
            self.assertEqual(await store.list_instances(), [])

    async def test_builtin_script_cannot_be_deleted(self) -> None:
        from src.indicator_runtime import ChartsStateStore

        with tempfile.TemporaryDirectory() as tmp:
            store = ChartsStateStore(path=Path(tmp) / "s.json")
            self.assertFalse(await store.delete_script("builtin.obi"))

    async def test_panel_with_series_bindings_round_trip(self) -> None:
        from packages.contracts.admin import ChartPanelSpec, ChartSeriesBinding
        from src.indicator_runtime import ChartsStateStore

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "admin_charts.json"
            store = ChartsStateStore(path=path)

            panel = ChartPanelSpec(
                panel_id="p-multi",
                chart_type="candle",
                symbol="BTCUSDT",
                source="raw_event",
                series_ref="",  # legacy field intentionally empty
                x=0, y=0, w=8, h=10,
                title="candle + overlay",
                series_bindings=(
                    ChartSeriesBinding(
                        binding_id="b-base",
                        source_kind="raw",
                        event_name="ohlcv",
                        symbol="BTCUSDT",
                        axis="left",
                        label="OHLCV",
                    ),
                    ChartSeriesBinding(
                        binding_id="b-mark",
                        source_kind="raw",
                        event_name="mark_price",
                        field_name="value",
                        symbol="BTCUSDT",
                        axis="right",
                        color="#ffb000",
                        label="Mark",
                    ),
                ),
            )
            await store.upsert_panel(panel)

            # Reload from disk into a fresh store.
            store2 = ChartsStateStore(path=path)
            store2.load()
            panels = await store2.list_panels()
            self.assertEqual(len(panels), 1)
            reloaded = panels[0]
            self.assertEqual(reloaded.panel_id, "p-multi")
            self.assertEqual(len(reloaded.series_bindings), 2)
            self.assertEqual(reloaded.series_bindings[0].source_kind, "raw")
            self.assertEqual(reloaded.series_bindings[0].event_name, "ohlcv")
            self.assertEqual(reloaded.series_bindings[1].field_name, "value")
            self.assertEqual(reloaded.series_bindings[1].axis, "right")
            self.assertEqual(reloaded.series_bindings[1].color, "#ffb000")

    async def test_legacy_panel_without_series_bindings_still_loads(self) -> None:
        """Panels persisted by step1 (no series_bindings key) must keep loading."""
        import json

        from src.indicator_runtime import ChartsStateStore

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "admin_charts.json"
            snapshot = {
                "panels": [
                    {
                        "panel_id": "legacy",
                        "chart_type": "line",
                        "symbol": "005930",
                        "source": "raw_event",
                        "series_ref": "trade",
                        "x": 0, "y": 0, "w": 6, "h": 6,
                        "title": "legacy panel",
                        "notes": None,
                        # series_bindings intentionally absent
                    }
                ],
                "scripts": [],
                "instances": [],
                "schema_version": "v1",
            }
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            store = ChartsStateStore(path=path)
            store.load()
            panels = await store.list_panels()
            self.assertEqual(len(panels), 1)
            self.assertEqual(panels[0].panel_id, "legacy")
            self.assertEqual(panels[0].series_ref, "trade")
            self.assertEqual(panels[0].series_bindings, ())


if __name__ == "__main__":
    unittest.main()
