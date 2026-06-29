"""
tests/test_schema.py
────────────────────────
Tests for data_agent/schema.py — optional business-column detection
(unit_price / current_stock / supplier / supplier_lead_time_days).

This is the fix that preserves per-row pricing/stock/supplier data
through cleaning instead of silently dropping it (see schema.py's
module docstring for the bug this fixed).
"""

from __future__ import annotations

import pandas as pd

from data_agent.schema import (
    map_optional_columns,
    attach_optional_columns,
    REQUIRED_COLUMNS,
)


# ── map_optional_columns ───────────────────────────────────────────────────────

def test_maps_exact_canonical_name():
    result = map_optional_columns(["unit_price"])
    assert result == {"unit_price": "unit_price"}


def test_maps_english_alias():
    result = map_optional_columns(["cost"])
    assert result == {"cost": "unit_price"}


def test_maps_arabic_alias():
    result = map_optional_columns(["المورد"])
    assert result == {"المورد": "supplier"}


def test_is_case_insensitive():
    result = map_optional_columns(["UNIT_PRICE"])
    assert result == {"UNIT_PRICE": "unit_price"}


def test_unrecognised_column_is_not_mapped():
    result = map_optional_columns(["some_random_column"])
    assert result == {}


def test_does_not_fuzzy_match_partial_strings():
    # "pricing_notes" should NOT match "price" — exact alias match only,
    # to avoid silently corrupting financial numbers (see schema.py docstring).
    result = map_optional_columns(["pricing_notes"])
    assert result == {}


def test_maps_multiple_distinct_columns():
    result = map_optional_columns(["price", "supplier_name", "lead_time_days"])
    assert result == {
        "price":            "unit_price",
        "supplier_name":    "supplier",
        "lead_time_days":   "supplier_lead_time_days",
    }


def test_each_canonical_name_used_at_most_once():
    # Two columns that both alias to "unit_price" — only the first
    # encountered should be mapped; the second is left unmapped to
    # avoid ambiguous double-mapping.
    result = map_optional_columns(["price", "cost"])
    assert len(result) == 1
    assert list(result.values()) == ["unit_price"]


# ── attach_optional_columns ────────────────────────────────────────────────────

def test_attach_adds_recognised_optional_column():
    df_original = pd.DataFrame({
        "date": ["2024-01-01"], "store": ["S1"], "item": ["ITEM_A"],
        "sales": [10], "unit_price": [5.5],
    })
    df_required = df_original[REQUIRED_COLUMNS]

    merged, added = attach_optional_columns(
        df_required, df_original, consumed_original_names=set(REQUIRED_COLUMNS)
    )
    assert "unit_price" in merged.columns
    assert merged["unit_price"].iloc[0] == 5.5
    assert added == ["unit_price"]


def test_attach_coerces_numeric_optional_columns():
    df_original = pd.DataFrame({
        "date": ["2024-01-01"], "store": ["S1"], "item": ["ITEM_A"],
        "sales": [10], "current_stock": ["250"],   # string, should become numeric
    })
    df_required = df_original[REQUIRED_COLUMNS]

    merged, added = attach_optional_columns(
        df_required, df_original, consumed_original_names=set(REQUIRED_COLUMNS)
    )
    assert pd.api.types.is_numeric_dtype(merged["current_stock"])
    assert merged["current_stock"].iloc[0] == 250.0


def test_attach_does_not_coerce_non_numeric_optional_columns():
    df_original = pd.DataFrame({
        "date": ["2024-01-01"], "store": ["S1"], "item": ["ITEM_A"],
        "sales": [10], "supplier": ["Acme Co."],
    })
    df_required = df_original[REQUIRED_COLUMNS]

    merged, added = attach_optional_columns(
        df_required, df_original, consumed_original_names=set(REQUIRED_COLUMNS)
    )
    assert merged["supplier"].iloc[0] == "Acme Co."


def test_attach_returns_unchanged_df_when_no_optional_columns_present():
    df_original = pd.DataFrame({
        "date": ["2024-01-01"], "store": ["S1"], "item": ["ITEM_A"], "sales": [10],
    })
    df_required = df_original[REQUIRED_COLUMNS]

    merged, added = attach_optional_columns(
        df_required, df_original, consumed_original_names=set(REQUIRED_COLUMNS)
    )
    assert added == []
    assert list(merged.columns) == REQUIRED_COLUMNS


def test_attach_skips_columns_already_consumed_as_required():
    # A column named "store" should never be reinterpreted as an
    # optional business column just because it appears in df_original.
    df_original = pd.DataFrame({
        "date": ["2024-01-01"], "store": ["S1"], "item": ["ITEM_A"], "sales": [10],
    })
    df_required = df_original[REQUIRED_COLUMNS]

    merged, added = attach_optional_columns(
        df_required, df_original, consumed_original_names=set(REQUIRED_COLUMNS)
    )
    assert "store" not in added
