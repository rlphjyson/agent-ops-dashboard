import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.db import get_engine, get_session
from app.deps import get_current_user
from app.models import Run, RunEvent, User
from app.schemas import RunCreateRequest, RunEventResponse, RunResponse
from app.services.agent_engines.base import AgentEngine
from app.services.agent_runner import execute_run, get_agent_engine
from app.services.event_bus import EventBus, get_event_bus

router = APIRouter(prefix="/runs", tags=["runs"])


def _to_run_response(run: Run) -> RunResponse:
    return RunResponse(
        id=run.id,
        prompt=run.prompt,
        status=run.status,
        result_text=run.result_text,
        error_message=run.error_message,
        cost_usd=run.cost_usd,
        num_turns=run.num_turns,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _to_event_response(event: RunEvent) -> RunEventResponse:
    assert event.id is not None
    return RunEventResponse(
        id=event.id,
        run_id=event.run_id,
        kind=event.kind,
        payload=json.loads(event.payload_json),
        created_at=event.created_at,
    )


def _get_owned_run(run_id: str, session: Session, user: User) -> Run:
    run = session.get(Run, run_id)
    if run is None or run.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.post("", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
def create_run(
    payload: RunCreateRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    engine: Engine = Depends(get_engine),
    agent_engine: AgentEngine = Depends(get_agent_engine),
    bus: EventBus = Depends(get_event_bus),
    user: User = Depends(get_current_user),
) -> RunResponse:
    run = Run(owner_id=user.id, prompt=payload.prompt)
    session.add(run)
    session.commit()
    session.refresh(run)

    background_tasks.add_task(
        execute_run,
        run.id,
        payload.prompt,
        engine,
        agent_engine,
        lambda event: bus.publish(run.id, event),
    )
    return _to_run_response(run)


@router.get("", response_model=list[RunResponse])
def list_runs(
    session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> list[RunResponse]:
    runs = session.exec(
        select(Run).where(Run.owner_id == user.id).order_by(Run.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_to_run_response(r) for r in runs]


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    run_id: str, session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> RunResponse:
    return _to_run_response(_get_owned_run(run_id, session, user))


@router.get("/{run_id}/events", response_model=list[RunEventResponse])
def get_run_events(
    run_id: str,
    after_id: int = 0,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[RunEventResponse]:
    _get_owned_run(run_id, session, user)
    events = session.exec(
        select(RunEvent)
        .where(RunEvent.run_id == run_id, RunEvent.id > after_id)  # type: ignore[operator]
        .order_by(RunEvent.id)  # type: ignore[arg-type]
    ).all()
    return [_to_event_response(e) for e in events]
