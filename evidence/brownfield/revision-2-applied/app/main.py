import os
import sqlite3
import time
from typing import Annotated, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, StrictInt, StrictStr, field_validator, model_validator

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


class CreateLink(BaseModel):
    url: StrictStr
    ttl_seconds: Optional[Annotated[StrictInt, Field(ge=1, le=86400)]] = None

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        if not _valid_url(v):
            raise ValueError("url must be a valid http/https URL")
        return v

    @model_validator(mode="after")
    def _no_explicit_null_ttl(self):
        if "ttl_seconds" in self.model_fields_set and self.ttl_seconds is None:
            raise ValueError("ttl_seconds must be an integer from 1 to 86400 when provided")
        return self


def create_app(db_path=None, code_generator=None, clock=None) -> FastAPI:
    path = db_path or os.environ.get("SHORTENER_DB", "shortener.db")
    path = str(path)
    init_db(path)
    now = clock if clock is not None else time.time
    app = FastAPI(title="URL Shortener")

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        errors = [{k: v for k, v in e.items() if k != "ctx"} for e in exc.errors()]
        return JSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)

    def gen():
        if code_generator is not None:
            return code_generator()
        return codes_module.generate_code()

    @app.post("/links")
    def create_link(payload: CreateLink, request: Request):
        expires_at = None
        if payload.ttl_seconds is not None:
            expires_at = now() + payload.ttl_seconds
        url = payload.url
        conn = connect(path)
        try:
            for _ in range(MAX_RETRIES):
                code = gen()
                try:
                    conn.execute(
                        "INSERT INTO links (code, url, clicks, expires_at) VALUES (?, ?, 0, ?)",
                        (code, url, expires_at),
                    )
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
            cur = conn.execute(
                "UPDATE links SET clicks = clicks + 1 "
                "WHERE code = ? AND (expires_at IS NULL OR ? < expires_at)",
                (code, now()),
            )
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
            row = conn.execute(
                "SELECT code, url, clicks, expires_at FROM links WHERE code = ?", (code,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        return {
            "code": row["code"],
            "url": row["url"],
            "clicks": row["clicks"],
            "expires_at": row["expires_at"],
        }

    return app
