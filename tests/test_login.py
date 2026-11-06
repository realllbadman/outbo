import pytest

from app import auth

LOGIN = {"username": "test-admin", "password": "test-password"}


@pytest.fixture(autouse=True)
def reset_failed_logins():
    auth._failures.clear()
    yield
    auth._failures.clear()


def test_admin_redirects_to_login_page_and_back(client):
    response = client.get("/admin/motors?status=sold", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login?next=/admin/motors%3Fstatus%3Dsold"

    page = client.get(response.headers["location"]).text
    assert "Admin sign in" in page and 'name="password"' in page

    signed_in = client.post("/admin/login", data={**LOGIN, "next": "/admin/motors?status=sold"}, follow_redirects=False)
    assert signed_in.status_code == 303 and signed_in.headers["location"] == "/admin/motors?status=sold"
    assert "Motors" in client.get("/admin/motors").text  # the session cookie now lets us in


def test_wrong_password_shows_error_and_does_not_sign_in(client):
    response = client.post("/admin/login", data={"username": "test-admin", "password": "nope"})
    assert response.status_code == 400 and "username or password is wrong" in response.text
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_log_out_ends_the_session(client):
    client.post("/admin/login", data=LOGIN)
    assert client.get("/admin", follow_redirects=False).status_code == 200
    assert "signed out" in client.post("/admin/logout").text
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_login_only_redirects_within_admin(client):
    response = client.post("/admin/login", data={**LOGIN, "next": "https://evil.example/"}, follow_redirects=False)
    assert response.headers["location"] == "/admin"
    response = client.post("/admin/login", data={**LOGIN, "next": "//evil.example"}, follow_redirects=False)
    assert response.headers["location"] == "/admin"


def test_too_many_wrong_passwords_locks_sign_in(client, monkeypatch):
    monkeypatch.setattr(auth.time, "sleep", lambda seconds: None)
    auth._failures.clear()
    for _ in range(auth.MAX_FAILURES):
        client.post("/admin/login", data={"username": "test-admin", "password": "nope"})
    locked = client.post("/admin/login", data=LOGIN)
    assert locked.status_code == 429 and "Too many wrong attempts" in locked.text
    auth._failures.clear()


def test_tampered_or_expired_session_is_rejected():
    token = auth.make_session(now=1000)
    assert auth.valid_session(token, now=1001)
    assert not auth.valid_session(token, now=1000 + auth.SESSION_SECONDS + 1)
    assert not auth.valid_session(token.replace("test-admin", "someone"), now=1001)
    assert not auth.valid_session("garbage")


def test_cross_site_login_post_is_refused(client):
    response = client.post("/admin/login", data=LOGIN, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
