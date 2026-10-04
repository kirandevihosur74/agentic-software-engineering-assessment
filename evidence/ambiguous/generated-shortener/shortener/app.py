import os
import secrets
import sqlite3
import string
from contextlib import closing
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, field_validator

ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 7
MAX_URL_LENGTH = 2048
MAX_ATTEMPTS = 10


def generate_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


class CreateLink(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def check_url(cls, v: str) -> str:
        if len(v) > MAX_URL_LENGTH:
            raise ValueError("url too long")
        if any(c.isspace() for c in v):
            raise ValueError("url must not contain whitespace")
        try:
            p = urlparse(v)
            host = p.hostname
        except ValueError:
            raise ValueError("invalid url")
        if p.scheme not in ("http", "https"):
            raise ValueError("url scheme must be http or https")
        if not host:
            raise ValueError("url must have a hostname")
        return v


class LinkCreated(BaseModel):
    code: str
    short_url: str


class LinkStats(BaseModel):
    code: str
    url: str
    clicks: int


def create_app(db_path: Optional[str] = None) -> FastAPI:
    path = str(db_path or os.environ.get("SHORTENER_DB") or "shortener.db")
    app = FastAPI(title="Shortener")
    app.state.db_path = path

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(app.state.db_path, timeout=10)

    with closing(connect()) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS links ("
            "code TEXT PRIMARY KEY, url TEXT NOT NULL, "
            "clicks INTEGER NOT NULL DEFAULT 0)"
        )
        conn.commit()

    @app.post("/links", status_code=201, response_model=LinkCreated)
    def create_link(body: CreateLink, request: Request):
        with closing(connect()) as conn:
            for _ in range(MAX_ATTEMPTS):
                code = generate_code()
                try:
                    conn.execute(
                        "INSERT INTO links (code, url) VALUES (?, ?)",
                        (code, body.url),
                    )
                    conn.commit()
                except sqlite3.IntegrityError:
                    conn.rollback()
                    continue
                base = str(request.base_url).rstrip("/")
                return LinkCreated(code=code, short_url=f"{base}/r/{code}")
        raise HTTPException(status_code=503, detail="could not allocate a unique code")

    @app.get("/r/{code}")
    def follow(code: str):
        with closing(connect()) as conn:
            cur = conn.execute(
                "UPDATE links SET clicks = clicks + 1 WHERE code = ?", (code,)
            )
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="not found")
            row = conn.execute(
                "SELECT url FROM links WHERE code = ?", (code,)
            ).fetchone()
        return RedirectResponse(row[0], status_code=302)

    @app.get("/links/{code}/stats", response_model=LinkStats)
    def stats(code: str):
        with closing(connect()) as conn:
            row = conn.execute(
                "SELECT code, url, clicks FROM links WHERE code = ?", (code,)
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        return LinkStats(code=row[0], url=row[1], clicks=row[2])

    return app
