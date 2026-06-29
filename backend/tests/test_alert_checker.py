"""
tests/test_alert_checker.py
───────────────────────────────
Tests for monitoring_jobs/alert_checker.py — decides whether a
scheduled monitoring run should trigger a low-stock / seasonal email.
"""

from __future__ import annotations

from monitoring_jobs.alert_checker import (
    check_alerts,
    build_alert_payload,
    STOCK_RATIO_THRESHOLD,
)


def _rec(item="ITEM_A", store="S1", reorder_point=0, recommended_stock=100,
         avg_daily_demand=5, seasonal_warning=False, warning_message=""):
    return {
        "item": item, "store": store,
        "reorder_point": reorder_point,
        "recommended_stock": recommended_stock,
        "avg_daily_demand": avg_daily_demand,
        "seasonal_warning": seasonal_warning,
        "warning_message": warning_message,
    }


def test_no_alerts_when_stock_is_healthy():
    recs = [_rec(reorder_point=10, recommended_stock=100)]
    result = check_alerts(recs)
    assert result.should_notify is False
    assert result.low_stock_alerts == []
    assert result.seasonal_alerts == []


def test_low_stock_alert_fires_above_threshold():
    # reorder_point (90) > recommended_stock (100) * 0.80 (=80) → should alert
    recs = [_rec(reorder_point=90, recommended_stock=100)]
    result = check_alerts(recs)
    assert result.should_notify is True
    assert len(result.low_stock_alerts) == 1
    assert result.low_stock_alerts[0]["item"] == "ITEM_A"


def test_low_stock_alert_does_not_fire_at_exact_threshold_boundary():
    # reorder_point exactly equal to threshold fraction should NOT fire
    # (the check is strictly greater-than).
    recs = [_rec(reorder_point=100 * STOCK_RATIO_THRESHOLD, recommended_stock=100)]
    result = check_alerts(recs)
    assert result.should_notify is False


def test_zero_recommended_stock_does_not_crash_or_alert():
    # rec_stock <= 0 must not trigger a division-style alert
    recs = [_rec(reorder_point=50, recommended_stock=0)]
    result = check_alerts(recs)
    assert result.should_notify is False


def test_seasonal_warning_triggers_notification():
    recs = [_rec(seasonal_warning=True, warning_message="موسم الذروة قريب")]
    result = check_alerts(recs)
    assert result.should_notify is True
    assert len(result.seasonal_alerts) == 1
    assert result.seasonal_alerts[0]["message"] == "موسم الذروة قريب"


def test_multiple_items_mixed_alerts():
    recs = [
        _rec(item="A", reorder_point=10, recommended_stock=100),           # healthy
        _rec(item="B", reorder_point=90, recommended_stock=100),           # low stock
        _rec(item="C", seasonal_warning=True, warning_message="تحذير"),   # seasonal
    ]
    result = check_alerts(recs)
    assert result.should_notify is True
    assert len(result.low_stock_alerts) == 1
    assert len(result.seasonal_alerts) == 1


def test_empty_recommendations_list_does_not_notify():
    result = check_alerts([])
    assert result.should_notify is False
    assert "لا توجد" in result.summary


def test_missing_fields_default_gracefully():
    # A malformed/partial dict should not raise — defaults to safe values.
    result = check_alerts([{"item": "X"}])
    assert result.should_notify is False


# ── build_alert_payload ────────────────────────────────────────────────────────

def test_build_alert_payload_returns_none_when_nothing_to_notify():
    recs = [_rec(reorder_point=10, recommended_stock=100)]
    result = check_alerts(recs)
    assert build_alert_payload(result) is None


def test_build_alert_payload_merges_low_stock_and_seasonal():
    recs = [
        _rec(item="A", reorder_point=90, recommended_stock=100),
        _rec(item="B", seasonal_warning=True, warning_message="تحذير موسمي"),
    ]
    result = check_alerts(recs)
    payload = build_alert_payload(result)

    assert payload is not None
    items = {p["item"] for p in payload}
    assert items == {"A", "B"}


def test_build_alert_payload_deduplicates_item_in_both_categories():
    # Same (item, store) flagged as BOTH low-stock AND seasonal —
    # should appear only once in the merged payload, prioritising the
    # low-stock entry (which has richer numeric data).
    recs = [
        _rec(item="A", store="S1", reorder_point=90, recommended_stock=100,
             seasonal_warning=True, warning_message="تحذير"),
    ]
    result = check_alerts(recs)
    payload = build_alert_payload(result)

    matching = [p for p in payload if p["item"] == "A" and p["store"] == "S1"]
    assert len(matching) == 1
    assert "reorder_point" in matching[0]   # came from the low-stock branch
