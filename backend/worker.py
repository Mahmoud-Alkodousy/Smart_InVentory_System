"""
worker.py
──────────
Celery worker — runs the heavy pipeline in a separate process.

Why a separate worker?
  FastAPI's BackgroundTasks runs in the same process as the web server.
  Our pipeline makes 3 LLM calls + Chronos inference + pandas work,
  which blocks the event loop and starves other requests under load.

  Celery moves that work to a dedicated process (or pool of processes),
  so the API stays responsive regardless of pipeline duration.

Start the worker with:
  celery -A worker worker --loglevel=info --concurrency=2

Requirements:
  pip install celery redis

Environment variables:
  REDIS_URL   — used as both broker and result backend (default: redis://localhost:6379/0)
"""

from __future__ import annotations

import os
import logging

from celery import Celery

# ── Load .env before anything else ───────────────────────────────────────────
os.environ.setdefault("PYTHONUTF8",       "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
from dotenv import load_dotenv

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
_env_loaded = load_dotenv(dotenv_path=_ENV_PATH, encoding="utf-8", override=True)

logging.basicConfig(level=logging.INFO)
logging.getLogger(__name__).info(
    "load_dotenv: path=%s found_and_loaded=%s OLLAMA=%r",
    _ENV_PATH, _env_loaded, os.getenv("OLLAMA"),
)

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── Celery app ────────────────────────────────────────────────────────────────

celery_app = Celery(
    "smart_inventory",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Prevent a single stuck task from blocking the worker forever
    task_soft_time_limit=300,   # 5 min — raises SoftTimeLimitExceeded
    task_time_limit=360,        # 6 min — kills the task process
    worker_prefetch_multiplier=1,  # one task at a time per worker process
)


# ── Pipeline task ─────────────────────────────────────────────────────────────

@celery_app.task(bind=True, name="run_pipeline_task")
def run_pipeline_task(
    self,
    job_id:         str,
    source,                 # bytes (list of ints from JSON) or str (URL)
    filename:       str,
    mime_type:      str,
    lead_time_days: int,
    extra_context:  str,
    unit_price:     float | None = None,    # NEW: optional price per unit
):
    """
    Heavy pipeline task — runs in the Celery worker process.

    source is either:
      - a list[int]  (bytes serialised to JSON-safe list)
      - a str        (Google Sheets URL)

    Delegates to api.pipeline_common.run_full_pipeline, the single
    shared implementation also used by the in-process fallback in
    api/routes.py and the scheduled runner in monitoring_jobs/scheduler.py.
    """
    from api.pipeline_common import run_full_pipeline

    if isinstance(source, list):
        source = bytes(source)

    run_full_pipeline(
        job_id=job_id,
        source=source,
        filename=filename,
        mime_type=mime_type,
        lead_time_days=lead_time_days,
        extra_context=extra_context,
        unit_price=unit_price,
    )