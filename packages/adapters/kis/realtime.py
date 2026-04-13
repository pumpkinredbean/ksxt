"""KIS realtime websocket client for narrow adapter runtime paths."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator

import websockets

from packages.contracts import SubscriptionSpec

from .auth import KISAuthMaterial
from .config import KISSettings
from .mappers import KISRealtimeRow, KISSubscriptionBinding, resolve_realtime_columns, resolve_subscription_binding


@dataclass(frozen=True, slots=True)
class KISRealtimeSubscriptionMessage:
    """Serializable KIS websocket subscribe payload scaffold."""

    binding: KISSubscriptionBinding
    approval_key: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "header": {
                "approval_key": self.approval_key,
                "content-type": "utf-8",
                "custtype": "P",
                "tr_type": "1",
            },
            "body": {
                "input": {
                    "tr_id": self.binding.tr_id,
                    "tr_key": self.binding.tr_key,
                }
            },
        }


class KISRealtimeClient:
    """Realtime websocket client used by the first KIS trade-stream runtime path."""

    def __init__(self, settings: KISSettings):
        self._settings = settings

    @property
    def settings(self) -> KISSettings:
        return self._settings

    def build_subscription_message(
        self,
        subscription: SubscriptionSpec,
        auth: KISAuthMaterial,
    ) -> KISRealtimeSubscriptionMessage:
        binding = resolve_subscription_binding(subscription)
        return KISRealtimeSubscriptionMessage(
            binding=binding,
            approval_key=auth.approval_key or "",
        )

    def connect(self):
        """Open a websocket connection to the KIS realtime endpoint."""

        return websockets.connect(
            f"{self._settings.ws_url}/tryitout",
            ping_interval=30,
            ping_timeout=30,
        )

    async def subscribe_many(
        self,
        subscriptions: list[SubscriptionSpec],
        auth: KISAuthMaterial,
    ) -> list[KISRealtimeSubscriptionMessage]:
        """Build outbound subscription messages for one websocket session."""

        return [self.build_subscription_message(subscription, auth) for subscription in subscriptions]

    async def stream_subscription_rows(
        self,
        subscription: SubscriptionSpec,
        auth: KISAuthMaterial,
    ) -> AsyncIterator[KISRealtimeRow]:
        """Yield parsed realtime rows for a single KIS subscription."""

        async for row in self.stream_subscriptions_rows([subscription], auth):
            yield row

    async def stream_subscriptions_rows(
        self,
        subscriptions: list[SubscriptionSpec],
        auth: KISAuthMaterial,
    ) -> AsyncIterator[KISRealtimeRow]:
        """Yield parsed realtime rows for multiple subscriptions over one websocket."""

        messages = await self.subscribe_many(subscriptions, auth)
        bindings_by_tr_id = {message.binding.tr_id: message.binding for message in messages}

        async with self.connect() as ws:
            for message in messages:
                await ws.send(json.dumps(message.as_dict()))

            async for raw in ws:
                parsed = await self._parse_many_message(raw=raw, bindings_by_tr_id=bindings_by_tr_id, ws=ws)
                if parsed is None:
                    continue
                for row in parsed:
                    yield row

    async def _parse_message(
        self,
        *,
        raw: str | bytes,
        binding: KISSubscriptionBinding,
        ws: Any,
    ) -> list[KISRealtimeRow] | None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")

        if not raw:
            return None

        if raw.startswith("{"):
            body = json.loads(raw)
            tr_id = body.get("header", {}).get("tr_id")
            if tr_id == "PINGPONG":
                await ws.pong(raw)
            return None

        if raw[0] not in {"0", "1"}:
            return None

        encrypted_flag, tr_id, count_text, payload = raw.split("|", 3)
        if encrypted_flag == "1":
            raise RuntimeError(f"Encrypted realtime frames are not supported yet: tr_id={tr_id}")
        if tr_id != binding.tr_id:
            return None

        row_count = int(count_text)
        columns = resolve_realtime_columns(tr_id)
        values = payload.split("^")
        row_width = len(columns)
        expected_value_count = row_count * len(columns)

        if len(values) != expected_value_count:
            if row_count <= 0 or len(values) % row_count != 0:
                raise ValueError(
                    f"Unexpected realtime payload width for {tr_id}: values={len(values)} count={count_text}"
                )
            row_width = len(values) // row_count

        received_at = datetime.now().astimezone()
        rows: list[KISRealtimeRow] = []
        for start in range(0, len(values), row_width):
            row_values = tuple(values[start:start + row_width][: len(columns)])
            fields = dict(zip(columns, row_values, strict=False))
            rows.append(
                KISRealtimeRow(
                    binding=binding,
                    tr_id=tr_id,
                    received_at=received_at,
                    raw_message=raw,
                    values=row_values,
                    fields=fields,
                )
            )
        return rows

    async def _parse_many_message(
        self,
        *,
        raw: str | bytes,
        bindings_by_tr_id: dict[str, KISSubscriptionBinding],
        ws: Any,
    ) -> list[KISRealtimeRow] | None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")

        if not raw:
            return None

        if raw.startswith("{"):
            body = json.loads(raw)
            tr_id = body.get("header", {}).get("tr_id")
            if tr_id == "PINGPONG":
                await ws.pong(raw)
            return None

        if raw[0] not in {"0", "1"}:
            return None

        _, tr_id, _, _ = raw.split("|", 3)
        binding = bindings_by_tr_id.get(tr_id)
        if binding is None:
            return None

        return await self._parse_message(raw=raw, binding=binding, ws=ws)
