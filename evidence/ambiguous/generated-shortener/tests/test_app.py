import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

from shortener import app as app_module
from shortener import create_app


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "t.db")


@pytest.fixture
def client(db):
    return TestClient(create_app(db), follow_redirects=False)


def make(client, url="https://example.com/a?b=1"):
    return client.post("/links", json={"url": url})


def test_create(client):
    r = make(client)
    assert r.status_code == 201
    d = r.json()
    assert re.fullmatch(r"[A-Za-z0-9]{7}", d["code"])
    assert d["short_url"] == f"http://testserver/r/{d['code']}"


def test_duplicates_get_new_codes(client):
    assert make(client).json()["code"] != make(client).json()["code"]


@pytest.mark.parametrize(
    "payload",
    [
        {"url": "ftp://example.com"},
        {"url": "http://"},
        {"url": "https://" + "a" * 2050 + ".com"},
        {"url": "https://exa mple.com"},
        {},
        {"url": 5},
    ],
)
def test_invalid(client, payload):
    assert client.post("/links", json=payload).status_code == 422


def test_private_allowed(client):
    assert make(client, "http://localhost:8000/x").status_code == 201
    assert make(client, "http://192.168.1.1/").status_code == 201


def test_redirect_and_clicks(client):
    code = make(client).json()["code"]
    assert client.get(f"/links/{code}/stats").json() == {
        "code": code,
        "url": "https://example.com/a?b=1",
        "clicks": 0,
    }
    for _ in range(3):
        r = client.get(f"/r/{code}")
        assert r.status_code == 302
        assert r.headers["location"] == "https://example.com/a?b=1"
        assert "set-cookie" not in r.headers
    assert client.get(f"/links/{code}/stats").json()["clicks"] == 3


def test_404(client):
    assert client.get("/r/nope123").status_code == 404
    assert client.get("/links/nope123/stats").status_code == 404


def test_schema_minimal(client, db):
    make(client)
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(links)")]
    conn.close()
    assert cols == ["code", "url", "clicks"]


def test_collision_retry(client, monkeypatch):
    first = make(client).json()["code"]
    seq = iter([first, first, "ZZZZZZZ"])
    monkeypatch.setattr(app_module, "generate_code", lambda: next(seq))
    assert make(client).json()["code"] == "ZZZZZZZ"


def test_collision_exhaustion(client, monkeypatch):
    first = make(client).json()["code"]
    monkeypatch.setattr(app_module, "generate_code", lambda: first)
    assert make(client).status_code == 503


def test_isolation(tmp_path):
    a = TestClient(create_app(str(tmp_path / "a.db")), follow_redirects=False)
    b = TestClient(create_app(str(tmp_path / "b.db")), follow_redirects=False)
    code = make(a).json()["code"]
    assert b.get(f"/links/{code}/stats").status_code == 404
