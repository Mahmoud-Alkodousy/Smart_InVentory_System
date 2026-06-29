"""
data_agent/schema.py
──────────────────────
Single source of truth for the REQUIRED columns and the OPTIONAL
business-enrichment columns the pipeline understands.

Why this file exists
─────────────────────
Before this fix, both the "direct" route (agent_pipeline._normalise_columns)
and the "smart_cleaned" route (smart_cleaner.clean) hard-sliced the
DataFrame down to exactly [date, store, item, sales] before returning it.

That silently destroyed any unit_price / current_stock / supplier /
lead-time columns the user uploaded — which meant the "per-item pricing"
and "current stock savings" features in ml/recommender.py only ever
worked through the single global `unit_price` form field, never through
per-row data columns, even though the recommender was written to support
exactly that.

OPTIONAL_ALIASES below lets every uploaded file's extra business columns
survive cleaning (under a canonical lower_snake_case name), with aliases
for common English/Arabic header variants — the same idea as
smart_cleaner.ALIASES, just for optional, non-blocking columns.
"""

from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS: list[str] = ["date", "store", "item", "sales"]

# canonical_name → list of accepted header aliases (case-insensitive, exact match)
OPTIONAL_ALIASES: dict[str, list[str]] = {
    "unit_price": [
        "unit_price", "price", "cost", "unit_cost", "item_price",
        "سعر", "السعر", "سعر الوحدة", "تكلفة",
    ],
    "current_stock": [
        "current_stock", "on_hand", "stock", "inventory", "qty_on_hand",
        "stock_on_hand", "available_stock", "المخزون", "المخزون الحالي", "الكمية المتوفرة",
    ],
    "supplier": [
        "supplier", "supplier_name", "vendor", "vendor_name",
        "المورد", "اسم المورد", "الموزع",
    ],
    "supplier_lead_time_days": [
        "supplier_lead_time_days", "supplier_lead_time", "lead_time_days",
        "lead_time", "delivery_days", "delivery_time", "supply_days",
        "مدة التوريد", "مدة التوصيل", "أيام التوريد",
    ],
}

# Columns that should be coerced to numeric after extraction
NUMERIC_OPTIONAL_COLUMNS = {"unit_price", "current_stock", "supplier_lead_time_days"}

ALL_OPTIONAL_CANONICAL: list[str] = list(OPTIONAL_ALIASES.keys())


def map_optional_columns(columns: list[str]) -> dict[str, str]:
    """
    Exact (case-insensitive) alias match → {original_column_name: canonical_name}.

    Deliberately NOT fuzzy — optional columns are a "nice to have" enrichment,
    and a wrong fuzzy match here (e.g. mistaking some unrelated column for
    'supplier') would silently corrupt financial numbers. Required columns
    keep using fuzzy matching in smart_cleaner.py; these don't.
    """
    result: dict[str, str] = {}
    used: set[str] = set()
    lower_lookup: dict[str, str] = {}
    for col in columns:
        key = str(col).strip().lower()
        if key not in lower_lookup:
            lower_lookup[key] = col

    for canonical, aliases in OPTIONAL_ALIASES.items():
        for alias in aliases:
            original = lower_lookup.get(alias.lower())
            if original is not None and original not in used:
                result[original] = canonical
                used.add(original)
                break
    return result


def attach_optional_columns(
    df_with_required: pd.DataFrame,
    df_original: pd.DataFrame,
    consumed_original_names: set[str],
) -> tuple[pd.DataFrame, list[str]]:
    """
    Find optional business columns in *df_original* (skipping any column
    name already consumed for date/store/item/sales) and attach them
    (renamed to their canonical name, coerced to numeric where relevant)
    onto *df_with_required*. Returns (merged_df, list_of_canonical_names_added).

    df_with_required and df_original must have the same row order/index.
    """
    candidate_cols = [c for c in df_original.columns if c not in consumed_original_names]
    opt_map = map_optional_columns(candidate_cols)
    if not opt_map:
        return df_with_required, []

    out = df_with_required.copy()
    added: list[str] = []
    for original_name, canonical in opt_map.items():
        series = df_original[original_name]
        if canonical in NUMERIC_OPTIONAL_COLUMNS:
            series = pd.to_numeric(series, errors="coerce")
        out[canonical] = series.values
        added.append(canonical)
    return out, added
