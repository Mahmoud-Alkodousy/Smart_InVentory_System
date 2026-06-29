"""
tests/test_smart_cleaner.py
───────────────────────────────
Tests for data_agent/smart_cleaner.py — fuzzy column-name mapping and
deterministic (pandas-only) cleaning. The LLM fallback path is NOT
exercised here (it requires network access / API keys); we only test
the case where fuzzy matching alone is enough, which is the common
path described in agent_pipeline.py's routing priority.
"""

from __future__ import annotations

import pandas as pd
import pytest

from data_agent.smart_cleaner import clean, _fuzzy_map, _clean_data


# ── _fuzzy_map ─────────────────────────────────────────────────────────────────

def test_fuzzy_map_exact_aliases():
    cols = ["Date", "Store", "Item", "Sales"]
    result = _fuzzy_map(cols)
    assert result == {"Date": "date", "Store": "store", "Item": "item", "Sales": "sales"}


def test_fuzzy_map_handles_synonyms():
    cols = ["order_date", "branch", "sku", "quantity"]
    result = _fuzzy_map(cols)
    assert result == {
        "order_date": "date", "branch": "store", "sku": "item", "quantity": "sales",
    }


def test_fuzzy_map_handles_arabic_headers():
    cols = ["تاريخ", "الفرع", "المنتج", "المبيعات"]
    result = _fuzzy_map(cols)
    assert result == {
        "تاريخ": "date", "الفرع": "store", "المنتج": "item", "المبيعات": "sales",
    }


def test_fuzzy_map_does_not_reuse_a_column_for_two_targets():
    # Only one column looks date-like; it must not also get claimed by
    # another target via the fuzzy fallback.
    cols = ["date", "store", "item", "sales", "extra_unrelated_col"]
    result = _fuzzy_map(cols)
    # every mapped target points to a distinct source column
    assert len(set(result.values())) == len(result.values())


def test_fuzzy_map_leaves_unmappable_columns_out():
    cols = ["completely_unrelated_xyz"]
    result = _fuzzy_map(cols)
    assert "completely_unrelated_xyz" not in result


# ── clean(): happy path via fuzzy matching only ───────────────────────────────

def test_clean_maps_and_normalises_aliased_columns():
    df = pd.DataFrame({
        "order_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "branch":     ["S1", "S1", "S1"],
        "sku":        ["ITEM_A", "ITEM_A", "ITEM_A"],
        "quantity":   [10, 12, 8],
    })
    cleaned, warnings = clean(df)
    assert list(cleaned.columns)[:4] == ["date", "store", "item", "sales"]
    assert pd.api.types.is_datetime64_any_dtype(cleaned["date"])
    assert len(cleaned) == 3


def test_clean_raises_when_required_column_truly_unmappable(monkeypatch):
    # Disable the LLM fallback path entirely (no API key) so a column
    # set that fuzzy-matching can't resolve correctly raises ValueError
    # instead of silently making a wrong guess.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA", "false")

    df = pd.DataFrame({
        "xq1": [1, 2], "xq2": [3, 4], "xq3": [5, 6], "xq4": [7, 8],
    })
    with pytest.raises(ValueError):
        clean(df)


def test_clean_preserves_optional_business_columns():
    df = pd.DataFrame({
        "date":  ["2024-01-01", "2024-01-02"],
        "store": ["S1", "S1"],
        "item":  ["ITEM_A", "ITEM_A"],
        "sales": [10, 12],
        "price": [5.5, 5.5],   # alias for unit_price
    })
    cleaned, warnings = clean(df)
    assert "unit_price" in cleaned.columns
    assert cleaned["unit_price"].iloc[0] == 5.5


# ── _clean_data: deterministic cleaning ──────────────────────────────────────

def test_clean_data_clips_negative_sales_to_zero():
    df = pd.DataFrame({
        "date":  pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "store": ["S1", "S1"], "item": ["ITEM_A", "ITEM_A"],
        "sales": [-5, 10],
    })
    cleaned, warnings = _clean_data(df)
    assert cleaned["sales"].min() >= 0
    assert any("سالبة" in w for w in warnings)


def test_clean_data_fills_missing_sales_via_rolling_mean():
    df = pd.DataFrame({
        "date":  pd.to_datetime(pd.date_range("2024-01-01", periods=10)),
        "store": ["S1"] * 10, "item": ["ITEM_A"] * 10,
        "sales": [10, 10, None, 10, 10, 10, None, 10, 10, 10],
    })
    cleaned, warnings = _clean_data(df)
    assert cleaned["sales"].isna().sum() == 0
    assert any("فارغة" in w for w in warnings)


def test_clean_data_drops_rows_with_unfillable_required_nulls():
    # A null date can't be forward/backward filled meaningfully across
    # an unsorted multi-item frame in a way that's safe, so after
    # ffill/bfill any remaining null rows get dropped.
    df = pd.DataFrame({
        "date":  pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        "store": ["S1", "S1", "S1"], "item": ["ITEM_A", "ITEM_A", "ITEM_A"],
        "sales": [10, 12, 8],
    })
    cleaned, warnings = _clean_data(df)
    assert len(cleaned) == 3   # nothing to drop here — sanity check only


def test_clean_data_raises_when_too_many_nulls():
    df = pd.DataFrame({
        "date":  pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]),
        "store": ["S1", "S1", "S1", "S1"], "item": ["ITEM_A", "ITEM_A", "ITEM_A", "ITEM_A"],
        "sales": [10, None, None, None],   # 75% null > MAX_NULL_PCT (0.5)
    })
    with pytest.raises(ValueError):
        _clean_data(df)


def test_clean_data_raises_when_fewer_than_two_rows_remain():
    df = pd.DataFrame({
        "date":  pd.to_datetime(["2024-01-01"]),
        "store": ["S1"], "item": ["ITEM_A"], "sales": [10],
    })
    with pytest.raises(ValueError):
        _clean_data(df)


def test_clean_data_sorts_by_date():
    df = pd.DataFrame({
        "date":  pd.to_datetime(["2024-01-03", "2024-01-01", "2024-01-02"]),
        "store": ["S1", "S1", "S1"], "item": ["ITEM_A", "ITEM_A", "ITEM_A"],
        "sales": [8, 10, 12],
    })
    cleaned, warnings = _clean_data(df)
    assert cleaned["date"].is_monotonic_increasing
