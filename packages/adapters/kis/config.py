from __future__ import annotations

import os
from dataclasses import dataclass

from packages.shared.config import ROOT_DIR


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
    if not _bool_env("KIS_BYPASS_PROXY", False):
        return

    for env_name in ("NO_PROXY", "no_proxy"):
        current = os.getenv(env_name, "")
        items = [item.strip() for item in current.split(",") if item.strip()]
        for host in KIS_PROXY_BYPASS_HOSTS:
            if host not in items:
                items.append(host)
        os.environ[env_name] = ",".join(items)


@dataclass(frozen=True)
class KISSettings:
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


def load_kis_settings() -> KISSettings:
    _ = ROOT_DIR
    _apply_proxy_bypass()
    return KISSettings(
        app_key=os.getenv("KIS_APP_KEY", "").strip(),
        app_secret=os.getenv("KIS_APP_SECRET", "").strip(),
        hts_id=os.getenv("KIS_HTS_ID", "").strip(),
        rest_url=os.getenv("KIS_REST_URL", "https://openapi.koreainvestment.com:9443").strip(),
        ws_url=os.getenv("KIS_WS_URL", "ws://ops.koreainvestment.com:21000").strip(),
    )


Settings = KISSettings
load_settings = load_kis_settings
settings = load_kis_settings()


__all__ = [
    "KISSettings",
    "KIS_PROXY_BYPASS_HOSTS",
    "ROOT_DIR",
    "Settings",
    "load_kis_settings",
    "load_settings",
    "settings",
]
