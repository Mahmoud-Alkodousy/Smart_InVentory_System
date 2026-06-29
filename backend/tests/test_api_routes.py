"""
tests/test_api_routes.py
────────────────────────────
Integration tests for the FastAPI routes using TestClient.

These run WITHOUT Redis, Celery, or a GPU — job_store and user_store
both have in-memory fallbacks (see api/job_store.py / monitoring_jobs/
user_store.py), which main.py already falls back to automatically when
Redis is unreachable. That fallback is exactly what makes these tests
possible without spinning up infrastructure.

We do NOT test the actual forecasting pipeline end-to-end here (that
needs Chronos weights + real inference, which is a slow, network-
dependent operation explicitly out of scope for unit/integration
tests). Instead we test the HTTP contract: validation, status codes,
auth gating, and the parts of job_store/user_store wiring that don't
require ML.

NOTE: the in-process fallback path (used when Celery isn't running)
dispatches the real pipeline on a background thread, which will try
to load Chronos and fail with "No module named 'chronos'" if the ML
deps aren't installed in this environment. That's expected and
harmless here — api.pipeline_common.run_full_pipeline catches it and
calls job_store.fail(), so it never crashes the test process. You'll
see a traceback printed to stderr from that background thread; it
does not affect any assertion above (every test here only checks the
synchronous HTTP response, not the eventual job outcome).
"""

from __future__ import annotations

import io
import os

import pytest

os.environ.setdefault("API_KEYS", "")
os.environ.setdefault("CHRONOS_DEVICE", "cpu")

from fastapi.testclient import TestClient
import main

client = TestClient(main.app)


# ── Health ─────────────────────────────────────────────────────────────────────

def test_health_endpoint_ok():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "auth_enabled" in body
    assert "store" in body


# ── Upload validation ──────────────────────────────────────────────────────────

def test_upload_with_no_file_and_no_sheets_url_returns_400():
    resp = client.post("/api/upload", data={"lead_time_days": "7"})
    assert resp.status_code == 400


def test_upload_rejects_unsupported_file_extension():
    fake_file = io.BytesIO(b"not a real spreadsheet")
    resp = client.post(
        "/api/upload",
        files={"file": ("malware.exe", fake_file, "application/octet-stream")},
    )
    assert resp.status_code == 415


def test_upload_rejects_invalid_google_sheets_url():
    resp = client.post(
        "/api/upload",
        data={"sheets_url": "https://example.com/not-a-real-sheet"},
    )
    assert resp.status_code == 400


def test_upload_clamps_lead_time_days_to_valid_range():
    # lead_time_days=99999 should be clamped to MAX_LEAD_TIME (365), not
    # rejected outright — this exercises api/routes.py's max(1, min(...))
    # clamp logic. We use a tiny valid CSV so the upload itself succeeds
    # and dispatches in the background; we only care that it's accepted.
    csv_bytes = b"date,store,item,sales\n2024-01-01,S1,A,10\n2024-01-02,S1,A,12\n"
    resp = client.post(
        "/api/upload",
        data={"lead_time_days": "99999"},
        files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200
    assert "job_id" in resp.json()


def test_upload_returns_job_id_and_processing_status():
    csv_bytes = b"date,store,item,sales\n2024-01-01,S1,A,10\n2024-01-02,S1,A,12\n"
    resp = client.post(
        "/api/upload",
        files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "processing"


# ── Forecast / report / drift polling ──────────────────────────────────────────

def test_forecast_for_nonexistent_job_returns_404():
    resp = client.get("/api/forecast/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_forecast_for_malformed_job_id_returns_404():
    resp = client.get("/api/forecast/not-a-valid-uuid")
    assert resp.status_code == 404


def test_report_for_nonexistent_job_returns_404():
    resp = client.get("/api/report/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_drift_for_nonexistent_job_returns_404():
    resp = client.get("/api/drift/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ── Purchase order ──────────────────────────────────────────────────────────────

def test_purchase_order_rejects_empty_items_list():
    resp = client.post("/api/purchase-order", json={"items": []})
    assert resp.status_code == 400


def test_purchase_order_rejects_too_many_items():
    items = [{"item": f"ITEM_{i}", "quantity": 1} for i in range(201)]   # MAX_PO_ITEMS=200
    resp = client.post("/api/purchase-order", json={"items": items})
    assert resp.status_code == 400


def test_purchase_order_generates_pdf_for_valid_items():
    resp = client.post("/api/purchase-order", json={
        "items": [{"item": "Widget", "quantity": 10, "unit_price": 5.0}],
        "supplier_name": "Test Supplier",
    })
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 0


def test_purchase_order_rejects_zero_or_negative_quantity():
    resp = client.post("/api/purchase-order", json={
        "items": [{"item": "Widget", "quantity": 0}],
    })
    assert resp.status_code == 422   # pydantic validation: quantity must be > 0


def test_auto_purchase_order_for_nonexistent_job_returns_404():
    resp = client.get("/api/purchase-order/auto/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ── Monitor: user registration ──────────────────────────────────────────────────

def test_register_rejects_invalid_email():
    resp = client.post("/api/monitor/register", json={
        "email": "not-an-email",
        "sheets_url": "https://docs.google.com/spreadsheets/d/abc123/edit",
    })
    assert resp.status_code == 422


def test_register_rejects_non_google_sheets_url():
    resp = client.post("/api/monitor/register", json={
        "email": "user@example.com",
        "sheets_url": "https://example.com/not-a-sheet",
    })
    assert resp.status_code == 400


def test_register_rejects_invalid_frequency():
    resp = client.post("/api/monitor/register", json={
        "email": "user@example.com",
        "sheets_url": "https://docs.google.com/spreadsheets/d/abc123/edit",
        "frequency": "hourly",   # not a valid frequency
    })
    assert resp.status_code == 422


def test_register_succeeds_with_valid_payload():
    resp = client.post("/api/monitor/register", json={
        "email": "user@example.com",
        "sheets_url": "https://docs.google.com/spreadsheets/d/abc123/edit",
        "frequency": "weekly",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert "user" in body
    assert body["user"]["email"] == "user@example.com"


def test_get_nonexistent_user_returns_404():
    resp = client.get("/api/monitor/users/does-not-exist")
    assert resp.status_code == 404


# ── Auth gating (only meaningful when API_KEYS is set) ─────────────────────────

def test_auth_disabled_by_default_allows_unauthenticated_health_check():
    # With no API_KEYS configured (the default in these tests), every
    # endpoint should be reachable without an X-API-Key header.
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["auth_enabled"] is False
