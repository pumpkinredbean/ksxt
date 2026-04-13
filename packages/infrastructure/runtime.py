"""In-process fan-out runtime for single-owner upstream subscriptions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from packages.contracts import SubscriptionSpec


T = TypeVar("T")


@dataclass(slots=True)
class _QueueMessage(Generic[T]):
    kind: str
    payload: T | BaseException | None = None


@dataclass(slots=True)
class _UpstreamState(Generic[T]):
    task: asyncio.Task[None]
    subscribers: set[asyncio.Queue[_QueueMessage[T]]] = field(default_factory=set)


class InProcessSubscriptionRuntime(Generic[T]):
    """Keep one upstream task per active subscription and fan out locally."""

    def __init__(self) -> None:
        self._states: dict[str, _UpstreamState[T]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        subscription: SubscriptionSpec,
        stream_factory: Callable[[SubscriptionSpec], AsyncIterator[T] | Awaitable[AsyncIterator[T]]],
    ) -> AsyncIterator[T]:
        queue: asyncio.Queue[_QueueMessage[T]] = asyncio.Queue()
        key = subscription.subscription_key

        async with self._lock:
            state = self._states.get(key)
            if state is None or state.task.done():
                task = asyncio.create_task(self._run_upstream(subscription, stream_factory))
                state = _UpstreamState(task=task)
                self._states[key] = state
            state.subscribers.add(queue)

        try:
            while True:
                message = await queue.get()
                if message.kind == "item":
                    yield message.payload  # type: ignore[misc]
                    continue
                if message.kind == "error":
                    payload = message.payload
                    if isinstance(payload, BaseException):
                        raise payload
                    raise RuntimeError("subscription runtime upstream failed")
                return
        finally:
            await self._detach(key, queue)

    async def aclose(self) -> None:
        async with self._lock:
            states = list(self._states.values())
            self._states.clear()

        for state in states:
            state.task.cancel()
        for state in states:
            try:
                await state.task
            except asyncio.CancelledError:
                pass

    async def _run_upstream(
        self,
        subscription: SubscriptionSpec,
        stream_factory: Callable[[SubscriptionSpec], AsyncIterator[T] | Awaitable[AsyncIterator[T]]],
    ) -> None:
        try:
            stream = stream_factory(subscription)
            if asyncio.iscoroutine(stream):
                stream = await stream
            async for item in stream:
                await self._broadcast(subscription.subscription_key, _QueueMessage(kind="item", payload=item))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._broadcast(subscription.subscription_key, _QueueMessage(kind="error", payload=exc))
        finally:
            await self._broadcast(subscription.subscription_key, _QueueMessage(kind="done"))

    async def _broadcast(self, key: str, message: _QueueMessage[T]) -> None:
        async with self._lock:
            state = self._states.get(key)
            subscribers = list(state.subscribers) if state is not None else []
        for queue in subscribers:
            await queue.put(message)

    async def _detach(self, key: str, queue: asyncio.Queue[_QueueMessage[T]]) -> None:
        task: asyncio.Task[None] | None = None
        async with self._lock:
            state = self._states.get(key)
            if state is None:
                return
            state.subscribers.discard(queue)
            if not state.subscribers:
                task = state.task
                self._states.pop(key, None)

        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
