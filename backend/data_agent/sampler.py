"""
data_agent/sampler.py
──────────────────────
Stratified sampling for the Data Fixer Agent.

Rather than feeding the Planner LLM the first N rows
(which may all look clean while corruption hides deeper),
we collect rows from the beginning, middle, end, AND
random positions spread across the full file.

Output: a compact metadata dict the Planner LLM can reason about.
"""

from __future__ import annotations

import random
from typing import Any

import numpy as np
import pandas as pd


# ── Config ────────────────────────────────────────────────────────────────────

N_RANDOM_ROWS   = 13   # random positions across the file
N_BOUNDARY_ROWS = 1    # rows from start and end
TOTAL_SAMPLE    = N_BOUNDARY_ROWS * 2 + N_RANDOM_ROWS  # = 15 rows


# ── Main sampler ──────────────────────────────────────────────────────────────

def build_sample_payload(df: pd.DataFrame, seed: int = 42) -> dict[str, Any]:
    """
    Build the metadata + sample rows dict that gets sent to the Planner LLM.

    Parameters
    ----------
    df   : Raw DataFrame from the loader (no column fixes yet).
    seed : Random seed for reproducibility.

    Returns
    -------
    dict with keys:
        columns        – list of column names
        dtypes         – {col: dtype_str}
        total_rows     – int
        null_counts    – {col: int}
        null_pct       – {col: float}  (0.0–1.0)
        unique_counts  – {col: int}
        sample_rows    – list of row dicts (up to 15 rows)
        numeric_stats  – {col: {mean, std, min, max}} for numeric cols
        sample_strategy– description of how rows were chosen
    """
    n = len(df)
    rng = random.Random(seed)

    # ── Stratified row indices ────────────────────────────────────────────────
    indices: list[int] = []

    # First row(s)
    indices += list(range(min(N_BOUNDARY_ROWS, n)))

    # Last row(s)
    if n > N_BOUNDARY_ROWS:
        indices += list(range(max(n - N_BOUNDARY_ROWS, N_BOUNDARY_ROWS), n))

    # Random positions from the rest
    remaining = [i for i in range(n) if i not in indices]
    random_picks = rng.sample(remaining, min(N_RANDOM_ROWS, len(remaining)))
    indices += sorted(random_picks)

    # De-duplicate and sort
    indices = sorted(set(indices))

    # ── Sample rows ───────────────────────────────────────────────────────────
    sample_df = df.iloc[indices].copy()

    # Convert everything to plain Python types for JSON serialisation
    sample_rows = _to_serialisable(sample_df)

    # ── Column metadata ───────────────────────────────────────────────────────
    null_counts  = df.isnull().sum().to_dict()
    null_pct     = {c: round(v / n, 4) for c, v in null_counts.items()}
    unique_counts = {c: int(df[c].nunique()) for c in df.columns}
    dtypes        = {c: str(df[c].dtype) for c in df.columns}

    # ── Numeric stats ─────────────────────────────────────────────────────────
    numeric_stats: dict[str, dict] = {}
    for col in df.select_dtypes(include=[np.number]).columns:
        s = df[col].dropna()
        if len(s) == 0:
            continue
        numeric_stats[col] = {
            "mean": round(float(s.mean()), 4),
            "std":  round(float(s.std()),  4) if len(s) > 1 else 0.0,
            "min":  round(float(s.min()),  4),
            "max":  round(float(s.max()),  4),
        }

    # ── Strategy description (helps LLM understand the sample) ───────────────
    strategy = (
        f"First {N_BOUNDARY_ROWS} row(s), last {N_BOUNDARY_ROWS} row(s), "
        f"and {len(random_picks)} rows randomly sampled from positions "
        f"across all {n:,} rows."
    )

    return {
        "columns":         list(df.columns),
        "dtypes":          dtypes,
        "total_rows":      n,
        "null_counts":     {c: int(v) for c, v in null_counts.items()},
        "null_pct":        null_pct,
        "unique_counts":   unique_counts,
        "numeric_stats":   numeric_stats,
        "sample_rows":     sample_rows,
        "sample_strategy": strategy,
    }


# ── Serialisation helper ──────────────────────────────────────────────────────

def _to_serialisable(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to a list of plain-Python dicts (JSON-safe)."""
    records = []
    for _, row in df.iterrows():
        record: dict[str, Any] = {}
        for col, val in row.items():
            if pd.isna(val) if not isinstance(val, (list, dict)) else False:
                record[col] = None
            elif isinstance(val, (np.integer,)):
                record[col] = int(val)
            elif isinstance(val, (np.floating,)):
                record[col] = round(float(val), 4)
            elif isinstance(val, pd.Timestamp):
                record[col] = str(val.date())
            else:
                record[col] = val
        records.append(record)
    return records
