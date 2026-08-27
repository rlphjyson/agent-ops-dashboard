import asyncio
from functools import lru_cache

from app.services.agent_runner import PersistedEvent


class EventBus:
    """In-process pub/sub relaying PersistedEvents to WebSocket subscribers -- one queue per
    connection, optionally filtered to a single run_id (None means "everything," for the fleet
    view). Only correct with a single Uvicorn worker process (--workers 1); a real multi-worker
    deployment would need Redis pub/sub or similar instead -- documented production constraint,
    not solved here."""

    def __init__(self) -> None:
        self._subscribers: dict[asyncio.Queue, str | None] = {}

    def subscribe(self, run_id: str | None) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[queue] = run_id
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.pop(queue, None)

    def publish(self, run_id: str, event: PersistedEvent) -> None:
        for queue, filter_run_id in self._subscribers.items():
            if filter_run_id is None or filter_run_id == run_id:
                queue.put_nowait(event)


@lru_cache
def get_event_bus() -> EventBus:
    return EventBus()
