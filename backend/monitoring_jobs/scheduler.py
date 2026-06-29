"""
monitoring_jobs/scheduler.py
──────────────────────────────
APScheduler-based background scheduler.

Frequencies supported:
  daily      — every day at 06:00 UTC
  weekly     — every Monday at 06:00 UTC
  monthly    — 1st of every month at 06:00 UTC
  quarterly  — 1st of Jan, Apr, Jul, Oct at 06:00 UTC
  semiannual — 1st of Jan, Jul at 06:00 UTC

Each job re-fetches the Google Sheet (or uses stored CSV) and runs
the full pipeline, then sends an email notification.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


# ── Live Google Sheets re-fetch ───────────────────────────────────────────────

def _fetch_sheet_bytes(user: dict) -> tuple[bytes, str, str]:
    """
    Returns (source_bytes_or_url, filename, mime_type).
    Prefers re-fetching from Google Sheets URL if available.
    Falls back to stored CSV bytes if URL is "__file__".
    """
    sheets_url = user.get("sheets_url", "")
    csv_data   = user.get("csv_data", "")

    # If we have a real Sheets URL, re-fetch it fresh every run
    if sheets_url and sheets_url != "__file__":
        logger.info("Scheduler: re-fetching Sheet for user %s", user["user_id"])
        try:
            from data_loader.sheets_loader import load_google_sheet

            # Use the existing loader which handles all edge cases
            df = load_google_sheet(sheets_url)
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            return csv_bytes, "sheet.csv", "text/csv"
        except Exception as exc:
            logger.warning(
                "Scheduler: failed to re-fetch Sheet for user %s (%s) — using stored CSV",
                user["user_id"], exc
            )
            # Fall through to stored CSV

    # Fallback: use stored CSV (base64-encoded)
    if csv_data:
        import base64
        return base64.b64decode(csv_data), "data.csv", "text/csv"

    raise ValueError(f"No data source available for user {user['user_id']}")


# ── Pipeline runner ───────────────────────────────────────────────────────────

def _run_pipeline_for_user(user: dict) -> tuple[Optional[dict], str]:
    """
    Runs the full pipeline for a single user.
    Returns (completed job dict, job_id) — job dict is None on failure.

    Delegates the actual pipeline orchestration to
    api.pipeline_common.run_full_pipeline, the single shared
    implementation also used by api/routes.py and worker.py. This
    function only handles what's specific to scheduled runs: re-fetching
    the user's data source and recording mark_ran on success.
    """
    from api.job_store import job_store
    from api.pipeline_common import run_full_pipeline

    job_id  = str(uuid.uuid4())
    user_id = user["user_id"]
    job_store.create(job_id)

    logger.info("Scheduler: starting job %s for user %s", job_id, user_id)

    try:
        source, filename, mime_type = _fetch_sheet_bytes(user)
    except ValueError as exc:
        job_store.fail(job_id, error=str(exc))
        logger.error("Scheduler: %s", exc)
        return None, job_id

    success = run_full_pipeline(
        job_id=job_id,
        source=source,
        filename=filename,
        mime_type=mime_type,
        lead_time_days=user.get("lead_time_days", 7),
        extra_context=user.get("extra_context", ""),
    )

    if not success:
        job = job_store.get(job_id)
        logger.warning(
            "Scheduler: pipeline failed for user %s — %s",
            user_id, job.get("error") if job else "unknown error",
        )
        return None, job_id

    from monitoring_jobs.user_store import user_store
    user_store.mark_ran(user_id, job_id)

    job = job_store.get(job_id)
    logger.info(
        "Scheduler: job %s done for user %s (%d items, %d stores)",
        job_id, user_id, job.get("n_items", 0), job.get("n_stores", 0),
    )
    return job, job_id


# ── Alert + email notification ────────────────────────────────────────────────

def _handle_alerts(user: dict, job: dict, job_id: str) -> None:
    from monitoring_jobs.alert_checker import check_alerts, build_alert_payload
    from monitoring_jobs.notifier import (
        notify_low_stock_alert,
        notify_analysis_done,
    )

    email    = user.get("email", "")
    recs     = job.get("recommendations", [])
    n_items  = job.get("n_items", 0)
    n_stores = job.get("n_stores", 0)
    report   = job.get("report", "")

    alert_result = check_alerts(recs, lead_time_days=user.get("lead_time_days", 7))

    if alert_result.should_notify:
        payload = build_alert_payload(alert_result)
        if payload:
            notify_low_stock_alert(email, payload)
    else:
        notify_analysis_done(
            email,
            n_items=n_items,
            n_stores=n_stores,
            job_id=job_id,
            report=report,
        )


# ── Per-frequency runner ──────────────────────────────────────────────────────

def _run_for_frequency(frequency: str) -> None:
    from monitoring_jobs.user_store import user_store
    users = user_store.users_by_frequency(frequency)
    logger.info("Scheduler: %s run — %d users", frequency, len(users))
    for user in users:
        job, job_id = _run_pipeline_for_user(user)
        if job:
            _handle_alerts(user, job, job_id)


def run_daily_jobs():      _run_for_frequency("daily")
def run_weekly_jobs():     _run_for_frequency("weekly")
def run_monthly_jobs():    _run_for_frequency("monthly")
def run_quarterly_jobs():  _run_for_frequency("quarterly")
def run_semiannual_jobs(): _run_for_frequency("semiannual")


# ── Scheduler lifecycle ───────────────────────────────────────────────────────

_scheduler = None


def start_scheduler() -> None:
    global _scheduler

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("APScheduler not installed — scheduled monitoring disabled.")
        return

    _scheduler = BackgroundScheduler(timezone="UTC")

    jobs = [
        ("daily_monitor",      run_daily_jobs,      CronTrigger(hour=6, minute=0, timezone="UTC")),
        ("weekly_monitor",     run_weekly_jobs,      CronTrigger(day_of_week="mon", hour=6, minute=0, timezone="UTC")),
        ("monthly_monitor",    run_monthly_jobs,     CronTrigger(day=1, hour=6, minute=0, timezone="UTC")),
        ("quarterly_monitor",  run_quarterly_jobs,   CronTrigger(month="1,4,7,10", day=1, hour=6, minute=0, timezone="UTC")),
        ("semiannual_monitor", run_semiannual_jobs,  CronTrigger(month="1,7", day=1, hour=6, minute=0, timezone="UTC")),
    ]

    for job_id, func, trigger in jobs:
        _scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=3600,
        )

    _scheduler.start()
    logger.info("Scheduler: started — daily/weekly/monthly/quarterly/semiannual @ 06:00 UTC")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler: stopped")
