import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from .database import engine, Base
from .limiter import limiter
from .logging_config import configure_logging
from .routers import frameworks, tools, assessments, export, pdf_export
from .routers import auth as auth_router

# Configure file-based logging before anything else writes to a logger.
configure_logging()
_access = logging.getLogger("caams.access")
_app    = logging.getLogger("caams.app")

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _app.info("STARTUP | CAAMS v1.0.0 | logging active")
    yield


app = FastAPI(
    title="CAAMS — Compliance and Auditing Made Simple",
    version="1.0.0",
    description=(
        "Pick a framework, add your tools, and get an auditor-ready coverage report. "
        "Supports CIS Controls, NIST CSF, SOC 2, PCI DSS 4.0, and HIPAA Security Rule."
    ),
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Set CAAMS_CORS_ORIGIN to your intranet hostname (e.g. https://caams.corp.local)
# to enable credentialed cross-origin requests.  If unset, CORS is open but
# credentials are disabled (browser same-origin requests always work regardless).
_cors_origin = os.getenv("CAAMS_CORS_ORIGIN", "")
if _cors_origin:
    _allowed_origins     = [_cors_origin]
    _allow_credentials   = True
else:
    _allowed_origins     = ["*"]
    _allow_credentials   = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Access log middleware ──────────────────────────────────────────────────────
# Replaces uvicorn's built-in access log (silenced in logging_config.py).
# Logs every request: client IP, method, path, status code, response time.
@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    client = (request.client.host if request.client else "unknown")
    _access.info(
        "%s | %s %s | %d | %.0fms",
        client,
        request.method,
        request.url.path,
        response.status_code,
        ms,
    )
    return response


# ── Unhandled exception logger ─────────────────────────────────────────────────
# HTTPExceptions (4xx/5xx raised intentionally) are re-raised so FastAPI's
# default handler returns the right response.  Genuine unhandled exceptions
# (bugs) get logged to app.log with a full traceback.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    _app.error(
        "UNHANDLED | %s %s | %s: %s",
        request.method,
        request.url.path,
        type(exc).__name__,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(auth_router.router)
app.include_router(frameworks.router)
app.include_router(tools.router)
app.include_router(assessments.router)
app.include_router(export.router)
app.include_router(pdf_export.router)

STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "app": "CAAMS", "version": "1.0.0"}


@app.get("/", include_in_schema=False)
def serve_ui():
    return FileResponse(STATIC_DIR / "index.html")
