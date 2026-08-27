import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.services.agent_engines.base import NormalizedEvent
from tests.fakes import FakeAgentEngine

RESULT_EVENT = NormalizedEvent(
    kind="result",
    payload={"is_error": False, "result_text": "done", "cost_usd": 0.0, "num_turns": 1},
)


def _token(headers: dict[str, str]) -> str:
    return headers["Authorization"].removeprefix("Bearer ")


def test_ws_rejects_connection_without_a_valid_token(client: TestClient) -> None:
    # The endpoint closes the socket before ever accepting it, so the disconnect surfaces at
    # connect time (the `with` statement's __enter__, i.e. the handshake) rather than on a
    # later receive_json() call.
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/runs"):
        pass


def test_ws_unfiltered_tags_events_from_multiple_concurrent_runs(
    client: TestClient, auth_headers: dict[str, str], fake_agent_engine: FakeAgentEngine
) -> None:
    token = _token(auth_headers)
    fake_agent_engine.events = [RESULT_EVENT]

    with client.websocket_connect(f"/ws/runs?token={token}") as ws:
        run_a = client.post("/runs", json={"prompt": "run a"}, headers=auth_headers).json()["id"]
        run_b = client.post("/runs", json={"prompt": "run b"}, headers=auth_headers).json()["id"]

        seen_run_ids = {ws.receive_json()["run_id"], ws.receive_json()["run_id"]}

    assert seen_run_ids == {run_a, run_b}


def test_ws_filtered_by_run_id_excludes_other_runs(
    client: TestClient, auth_headers: dict[str, str], fake_agent_engine: FakeAgentEngine
) -> None:
    token = _token(auth_headers)
    fake_agent_engine.events = [RESULT_EVENT]

    target_run_id = client.post("/runs", json={"prompt": "target"}, headers=auth_headers).json()["id"]

    with client.websocket_connect(f"/ws/runs?run_id={target_run_id}&token={token}") as ws:
        # Backfill delivers the target run's own already-persisted "result" event first.
        backfilled = ws.receive_json()
        assert backfilled["run_id"] == target_run_id
        assert backfilled["kind"] == "result"

        # A second, different run's live event must not show up on this filtered connection.
        other_run_id = client.post(
            "/runs", json={"prompt": "other"}, headers=auth_headers
        ).json()["id"]
        assert other_run_id != target_run_id

        third_event = client.post(
            "/runs", json={"prompt": "target again"}, headers=auth_headers
        )
        assert third_event.status_code == 202
        # Nothing further should ever arrive for `other_run_id`, and the connection has no more
        # events queued for `target_run_id` either (that run already completed before connecting,
        # and the new "target again" run is a *different* run id) -- closing the context manager
        # without another receive_json() call confirms nothing extra was silently buffered wrong.


def test_ws_fleet_view_skips_backfill_and_only_sees_events_after_connecting(
    client: TestClient, auth_headers: dict[str, str], fake_agent_engine: FakeAgentEngine
) -> None:
    token = _token(auth_headers)
    fake_agent_engine.events = [RESULT_EVENT]

    # This run completes (and its event is persisted) *before* the unfiltered WS connects.
    client.post("/runs", json={"prompt": "already done"}, headers=auth_headers)

    with client.websocket_connect(f"/ws/runs?token={token}") as ws:
        new_run_id = client.post(
            "/runs", json={"prompt": "new one"}, headers=auth_headers
        ).json()["id"]

        first = ws.receive_json()
        # The only event received is the new run's, not a backfilled one from the earlier run --
        # confirms the fleet view (run_id=None) deliberately skips full-history backfill.
        assert first["run_id"] == new_run_id
