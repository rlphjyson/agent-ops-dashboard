from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Run
from app.services.agent_engines.base import NormalizedEvent
from tests.fakes import FakeAgentEngine


def test_create_run_requires_auth(client: TestClient) -> None:
    response = client.post("/runs", json={"prompt": "do something"})
    assert response.status_code == 401


def test_create_run_returns_202_immediately_with_the_created_run(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post("/runs", json={"prompt": "do something"}, headers=auth_headers)
    assert response.status_code == 202
    body = response.json()
    assert body["prompt"] == "do something"
    assert body["id"]
    # The response itself reflects the run's state at creation time, before the background task
    # is scheduled -- this is what create_run's own returned RunResponse always is, regardless of
    # how the background task later resolves.
    assert body["status"] == "queued"


def test_create_run_eventually_runs_the_fake_engine_to_completion(
    client: TestClient, auth_headers: dict[str, str], fake_agent_engine: FakeAgentEngine
) -> None:
    fake_agent_engine.events = [
        NormalizedEvent(
            kind="result",
            payload={"is_error": False, "result_text": "all done", "cost_usd": 0.01, "num_turns": 1},
        )
    ]

    create_response = client.post("/runs", json={"prompt": "hi"}, headers=auth_headers)
    run_id = create_response.json()["id"]

    get_response = client.get(f"/runs/{run_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "completed"
    assert get_response.json()["result_text"] == "all done"


def test_list_runs_only_returns_the_caller_owned_runs(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post("/runs", json={"prompt": "first"}, headers=auth_headers)
    client.post("/runs", json={"prompt": "second"}, headers=auth_headers)

    response = client.get("/runs", headers=auth_headers)
    assert response.status_code == 200
    prompts = {r["prompt"] for r in response.json()}
    assert prompts == {"first", "second"}


def test_get_run_404s_for_unknown_id(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/runs/does-not-exist", headers=auth_headers)
    assert response.status_code == 404


def test_get_run_events_returns_events_in_order(
    client: TestClient, auth_headers: dict[str, str], fake_agent_engine: FakeAgentEngine
) -> None:
    fake_agent_engine.events = [
        NormalizedEvent(kind="assistant_text", payload={"text": "thinking..."}),
        NormalizedEvent(
            kind="result",
            payload={"is_error": False, "result_text": "done", "cost_usd": 0.0, "num_turns": 1},
        ),
    ]

    create_response = client.post("/runs", json={"prompt": "hi"}, headers=auth_headers)
    run_id = create_response.json()["id"]

    response = client.get(f"/runs/{run_id}/events", headers=auth_headers)
    assert response.status_code == 200
    kinds = [e["kind"] for e in response.json()]
    assert kinds == ["assistant_text", "result"]


def test_get_run_events_after_id_filters_earlier_events(
    client: TestClient, auth_headers: dict[str, str], fake_agent_engine: FakeAgentEngine
) -> None:
    fake_agent_engine.events = [
        NormalizedEvent(kind="assistant_text", payload={"text": "first"}),
        NormalizedEvent(kind="assistant_text", payload={"text": "second"}),
    ]

    create_response = client.post("/runs", json={"prompt": "hi"}, headers=auth_headers)
    run_id = create_response.json()["id"]

    all_events = client.get(f"/runs/{run_id}/events", headers=auth_headers).json()
    first_id = all_events[0]["id"]

    response = client.get(f"/runs/{run_id}/events?after_id={first_id}", headers=auth_headers)
    assert [e["payload"]["text"] for e in response.json()] == ["second"]


def test_run_events_404s_for_a_run_owned_by_someone_else(client: TestClient) -> None:
    owner_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/auth/signup", json={"email": "owner@example.com", "password": "password123"}
        ).json()["access_token"]
    }
    other_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/auth/signup", json={"email": "other@example.com", "password": "password123"}
        ).json()["access_token"]
    }

    run_id = client.post("/runs", json={"prompt": "secret"}, headers=owner_headers).json()["id"]

    response = client.get(f"/runs/{run_id}", headers=other_headers)
    assert response.status_code == 404

    response = client.get(f"/runs/{run_id}/events", headers=other_headers)
    assert response.status_code == 404


def test_delete_run_removes_it_and_its_events(
    client: TestClient, auth_headers: dict[str, str], fake_agent_engine: FakeAgentEngine
) -> None:
    fake_agent_engine.events = [
        NormalizedEvent(kind="assistant_text", payload={"text": "hi"}),
    ]
    run_id = client.post("/runs", json={"prompt": "to delete"}, headers=auth_headers).json()["id"]

    response = client.delete(f"/runs/{run_id}", headers=auth_headers)
    assert response.status_code == 204

    assert client.get(f"/runs/{run_id}", headers=auth_headers).status_code == 404
    assert client.get(f"/runs/{run_id}/events", headers=auth_headers).status_code == 404
    assert run_id not in [r["id"] for r in client.get("/runs", headers=auth_headers).json()]


def test_delete_run_requires_auth(client: TestClient) -> None:
    response = client.delete("/runs/some-id")
    assert response.status_code == 401


def test_delete_run_404s_for_a_run_owned_by_someone_else(client: TestClient) -> None:
    owner_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/auth/signup", json={"email": "owner2@example.com", "password": "password123"}
        ).json()["access_token"]
    }
    other_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/auth/signup", json={"email": "other2@example.com", "password": "password123"}
        ).json()["access_token"]
    }

    run_id = client.post("/runs", json={"prompt": "secret"}, headers=owner_headers).json()["id"]

    response = client.delete(f"/runs/{run_id}", headers=other_headers)
    assert response.status_code == 404
    # Never actually deleted -- the owner can still see it.
    assert client.get(f"/runs/{run_id}", headers=owner_headers).status_code == 200


def test_delete_run_404s_for_an_unknown_id(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.delete("/runs/does-not-exist", headers=auth_headers)
    assert response.status_code == 404


def test_send_message_continues_a_completed_run_with_its_session_id(
    client: TestClient, auth_headers: dict[str, str], fake_agent_engine: FakeAgentEngine
) -> None:
    fake_agent_engine.events = [
        NormalizedEvent(
            kind="result",
            payload={
                "is_error": False,
                "result_text": "first turn done",
                "cost_usd": 0.01,
                "num_turns": 1,
                "session_id": "sess-1",
            },
        )
    ]
    run_id = client.post("/runs", json={"prompt": "first"}, headers=auth_headers).json()["id"]
    assert client.get(f"/runs/{run_id}", headers=auth_headers).json()["status"] == "completed"

    response = client.post(
        f"/runs/{run_id}/messages", json={"prompt": "follow up"}, headers=auth_headers
    )
    assert response.status_code == 202

    assert fake_agent_engine.received_prompt == "follow up"
    assert fake_agent_engine.received_resume_session_id == "sess-1"

    kinds = [e["kind"] for e in client.get(f"/runs/{run_id}/events", headers=auth_headers).json()]
    assert kinds.count("user_text") == 1
    assert kinds[-1] == "result"


def test_send_message_requires_auth(client: TestClient) -> None:
    response = client.post("/runs/some-id/messages", json={"prompt": "hi"})
    assert response.status_code == 401


def test_send_message_404s_for_a_run_owned_by_someone_else(client: TestClient) -> None:
    owner_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/auth/signup", json={"email": "owner3@example.com", "password": "password123"}
        ).json()["access_token"]
    }
    other_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/auth/signup", json={"email": "other3@example.com", "password": "password123"}
        ).json()["access_token"]
    }
    run_id = client.post("/runs", json={"prompt": "secret"}, headers=owner_headers).json()["id"]

    response = client.post(f"/runs/{run_id}/messages", json={"prompt": "hi"}, headers=other_headers)
    assert response.status_code == 404


def test_send_message_409s_when_the_run_is_still_in_progress(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    run_id = client.post("/runs", json={"prompt": "first"}, headers=auth_headers).json()["id"]
    run = session.get(Run, run_id)
    assert run is not None
    run.status = "running"
    session.add(run)
    session.commit()

    response = client.post(
        f"/runs/{run_id}/messages", json={"prompt": "follow up"}, headers=auth_headers
    )
    assert response.status_code == 409


def test_send_message_400s_without_a_resumable_session(
    client: TestClient, auth_headers: dict[str, str], fake_agent_engine: FakeAgentEngine
) -> None:
    fake_agent_engine.events = [
        NormalizedEvent(
            kind="result",
            payload={"is_error": False, "result_text": "done", "cost_usd": 0.0, "num_turns": 1},
        )
    ]
    run_id = client.post("/runs", json={"prompt": "first"}, headers=auth_headers).json()["id"]

    response = client.post(
        f"/runs/{run_id}/messages", json={"prompt": "follow up"}, headers=auth_headers
    )
    assert response.status_code == 400


def test_cancel_run_marks_it_cancelled_via_fallback_when_the_task_already_finished(
    client: TestClient, auth_headers: dict[str, str], fake_agent_engine: FakeAgentEngine
) -> None:
    # A fake engine that yields nothing never produces a terminal "result"/"error" event, so the
    # run is left showing "running" even though its background task has, in fact, already
    # finished -- exactly the "no live task registered" condition cancel_run's fallback exists
    # for (also the real-world shape of a server restart leaving a run stuck "running").
    fake_agent_engine.events = []
    run_id = client.post("/runs", json={"prompt": "stuck"}, headers=auth_headers).json()["id"]
    assert client.get(f"/runs/{run_id}", headers=auth_headers).json()["status"] == "running"

    response = client.post(f"/runs/{run_id}/cancel", headers=auth_headers)
    assert response.status_code == 202
    assert response.json()["status"] == "cancelled"
    assert client.get(f"/runs/{run_id}", headers=auth_headers).json()["status"] == "cancelled"


def test_cancel_run_requires_auth(client: TestClient) -> None:
    response = client.post("/runs/some-id/cancel")
    assert response.status_code == 401


def test_cancel_run_404s_for_a_run_owned_by_someone_else(client: TestClient) -> None:
    owner_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/auth/signup", json={"email": "owner4@example.com", "password": "password123"}
        ).json()["access_token"]
    }
    other_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/auth/signup", json={"email": "other4@example.com", "password": "password123"}
        ).json()["access_token"]
    }
    run_id = client.post("/runs", json={"prompt": "secret"}, headers=owner_headers).json()["id"]

    response = client.post(f"/runs/{run_id}/cancel", headers=other_headers)
    assert response.status_code == 404


def test_cancel_run_409s_when_the_run_is_not_in_progress(
    client: TestClient, auth_headers: dict[str, str], fake_agent_engine: FakeAgentEngine
) -> None:
    fake_agent_engine.events = [
        NormalizedEvent(
            kind="result",
            payload={"is_error": False, "result_text": "done", "cost_usd": 0.0, "num_turns": 1},
        )
    ]
    run_id = client.post("/runs", json={"prompt": "first"}, headers=auth_headers).json()["id"]

    response = client.post(f"/runs/{run_id}/cancel", headers=auth_headers)
    assert response.status_code == 409
