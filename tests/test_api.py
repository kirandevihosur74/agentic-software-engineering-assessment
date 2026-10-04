from fastapi.testclient import TestClient
from shortener.app import app

client = TestClient(app)


def test_health_and_explicit_unimplemented_route():
    assert client.get("/health").json()["mode"] == "scaffold"
    assert client.post("/links", json={"url": "https://example.com"}).status_code == 501


def test_disallows_non_http_urls():
    assert client.post("/links", json={"url": "file:///etc/passwd"}).status_code == 422
