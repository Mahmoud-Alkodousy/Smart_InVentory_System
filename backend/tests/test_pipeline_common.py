"""
tests/test_pipeline_common.py
─────────────────────────────────
End-to-end tests for api.pipeline_common.run_full_pipeline — the
single shared orchestrator used by api/routes.py, worker.py, and
monitoring_jobs/scheduler.py.

WHY THIS FILE EXISTS:
A previous refactor that introduced run_full_pipeline() accidentally
deleted build_pipeline_extras() in the same edit (a str_replace whose
old_str started at that function's `def` line swallowed it). Every
existing test still passed, because:
  - test_api_routes.py's upload tests never wait for the background
    job to finish — they only assert on the immediate HTTP response.
  - The background thread itself failed early at the Chronos-loading
    step (ModuleNotFoundError, since chronos isn't installed in the
    test env) — execution never reached the line that referenced the
    missing function.
  - Unit tests for recommend()/detect_drift() etc. call those
    functions directly and never go through run_full_pipeline at all.

So the bug shipped, and only surfaced in a real environment with
Chronos installed, several steps into a 132-second pipeline run.

These tests close that gap: they run run_full_pipeline() in full,
start to finish, with ONLY the genuinely slow/external pieces mocked
out (Chronos inference, the LLM report call). Every other line —
including build_pipeline_extras, extract_optional_signals,
build_timeseries_payload, detect_drift, job_store.complete — executes
for real. If a future refactor deletes or misnames a function again,
one of these tests will raise NameError immediately.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pandas as pd
import pytest

os.environ.setdefault("API_KEYS", "")
os.environ.setdefault("CHRONOS_DEVICE", "cpu")

from api.pipeline_common import run_full_pipeline
from api.job_store import job_store


def _fake_forecast(df: pd.DataFrame) -> pd.DataFrame:
    """Stand-in for ml.model.forecast — same shape, no Chronos needed."""
    pairs = df[["store", "item"]].drop_duplicates().values.tolist()
    future_dates = pd.date_range("2024-03-01", periods=90, freq="D")
    rows = []
    for store, item in pairs:
        for d in future_dates:
            rows.append({
                "date": d, "store": store, "item": item,
                "pred_sales": 12.0, "pred_sales_low": 8.0, "pred_sales_high": 16.0,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def sample_csv_bytes() -> bytes:
    rows = ["date,store,item,sales"]
    dates = pd.date_range("2024-01-01", periods=40, freq="D")
    for d in dates:
        rows.append(f"{d.date()},S1,ITEM_A,{10 + (d.dayofyear % 5)}")
    return ("\n".join(rows)).encode("utf-8")


@patch("ml.model.forecast", side_effect=_fake_forecast)
@patch(
    "reporting.report_generator.generate_report",
    return_value="تقرير تجريبي — كل شيء يعمل بشكل سليم.",
)
def test_run_full_pipeline_succeeds_end_to_end(mock_report, mock_forecast, sample_csv_bytes):
    """
    The exact scenario that broke in production: a clean CSV, routed
    via the 'direct' path (no cleaning needed), going all the way
    through forecast → recommend → build_pipeline_extras → drift →
    report → job_store.complete without hitting any NameError.
    """
    job_id = "test-job-e2e-success"
    job_store.create(job_id)

    success = run_full_pipeline(
        job_id=job_id,
        source=sample_csv_bytes,
        filename="sales.csv",
        mime_type="text/csv",
        lead_time_days=7,
    )

    assert success is True
    mock_forecast.assert_called_once()
    mock_report.assert_called_once()

    job = job_store.get(job_id)
    assert job["status"] == "done"
    assert len(job["recommendations"]) > 0
    # These three keys only get populated by build_pipeline_extras —
    # their presence (even as empty lists) confirms it actually ran.
    assert "suppliers" in job
    assert "supplier_switches" in job
    assert "transfers" in job
    assert "events" in job
    assert "timeseries" in job
    assert job["report"] == "تقرير تجريبي — كل شيء يعمل بشكل سليم."


@patch("ml.model.forecast", side_effect=_fake_forecast)
@patch("reporting.report_generator.generate_report", return_value="تقرير")
def test_run_full_pipeline_with_pricing_and_stock_columns(mock_report, mock_forecast):
    """
    Same end-to-end run, but with optional business columns present
    (unit_price, current_stock) — exercises extract_optional_signals
    feeding into recommend() through the full orchestrator, not just
    in isolation like test_recommender.py does.
    """
    rows = ["date,store,item,sales,unit_price,current_stock"]
    dates = pd.date_range("2024-01-01", periods=40, freq="D")
    for d in dates:
        rows.append(f"{d.date()},S1,ITEM_A,{10 + (d.dayofyear % 5)},25.0,500")
    csv_bytes = ("\n".join(rows)).encode("utf-8")

    job_id = "test-job-e2e-pricing"
    job_store.create(job_id)

    success = run_full_pipeline(
        job_id=job_id, source=csv_bytes, filename="sales.csv",
        mime_type="text/csv", lead_time_days=7,
    )

    assert success is True
    job = job_store.get(job_id)
    assert job["status"] == "done"
    assert job["recommendations"][0]["unit_price"] == 25.0


@patch("ml.model.forecast", side_effect=_fake_forecast)
def test_run_full_pipeline_falls_back_to_default_report_on_llm_failure(mock_forecast):
    """
    If the LLM report call fails, the pipeline must still complete
    successfully with a graceful fallback message — not crash.
    """
    from reporting.report_generator import ReportGeneratorError

    rows = ["date,store,item,sales"]
    dates = pd.date_range("2024-01-01", periods=40, freq="D")
    for d in dates:
        rows.append(f"{d.date()},S1,ITEM_A,{10 + (d.dayofyear % 5)}")
    csv_bytes = ("\n".join(rows)).encode("utf-8")

    job_id = "test-job-e2e-llm-failure"
    job_store.create(job_id)

    with patch(
        "reporting.report_generator.generate_report",
        side_effect=ReportGeneratorError("API unavailable"),
    ):
        success = run_full_pipeline(
            job_id=job_id, source=csv_bytes, filename="sales.csv",
            mime_type="text/csv", lead_time_days=7,
        )

    assert success is True   # report failure is non-fatal
    job = job_store.get(job_id)
    assert job["status"] == "done"
    assert "تعذّر" in job["report"]   # graceful fallback message


def test_run_full_pipeline_fails_gracefully_on_unparseable_data():
    job_id = "test-job-e2e-bad-data"
    job_store.create(job_id)

    success = run_full_pipeline(
        job_id=job_id,
        source=b"this is not a csv at all, just garbage bytes \x00\x01",
        filename="garbage.csv",
        mime_type="text/csv",
        lead_time_days=7,
    )

    assert success is False
    job = job_store.get(job_id)
    assert job["status"] == "failed"
