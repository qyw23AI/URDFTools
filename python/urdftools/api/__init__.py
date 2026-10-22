"""Loopback-only HTTP shell with per-session credentials."""
import secrets
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from urdftools.core import runtime_status


def create_app(token: str):
    if len(token) < 32:
        raise ValueError("A session token of at least 32 characters is required")
    app = FastAPI(title="URDFTools", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def authorize(request: Request, call_next):
        if request.headers.get("origin") is not None:
            return JSONResponse({"code": "origin_rejected"}, status_code=403)
        if not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + token):
            return JSONResponse({"code": "unauthorized"}, status_code=401)
        return await call_next(request)

    @app.get("/v1/health")
    def health():
        return runtime_status()

    return app
