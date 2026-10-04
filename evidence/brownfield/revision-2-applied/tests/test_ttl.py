import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

URL = "https://example.com/x"


class FakeClock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return FakeClock(1000.0)


@pytest.fixture
def tc(db_path, clock):
    return TestClient(create_app(db_path, clock=clock))


def mk(c, **extra):
    return c.post("/links", json={"url": URL, **extra})


@pytest.mark.parametrize(
    "ttl", [True, False, "10", 10.0, 5.5, 0, -1, 86401, None, [1], {}]
)
def test_invalid_ttl(tc, ttl):
    assert mk(tc, ttl_seconds=ttl).status_code == 422


@pytest.mark.parametrize("ttl", [1, 86400])
def test_valid_ttl(tc, ttl):
    r = mk(tc, ttl_seconds=ttl)
    assert r.status_code == 201
    s = tc.get(f"/links/{r.json()['code']}/stats").json()
    assert s["expires_at"] == 1000.0 + ttl


def test_malformed_body_422(tc):
    assert tc.post("/links", content=b"{bad", headers={"content-type": "application/json"}).status_code == 422
    assert tc.post("/links", json=[1, 2]).status_code == 422


def test_omitted_ttl_never_expires(tc, clock):
    code = mk(tc).json()["code"]
    clock.t = 10**12
    assert tc.get(f"/r/{code}", follow_redirects=False).status_code == 302
    assert tc.get(f"/links/{code}/stats").json()["expires_at"] is None


def test_exact_boundary(tc, clock):
    code = mk(tc, ttl_seconds=10).json()["code"]
    clock.t = 1009.0
    assert tc.get(f"/r/{code}", follow_redirects=False).status_code == 302
    clock.t = 1010.0
    assert tc.get(f"/r/{code}", follow_redirects=False).status_code == 404
    clock.t = 1011.0
    assert tc.get(f"/r/{code}", follow_redirects=False).status_code == 404


def test_fractional_boundary(tc, clock):
    clock.t = 1000.25
    code = mk(tc, ttl_seconds=1).json()["code"]
    assert tc.get(f"/links/{code}/stats").json()["expires_at"] == 1001.25
    clock.t = 1001.2499
    assert tc.get(f"/r/{code}", follow_redirects=False).status_code == 302
    clock.t = 1001.25
    assert tc.get(f"/r/{code}", follow_redirects=False).status_code == 404


def test_expired_clicks_not_counted_and_stats_available(tc, clock):
    code = mk(tc, ttl_seconds=5).json()["code"]
    for _ in range(2):
        assert tc.get(f"/r/{code}", follow_redirects=False).status_code == 302
    clock.t = 1005.0
    for _ in range(3):
        assert tc.get(f"/r/{code}", follow_redirects=False).status_code == 404
    r = tc.get(f"/links/{code}/stats")
    assert r.status_code == 200
    assert r.json() == {"code": code, "url": URL, "clicks": 2, "expires_at": 1005.0}


def test_legacy_db_migration(db_path, clock):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE links (code TEXT PRIMARY KEY, url TEXT NOT NULL, "
        "clicks INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO links VALUES ('OLDCODE', 'https://old.example.com', 7)")
    conn.commit()
    conn.close()

    c = TestClient(create_app(db_path, clock=clock))
    assert c.get("/links/OLDCODE/stats").json() == {
        "code": "OLDCODE",
        "url": "https://old.example.com",
        "clicks": 7,
        "expires_at": None,
    }
    clock.t = 10**12
    assert c.get("/r/OLDCODE", follow_redirects=False).status_code == 302
    assert c.get("/links/OLDCODE/stats").json()["clicks"] == 8

    # idempotent second startup
    c2 = TestClient(create_app(db_path, clock=clock))
    assert c2.get("/links/OLDCODE/stats").json()["clicks"] == 8
    assert c2.post("/links", json={"url": URL, "ttl_seconds": 3}).status_code == 201
