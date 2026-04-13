from __future__ import annotations

import json
import time

from packages.contracts.topics import RAW_EVENTS_TOPIC
from packages.shared.config import load_service_settings
from packages.shared.events import build_service_event


def main() -> None:
    settings = load_service_settings("collector")

    while True:
        event = build_service_event(
            event_type="collector.heartbeat",
            source="apps.collector.service",
            payload={
                "topic": RAW_EVENTS_TOPIC,
                "symbol": settings.symbol,
                "market": settings.market,
                "bootstrap_servers": settings.bootstrap_servers,
                "clickhouse_url": settings.clickhouse_url,
                "phase": "phase-1-placeholder",
            },
        )
        print(json.dumps(event, ensure_ascii=False), flush=True)
        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
