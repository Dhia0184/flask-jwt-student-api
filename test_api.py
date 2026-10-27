import os
import tempfile
import jwt
import auth

import pytest

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"

import api  # noqa: E402
from models import ROLE_ADMIN, ROLE_STUDENT, Student, User, db  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    with api.app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(
            username="admin",
            keycloak_sub="admin-sub",
            role=ROLE_ADMIN,
        )

        db.session.add(admin)
        db.session.commit()

    # Simulate verified Keycloak access tokens.
    token_subjects = {
        "admin-token": "admin-sub",
        "student-token": "student-sub",
    }

    def fake_decode_keycloak_access_token(token):
        if token == "expired-token":
            raise jwt.ExpiredSignatureError("Token has expired")

        subject = token_subjects.get(token)

        if subject is None:
            raise jwt.InvalidTokenError("Invalid test token")

        return {"sub": subject}

    monkeypatch.setattr(
        auth,
        "decode_keycloak_access_token",
        fake_decode_keycloak_access_token,
    )

    return api.app.test_client()


def headers(client=None, token="admin-token"):
    return {"Authorization": f"Bearer {token}"}


def make_student(client, h, **over):
    body = {"FN": "Aya", "LN": "Ben", "DMjr": True, "Level": 2, **over}
    return client.post("/students", json=body, headers=h)


def report_body(id_s, **over):
    return {"ID_S": id_s, "Title": "T", "Type": "x", "K1": "a", "K2": "b", "K3": "c",
            "Release_Date": "2026-01-01", **over}


def test_auth_me_resolves_keycloak_subject(client):
    response = client.get(
        "/auth/me",
        headers=headers(client),
    )

    assert response.status_code == 200

    user = response.get_json()
    assert user["username"] == "admin"
    assert user["role"] == "admin"


def test_legacy_auth_endpoints_removed(client):
    for path in ("/auth/login", "/auth/refresh", "/auth/register"):
        response = client.post(path, json={})
        assert response.status_code == 404


def test_no_token_and_garbage_token(client):
    assert client.get("/students").status_code == 401

    response = client.get(
        "/students",
        headers={"Authorization": "Bearer abc.def.ghi"},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_expired_access_token(client):
    response = client.get(
        "/students",
        headers=headers(client, "expired-token"),
    )

    assert response.status_code == 401
    assert "expired" in response.get_json()["error"].lower()

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
    admin_headers = headers(client)

    # Create two student records as the admin.
    student1 = make_student(client, admin_headers).get_json()
    student2 = make_student(
        client,
        admin_headers,
        FN="Omar",
    ).get_json()

    s1 = student1["ID_S"]
    s2 = student2["ID_S"]

    # Create a local user linked to student1 and the test Keycloak subject.
    with api.app.app_context():
        student_user = User(
            username="aya",
            role=ROLE_STUDENT,
            ID_S=s1,
            keycloak_sub="student-sub",
        )

        db.session.add(student_user)
        db.session.commit()

    student_headers = headers(client, "student-token")

    # A student cannot list all students or create/delete student records.
    assert client.get(
        "/students",
        headers=student_headers,
    ).status_code == 403

    assert make_student(client, student_headers).status_code == 403

    assert client.delete(
        f"/students/{s1}",
        headers=student_headers,
    ).status_code == 403

    # A student can access their own record, but not another student's.
    assert client.get(
        f"/students/{s1}",
        headers=student_headers,
    ).status_code == 200

    assert client.get(
        f"/students/{s2}",
        headers=student_headers,
    ).status_code == 403

    # The student can create a report for their own student record only.
    assert client.post(
        "/reports",
        json=report_body(s1),
        headers=student_headers,
    ).status_code == 201

    assert client.post(
        "/reports",
        json=report_body(s2),
        headers=student_headers,
    ).status_code == 403


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

