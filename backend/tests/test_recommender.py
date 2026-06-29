"""
tests/test_recommender.py
────────────────────────────
Tests for ml/recommender.py — the core inventory-recommendation logic.

Covers:
  - CV → buffer tier mapping
  - recommend() happy path (shape, types, basic sanity of numbers)
  - Financial fields (capital_tied_up / savings_value) only appear when
    a price is actually available
  - current_stock is resolved per (store, item), not per item alone
  - Seasonal warning fires only with a real seasonal concentration
"""

from __future__ import annotations

import pandas as pd
import pytest

from ml.recommender import (
    recommend,
    ItemRecommendation,
    _compute_cv,
    _cv_to_buffer,
)


# ── _cv_to_buffer ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("cv,expected_buffer", [
    (0.0,   0.10),
    (0.19,  0.10),
    (0.20,  0.20),   # boundary — exactly 0.2 goes to medium tier
    (0.35,  0.20),
    (0.49,  0.20),
    (0.50,  0.35),   # boundary — exactly 0.5 goes to high tier
    (1.50,  0.35),
])
def test_cv_to_buffer_tiers(cv, expected_buffer):
    assert _cv_to_buffer(cv) == expected_buffer


# ── _compute_cv ──────────────────────────────────────────────────────────────

def test_compute_cv_empty_series_returns_zero():
    assert _compute_cv(pd.Series([], dtype=float)) == 0.0


def test_compute_cv_zero_mean_returns_zero():
    # All-zero sales → mean is 0 → would divide by zero without the guard
    assert _compute_cv(pd.Series([0, 0, 0])) == 0.0


def test_compute_cv_constant_series_is_zero_volatility():
    # No variation at all → CV should be exactly 0
    assert _compute_cv(pd.Series([10, 10, 10, 10])) == 0.0


def test_compute_cv_increases_with_volatility():
    stable   = pd.Series([10, 11, 9, 10, 10])
    volatile = pd.Series([1, 50, 2, 45, 3])
    assert _compute_cv(volatile) > _compute_cv(stable)


# ── recommend() happy path ───────────────────────────────────────────────────

def test_recommend_returns_one_row_per_store_item_pair(clean_sales_df, forecast_df_for):
    recs = recommend(history_df=clean_sales_df, forecast_df=forecast_df_for, lead_time_days=7)

    expected_pairs = set(
        clean_sales_df[["store", "item"]].drop_duplicates().itertuples(index=False, name=None)
    )
    actual_pairs = {(r.store, r.item) for r in recs}

    assert actual_pairs == expected_pairs
    assert all(isinstance(r, ItemRecommendation) for r in recs)


def test_recommend_basic_fields_are_non_negative(clean_sales_df, forecast_df_for):
    recs = recommend(history_df=clean_sales_df, forecast_df=forecast_df_for, lead_time_days=7)

    for r in recs:
        assert r.forecast_90d >= 0
        assert r.recommended_stock >= 0
        assert r.reorder_point >= 0
        assert r.buffer_pct in (0.10, 0.20, 0.35)


def test_recommend_without_price_has_no_financial_fields(clean_sales_df, forecast_df_for):
    recs = recommend(history_df=clean_sales_df, forecast_df=forecast_df_for, lead_time_days=7)
    for r in recs:
        assert r.unit_price is None
        assert r.capital_tied_up is None
        assert r.safety_stock_value is None


def test_recommend_with_global_unit_price_populates_financials(clean_sales_df, forecast_df_for):
    recs = recommend(
        history_df=clean_sales_df, forecast_df=forecast_df_for,
        lead_time_days=7, unit_price=10.0,
    )
    for r in recs:
        assert r.unit_price == 10.0
        assert r.capital_tied_up is not None
        assert r.capital_tied_up == pytest.approx(r.recommended_stock * 10.0, rel=1e-3)


def test_per_item_price_overrides_global_unit_price(clean_sales_df, forecast_df_for):
    item_prices = {"ITEM_A": 100.0}   # only ITEM_A has a specific price
    recs = recommend(
        history_df=clean_sales_df, forecast_df=forecast_df_for,
        lead_time_days=7, unit_price=5.0, item_prices=item_prices,
    )
    by_item = {r.item: r for r in recs}
    assert by_item["ITEM_A"].unit_price == 100.0      # overridden
    assert by_item["ITEM_B"].unit_price == 5.0        # falls back to global


def test_current_stock_is_keyed_by_store_and_item_not_item_alone(clean_sales_df, forecast_df_for):
    # Same item, different stock per branch — must not be collapsed/averaged.
    current_stocks = {
        ("S1", "ITEM_A"): 5000.0,   # plenty of stock → should report excess
        ("S2", "ITEM_A"): 0.0,      # no stock at all → no excess
    }
    recs = recommend(
        history_df=clean_sales_df, forecast_df=forecast_df_for,
        lead_time_days=7, unit_price=10.0, current_stocks=current_stocks,
    )
    by_store_item = {(r.store, r.item): r for r in recs}

    s1_item_a = by_store_item[("S1", "ITEM_A")]
    s2_item_a = by_store_item[("S2", "ITEM_A")]

    assert s1_item_a.current_stock == 5000.0
    assert s1_item_a.excess_units is not None and s1_item_a.excess_units > 0

    assert s2_item_a.current_stock == 0.0
    assert s2_item_a.excess_units == 0.0   # no excess when stock is 0


def test_supplier_info_is_passed_through_per_item(clean_sales_df, forecast_df_for):
    supplier_map = {"ITEM_A": "Acme Co."}
    supplier_lead_time_map = {"ITEM_A": 14.0}

    recs = recommend(
        history_df=clean_sales_df, forecast_df=forecast_df_for,
        lead_time_days=7,
        supplier_map=supplier_map,
        supplier_lead_time_map=supplier_lead_time_map,
    )
    by_item = {r.item: r for r in recs}
    assert by_item["ITEM_A"].supplier == "Acme Co."
    assert by_item["ITEM_A"].supplier_lead_time_days == 14.0
    assert by_item["ITEM_B"].supplier is None


def test_recommend_handles_item_with_no_history_gracefully(forecast_df_for):
    # history_df has zero rows for these (store, item) pairs — recommend()
    # must not crash, just treat history as empty (CV defaults to 0).
    empty_history = pd.DataFrame(columns=["date", "store", "item", "sales"])
    recs = recommend(history_df=empty_history, forecast_df=forecast_df_for, lead_time_days=7)

    assert len(recs) > 0
    for r in recs:
        assert r.cv == 0.0
        assert r.buffer_pct == 0.10   # CV=0 → lowest tier


# ── Seasonal warning ──────────────────────────────────────────────────────────

def test_seasonal_warning_fires_for_concentrated_demand(forecast_df_for):
    # 200 days, but 90% of all sales happen in Q4 (Oct-Dec) — a real spike.
    dates = pd.date_range("2024-01-01", periods=200, freq="D")
    rows = []
    for d in dates:
        sales = 100 if d.quarter == 4 else 2
        rows.append({"date": d, "store": "S1", "item": "ITEM_A", "sales": sales})
    history = pd.DataFrame(rows)

    fc = pd.DataFrame({
        "date":            pd.date_range("2024-08-01", periods=90, freq="D"),
        "store":           "S1",
        "item":            "ITEM_A",
        "pred_sales":      10.0,
        "pred_sales_low":  5.0,
        "pred_sales_high": 15.0,
    })

    recs = recommend(history_df=history, forecast_df=fc, lead_time_days=7)
    assert recs[0].seasonal_warning is True
    assert "الربع" in recs[0].warning_message   # Arabic quarter name present


def test_seasonal_warning_does_not_fire_for_evenly_spread_demand():
    # A full year of perfectly flat demand, spread evenly across all four
    # quarters — no single quarter should dominate, so no seasonal warning.
    dates = pd.date_range("2024-01-01", periods=365, freq="D")
    history = pd.DataFrame({
        "date":  dates,
        "store": "S1",
        "item":  "ITEM_A",
        "sales": [10] * len(dates),
    })
    fc = pd.DataFrame({
        "date":            pd.date_range("2025-01-01", periods=90, freq="D"),
        "store":           "S1",
        "item":            "ITEM_A",
        "pred_sales":      10.0,
        "pred_sales_low":  8.0,
        "pred_sales_high": 12.0,
    })

    recs = recommend(history_df=history, forecast_df=fc, lead_time_days=7)
    assert recs[0].seasonal_warning is False


def test_seasonal_warning_skipped_for_short_history(forecast_df_for):
    # Less than 30 rows of history — too short to judge seasonality reliably.
    short_history = pd.DataFrame({
        "date":  pd.date_range("2024-01-01", periods=10, freq="D"),
        "store": "S1",
        "item":  "ITEM_A",
        "sales": [100] * 10,
    })
    recs = recommend(history_df=short_history, forecast_df=forecast_df_for, lead_time_days=7)
    by_item = {r.item: r for r in recs if r.store == "S1"}
    assert by_item["ITEM_A"].seasonal_warning is False
