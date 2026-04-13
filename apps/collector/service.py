from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from apps.collector.publisher import CollectorPublisher
from apps.collector.runtime import CollectorRuntime
from packages.contracts.topics import DASHBOARD_EVENTS_TOPIC
from packages.infrastructure.kafka import AsyncKafkaJsonBroker
from packages.infrastructure.runtime import InProcessSubscriptionRuntime
from packages.shared.config import load_service_settings
from src.config import settings as kis_settings
@dataclass(frozen=True, slots=True)
class DashboardSubscription:
    symbol: str
    market: str

    @property
    def subscription_key(self) -> str:
        return f"dashboard:{self.market.lower()}:{self.symbol}"


class CollectorDashboardService:
    def __init__(self, settings: Any):
        self._collector_runtime = CollectorRuntime(kis_settings)
        self._broker = AsyncKafkaJsonBroker(settings.bootstrap_servers)
        self._publisher = CollectorPublisher(self._broker)
        self._subscription_runtime = InProcessSubscriptionRuntime[tuple[str, dict[str, Any]]]()

    async def aclose(self) -> None:
        await self._subscription_runtime.aclose()
        await self._broker.aclose()
        await self._collector_runtime.aclose()

    async def stream_dashboard(
        self,
        *,
        symbol: str,
        market: str,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        subscription = DashboardSubscription(symbol=symbol, market=market)
        async for item in self._subscription_runtime.subscribe(subscription, self._open_dashboard_stream):
            yield item

    async def fetch_price_chart(self, *, symbol: str, market: str, interval: int) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._collector_runtime.fetch_price_chart,
            symbol=symbol,
            market=market,
            interval=interval,
        )

    async def _open_dashboard_stream(
        self,
        subscription: DashboardSubscription,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        queue: asyncio.Queue[tuple[str, dict[str, Any]] | BaseException | None] = asyncio.Queue()

        async def pump_broker_events() -> None:
            try:
                async for message in self._broker.subscribe(
                    topic=DASHBOARD_EVENTS_TOPIC,
                    group_id=self._build_dashboard_group_id(subscription),
                ):
                    if message.get("symbol") != subscription.symbol:
                        continue
                    if str(message.get("market", "")).lower() != subscription.market.lower():
                        continue
                    event_name = message.get("event_name")
                    payload = message.get("payload")
                    if isinstance(event_name, str) and isinstance(payload, dict):
                        await queue.put((event_name, payload))
            except Exception as exc:
                await queue.put(exc)
            finally:
                await queue.put(None)

        async def publish_upstream_events() -> None:
            try:
                async for event_name, payload in self._collector_runtime.stream_dashboard(
                    symbol=subscription.symbol,
                    market=subscription.market,
                ):
                    await self._publisher.publish_dashboard_event(
                        symbol=subscription.symbol,
                        market=subscription.market,
                        event_name=event_name,
                        payload=payload,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await queue.put(exc)

        broker_task = asyncio.create_task(pump_broker_events())
        publisher_task = asyncio.create_task(publish_upstream_events())

        try:
            while True:
                item = await queue.get()
                if item is None:
                    return
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            publisher_task.cancel()
            broker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await publisher_task
            with contextlib.suppress(asyncio.CancelledError):
                await broker_task

    def _build_dashboard_group_id(self, subscription: DashboardSubscription) -> str:
        subscription_key = subscription.subscription_key.replace(":", "-")
        return f"collector-dashboard-{subscription_key}-{uuid.uuid4().hex}"


app = FastAPI(title="Collector Service")
service_settings = load_service_settings("collector")
dashboard_service = CollectorDashboardService(service_settings)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "service": service_settings.service_name,
            "symbol": service_settings.symbol,
            "market": service_settings.market,
        }
    )


@app.on_event("shutdown")
async def shutdown_runtime() -> None:
    await dashboard_service.aclose()


@app.get("/stream")
async def stream(
    request: Request,
    symbol: str = Query(..., min_length=1),
    market: str = Query("krx", pattern="^(krx|nxt|total)$"),
) -> StreamingResponse:
    async def event_generator() -> AsyncIterator[str]:
        disconnect_task: asyncio.Task[Any] | None = None
        stream_task: asyncio.Task[Any] | None = None
        queue: asyncio.Queue[tuple[str, dict[str, Any]] | BaseException | None] = asyncio.Queue()

        async def watch_disconnect() -> None:
            while not await request.is_disconnected():
                await asyncio.sleep(0.25)

        async def pump_dashboard_events() -> None:
            try:
                async for event_name, payload in dashboard_service.stream_dashboard(symbol=symbol, market=market):
                    if await request.is_disconnected():
                        return
                    await queue.put((event_name, payload))
            except Exception as exc:
                await queue.put(exc)
            finally:
                await queue.put(None)

        try:
            disconnect_task = asyncio.create_task(watch_disconnect())
            stream_task = asyncio.create_task(pump_dashboard_events())

            while True:
                item = await queue.get()
                if item is None:
                    return
                if isinstance(item, BaseException):
                    raise item
                if await request.is_disconnected():
                    return
                event_name, payload = item
                yield f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except Exception as exc:
            if not await request.is_disconnected():
                error_payload = {"error": str(exc)}
                yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
        finally:
            if stream_task is not None:
                stream_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stream_task
            if disconnect_task is not None:
                disconnect_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await disconnect_task

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/price-chart")
async def price_chart(
    symbol: str = Query(..., min_length=1),
    market: str = Query("krx", pattern="^(krx|nxt|total)$"),
    interval: int = Query(..., ge=10, le=60),
) -> JSONResponse:
    if interval not in {10, 30, 60}:
        return JSONResponse({"error": "unsupported interval"}, status_code=400)

    try:
        payload = await dashboard_service.fetch_price_chart(
            symbol=symbol,
            market=market,
            interval=interval,
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except NotImplementedError as exc:
        return JSONResponse({"error": str(exc)}, status_code=501)

    return JSONResponse(payload)


def main() -> None:
    uvicorn.run(
        "apps.collector.service:app",
        host=service_settings.host,
        port=service_settings.port,
        log_level=service_settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
