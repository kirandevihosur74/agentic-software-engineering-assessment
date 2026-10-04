import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

URL = "https://example.com/a?b=1&c=D"


def make(client, url=URL):
    return client.post("/links", json={"url": url})


def test_create_and_code_format(client):
    r = make(client)
    assert r.status_code == 201
    data = r.json()
    assert re.fullmatch(r"[A-Za-z0-9]{7}", data["code"])
    assert data["short_url"].endswith("/r/" + data["code"])
    assert data["url"] == URL


def test_duplicate_urls_get_new_codes(client):
    a = make(client).json()["code"]
    b = make(client).json()["code"]
    assert a != b


def test_redirect_302(client):
    code = make(client).json()["code"]
    r = client.get(f"/r/{code}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == URL


def test_unknown_404(client):
    assert client.get("/r/nope123", follow_redirects=False).status_code == 404
    assert client.get("/links/nope123/stats").status_code == 404


def test_click_counting_and_stats(client):
    code = make(client).json()["code"]
    assert client.get(f"/links/{code}/stats").json()["clicks"] == 0
    for _ in range(3):
        client.get(f"/r/{code}", follow_redirects=False)
    s = client.get(f"/links/{code}/stats").json()
    assert s == {"code": code, "url": URL, "clicks": 3}


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com/x", "javascript:alert(1)", "http://", "example.com", "", None, 5],
)
def test_invalid_urls(client, url):
    assert make(client, url).status_code == 422


def test_missing_url(client):
    assert client.post("/links", json={}).status_code == 422


def test_collision_retry(db_path):
    seq = iter(["AAAAAAA", "AAAAAAA", "BBBBBBB"])
    c = TestClient(create_app(db_path, code_generator=lambda: next(seq)))
    assert make(c).json()["code"] == "AAAAAAA"
    assert make(c).json()["code"] == "BBBBBBB"


def test_retry_exhaustion(db_path):
    c = TestClient(create_app(db_path, code_generator=lambda: "AAAAAAA"))
    assert make(c).status_code == 201
    assert make(c).status_code == 503
