"""
main.py
────────
FastAPI application entry point — production-hardened.

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
# ── Force UTF-8 globally — must be before any other imports ──────────────────
os.environ["PYTHONUTF8"]        = "1"
os.environ["PYTHONIOENCODING"]  = "utf-8"
os.environ["SLOWAPI_NO_DOTENV"] = "1"
from dotenv import load_dotenv
load_dotenv(encoding="utf-8")

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.rate_limiter import limiter
from api.routes import router
from api.monitor_routes import router as monitor_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Smart Inventory Manager API",
    description=(
        "AI-powered demand forecasting and inventory recommendation system. "
        "Upload your sales data (CSV / Excel / JSON / Google Sheets) and receive "
        "a 90-day forecast with dynamic safety buffers and an Arabic business report."
    ),
    version="1.1.0",
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "false").lower() == "true" else None,
    redoc_url=None,
)


# ── Rate limiter ──────────────────────────────────────────────────────────────

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# ── CORS ──────────────────────────────────────────────────────────────────────

_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


# ── Trusted hosts ─────────────────────────────────────────────────────────────

_raw_hosts = os.getenv("ALLOWED_HOSTS", "*")
if _raw_hosts != "*":
    ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(router)
app.include_router(monitor_router)


# ── Startup checks ────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_checks():
    is_production = os.getenv("ENV", "development").lower() == "production"

    if is_production:
        required_prod_vars = {
            "OPENROUTER_API_KEY": "LLM report generation will fail",
            "API_KEYS":           "API is running without authentication",
            "ALLOWED_ORIGINS":    "CORS is using default localhost origins",
        }
        for var, warning in required_prod_vars.items():
            val = os.getenv(var, "")
            if not val:
                logger.warning("⚠️  PRODUCTION WARNING: %s not set — %s", var, warning)

        if os.getenv("ALLOWED_HOSTS", "*") == "*":
            logger.warning("⚠️  PRODUCTION WARNING: ALLOWED_HOSTS=* — set to your domain")

    from api.routes import _AUTH_ENABLED
    if _AUTH_ENABLED:
        logger.info("🔒 API key authentication enabled")
    else:
        logger.warning("🔓 API key authentication DISABLED (set API_KEYS env var to enable)")

    from api.job_store import job_store
    store_type = "Redis" if hasattr(job_store, "_r") else "in-memory (Redis unavailable)"
    logger.info("📦 Job store: %s", store_type)

    # ── Start scheduled monitoring ────────────────────────────────────────────
    from monitoring_jobs.scheduler import start_scheduler
    start_scheduler()

    logger.info("🚀 Smart Inventory Manager API v1.1 is ready.")


@app.on_event("shutdown")
async def shutdown():
    from monitoring_jobs.scheduler import stop_scheduler
    stop_scheduler()


# ── Dev runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
