from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class ServiceSettings:
    service_name: str
    app_env: str
    host: str
    port: int
    bootstrap_servers: str
    clickhouse_url: str
    symbol: str
    market: str
    log_level: str
    poll_interval_seconds: int


def load_service_settings(service_name: str) -> ServiceSettings:
    return ServiceSettings(
        service_name=service_name,
        app_env=os.getenv("APP_ENV", "development").strip() or "development",
        host=os.getenv("APP_HOST", "0.0.0.0").strip() or "0.0.0.0",
        port=int(os.getenv("APP_PORT", "8000")),
        bootstrap_servers=os.getenv("BOOTSTRAP_SERVERS", "redpanda:9092").strip() or "redpanda:9092",
        clickhouse_url=os.getenv("CLICKHOUSE_URL", "http://clickhouse:8123").strip() or "http://clickhouse:8123",
        symbol=(os.getenv("SYMBOL") or os.getenv("KIS_SYMBOL") or "005930").strip() or "005930",
        market=(os.getenv("MARKET") or os.getenv("KIS_MARKET") or "krx").strip() or "krx",
        log_level=os.getenv("LOG_LEVEL", "INFO").strip() or "INFO",
        poll_interval_seconds=max(1, int(os.getenv("POLL_INTERVAL_SECONDS", "30"))),
    )
