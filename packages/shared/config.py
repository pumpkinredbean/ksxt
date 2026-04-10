from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

KIS_PROXY_BYPASS_HOSTS = [
    "openapi.koreainvestment.com",
    "openapivts.koreainvestment.com",
    "ops.koreainvestment.com",
]


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _apply_proxy_bypass() -> None:
    if not _bool_env("KIS_BYPASS_PROXY", True):
        return

    for env_name in ("NO_PROXY", "no_proxy"):
        current = os.getenv(env_name, "")
        items = [item.strip() for item in current.split(",") if item.strip()]
        for host in KIS_PROXY_BYPASS_HOSTS:
            if host not in items:
                items.append(host)
        os.environ[env_name] = ",".join(items)


@dataclass(frozen=True)
class Settings:
    app_key: str
    app_secret: str
    hts_id: str
    rest_url: str
    ws_url: str

    def require_kis_credentials(self) -> None:
        missing = []
        if not self.app_key:
            missing.append("KIS_APP_KEY")
        if not self.app_secret:
            missing.append("KIS_APP_SECRET")
        if missing:
            raise ValueError(f".env에 다음 값을 입력해야 합니다: {', '.join(missing)}")


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


def load_settings() -> Settings:
    _apply_proxy_bypass()
    return Settings(
        app_key=os.getenv("KIS_APP_KEY", "").strip(),
        app_secret=os.getenv("KIS_APP_SECRET", "").strip(),
        hts_id=os.getenv("KIS_HTS_ID", "").strip(),
        rest_url=os.getenv("KIS_REST_URL", "https://openapi.koreainvestment.com:9443").strip(),
        ws_url=os.getenv("KIS_WS_URL", "ws://ops.koreainvestment.com:21000").strip(),
    )


def load_service_settings(service_name: str) -> ServiceSettings:
    return ServiceSettings(
        service_name=service_name,
        app_env=os.getenv("APP_ENV", "development").strip() or "development",
        host=os.getenv("APP_HOST", "0.0.0.0").strip() or "0.0.0.0",
        port=int(os.getenv("APP_PORT", "8000")),
        bootstrap_servers=os.getenv("BOOTSTRAP_SERVERS", "redpanda:9092").strip() or "redpanda:9092",
        clickhouse_url=os.getenv("CLICKHOUSE_URL", "http://clickhouse:8123").strip() or "http://clickhouse:8123",
        symbol=os.getenv("KIS_SYMBOL", "005930").strip() or "005930",
        market=os.getenv("KIS_MARKET", "krx").strip() or "krx",
        log_level=os.getenv("LOG_LEVEL", "INFO").strip() or "INFO",
        poll_interval_seconds=max(1, int(os.getenv("POLL_INTERVAL_SECONDS", "30"))),
    )


settings = load_settings()
