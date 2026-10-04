"""API boundaries only; persistent storage and business logic are future work."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl

app = FastAPI(title="URL Shortener Scaffold", version="0.1.0")


class CreateLinkRequest(BaseModel):
    url: HttpUrl


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "scaffold"}


@app.post("/links", status_code=201)
def create_link(request: CreateLinkRequest):
    raise HTTPException(501, "Link creation is not implemented")


@app.get("/r/{code}")
def redirect_link(code: str):
    raise HTTPException(501, "Redirects are not implemented")


@app.get("/links/{code}/stats")
def link_stats(code: str):
    raise HTTPException(501, "Analytics are not implemented")
