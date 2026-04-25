#!/usr/bin/env python3
"""Run the repo-local ECharts renderer prototype and write evidence."""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs" / "prototypes" / "echarts-renderer-prototype.html"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="docs/verification/echarts-renderer-prototype-latest")
    args = parser.parse_args()
    out = (ROOT / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
      port = httpd.server_address[1]
      thread = threading.Thread(target=httpd.serve_forever, daemon=True)
      thread.start()
      url = f"http://127.0.0.1:{port}/docs/prototypes/{HTML.name}"
      with sync_playwright() as p:
          browser = p.chromium.launch()
          page = browser.new_page(viewport={"width": 1440, "height": 980})
          page.goto(url, wait_until="networkidle")
          page.wait_for_function("window.__ECHARTS_PROTOTYPE__ && window.__ECHARTS_PROTOTYPE__.metrics.linePoints === 10000")
          before = page.evaluate("window.__ECHARTS_PROTOTYPE__.metrics")
          page.set_viewport_size({"width": 980, "height": 900})
          page.wait_for_timeout(250)
          after = page.evaluate("window.__ECHARTS_PROTOTYPE__.metrics")
          screenshot = out / "echarts-prototype.png"
          page.screenshot(path=str(screenshot), full_page=True)
          browser.close()
      httpd.shutdown()

    evidence = {
        "url": url,
        "html": str(HTML.relative_to(ROOT)),
        "screenshot": str(screenshot.relative_to(ROOT)),
        "checks": {
            "line": before["linePoints"] == 10000,
            "candle": before["candlePoints"] == 10000,
            "overlay": before["overlaySeries"] == 2,
            "tooltip": before["tooltipEnabled"] is True,
            "dataZoom": before["dataZoomEnabled"] is True,
            "arbitraryPaths": before["arbitraryXPath"] == "rawPathCanMove.x" and before["arbitraryYPath"] == "rawPathCanMove.y",
            "resizeFullWidth": before["fullWidthClientWidth"] > 900 and after["fullWidthClientWidth"] > 700,
            "tenKFeasible": before["renderMs"] < 3000,
        },
        "metricsBeforeResize": before,
        "metricsAfterViewportResize": after,
        "decision": "MIGRATE_TO_ECHARTS",
    }
    (out / "echarts-prototype-evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
