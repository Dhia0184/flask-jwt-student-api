import os
import tempfile
import time

import pytest

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-123"

import api  # noqa: E402
from models import ROLE_ADMIN, User, db  # noqa: E402


@pytest.fixture()
def client():
    with api.app.app_context():
        db.drop_all()
        db.create_all()
        admin = User(username="admin", role=ROLE_ADMIN)
        admin.set_password("adminpass1")
        db.session.add(admin)
        db.session.commit()
    return api.app.test_client()


def login(client, username, password):
    r = client.post("/auth/login", json={"username": username, "password": password})
    return r


def headers(client, username="admin", password="adminpass1"):
    token = login(client, username, password).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def make_student(client, h, **over):
    body = {"FN": "Aya", "LN": "Ben", "DMjr": True, "Level": 2, **over}
    return client.post("/students", json=body, headers=h)


def report_body(id_s, **over):
    return {"ID_S": id_s, "Title": "T", "Type": "x", "K1": "a", "K2": "b", "K3": "c",
            "Release_Date": "2026-01-01", **over}


def test_login_ok_and_bad(client):
    r = login(client, "admin", "adminpass1")
    assert r.status_code == 200 and {"access_token", "refresh_token"} <= set(r.get_json())
    assert login(client, "admin", "wrong").status_code == 401
    assert login(client, "nobody", "whatever1").status_code == 401


def test_no_token_and_garbage_token(client):
    assert client.get("/students").status_code == 401
    r = client.get("/students", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401 and r.headers["WWW-Authenticate"] == "Bearer"


def test_refresh_token_cannot_be_used_as_access(client):
    refresh = login(client, "admin", "adminpass1").get_json()["refresh_token"]
    r = client.get("/students", headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 401


def test_expired_access_token(client, monkeypatch):
    import auth
    monkeypatch.setattr(auth, "ACCESS_TOKEN_TTL", -10)
    h = headers(client)
    r = client.get("/students", headers=h)
    assert r.status_code == 401 and "expired" in r.get_json()["error"]


def test_refresh_flow(client):
    refresh = login(client, "admin", "adminpass1").get_json()["refresh_token"]
    r = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.get_json()['access_token']}"}
    assert client.get("/auth/me", headers=h).get_json()["username"] == "admin"
    assert client.post("/auth/refresh", json={"refresh_token": "nope"}).status_code == 401


def test_roundtrip_get_then_put_works(client):
    h = headers(client)
    s = make_student(client, h).get_json()
    assert "ID_S" in s
    s["Level"] = 3
    r = client.put(f"/students/{s['ID_S']}", json=s, headers=h)
    assert r.status_code == 200 and r.get_json()["Level"] == 3


def test_student_validation_on_create(client):
    h = headers(client)
    assert make_student(client, h, FN=123).status_code == 400
    assert make_student(client, h, FN="  ").status_code == 400
    assert make_student(client, h, Level=9).status_code == 400
    assert make_student(client, h, DMjr=1).status_code == 400


def test_student_role_permissions(client):
    ah = headers(client)
    s1 = make_student(client, ah).get_json()["ID_S"]
    s2 = make_student(client, ah, FN="Omar").get_json()["ID_S"]
    r = client.post("/auth/register", headers=ah,
                    json={"username": "aya", "password": "ayapass12", "ID_S": s1})
    assert r.status_code == 201
    sh = headers(client, "aya", "ayapass12")

    assert client.get("/students", headers=sh).status_code == 403
    assert client.get(f"/students/{s1}", headers=sh).status_code == 200
    assert client.get(f"/students/{s2}", headers=sh).status_code == 403
    assert make_student(client, sh).status_code == 403
    assert client.delete(f"/students/{s1}", headers=sh).status_code == 403
    assert client.post("/auth/register", headers=sh,
                       json={"username": "x" * 5, "password": "12345678"}).status_code == 403

    # own reports ok, someone else's not
    assert client.post("/reports", json=report_body(s1), headers=sh).status_code == 201
    assert client.post("/reports", json=report_body(s2), headers=sh).status_code == 403


def test_report_rules(client):
    h = headers(client)
    s = make_student(client, h).get_json()["ID_S"]
    r1 = client.post("/reports", json=report_body(s), headers=h)
    assert r1.status_code == 201 and "ID_R" in r1.get_json()
    assert client.post("/reports", json=report_body(s), headers=h).status_code == 201
    assert client.post("/reports", json=report_body(s), headers=h).status_code == 400  # max 2
    assert client.post("/reports", json=report_body(s, Release_Date="nope"), headers=h).status_code == 400
    assert client.post("/reports", json=report_body(999), headers=h).status_code == 404
    # reports GET stays public
    assert client.get("/reports").status_code == 200
    assert client.get(f"/reports/{r1.get_json()['ID_R']}").status_code == 200


def test_pagination_and_cascade(client):
    h = headers(client)
    for i in range(3):
        make_student(client, h, FN=f"S{i}")
    r = client.get("/students?limit=2&page=2", headers=h)
    assert len(r.get_json()) == 1 and r.headers["X-Total-Count"] == "3"
    sid = client.get("/students", headers=h).get_json()[0]["ID_S"]
    client.post("/reports", json=report_body(sid), headers=h)
    assert client.delete(f"/students/{sid}", headers=h).status_code == 200
    assert client.get("/reports").get_json() == []


def test_duplicate_username_and_weak_password(client):
    h = headers(client)
    assert client.post("/auth/register", headers=h,
                       json={"username": "admin", "password": "longenough1"}).status_code == 409
    assert client.post("/auth/register", headers=h,
                       json={"username": "newuser", "password": "short"}).status_code == 400
