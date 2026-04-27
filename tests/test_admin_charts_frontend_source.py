"""Source-level regressions for the admin charts binding workbench."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARTS_VIEW = ROOT / "apps" / "admin_web" / "src" / "views" / "ChartsView.tsx"
STYLES = ROOT / "apps" / "admin_web" / "src" / "styles.css"


def test_field_binding_uses_strict_select_not_free_text_datalist() -> None:
    source = CHARTS_VIEW.read_text()

    assert "<datalist" not in source
    assert "list={`fields-" not in source
    assert "— select target/event first —" in source
    assert "disabled={!slotTarget || !slot.event_name || valueFields.length === 0}" in source


def test_raw_binding_uses_slot_field_before_param_field_and_syncs_param() -> None:
    source = CHARTS_VIEW.read_text()

    assert "slot.field_name ?? binding.param_values.field" in source
    assert "slot.time_field_name ?? binding.param_values.time_field" in source
    assert "syncRawFieldParam(binding, input_bindings)" in source
    assert "time_field: source?.time_field_name" in source


def test_x_and_y_candidates_share_single_raw_path_catalog() -> None:
    source = CHARTS_VIEW.read_text()

    assert "export function computeRawPathCatalog" in source
    assert "computeAllowedTimeFields" in source
    assert "return computeRawPathCatalog(eventName, target, rawEvents);" in source
    assert "const timeFieldRes = computeRawPathCatalog(slot.event_name, slotTarget, rawEvents);" in source
    assert "const fieldRes = computeAllowedFields(" in source
    assert "x raw path" in source
    assert "y raw path" in source
    assert "disabled={!slotTarget || !slot.event_name || timeFields.length === 0}" in source
    assert "TIME_FIELD_PRIORITY" not in source
    assert "function isTimeLikePath" not in source


def test_normalized_candidates_are_filtered_from_value_fields() -> None:
    source = CHARTS_VIEW.read_text()

    assert "current.startsWith('normalized.')" in source
    assert "k === 'normalized'" in source


def test_normalize_panel_scrubs_legacy_normalized_bindings() -> None:
    source = CHARTS_VIEW.read_text()

    assert "function scrubLegacyNormalizedBindingValue" in source
    assert "value.startsWith('normalized.')" in source
    assert "time_field_name: bindingText(raw.base_feed.time_field_name)" in source
    assert "time_field_name: bindingText(s.time_field_name)" in source
    assert "field_name: bindingText(s.field_name)" in source
    assert "param_values: sanitizeParamValues(paramValuesFromAny(b.param_values))" in source


def test_layout_storage_is_v4_and_clamped_full_width() -> None:
    source = CHARTS_VIEW.read_text()

    assert "preferredLayout.v4" in source
    assert "workingLayout.v4" in source
    assert "preferredLayout.v1" not in source
    assert "workingLayout.v1" not in source
    assert "seed.v3.done" not in source
    assert "export function clampChartLayoutItem" in source
    assert "x: 0" in source
    assert "w: CHART_LAYOUT_COLS" in source
    assert "h: Math.max(MIN_CHART_LAYOUT_H" in source
    assert "setLayout(clampChartLayout(preferred))" in source
    assert "onLayoutChange={(next) => setLayout(clampChartLayout(next))}" in source


def test_chart_time_extraction_supports_selected_field_and_fallbacks() -> None:
    source = CHARTS_VIEW.read_text()

    assert "export function parseChartTime" in source
    assert "raw < 10_000_000_000 ? raw * 1000 : raw" in source
    assert "extractChartTime(r, spec.base_feed?.time_field_name)" in source
    assert "extractChartTime(r, timeField)" in source


def test_production_chart_renderer_uses_echarts_not_lightweight_charts() -> None:
    source = CHARTS_VIEW.read_text()

    assert "from 'lightweight-charts'" not in source
    assert "createChart" not in source
    assert "echarts.init" in source
    assert "type: 'candlestick'" in source
    assert "type: 'line'" in source
    assert "tooltip: { trigger: 'axis'" in source
    assert "dataZoom:" in source


def test_charts_grid_is_not_shrunk_by_inspector_column() -> None:
    css = STYLES.read_text()
    source = CHARTS_VIEW.read_text()

    assert "grid-template-columns: minmax(0, 1fr);" in css
    assert "grid-template-columns: 1fr 340px" not in css
    assert "width={1200}" not in source


def test_raw_event_target_mirror_updates_existing_keys() -> None:
    source = CHARTS_VIEW.read_text()

    assert "rawSampleKey(targetId, eventName)" in source
    assert "ingestRawEventRow(prev, eventName, targetKeys, row)" in source
    assert "rawEventMirrorKeysForPanels(" in source
    assert "rawEvents.size" not in source
    assert "`${target.instrument.symbol}:${eventName}`" not in source


def test_selectors_use_actual_target_event_samples_only() -> None:
    source = CHARTS_VIEW.read_text()

    helper_start = source.index("export function computeRawPathCatalog")
    helper_end = source.index("export function rawEventMirrorKeysForPanels")
    helper = source[helper_start:helper_end]
    assert "canonicalSchemas" not in helper
    assert "field_hints" not in helper
    assert "return { fields: [], layer: 'empty' }" in helper
    assert "sampleOptionLabel" in source
    assert "— sample unavailable —" in source
    assert "newAllowedEvents[0]" not in source


def test_event_options_ignore_indicator_event_names_and_warn_only() -> None:
    source = CHARTS_VIEW.read_text()

    helper_start = source.index("export function computeAllowedEvents")
    helper_end = source.index("export type FieldOptionLayer")
    helper = source[helper_start:helper_end]
    assert "_slotEventNames" in helper
    assert "slotEventNames" not in helper.replace("_slotEventNames", "")
    assert "target.event_types" in helper
    assert "supported_event_types" in helper
    assert "showCompatibilityWarning" in source
    assert "binding.indicator_ref !== 'builtin.raw'" in source


def test_selected_target_event_fetches_scoped_raw_samples() -> None:
    source = CHARTS_VIEW.read_text()

    assert "selectedSamplePairs(panels)" in source
    assert "/api/admin/events?target_id=${encodeURIComponent(pair.targetId)}&event_name=${encodeURIComponent(pair.eventName)}&limit=50" in source
    assert "/api/admin/events?limit=200" not in source


def test_raw_paths_and_reader_support_bracket_syntax() -> None:
    source = CHARTS_VIEW.read_text()

    assert "function pathTokens" in source
    assert "tokens.push(n)" in source
    assert "Array.isArray(cur) && part < cur.length" in source
    assert "`${prefix}[${i}]`" in source
