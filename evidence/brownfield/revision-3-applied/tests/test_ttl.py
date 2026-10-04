import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

URL = "https://example.com/x"


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock(1000.0)


@pytest.fixture
def c(db_path, clock):
    return TestClient(create_app(db_path, clock=clock))


def post(c, **body):
    body.setdefault("url", URL)
    return c.post("/links", json=body)


def get(c, code):
    return c.get(f"/r/{code}", follow_redirects=False)


@pytest.mark.parametrize("ttl", [1, 86401, 604800])
def test_valid_ttl(c, ttl):
    r = post(c, ttl_seconds=ttl)
    assert r.status_code == 201
    code = r.json()["code"]
    assert c.get(f"/links/{code}/stats").json()["expires_at"] == 1000.0 + ttl


@pytest.mark.parametrize("ttl", [True, False, "5", 5.0, 0, -1, 604801, None, [], {}])
def test_invalid_ttl(c, ttl):
    assert post(c, ttl_seconds=ttl).status_code == 422


def test_invalid_ttl_json_shape(c):
    r = post(c, ttl_seconds=0)
    assert r.status_code == 422
    assert "detail" in r.json()


def test_malformed_and_non_object_body(c):
    r = c.post("/links", content=b"{bad", headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert c.post("/links", json=[1]).status_code == 422
    assert c.post("/links", json=None).status_code == 422


def test_omitted_ttl_never_expires(c, clock):
    code = post(c).json()["code"]
    clock.now = 10**12
    assert get(c, code).status_code == 302
    s = c.get(f"/links/{code}/stats").json()
    assert s["expires_at"] is None
    assert s["clicks"] == 1


def test_exact_boundary(c, clock):
    code = post(c, ttl_seconds=10).json()["code"]
    clock.now = 1009.0
    assert get(c, code).status_code == 302
    clock.now = 1010.0
    assert get(c, code).status_code == 410
    clock.now = 1011.0
    assert get(c, code).status_code == 410


def test_fractional_boundary(db_path):
    clk = FakeClock(1000.25)
    c = TestClient(create_app(db_path, clock=clk))
    code = post(c, ttl_seconds=1).json()["code"]
    assert c.get(f"/links/{code}/stats").json()["expires_at"] == 1001.25
    clk.now = 1001.2499
    assert get(c, code).status_code == 302
    clk.now = 1001.25
    assert get(c, code).status_code == 410


def test_expired_clicks_unchanged_and_stats_available(c, clock):
    code = post(c, ttl_seconds=5).json()["code"]
    assert get(c, code).status_code == 302
    assert get(c, code).status_code == 302
    clock.now = 1005.0
    for _ in range(3):
        assert get(c, code).status_code == 410
    r = c.get(f"/links/{code}/stats")
    assert r.status_code == 200
    assert r.json() == {"code": code, "url": URL, "clicks": 2, "expires_at": 1005.0}


def test_410_vs_404(c, clock):
    code = post(c, ttl_seconds=1).json()["code"]
    clock.now = 2000.0
    assert get(c, code).status_code == 410
    assert get(c, "unknown1").status_code == 404


def test_migration(tmp_path):
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE links (code TEXT PRIMARY KEY, url TEXT NOT NULL, "
        "clicks INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("INSERT INTO links VALUES ('OLDCODE', 'https://old.example/', 7)")
    conn.commit()
    conn.close()

    clk = FakeClock(10**11)
    c = TestClient(create_app(path, clock=clk))
    assert c.get("/links/OLDCODE/stats").json() == {
        "code": "OLDCODE",
        "url": "https://old.example/",
        "clicks": 7,
        "expires_at": None,
    }
    assert get(c, "OLDCODE").status_code == 302
    assert c.get("/links/OLDCODE/stats").json()["clicks"] == 8

    # second init is safe
    c2 = TestClient(create_app(path, clock=clk))
    assert c2.get("/links/OLDCODE/stats").json()["clicks"] == 8
    assert post(c2, ttl_seconds=5).status_code == 201
