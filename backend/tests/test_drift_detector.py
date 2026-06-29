"""
tests/test_drift_detector.py
────────────────────────────────
Tests for monitoring/drift_detector.py — self-contained data-quality
checks (missing values, outliers, zero-sales streaks, short history).
"""

from __future__ import annotations

import pandas as pd

from monitoring.drift_detector import detect_drift, _max_zero_streak, MIN_ROWS_FOR_CHECK


# ── _max_zero_streak ──────────────────────────────────────────────────────────

def test_max_zero_streak_no_zeros():
    assert _max_zero_streak([1, 2, 3, 4]) == 0


def test_max_zero_streak_all_zeros():
    assert _max_zero_streak([0, 0, 0, 0]) == 4


def test_max_zero_streak_finds_longest_run():
    assert _max_zero_streak([1, 0, 0, 5, 0, 0, 0, 2]) == 3


def test_max_zero_streak_empty_list():
    assert _max_zero_streak([]) == 0


# ── detect_drift: skip path ──────────────────────────────────────────────────

def test_skips_check_when_too_few_rows():
    df = pd.DataFrame({
        "date":  pd.date_range("2024-01-01", periods=5, freq="D"),
        "store": "S1", "item": "ITEM_A", "sales": [10, 11, 9, 10, 12],
    })
    assert len(df) < MIN_ROWS_FOR_CHECK
    report = detect_drift(df)
    assert report.has_drift is False
    assert report.skipped_reason != ""
    assert report.total_checked == 0


# ── detect_drift: clean data ──────────────────────────────────────────────────

def test_clean_data_reports_no_drift(clean_sales_df):
    # clean_sales_df has 160 rows, no nulls, no outliers, no long zero
    # streaks, and spans ~40 days. It IS shorter than MIN_HISTORY_DAYS (90),
    # so that one check will fire — but nothing else should.
    report = detect_drift(clean_sales_df)
    fired = {d.feature for d in report.feature_details if d.is_drifted}
    assert fired == {"history_span_days"}


# ── detect_drift: missing values ─────────────────────────────────────────────

def test_flags_high_null_ratio_in_sales():
    n = 50
    sales = [10] * n
    for i in range(0, 10):   # 20% nulls — above the 5% threshold
        sales[i] = None
    df = pd.DataFrame({
        "date":  pd.date_range("2024-01-01", periods=n, freq="D"),
        "store": "S1", "item": "ITEM_A", "sales": sales,
    })
    report = detect_drift(df)
    assert report.has_drift is True
    assert any("sales" in a for a in report.alerts)


def test_low_null_ratio_does_not_flag():
    n = 100
    sales = [10] * n
    sales[0] = None   # 1% nulls — below the 5% threshold
    df = pd.DataFrame({
        "date":  pd.date_range("2024-01-01", periods=n, freq="D"),
        "store": "S1", "item": "ITEM_A", "sales": sales,
    })
    report = detect_drift(df)
    missing_sales_check = next(d for d in report.feature_details if d.feature == "missing_sales")
    assert missing_sales_check.is_drifted is False


# ── detect_drift: outliers ───────────────────────────────────────────────────

def test_flags_extreme_sales_outliers():
    import random
    random.seed(42)
    n = 200
    # Realistic variance (8-12) so IQR is non-zero — a perfectly flat
    # baseline (all 10s) gives IQR=0 and the outlier check is a no-op
    # by design (see drift_detector.py's `if iqr > 0` guard).
    sales = [random.randint(8, 12) for _ in range(n)]
    for i in range(5):
        sales[i] = 100000   # extreme spikes far beyond Q3 + 5*IQR
    df = pd.DataFrame({
        "date":  pd.date_range("2024-01-01", periods=n, freq="D"),
        "store": "S1", "item": "ITEM_A", "sales": sales,
    })
    report = detect_drift(df)
    outlier_check = next(d for d in report.feature_details if d.feature == "sales_outliers")
    assert outlier_check.is_drifted is True


def test_no_outliers_in_uniform_data(clean_sales_df):
    report = detect_drift(clean_sales_df)
    outlier_check = next(d for d in report.feature_details if d.feature == "sales_outliers")
    assert outlier_check.is_drifted is False


# ── detect_drift: zero-sales streaks ─────────────────────────────────────────

def test_flags_long_zero_sales_streak():
    n = 60
    sales = [10] * n
    sales[10:35] = [0] * 25   # 25-day streak, above the 14-day threshold
    df = pd.DataFrame({
        "date":  pd.date_range("2024-01-01", periods=n, freq="D"),
        "store": "S1", "item": "ITEM_A", "sales": sales,
    })
    report = detect_drift(df)
    streak_check = next(d for d in report.feature_details if d.feature == "zero_sales_streak")
    assert streak_check.is_drifted is True
    assert any("ITEM_A" in a for a in report.alerts)


def test_short_zero_streak_does_not_flag():
    n = 60
    sales = [10] * n
    sales[10:15] = [0] * 5   # only 5-day streak, below the 14-day threshold
    df = pd.DataFrame({
        "date":  pd.date_range("2024-01-01", periods=n, freq="D"),
        "store": "S1", "item": "ITEM_A", "sales": sales,
    })
    report = detect_drift(df)
    streak_check = next(d for d in report.feature_details if d.feature == "zero_sales_streak")
    assert streak_check.is_drifted is False


# ── detect_drift: short history ──────────────────────────────────────────────

def test_flags_short_overall_history():
    n = 35   # > MIN_ROWS_FOR_CHECK (30) but < MIN_HISTORY_DAYS (90)
    df = pd.DataFrame({
        "date":  pd.date_range("2024-01-01", periods=n, freq="D"),
        "store": "S1", "item": "ITEM_A", "sales": [10] * n,
    })
    report = detect_drift(df)
    history_check = next(d for d in report.feature_details if d.feature == "history_span_days")
    assert history_check.is_drifted is True


def test_long_history_does_not_flag():
    n = 120   # > MIN_HISTORY_DAYS (90)
    df = pd.DataFrame({
        "date":  pd.date_range("2024-01-01", periods=n, freq="D"),
        "store": "S1", "item": "ITEM_A", "sales": [10] * n,
    })
    report = detect_drift(df)
    history_check = next(d for d in report.feature_details if d.feature == "history_span_days")
    assert history_check.is_drifted is False


# ── DriftReport.summary() ─────────────────────────────────────────────────────

def test_summary_mentions_skip_reason_when_skipped():
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=3, freq="D"),
        "store": "S1", "item": "ITEM_A", "sales": [1, 2, 3],
    })
    report = detect_drift(df)
    assert "تخطيه" in report.summary()


def test_summary_reports_clean_when_no_drift():
    n = 120
    df = pd.DataFrame({
        "date":  pd.date_range("2024-01-01", periods=n, freq="D"),
        "store": "S1", "item": "ITEM_A", "sales": [10] * n,
    })
    report = detect_drift(df)
    assert "لا مشاكل" in report.summary()
