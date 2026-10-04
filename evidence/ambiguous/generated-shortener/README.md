# Privacy-friendly URL shortener

FastAPI + SQLite. Each link stores only its code, URL and an aggregate click count. No IPs, user agents, referrers, timestamps or cookies are stored.

## Endpoints

```
curl -X POST localhost:8000/links -H 'content-type: application/json' -d '{"url":"https://example.com"}'
curl -i localhost:8000/r/<code>          # 302 redirect, counts a click
curl localhost:8000/links/<code>/stats   # {"code","url","clicks"} (public)
```

Codes are 7 random case-sensitive alphanumeric characters; every submission gets a new code. Only http/https URLs (max 2048 chars, with a hostname) are accepted. URLs are never fetched. Private-address destinations are allowed (local demo), so this is an open redirect; do not expose it publicly as is. `short_url` is derived from the request base URL (Host header).

## Run

```
SHORTENER_DB=shortener.db uvicorn --factory shortener:create_app
```

(uvicorn must be available in your environment.)

## Test

```
pytest
```
