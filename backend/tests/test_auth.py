from fastapi.testclient import TestClient


def test_signup_creates_user_and_returns_token(client: TestClient) -> None:
    response = client.post("/auth/signup", json={"email": "a@example.com", "password": "password123"})
    assert response.status_code == 201
    assert "access_token" in response.json()


def test_signup_duplicate_email_rejected(client: TestClient) -> None:
    client.post("/auth/signup", json={"email": "a@example.com", "password": "password123"})
    response = client.post("/auth/signup", json={"email": "a@example.com", "password": "password123"})
    assert response.status_code == 409


def test_login_with_correct_password_succeeds(client: TestClient) -> None:
    client.post("/auth/signup", json={"email": "a@example.com", "password": "password123"})
    response = client.post("/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_with_wrong_password_rejected(client: TestClient) -> None:
    client.post("/auth/signup", json={"email": "a@example.com", "password": "password123"})
    response = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-password"})
    assert response.status_code == 401
