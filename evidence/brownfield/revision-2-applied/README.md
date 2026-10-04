# URL Shortener

FastAPI + SQLite URL shortener with optional link expiry.

## Setup

    pip install fastapi uvicorn httpx pytest

## Configuration

- `SHORTENER_DB`: path to the SQLite file (default `shortener.db`). Existing
  databases are migrated automatically at startup (adds a nullable
  `expires_at` column; links and click counts are kept and stay non-expiring).

## Run

    SHORTENER_DB=/path/to/shortener.db uvicorn app.main:create_app --factory

## API

- `POST /links` body `{"url": "https://...", "ttl_seconds": 60}`; `ttl_seconds`
  is optional (omitted = never expires) and must be a strict integer 1..86400.
  Returns 201 `{code, short_url, url}`; invalid input returns 422.
- `GET /r/{code}` returns 302, or 404 if unknown or expired
  (`now >= expires_at`). Expired links do not count clicks.
- `GET /links/{code}/stats` returns `{code, url, clicks, expires_at}`
  (`expires_at` is a UTC Unix timestamp or null); works for expired links.

## Tests

    pytest
