from fastapi.testclient import TestClient

from pos_service.auth import SESSION_COOKIE
from pos_service.models import POSUser


def test_login_success_sets_cookie(client: TestClient, cashier: POSUser) -> None:
    r = client.post(
        "/api/auth/login",
        json={"username": "mike", "password": "supersecret"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "mike"
    assert body["display_name"] == "Mike Hightower"
    assert body["must_change_password"] is False
    assert SESSION_COOKIE in r.cookies


def test_login_wrong_password(client: TestClient, cashier: POSUser) -> None:
    r = client.post(
        "/api/auth/login",
        json={"username": "mike", "password": "wrong"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "invalid_credentials"


def test_login_unknown_user(client: TestClient) -> None:
    r = client.post(
        "/api/auth/login",
        json={"username": "nobody", "password": "x"},
    )
    assert r.status_code == 401


def test_me_requires_session(client: TestClient) -> None:
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "not_authenticated"


def test_me_after_login(client: TestClient, cashier: POSUser) -> None:
    client.post(
        "/api/auth/login",
        json={"username": "mike", "password": "supersecret"},
    )
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "mike"


def test_logout_clears_session(client: TestClient, cashier: POSUser) -> None:
    client.post(
        "/api/auth/login",
        json={"username": "mike", "password": "supersecret"},
    )
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    after = client.get("/api/auth/me")
    assert after.status_code == 401


def test_seeded_admin_must_change_password_on_first_login(
    client: TestClient, admin: POSUser
) -> None:
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    assert r.status_code == 200
    assert r.json()["must_change_password"] is True


def test_change_password_clears_flag(client: TestClient, admin: POSUser) -> None:
    client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "admin", "new_password": "new-strong-pass"},
    )
    assert r.status_code == 200
    assert r.json()["must_change_password"] is False

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["must_change_password"] is False


def test_change_password_rejects_wrong_current(client: TestClient, admin: POSUser) -> None:
    client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong", "new_password": "new-strong-pass"},
    )
    assert r.status_code == 401


def test_change_password_rejects_same_password(client: TestClient, cashier: POSUser) -> None:
    client.post("/api/auth/login", json={"username": "mike", "password": "supersecret"})
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "supersecret", "new_password": "supersecret"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "new_password_must_differ"


def test_change_password_rejects_short_password(client: TestClient, admin: POSUser) -> None:
    client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "admin", "new_password": "short"},
    )
    assert r.status_code == 422


