"""
api/monitor_routes.py
──────────────────────
REST endpoints for multi-user scheduled monitoring.

Endpoints (all under /api/monitor):
  POST   /api/monitor/register              Register with Google Sheets URL
  POST   /api/monitor/register-with-file    Register with uploaded CSV file
  GET    /api/monitor/users                 List all users (admin)
  GET    /api/monitor/users/{user_id}       Get single user
  PATCH  /api/monitor/users/{user_id}       Update user settings
  DELETE /api/monitor/users/{user_id}       Remove user
  POST   /api/monitor/users/{user_id}/run   Trigger manual analysis now
  GET    /api/monitor/users/{user_id}/last  Get last job results
"""

import base64
import threading
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, Security, UploadFile
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field, field_validator

from api.rate_limiter import limiter
from api.routes import _AUTH_ENABLED, _VALID_API_KEYS
from monitoring_jobs.user_store import user_store, VALID_FREQUENCIES

router = APIRouter(prefix="/api/monitor", tags=["monitoring"])

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _verify_api_key(api_key: Optional[str] = Security(_API_KEY_HEADER)) -> None:
    if not _AUTH_ENABLED:
        return
    if not api_key or api_key not in _VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


# ── Pydantic models ───────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:          str = Field(..., description="Recipient email address")
    sheets_url:     str = Field(..., description="Full Google Sheets URL")
    frequency:      str = Field("weekly", description="'daily'|'weekly'|'monthly'|'quarterly'|'semiannual'")
    lead_time_days: int = Field(7, ge=1, le=365)
    extra_context:  str = Field("", max_length=500)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        if v not in VALID_FREQUENCIES:
            raise ValueError(f"frequency must be one of: {', '.join(VALID_FREQUENCIES)}")
        return v


class UpdateRequest(BaseModel):
    email:          Optional[str] = None
    sheets_url:     Optional[str] = None
    frequency:      Optional[str] = None
    lead_time_days: Optional[int] = Field(default=None, ge=1, le=365)
    extra_context:  Optional[str] = Field(default=None, max_length=500)
    enabled:        Optional[bool] = None

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_FREQUENCIES:
            raise ValueError(f"frequency must be one of: {', '.join(VALID_FREQUENCIES)}")
        return v


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
@limiter.limit("20/minute")
def register_user(
    request: Request,
    body:    RegisterRequest,
    _auth:   None = Security(_verify_api_key),
):
    """Register a new Google Sheet for scheduled monitoring."""
    if not body.sheets_url.startswith("https://docs.google.com/spreadsheets/"):
        raise HTTPException(status_code=400, detail="Invalid Google Sheets URL.")

    record = user_store.create(
        email=body.email,
        sheets_url=body.sheets_url,
        frequency=body.frequency,
        lead_time_days=body.lead_time_days,
        extra_context=body.extra_context,
    )

    # Send welcome email (non-blocking)
    def _welcome():
        from monitoring_jobs.notifier import notify_welcome
        notify_welcome(
            email=body.email,
            user_id=record["user_id"],
            frequency=body.frequency,
            sheets_url=body.sheets_url,
        )
    threading.Thread(target=_welcome, daemon=True).start()

    return {"message": "تم التسجيل بنجاح", "user": _safe(record)}


@router.post("/register-with-file", status_code=201)
@limiter.limit("20/minute")
async def register_user_with_file(
    request:        Request,
    email:          str        = Form(...),
    file:           UploadFile = File(...),
    frequency:      str        = Form("weekly"),
    lead_time_days: int        = Form(7),
    extra_context:  str        = Form(""),
    _auth:          None       = Security(_verify_api_key),
):
    """Register with a pre-fetched CSV file."""
    # Validate email
    email = email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Invalid email address.")

    # Validate frequency
    if frequency not in VALID_FREQUENCIES:
        raise HTTPException(
            status_code=400,
            detail=f"frequency must be one of: {', '.join(VALID_FREQUENCIES)}"
        )

    csv_bytes = await file.read()
    if not csv_bytes:
        raise HTTPException(status_code=400, detail="الملف فارغ.")

    csv_b64 = base64.b64encode(csv_bytes).decode()

    record = user_store.create(
        email=email,
        sheets_url="__file__",
        frequency=frequency,
        lead_time_days=max(1, min(int(lead_time_days), 365)),
        extra_context=extra_context.strip()[:500],
    )
    user_store.update(record["user_id"], csv_data=csv_b64)

    # Send welcome email (non-blocking)
    def _welcome():
        from monitoring_jobs.notifier import notify_welcome
        notify_welcome(
            email=email,
            user_id=record["user_id"],
            frequency=frequency,
            sheets_url="__file__",
        )
    threading.Thread(target=_welcome, daemon=True).start()

    return {"message": "تم التسجيل بنجاح", "user": _safe(record)}


@router.get("/users")
@limiter.limit("60/minute")
def list_users(
    request: Request,
    _auth:   None = Security(_verify_api_key),
):
    users = user_store.all_users()
    return {"count": len(users), "users": [_safe(u) for u in users]}


@router.get("/users/{user_id}")
@limiter.limit("60/minute")
def get_user(request: Request, user_id: str, _auth: None = Security(_verify_api_key)):
    return _safe(_get_or_404(user_id))


@router.patch("/users/{user_id}")
@limiter.limit("30/minute")
def update_user(
    request: Request,
    user_id: str,
    body:    UpdateRequest,
    _auth:   None = Security(_verify_api_key),
):
    _get_or_404(user_id)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "sheets_url" in updates and not updates["sheets_url"].startswith(
        "https://docs.google.com/spreadsheets/"
    ):
        raise HTTPException(status_code=400, detail="Invalid Google Sheets URL.")
    updated = user_store.update(user_id, **updates)
    return {"message": "تم التحديث", "user": _safe(updated)}


@router.delete("/users/{user_id}", status_code=200)
@limiter.limit("20/minute")
def delete_user(request: Request, user_id: str, _auth: None = Security(_verify_api_key)):
    _get_or_404(user_id)
    user_store.delete(user_id)
    return {"message": "تم حذف المستخدم"}


@router.post("/users/{user_id}/run")
@limiter.limit("5/minute")
def trigger_manual_run(
    request: Request,
    user_id: str,
    _auth:   None = Security(_verify_api_key),
):
    """Trigger an immediate pipeline run for this user."""
    user = _get_or_404(user_id)

    def _run():
        from monitoring_jobs.scheduler import _run_pipeline_for_user, _handle_alerts
        job, job_id = _run_pipeline_for_user(user)
        if job:
            _handle_alerts(user, job, job_id)

    threading.Thread(target=_run, daemon=True).start()
    return {
        "message": "بدأ التشغيل في الخلفية — ستصلك إشعارات على إيميلك",
        "user_id": user_id,
        "email":   user.get("email", ""),
    }


@router.get("/users/{user_id}/last")
@limiter.limit("60/minute")
def get_last_job(
    request: Request,
    user_id: str,
    _auth:   None = Security(_verify_api_key),
):
    user   = _get_or_404(user_id)
    job_id = user.get("last_job_id", "")

    if not job_id:
        raise HTTPException(status_code=404, detail="لا يوجد تحليل سابق لهذا المستخدم.")

    from api.job_store import job_store
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail="انتهت صلاحية نتيجة التحليل السابق (تُحذف بعد ساعة).",
        )
    return {"user_id": user_id, "job": job}


@router.get("/frequencies")
def list_frequencies():
    """Return available monitoring frequencies with Arabic labels."""
    return {
        "frequencies": [
            {"value": "daily",      "label": "يومياً",       "description": "كل يوم"},
            {"value": "weekly",     "label": "أسبوعياً",     "description": "كل إثنين"},
            {"value": "monthly",    "label": "شهرياً",       "description": "أول كل شهر"},
            {"value": "quarterly",  "label": "كل 3 أشهر",   "description": "يناير، أبريل، يوليو، أكتوبر"},
            {"value": "semiannual", "label": "كل 6 أشهر",   "description": "يناير ويوليو"},
        ]
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_or_404(user_id: str) -> dict:
    user = user_store.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"المستخدم '{user_id}' غير موجود.")
    return user


def _safe(record: dict) -> dict:
    """Strip sensitive fields from API responses."""
    r = dict(record)
    r.pop("csv_data", None)   # never expose stored CSV
    return r
