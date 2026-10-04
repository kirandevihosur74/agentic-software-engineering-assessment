# URL Shortener

FastAPI + SQLite URL shortener with optional link expiry.

## Setup

Requires Python 3.9+ with `fastapi`, `uvicorn` (to serve), `pytest` and `httpx` (for tests) installed.

## Environment

- `SHORTENER_DB`: path to the SQLite file (default `shortener.db`). Existing databases are migrated automatically on startup (an `expires_at` column is added; existing links never expire and keep their click counts).

## Run

    uvicorn app.main:create_app --factory

## Test

    pytest

## API

- `POST /links` with `{"url": "https://...", "ttl_seconds": 3600}` returns 201 with `code`, `short_url`, `url`.
  - `url` must be http/https.
  - `ttl_seconds` is optional. If present it must be a strict integer from 1 through 604800 (seven days). Booleans, strings, floats, zero, negatives, larger values and explicit `null` return 422. Omit it for a non-expiring link.
- `GET /r/{code}`: 302 redirect and click count increment. Returns **410** once the link has expired (now >= expires_at; clicks are not counted), and **404** for an unknown code.
- `GET /links/{code}/stats`: returns `code`, `url`, `clicks`, `expires_at` (UTC Unix timestamp as a float, `null` if non-expiring). It still works for expired links.

Expiry is lazy: expired rows stay in the database.
