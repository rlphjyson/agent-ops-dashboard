import json

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.db import get_engine
from app.models import RunEvent
from app.security import decode_access_token
from app.services.agent_runner import PersistedEvent
from app.services.event_bus import EventBus, get_event_bus

router = APIRouter()


def _serialize(event: PersistedEvent) -> dict:
    return {
        "id": event.id,
        "run_id": event.run_id,
        "kind": event.kind,
        "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }


def _from_row(row: RunEvent) -> PersistedEvent:
    assert row.id is not None
    return PersistedEvent(
        id=row.id,
        run_id=row.run_id,
        kind=row.kind,
        payload=json.loads(row.payload_json),
        created_at=row.created_at,
    )


@router.websocket("/ws/runs")
async def ws_runs(
    websocket: WebSocket,
    run_id: str | None = Query(default=None),
    token: str | None = Query(default=None),
    bus: EventBus = Depends(get_event_bus),
    engine: Engine = Depends(get_engine),
) -> None:
    # A browser's native WebSocket API can't set an Authorization header, so the token travels
    # as a query param instead -- same reason prreview-ai's frontend can't do this for its SSE
    # stream either (that one rides on a plain fetch() instead, which *can* set headers).
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    # Subscribe BEFORE any DB backfill query, so events published while backfill is running land
    # in the queue instead of being missed -- then dedupe by id against whatever backfill already
    # sent (RunEvent.id is a single global autoincrement, so a plain "highest id sent so far"
    # watermark is a valid dedupe key across every run's events, not just one run's).
    queue = bus.subscribe(run_id)
    last_sent_id = 0
    try:
        # Full-history backfill only makes sense for one run's detail view. The fleet view
        # (run_id=None) already has GET /runs for its initial state; replaying every event ever
        # recorded across every run on every fleet-page connection would be wasteful and
        # unbounded, so it only gets the live tail from here on.
        if run_id is not None:
            with Session(engine) as session:
                rows = session.exec(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id)
                    .order_by(RunEvent.id)  # type: ignore[arg-type]
                ).all()
            for row in rows:
                event = _from_row(row)
                await websocket.send_json(_serialize(event))
                last_sent_id = event.id

        while True:
            event = await queue.get()
            if event.id <= last_sent_id:
                continue
            await websocket.send_json(_serialize(event))
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)
