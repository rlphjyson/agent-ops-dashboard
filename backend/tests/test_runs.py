from fastapi.testclient import TestClient

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
