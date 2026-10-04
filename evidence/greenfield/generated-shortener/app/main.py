import os
import sqlite3
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from . import codes as codes_module
from .db import connect, init_db

MAX_RETRIES = 10


def _valid_url(url) -> bool:
    if not isinstance(url, str) or not url or url != url.strip():
        return False
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.hostname)
    except ValueError:
        return False


def create_app(db_path=None, code_generator=None) -> FastAPI:
    path = db_path or os.environ.get("SHORTENER_DB", "shortener.db")
    path = str(path)
    init_db(path)
    app = FastAPI(title="URL Shortener")

    def gen():
        if code_generator is not None:
            return code_generator()
        return codes_module.generate_code()

    @app.post("/links")
    async def create_link(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid JSON"}, status_code=422)
        url = body.get("url") if isinstance(body, dict) else None
        if not _valid_url(url):
            return JSONResponse({"detail": "url must be a valid http/https URL"}, status_code=422)
        conn = connect(path)
        try:
            for _ in range(MAX_RETRIES):
                code = gen()
                try:
                    conn.execute("INSERT INTO links (code, url, clicks) VALUES (?, ?, 0)", (code, url))
                    conn.commit()
                except sqlite3.IntegrityError:
                    conn.rollback()
                    continue
                return JSONResponse(
                    {
                        "code": code,
                        "short_url": str(request.base_url) + "r/" + code,
                        "url": url,
                    },
                    status_code=201,
                )
            return JSONResponse({"detail": "could not allocate a unique code"}, status_code=503)
        finally:
            conn.close()

    @app.get("/r/{code}")
    def redirect(code: str):
        conn = connect(path)
        try:
            cur = conn.execute("UPDATE links SET clicks = clicks + 1 WHERE code = ?", (code,))
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="not found")
            row = conn.execute("SELECT url FROM links WHERE code = ?", (code,)).fetchone()
        finally:
            conn.close()
        return RedirectResponse(row["url"], status_code=302)

    @app.get("/links/{code}/stats")
    def stats(code: str):
        conn = connect(path)
        try:
            row = conn.execute("SELECT code, url, clicks FROM links WHERE code = ?", (code,)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        return {"code": row["code"], "url": row["url"], "clicks": row["clicks"]}

    return app
