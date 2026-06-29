"""
tests/conftest.py
───────────────────
Shared pytest fixtures used across the test suite.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

# Make the backend package importable when running `pytest` from the
# backend/ directory (where this tests/ folder lives).
sys.path.insert(0, str(Path(__file__).parent.parent))

# Force CPU + disable auth/network-touching env vars before any app
# module is imported, so tests never accidentally try to hit Redis,
# Celery, OpenRouter, or a GPU.
os.environ.setdefault("CHRONOS_DEVICE", "cpu")
os.environ.setdefault("API_KEYS", "")
os.environ.setdefault("ENV", "test")


@pytest.fixture
def clean_sales_df() -> pd.DataFrame:
    """
    A minimal, already-clean DataFrame matching the canonical schema:
    date | store | item | sales

    Two stores × two items × 40 days = 160 rows, stable demand pattern
    (no seasonality, no outliers) — good default for "happy path" tests.
    """
    dates = pd.date_range("2024-01-01", periods=40, freq="D")
    rows = []
    for store in ["S1", "S2"]:
        for item in ["ITEM_A", "ITEM_B"]:
            for i, d in enumerate(dates):
                rows.append({
                    "date":  d,
                    "store": store,
                    "item":  item,
                    "sales": 10 + (i % 5),   # mild variation, always positive
                })
    return pd.DataFrame(rows)


@pytest.fixture
def messy_sales_df() -> pd.DataFrame:
    """
    A DataFrame with common real-world issues: mixed-case/aliased
    column names, string dates, a negative sales value, and a few
    nulls — used to exercise fast_validator / smart_cleaner paths.
    """
    return pd.DataFrame({
        "Date":  ["2024-01-01", "2024-01-02", "2024-01-03", None, "2024-01-05"],
        "Store": ["S1", "S1", "S1", "S1", "S1"],
        "Item":  ["ITEM_A", "ITEM_A", "ITEM_A", "ITEM_A", "ITEM_A"],
        "Sales": [10, -5, 12, 8, 9],
    })


@pytest.fixture
def forecast_df_for(clean_sales_df: pd.DataFrame) -> pd.DataFrame:
    """
    A synthetic 90-day forecast DataFrame shaped like ml.model.forecast()'s
    output, for every (store, item) pair in clean_sales_df — without
    actually running Chronos (which needs torch + network access to
    download model weights).
    """
    pairs = clean_sales_df[["store", "item"]].drop_duplicates().values.tolist()
    future_dates = pd.date_range("2024-02-10", periods=90, freq="D")

    rows = []
    for store, item in pairs:
        for d in future_dates:
            rows.append({
                "date":            d,
                "store":           store,
                "item":            item,
                "pred_sales":      12.0,
                "pred_sales_low":  8.0,
                "pred_sales_high": 16.0,
            })
    return pd.DataFrame(rows)
