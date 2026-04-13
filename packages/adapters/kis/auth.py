"""KIS auth helpers for the adapter runtime path."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import requests

from .config import KISSettings


@dataclass(frozen=True, slots=True)
class KISAuthMaterial:
    """Runtime auth values needed by the KIS realtime connection."""

    approval_key: str | None = None
    access_token: str | None = None


class KISAuthProvider:
    """Issue runtime auth material needed by the KIS realtime websocket."""

    def __init__(self, settings: KISSettings):
        self._settings = settings

    @property
    def settings(self) -> KISSettings:
        return self._settings

    def is_configured(self) -> bool:
        """Return whether credentials are present for a live call path."""

        return bool(self._settings.app_key and self._settings.app_secret)

    async def issue_realtime_credentials(self) -> KISAuthMaterial:
        """Fetch the realtime approval key required for websocket subscriptions."""

        approval_key = await asyncio.to_thread(self._request_approval_key)
        return KISAuthMaterial(approval_key=approval_key)

    def _request_approval_key(self) -> str:
        self._settings.require_kis_credentials()

        response = requests.post(
            f"{self._settings.rest_url}/oauth2/Approval",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "charset": "UTF-8",
            },
            data=json.dumps(
                {
                    "grant_type": "client_credentials",
                    "appkey": self._settings.app_key,
                    "secretkey": self._settings.app_secret,
                }
            ),
            timeout=15,
        )
        response.raise_for_status()

        body = response.json()
        approval_key = str(body.get("approval_key") or "").strip()
        if not approval_key:
            raise RuntimeError(f"approval_key 발급 실패: {body}")

        return approval_key
