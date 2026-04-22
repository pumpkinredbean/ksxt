"""Contract tests for the multi-series ChartPanelSpec model (step 2).

Asserts:

* ``series_bindings`` defaults to an empty tuple.
* ``ChartPanelSpec`` and ``ChartSeriesBinding`` remain frozen.
* ``dataclasses.replace`` can swap ``series_bindings`` to a new tuple.
* ``asdict()`` serialises ``series_bindings`` as a list of dicts
  (matching what the JSON snapshot on disk actually contains).
"""

from __future__ import annotations

import dataclasses
import unittest


class ChartPanelMultiSeriesContractTests(unittest.TestCase):
    def test_series_bindings_default_is_empty_tuple(self) -> None:
        from packages.contracts.admin import ChartPanelSpec

        spec = ChartPanelSpec(
            panel_id="p1",
            chart_type="line",
            symbol="005930",
        )
        self.assertEqual(spec.series_bindings, ())
        self.assertEqual(spec.series_ref, "")
        self.assertEqual(spec.source, "raw_event")

    def test_panel_and_binding_are_frozen(self) -> None:
        from packages.contracts.admin import ChartPanelSpec, ChartSeriesBinding

        binding = ChartSeriesBinding(binding_id="b1", source_kind="raw")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            binding.axis = "right"  # type: ignore[misc]
        spec = ChartPanelSpec(
            panel_id="p1",
            chart_type="line",
            symbol="005930",
            series_bindings=(binding,),
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            spec.symbol = "000660"  # type: ignore[misc]

    def test_replace_swaps_bindings(self) -> None:
        from packages.contracts.admin import ChartPanelSpec, ChartSeriesBinding

        spec = ChartPanelSpec(panel_id="p1", chart_type="line", symbol="T")
        b1 = ChartSeriesBinding(binding_id="b1", source_kind="raw", event_name="trade", field_name="price")
        b2 = ChartSeriesBinding(binding_id="b2", source_kind="script", target_id="inst-xyz", output_name="value")
        next_spec = dataclasses.replace(spec, series_bindings=(b1, b2))
        self.assertEqual(len(next_spec.series_bindings), 2)
        self.assertEqual(next_spec.series_bindings[0].event_name, "trade")
        self.assertEqual(next_spec.series_bindings[1].target_id, "inst-xyz")

    def test_asdict_serialises_bindings_as_list_of_dicts(self) -> None:
        import json

        from packages.contracts.admin import ChartPanelSpec, ChartSeriesBinding

        spec = ChartPanelSpec(
            panel_id="p1",
            chart_type="candle",
            symbol="BTCUSDT",
            series_bindings=(
                ChartSeriesBinding(
                    binding_id="b1",
                    source_kind="raw",
                    event_name="ohlcv",
                    axis="left",
                    label="OHLCV",
                ),
                ChartSeriesBinding(
                    binding_id="b2",
                    source_kind="raw",
                    event_name="mark_price",
                    field_name="value",
                    axis="right",
                    label="Mark",
                ),
            ),
        )
        dumped = dataclasses.asdict(spec)
        # asdict preserves tuples for tuple fields; json serialisation
        # (the persistence path) collapses tuples to lists, so reloading
        # via json.loads yields list-of-dicts — assert that pipeline.
        bindings_value = dumped["series_bindings"]
        self.assertIn(type(bindings_value).__name__, {"tuple", "list"})
        self.assertEqual(len(bindings_value), 2)
        roundtripped = json.loads(json.dumps(dumped))
        self.assertIsInstance(roundtripped["series_bindings"], list)
        self.assertEqual(roundtripped["series_bindings"][0]["event_name"], "ohlcv")
        self.assertEqual(roundtripped["series_bindings"][1]["axis"], "right")

    def test_source_kinds_accept_raw_builtin_script(self) -> None:
        from packages.contracts.admin import ChartSeriesBinding

        for kind in ("raw", "builtin", "script"):
            ChartSeriesBinding(binding_id=f"b-{kind}", source_kind=kind)


if __name__ == "__main__":
    unittest.main()
