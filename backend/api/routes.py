"""
api/routes.py
──────────────
FastAPI route definitions.

Pipeline jobs are now dispatched to a Celery worker (worker.py)
instead of FastAPI BackgroundTasks, so the heavy work (LLM calls +
Chronos inference) runs in a separate process and never blocks the
API event loop.

Endpoints:
  POST /api/upload          — Upload file, dispatch Celery task
  GET  /api/forecast/{id}   — Poll forecast results
  GET  /api/report/{id}     — Get Arabic LLM report
  GET  /api/drift/{id}      — Get drift analysis
  GET  /api/health          — Health check (no auth required)
"""

import os
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile, HTTPException, Request, Security
from fastapi.security.api_key import APIKeyHeader

from api.job_store import job_store, JobStatus
from api.rate_limiter import limiter


router = APIRouter(prefix="/api")


# ── Auth ──────────────────────────────────────────────────────────────────────

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_VALID_API_KEYS: set[str] = set(
    filter(None, os.getenv("API_KEYS", "").split(","))
)
_AUTH_ENABLED = bool(_VALID_API_KEYS)


def _verify_api_key(api_key: Optional[str] = Security(_API_KEY_HEADER)) -> None:
    if not _AUTH_ENABLED:
        return
    if not api_key or api_key not in _VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


# ── Config ────────────────────────────────────────────────────────────────────

MAX_FILE_SIZE_MB  = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_FILE_SIZE_B   = MAX_FILE_SIZE_MB * 1024 * 1024

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json"}
ALLOWED_MIME_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/json",
    "text/json",
    "application/octet-stream",
}

MAX_CONTEXT_LEN = 500
MAX_LEAD_TIME   = 365


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    from api.job_store import REDIS_URL
    return {
        "status":       "ok",
        "service":      "Smart Inventory Manager",
        "auth_enabled": _AUTH_ENABLED,
        "store":        "redis" if hasattr(job_store, "_r") else "in-memory",
    }


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload")
@limiter.limit(os.getenv("UPLOAD_RATE_LIMIT", "10/minute"))
async def upload_file(
    request:          Request,
    file:             Optional[UploadFile] = File(default=None),
    sheets_url:       Optional[str]        = Form(default=None),
    lead_time_days:   int                  = Form(default=7),
    extra_context:    str                  = Form(default=""),
    unit_price:       Optional[float]      = Form(default=None),   # NEW: optional price per unit
    _auth: None = Security(_verify_api_key),
):
    """
    Accept a file (CSV / Excel / JSON) or Google Sheets URL.
    Dispatches a Celery task and returns job_id immediately.
    Poll /api/forecast/{job_id} for results.
    """
    if file is None and not sheets_url:
        raise HTTPException(
            status_code=400,
            detail="Provide either a file upload or a Google Sheets URL.",
        )

    lead_time_days = max(1, min(lead_time_days, MAX_LEAD_TIME))
    extra_context  = extra_context.strip()[:MAX_CONTEXT_LEN]
    if unit_price is not None:
        unit_price = max(0.0, unit_price)  # clamp negative values

    if file is not None:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_FILE_SIZE_B:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB} MB.",
            )

        filename  = file.filename or ""
        mime_type = file.content_type or ""
        ext       = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext and ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        file_bytes = await file.read(MAX_FILE_SIZE_B + 1)
        if len(file_bytes) > MAX_FILE_SIZE_B:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB} MB.",
            )

        # Serialise bytes → list[int] so Celery can JSON-encode the task args
        source    = list(file_bytes)

    else:
        sheets_url = sheets_url.strip()
        if not sheets_url.startswith("https://docs.google.com/spreadsheets/"):
            raise HTTPException(
                status_code=400,
                detail="Invalid Google Sheets URL.",
            )
        source    = sheets_url
        filename  = ""
        mime_type = ""

    # ── Dispatch to Celery worker ─────────────────────────────────────────────
    job_id = str(uuid.uuid4())
    job_store.create(job_id)

    _dispatched = False
    try:
        from worker import celery_app, run_pipeline_task

        # ── FIX: Verify at least one worker is actually running ───────────────
        # .delay() succeeds even with no worker — the task sits in the queue
        # forever and the job stays "processing". inspect().active() lets us
        # confirm a live worker exists before trusting Celery with the task.
        import logging as _log
        _logger = _log.getLogger(__name__)
        try:
            _inspector = celery_app.control.inspect(timeout=1.0)
            _active    = _inspector.active()       # None or {} if no workers
            _worker_up = bool(_active)
        except Exception:
            _worker_up = False

        if _worker_up:
            run_pipeline_task.delay(
                job_id=job_id,
                source=source,
                filename=filename,
                mime_type=mime_type,
                lead_time_days=lead_time_days,
                extra_context=extra_context,
                unit_price=unit_price,
            )
            _dispatched = True
        else:
            _logger.warning(
                "Celery imported but no live workers found — "
                "falling back to in-process execution."
            )
    except Exception as exc:
        import logging as _log
        _log.getLogger(__name__).warning(
            "Celery unavailable (%s) — falling back to in-process execution.", exc
        )

    if not _dispatched:
        import threading
        t = threading.Thread(
            target=_run_pipeline_fallback,
            kwargs=dict(
                job_id=job_id,
                source=bytes(source) if isinstance(source, list) else source,
                filename=filename,
                mime_type=mime_type,
                lead_time_days=lead_time_days,
                extra_context=extra_context,
                unit_price=unit_price,
            ),
            daemon=True,
        )
        t.start()

    return {"job_id": job_id, "status": "processing"}


# ── Forecast ──────────────────────────────────────────────────────────────────

@router.get("/forecast/{job_id}")
@limiter.limit(os.getenv("POLL_RATE_LIMIT", "60/minute"))
def get_forecast(
    request: Request,
    job_id: str,
    _auth: None = Security(_verify_api_key),
):
    job = _get_job_or_404(job_id)

    if job["status"] == JobStatus.PROCESSING:
        return {
            "job_id":       job_id,
            "status":       "processing",
            "current_step": job.get("current_step", "load"),
        }

    if job["status"] == JobStatus.FAILED:
        return {
            "job_id":         job_id,
            "status":         "failed",
            "error":          job.get("error", "Unknown error"),
            "attempt_errors": job.get("attempt_errors", []),
        }

    return {
        "job_id":          job_id,
        "status":          "done",
        "route":           job.get("route"),
        "n_rows":          job.get("n_rows"),
        "n_stores":        job.get("n_stores"),
        "n_items":         job.get("n_items"),
        "date_min":        job.get("date_min"),
        "date_max":        job.get("date_max"),
        "recommendations": job.get("recommendations", []),
        "warnings":        job.get("warnings", []),
        "timeseries":      job.get("timeseries", []),
        "suppliers":         job.get("suppliers", []),
        "supplier_switches": job.get("supplier_switches", []),
        "transfers":         job.get("transfers", []),
        "events":            job.get("events", []),
    }


# ── Report ────────────────────────────────────────────────────────────────────

@router.get("/report/{job_id}")
@limiter.limit(os.getenv("POLL_RATE_LIMIT", "60/minute"))
def get_report(
    request: Request,
    job_id: str,
    _auth: None = Security(_verify_api_key),
):
    job = _get_job_or_404(job_id)

    if job["status"] == JobStatus.PROCESSING:
        return {"job_id": job_id, "status": "processing"}

    if job["status"] == JobStatus.FAILED:
        raise HTTPException(status_code=400, detail="Job failed — no report available.")

    report = job.get("report")
    if not report:
        raise HTTPException(status_code=404, detail="Report not yet generated.")

    return {"job_id": job_id, "report": report}


# ── Drift ─────────────────────────────────────────────────────────────────────

@router.get("/drift/{job_id}")
@limiter.limit(os.getenv("POLL_RATE_LIMIT", "60/minute"))
def get_drift(
    request: Request,
    job_id: str,
    _auth: None = Security(_verify_api_key),
):
    job = _get_job_or_404(job_id)

    if job["status"] == JobStatus.PROCESSING:
        return {"job_id": job_id, "status": "processing"}

    if job["status"] == JobStatus.FAILED:
        raise HTTPException(status_code=400, detail="Job failed — no drift data.")

    drift = job.get("drift")
    if drift is None:
        raise HTTPException(status_code=404, detail="Drift data not available.")

    return {"job_id": job_id, "drift": drift}


# ── Purchase Order (PDF) ───────────────────────────────────────────────────────

from pydantic import BaseModel, Field
from fastapi.responses import Response

MAX_PO_ITEMS = 200


class POItemIn(BaseModel):
    item:       str
    quantity:   float = Field(gt=0)
    unit_price: Optional[float] = None
    store:      Optional[str]   = None


class PurchaseOrderRequest(BaseModel):
    items:                  list[POItemIn]
    supplier_name:          str = "Primary Supplier"
    expected_delivery_days: Optional[int] = None
    notes:                  str = ""
    currency:               str = "EGP"


@router.post("/purchase-order")
@limiter.limit(os.getenv("POLL_RATE_LIMIT", "60/minute"))
def create_purchase_order(
    request: Request,
    payload: PurchaseOrderRequest,
    _auth: None = Security(_verify_api_key),
):
    """
    Generate a Purchase Order PDF from an explicit list of line items.
    Independent of any job_id, so it also works for hand-picked items or
    from Demo Mode data — the frontend just needs item/quantity/price.
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="No items provided.")
    if len(payload.items) > MAX_PO_ITEMS:
        raise HTTPException(status_code=400, detail=f"Too many items (max {MAX_PO_ITEMS}).")

    from reporting.purchase_order import PurchaseOrder, POLineItem, generate_purchase_order_pdf

    po = PurchaseOrder(
        items=[
            POLineItem(item=i.item, quantity=i.quantity, unit_price=i.unit_price, store=i.store)
            for i in payload.items
        ],
        supplier_name=payload.supplier_name or "—",
        expected_delivery_days=payload.expected_delivery_days,
        notes=payload.notes,
        currency=payload.currency or "EGP",
    )
    pdf_bytes = generate_purchase_order_pdf(po)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{po.po_number}.pdf"'},
    )


@router.get("/purchase-order/auto/{job_id}")
@limiter.limit(os.getenv("POLL_RATE_LIMIT", "60/minute"))
def auto_purchase_order(
    request: Request,
    job_id: str,
    supplier: Optional[str] = None,
    only_at_risk: bool = False,
    top_n: Optional[int] = None,
    _auth: None = Security(_verify_api_key),
):
    """
    Auto-build a Purchase Order PDF straight from a completed job's
    recommendations — optionally scoped to one supplier and/or at-risk
    items only, capped to the top_n items by recommended quantity.
    """
    job = _get_job_or_404(job_id)
    if job["status"] != JobStatus.DONE:
        raise HTTPException(status_code=400, detail="Job is not finished yet.")

    recs = job.get("recommendations", [])
    if not recs:
        raise HTTPException(status_code=404, detail="No recommendations available for this job.")

    if supplier:
        recs = [r for r in recs if str(r.get("supplier")) == supplier]
        if not recs:
            raise HTTPException(status_code=404, detail=f"No items found for supplier '{supplier}'.")

    from reporting.purchase_order import build_auto_po_from_recommendations, generate_purchase_order_pdf
    po = build_auto_po_from_recommendations(
        recs,
        supplier_name=supplier or "Primary Supplier",
        only_at_risk=only_at_risk,
        top_n=top_n,
    )
    if not po.items:
        raise HTTPException(status_code=404, detail="No items matched the given filters.")

    pdf_bytes = generate_purchase_order_pdf(po)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{po.po_number}.pdf"'},
    )


# ── Fallback (no Celery) ──────────────────────────────────────────────────────

def _run_pipeline_fallback(
    job_id:         str,
    source,
    filename:       str,
    mime_type:      str,
    lead_time_days: int,
    extra_context:  str,
    unit_price:     float | None = None,
):
    """
    In-process fallback used only when Celery is not running (dev mode).
    Not suitable for production — blocks a thread for the full duration.

    Delegates to api.pipeline_common.run_full_pipeline, the single
    shared implementation also used by worker.py and the scheduler.
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


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_job_or_404(job_id: str) -> dict:
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Job not found.")

    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found or expired.")
    return job