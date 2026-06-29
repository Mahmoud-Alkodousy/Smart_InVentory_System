"""
tests/test_fast_validator.py
───────────────────────────────
Tests for data_agent/fast_validator.py — the zero-LLM-call fast path
that decides whether uploaded data needs cleaning at all.
"""

from __future__ import annotations

import pandas as pd

from data_agent.fast_validator import validate, REQUIRED_COLUMNS


def test_passes_on_already_clean_data():
    df = pd.DataFrame({
        "date":  ["2024-01-01", "2024-01-02", "2024-01-03"],
        "store": ["S1", "S1", "S1"],
        "item":  ["ITEM_A", "ITEM_A", "ITEM_A"],
        "sales": [10, 12, 8],
    })
    result = validate(df)
    assert result.passed is True
    assert result.n_rows == 3
    assert result.n_stores == 1
    assert result.n_items == 1
    assert result.errors == []


def test_fails_when_required_column_missing():
    df = pd.DataFrame({
        "date":  ["2024-01-01", "2024-01-02"],
        "store": ["S1", "S1"],
        "sales": [10, 12],
        # "item" column missing
    })
    result = validate(df)
    assert result.passed is False
    assert any("item" in e for e in result.errors)


def test_fails_on_too_few_rows():
    df = pd.DataFrame({
        "date":  ["2024-01-01"],
        "store": ["S1"],
        "item":  ["ITEM_A"],
        "sales": [10],
    })
    result = validate(df)
    assert result.passed is False
    assert any("row" in e.lower() for e in result.errors)


def test_fails_on_unparseable_date():
    df = pd.DataFrame({
        "date":  ["not-a-date", "also-not-a-date"],
        "store": ["S1", "S1"],
        "item":  ["ITEM_A", "ITEM_A"],
        "sales": [10, 12],
    })
    result = validate(df)
    assert result.passed is False


def test_fails_on_non_numeric_sales():
    df = pd.DataFrame({
        "date":  ["2024-01-01", "2024-01-02"],
        "store": ["S1", "S1"],
        "item":  ["ITEM_A", "ITEM_A"],
        "sales": ["high", "low"],
    })
    result = validate(df)
    assert result.passed is False
    assert any("sales" in e.lower() for e in result.errors)


def test_fails_on_negative_sales():
    df = pd.DataFrame({
        "date":  ["2024-01-01", "2024-01-02"],
        "store": ["S1", "S1"],
        "item":  ["ITEM_A", "ITEM_A"],
        "sales": [10, -5],
    })
    result = validate(df)
    assert result.passed is False
    assert any("negative" in e.lower() for e in result.errors)


def test_fails_on_null_values_in_required_columns():
    df = pd.DataFrame({
        "date":  ["2024-01-01", None],
        "store": ["S1", "S1"],
        "item":  ["ITEM_A", "ITEM_A"],
        "sales": [10, 12],
    })
    result = validate(df)
    assert result.passed is False
    assert any("null" in e.lower() for e in result.errors)


def test_column_names_are_case_and_whitespace_insensitive():
    df = pd.DataFrame({
        " Date ":  ["2024-01-01", "2024-01-02"],
        "STORE":   ["S1", "S1"],
        "Item":    ["ITEM_A", "ITEM_A"],
        "sales":   [10, 12],
    })
    result = validate(df)
    assert result.passed is True


def test_warns_but_passes_on_duplicate_rows():
    df = pd.DataFrame({
        "date":  ["2024-01-01", "2024-01-01", "2024-01-02"],
        "store": ["S1", "S1", "S1"],
        "item":  ["ITEM_A", "ITEM_A", "ITEM_A"],
        "sales": [10, 10, 12],
    })
    result = validate(df)
    assert result.passed is True
    assert any("duplicate" in w.lower() for w in result.warnings)


def test_recognised_optional_column_produces_warning_not_error():
    df = pd.DataFrame({
        "date":       ["2024-01-01", "2024-01-02"],
        "store":      ["S1", "S1"],
        "item":       ["ITEM_A", "ITEM_A"],
        "sales":      [10, 12],
        "unit_price": [5.0, 5.0],
    })
    result = validate(df)
    assert result.passed is True
    assert any("سعر" in w or "unit_price" in w for w in result.warnings)


def test_required_columns_constant_is_stable():
    # Locks in the canonical schema so an accidental rename anywhere
    # else in the pipeline gets caught immediately by this test.
    assert REQUIRED_COLUMNS == ["date", "store", "item", "sales"]
