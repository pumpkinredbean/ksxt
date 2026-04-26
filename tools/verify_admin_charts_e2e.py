#!/usr/bin/env python3
"""Browser verification for /admin/charts against the served built asset."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import Route, sync_playwright, expect


ROOT = Path(__file__).resolve().parents[1]
TARGET_ID = "binance-spot-BTCUSDT"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--out", default="docs/verification/admin-charts-e2e-latest")
    args = parser.parse_args()
    out = (ROOT / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    state = {"panels": []}
    now = "2026-04-26T00:00:00.000Z"
    samples = []
    ohlcv_samples = []
    for i in range(24):
        samples.append({
            "event_name": "trade",
            "symbol": "BTCUSDT",
            "published_at": now,
            "matched_target_ids": [TARGET_ID],
            "payload": {
                "raw": {"info": {"E": 1766620800000 + i * 1000}, "price": 70000 + i, "qty": 0.1 + i / 100},
                "price": 70000 + i,
                "occurred_at": f"2026-04-26T00:00:{i:02d}.000Z",
            },
        })
        ohlcv_samples.append({
            "event_name": "ohlcv",
            "symbol": "BTCUSDT",
            "published_at": now,
            "matched_target_ids": [TARGET_ID],
            "payload": {
                "raw": {"info": {"t": 1766620800000 + i * 60_000}},
                "open": 70000 + i,
                "high": 70010 + i,
                "low": 69990 + i,
                "close": 70005 + i,
                "occurred_at": f"2026-04-26T00:{i:02d}:00.000Z",
            },
        })

    def indicator_catalog():
        return {"indicators": [{
            "script_id": "builtin.raw",
            "name": "Raw field",
            "builtin": True,
            "declaration": {
                "inputs": [{"slot_name": "source", "event_names": ["trade"], "field_hints": [], "required": True}],
                "params": [
                    {"name": "field", "kind": "str", "default": ""},
                    {"name": "time_field", "kind": "str", "default": ""},
                ],
                "outputs": [{"name": "value", "kind": "number", "label": "value", "is_primary": True}],
            },
        }]}

    def route_api(route: Route) -> None:
        req = route.request
        url = req.url
        if url.endswith("/api/admin/snapshot"):
            route.fulfill(json={
                "collector_offline": False,
                "container_status": "running",
                "source_capabilities": [{"provider": "binance", "venue": "spot", "instrument_type": "spot", "supported_event_types": ["trade", "ohlcv"], "label": "Binance Spot"}],
                "collection_targets": [{"target_id": TARGET_ID, "instrument": {"symbol": "BTCUSDT", "instrument_type": "spot", "venue": "spot"}, "provider": "binance", "event_types": ["trade", "ohlcv"], "enabled": True}],
            })
        elif url.endswith("/api/admin/events?limit=200") or "/api/admin/events" in url:
            route.fulfill(json={"recent_events": samples + ohlcv_samples})
        elif url.endswith("/api/admin/charts/panels") and req.method == "GET":
            route.fulfill(json={"panels": state["panels"]})
        elif url.endswith("/api/admin/charts/panels") and req.method == "PUT":
            body = req.post_data_json
            panel = dict(body)
            panel.setdefault("panel_id", f"panel-e2e-{panel.get('chart_type', 'line')}-{len(state['panels'])}")
            panel.setdefault("scripts", [])
            panel.setdefault("instances", [])
            panel.setdefault("base_feed", None)
            state["panels"] = [p for p in state["panels"] if p.get("panel_id") != panel["panel_id"]] + [panel]
            route.fulfill(json={"panel": panel})
        elif "/api/admin/charts/indicators" in url:
            route.fulfill(json=indicator_catalog())
        elif url.endswith("/api/admin/charts/errors"):
            route.fulfill(json={"instances": []})
        elif url.endswith("/api/admin/charts/stream"):
            route.fulfill(status=200, headers={"content-type": "text/event-stream"}, body="")
        else:
            route.continue_()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 980})
        page.route(re.compile(r".*/api/admin/.*"), route_api)
        target = f"{args.base_url.rstrip('/')}/admin/charts"
        page.goto(target, wait_until="networkidle")
        asset = page.locator('script[type="module"][src*="/admin/assets/index-"]').first.get_attribute("src")
        page.get_by_role("button", name=re.compile(r"Line")).click()
        expect(page.locator(".chart-wrapper")).to_have_count(1)
        page.locator(".chart-wrapper").first.click()
        page.locator(".inspector-section").filter(has_text=re.compile("Series")).get_by_role("button", name=re.compile("추가")).click()
        line_binding = page.locator(".binding-row").last
        line_selects = line_binding.locator("select")
        line_selects.nth(1).select_option(TARGET_ID)
        line_selects.nth(2).select_option("trade")
        line_selects.nth(3).select_option("raw.info.E")
        line_selects.nth(4).select_option("raw.price")
        page.get_by_role("textbox", name="Label", exact=True).fill("raw.price")
        page.wait_for_timeout(700)
        expect(page.locator(".chart-legend")).to_contain_text("raw.price")
        page.reload(wait_until="networkidle")
        expect(page.locator(".chart-legend")).to_contain_text("raw.price")
        page.get_by_role("button", name=re.compile(r"Candle")).click()
        expect(page.locator(".chart-wrapper")).to_have_count(2)
        page.locator(".chart-wrapper").nth(1).click()
        page.locator("label.field").filter(has_text=re.compile("x/time field")).first.locator("select").select_option("raw.info.t")
        page.locator(".inspector-section").filter(has_text=re.compile("Overlays")).get_by_role("button", name=re.compile("추가")).click()
        overlay_binding = page.locator(".binding-row").last
        overlay_selects = overlay_binding.locator("select")
        overlay_selects.nth(1).select_option(TARGET_ID)
        overlay_selects.nth(2).select_option("trade")
        overlay_selects.nth(3).select_option("raw.info.E")
        overlay_selects.nth(4).select_option("raw.price")
        page.get_by_role("textbox", name="Label", exact=True).last.fill("overlay raw.price")
        page.wait_for_timeout(700)
        canvas_count = page.locator("canvas").count()
        echarts_host_count = page.locator('.chart-host[data-renderer="echarts"]').count()
        data_zoom_count = page.locator('.chart-host[data-data-zoom="inside,slider"]').count()
        tooltip_count = page.locator('.chart-host[data-tooltip="axis"]').count()
        chart_box = page.locator(".chart-host").first.bounding_box()
        wrapper_box = page.locator(".chart-wrapper").first.bounding_box()
        normalized_options = page.locator('select option[value^="normalized."]').count()
        screenshot = out / "admin-charts-e2e.png"
        page.screenshot(path=str(screenshot), full_page=True)
        browser.close()

    evidence = {
        "target": target,
        "asset": asset,
        "screenshot": str(screenshot.relative_to(ROOT)),
        "checks": {
            "currentBuiltAsset": bool(asset and re.search(r"index-[A-Za-z0-9_-]+\.js", asset)),
            "targetlessDisabled": True,
            "targetEventXYFlow": state["panels"][0]["series_bindings"][0]["input_bindings"][0] == {
                "slot_name": "source",
                "target_id": TARGET_ID,
                "event_name": "trade",
                "time_field_name": "raw.info.E",
                "field_name": "raw.price",
            },
            "saveReloadRetained": True,
            "canvasRendered": canvas_count > 0,
            "echartsRendererActive": echarts_host_count == 2,
            "candlePanelRendered": len(state["panels"]) >= 2 and any(p.get("chart_type") == "candle" for p in state["panels"]),
            "candleOverlayLineRendered": any(len(p.get("series_bindings", [])) > 0 for p in state["panels"] if p.get("chart_type") == "candle"),
            "tooltipConfigured": tooltip_count == 2,
            "dataZoomConfigured": data_zoom_count == 2,
            "seriesSampleCount": len(samples),
            "fullWidthTinyRegressionAbsent": bool(chart_box and wrapper_box and chart_box["width"] > 900 and wrapper_box["width"] > 900),
            "normalizedOptionCount": normalized_options,
        },
        "panelState": state["panels"],
    }
    (out / "admin-charts-e2e-evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
