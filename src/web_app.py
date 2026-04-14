from __future__ import annotations

import asyncio
import contextlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from packages.contracts.topics import DASHBOARD_CONTROL_TOPIC, DASHBOARD_EVENTS_TOPIC
from packages.infrastructure.kafka import AsyncKafkaJsonBroker
from packages.shared.config import load_service_settings

app = FastAPI(title="KIS Program Trade Realtime")
service_settings = load_service_settings("api-web")
dashboard_broker = AsyncKafkaJsonBroker(service_settings.bootstrap_servers)
collector_base_url = os.getenv("COLLECTOR_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
WEB_DIR = Path(__file__).resolve().parent / "web"

app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def _serialize_sse_lines(lines: list[str]) -> str:
    return "".join(f"{line}\n" for line in lines)


def _collector_request(
    method: str,
    path: str,
    **kwargs: Any,
) -> requests.Response:
    with requests.Session() as session:
        session.trust_env = False
        response = session.request(method, f"{collector_base_url}{path}", **kwargs)
        return response


def _resolve_market_scope(*, scope: str | None = None, market: str | None = None) -> str:
    resolved = (scope or market or "total").strip().lower()
    if resolved not in {"krx", "nxt", "total"}:
        raise ValueError(f"unsupported market scope: {scope or market}")
    return resolved


def _build_dashboard_group_id(*, symbol: str, market_scope: str) -> str:
    subscription_key = f"{market_scope.lower()}-{symbol}"
    return f"api-web-dashboard-{subscription_key}-{uuid.uuid4().hex}"


async def _publish_dashboard_control(*, action: str, owner_id: str, symbol: str, market_scope: str) -> None:
    await dashboard_broker.publish(
        topic=DASHBOARD_CONTROL_TOPIC,
        key=owner_id,
        value={
            "action": action,
            "owner_id": owner_id,
            "symbol": symbol,
            "market_scope": market_scope.lower(),
            "market": market_scope.lower(),
            "requested_at": datetime.utcnow().isoformat(),
            "schema_version": "v1",
        },
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.on_event("shutdown")
async def shutdown_runtime() -> None:
    await dashboard_broker.aclose()


@app.get("/api/price-chart")
async def price_chart(
    symbol: str = Query(..., min_length=1),
    scope: str | None = Query(None, pattern="^(krx|nxt|total)$"),
    market: str | None = Query(None, pattern="^(krx|nxt|total)$"),
    interval: int = Query(..., ge=1, le=60),
) -> JSONResponse:
    try:
        market_scope = _resolve_market_scope(scope=scope, market=market)
        response = await asyncio.to_thread(
            _collector_request,
            "GET",
            "/api/price-chart",
            params={"symbol": symbol, "scope": market_scope, "interval": interval},
            timeout=15,
        )
        response.raise_for_status()
        return JSONResponse(response.json())
    except requests.HTTPError as exc:
        response = exc.response
        if response is not None:
            try:
                payload = response.json()
            except ValueError:
                payload = {"error": response.text or str(exc)}
            return JSONResponse(payload, status_code=response.status_code)
        return JSONResponse({"error": str(exc)}, status_code=502)
    except requests.RequestException as exc:
        return JSONResponse({"error": f"collector price-chart relay failed: {exc}"}, status_code=502)


@app.get("/stream")
async def stream(
    request: Request,
    symbol: str = Query(..., min_length=1),
    scope: str | None = Query(None, pattern="^(krx|nxt|total)$"),
    market: str | None = Query(None, pattern="^(krx|nxt|total)$"),
) -> StreamingResponse:
    market_scope = _resolve_market_scope(scope=scope, market=market)

    async def event_generator() -> Any:
        queue: asyncio.Queue[str | BaseException | None] = asyncio.Queue()
        control_owner_id = uuid.uuid4().hex
        consumer_task: asyncio.Task[Any] | None = None
        disconnect_task: asyncio.Task[Any] | None = None

        async def watch_disconnect() -> None:
            while not await request.is_disconnected():
                await asyncio.sleep(0.25)
            await queue.put(None)

        async def pump_dashboard_events() -> None:
            try:
                async with dashboard_broker.open_subscription(
                    topic=DASHBOARD_EVENTS_TOPIC,
                    group_id=_build_dashboard_group_id(symbol=symbol, market_scope=market_scope),
                ) as consumer:
                    await _publish_dashboard_control(
                        action="start",
                        owner_id=control_owner_id,
                        symbol=symbol,
                        market_scope=market_scope,
                    )

                    async for message in consumer:
                        if await request.is_disconnected():
                            return

                        payload = message.value if isinstance(message.value, dict) else None
                        if payload is None:
                            continue
                        if payload.get("symbol") != symbol:
                            continue
                        payload_market_scope = str(payload.get("market_scope") or payload.get("market") or "").lower()
                        if payload_market_scope != market_scope.lower():
                            continue

                        event_name = payload.get("event_name")
                        event_payload = payload.get("payload")
                        if not isinstance(event_name, str) or not isinstance(event_payload, dict):
                            continue

                        await queue.put(
                            _serialize_sse_lines(
                                [
                                    f"event: {event_name}",
                                    f"data: {json.dumps(event_payload, ensure_ascii=False)}",
                                    "",
                                ]
                            )
                        )
            except Exception as exc:
                await queue.put(exc)
            finally:
                with contextlib.suppress(Exception):
                    await _publish_dashboard_control(
                        action="stop",
                        owner_id=control_owner_id,
                        symbol=symbol,
                        market_scope=market_scope,
                    )
                await queue.put(None)

        consumer_task = asyncio.create_task(pump_dashboard_events())
        disconnect_task = asyncio.create_task(watch_disconnect())

        try:
            while True:
                item = await queue.get()
                if item is None:
                    return
                if isinstance(item, BaseException):
                    raise item
                yield item
        except Exception as exc:
            if not await request.is_disconnected():
                error_payload = {"error": str(exc)}
                yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
        finally:
            if consumer_task is not None:
                consumer_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await consumer_task
            if disconnect_task is not None:
                disconnect_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await disconnect_task

    return StreamingResponse(event_generator(), media_type="text/event-stream")
