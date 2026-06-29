"""
ml/model.py
────────────
Chronos T5-Large inference — zero-shot demand forecasting.

Replaces the previous XGBoost model that was trained on the Favorita
grocery dataset (Ecuador, 2013-2017) and required Ecuador-specific
features (oil prices, Ecuador holidays, store clusters).

Why Chronos?
  - Zero-shot: works on ANY sales data without retraining.
  - No domain-specific features needed — only the sales numbers.
  - Returns confidence intervals (low / median / high) not just a
    single point estimate, enabling risk-aware stock decisions.

Model sizes vs VRAM:
  chronos-t5-small  (~250 MB,  ~1 GB VRAM)
  chronos-t5-base   (~500 MB,  ~2 GB VRAM)
  chronos-t5-large  (~800 MB,  ~4 GB VRAM)  ← default (RTX 4050 6GB)
  chronos-t5-xl     (~3  GB,  ~10 GB VRAM)

On CPU: set CHRONOS_DEVICE=cpu in .env (slower but works everywhere).

Run with:
  pip install chronos-forecasting torch
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

CHRONOS_MODEL   = os.getenv("CHRONOS_MODEL",  "amazon/chronos-t5-large")
_DEFAULT_DEVICE = "cuda"  # overridden to "cpu" below if CUDA unavailable
FORECAST_DAYS   = 90

def _resolve_device() -> str:
    requested = os.getenv("CHRONOS_DEVICE", _DEFAULT_DEVICE)
    if requested == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                logger.warning(
                    "CHRONOS_DEVICE=cuda but CUDA not available — falling back to CPU. "
                    "Set CHRONOS_DEVICE=cpu in .env to suppress this warning."
                )
                return "cpu"
        except ImportError:
            return "cpu"
    return requested

CHRONOS_DEVICE = _resolve_device()

# ── Pipeline singleton ────────────────────────────────────────────────────────

_pipeline = None
_pipeline_lock = None


def _get_lock():
    global _pipeline_lock
    if _pipeline_lock is None:
        import threading
        _pipeline_lock = threading.Lock()
    return _pipeline_lock


def _load_pipeline():
    """Load Chronos pipeline once and cache (thread-safe singleton)."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    with _get_lock():
        if _pipeline is not None:          # double-checked locking
            return _pipeline

        try:
            from chronos import ChronosPipeline
            import torch

            device = CHRONOS_DEVICE
            # bfloat16 is supported on Ada Lovelace (RTX 40xx) and saves VRAM
            dtype = torch.bfloat16 if device == "cuda" else torch.float32

            logger.info(
                "Loading Chronos pipeline: model=%s  device=%s  dtype=%s",
                CHRONOS_MODEL, device, dtype,
            )

            _pipeline = ChronosPipeline.from_pretrained(
                CHRONOS_MODEL,
                device_map=device,
                dtype=dtype,
            )
            logger.info("Chronos pipeline loaded successfully.")

        except Exception as exc:
            raise ModelLoadError(
                f"Failed to load Chronos pipeline: {exc}\n"
                "Install with: pip install chronos-forecasting torch"
            ) from exc

    return _pipeline


# ── Main entry point ──────────────────────────────────────────────────────────

def forecast(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate a 90-day sales forecast for every (store, item) pair.

    Parameters
    ----------
    df : Clean 4-column DataFrame — date | store | item | sales
         (output of agent_pipeline.run_pipeline)

    Returns
    -------
    pd.DataFrame with columns:
        date, store, item, pred_sales,
        pred_sales_low, pred_sales_high

        pred_sales       = median forecast  (use for expected stock)
        pred_sales_low   = 10th percentile  (optimistic scenario)
        pred_sales_high  = 90th percentile  (conservative / safe stock)

    Raises
    ------
    ModelLoadError : if Chronos cannot be loaded
    """
    pipeline = _load_pipeline()

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    pairs = df[["store", "item"]].drop_duplicates().values.tolist()
    logger.info(
        "Forecasting %d store×item pairs over %d days with Chronos",
        len(pairs), FORECAST_DAYS,
    )

    all_forecasts: list[pd.DataFrame] = []

    # Batch inference: group contexts by length bucket for efficiency on CPU
    BATCH_SIZE = int(os.getenv("CHRONOS_BATCH_SIZE", "8"))
    import torch

    # Pre-build all histories — and remember each pair's actual last date,
    # so the forecast continues from where the real data ends instead of
    # silently anchoring to "today" (see _forecast_pair).
    histories   = []
    last_dates  = []
    for store, item in pairs:
        mask     = (df["store"] == store) & (df["item"] == item)
        pair_df  = df[mask].sort_values("date")
        history  = pair_df["sales"].clip(lower=0).fillna(0).values
        if len(history) == 0:
            history   = np.array([0.0])
            last_date = pd.Timestamp.today().normalize()
        else:
            last_date = pair_df["date"].iloc[-1]
        histories.append(history)
        last_dates.append(last_date)

    # Process in batches
    for batch_start in range(0, len(pairs), BATCH_SIZE):
        batch_pairs    = pairs[batch_start:batch_start + BATCH_SIZE]
        batch_hist     = histories[batch_start:batch_start + BATCH_SIZE]
        batch_lastdate = last_dates[batch_start:batch_start + BATCH_SIZE]

        for (store, item), history, last_date in zip(batch_pairs, batch_hist, batch_lastdate):
            pair_fc = _forecast_pair(pipeline, history, store, item, last_date)
            all_forecasts.append(pair_fc)

        if (batch_start // BATCH_SIZE) % 5 == 0:
            logger.info(
                "Forecast progress: %d / %d pairs done",
                min(batch_start + BATCH_SIZE, len(pairs)), len(pairs),
            )

    result = pd.concat(all_forecasts, ignore_index=True)
    logger.info("Forecast complete — %d rows generated", len(result))
    return result


# ── Per-pair forecast ─────────────────────────────────────────────────────────

def _forecast_pair(
    pipeline,
    history: np.ndarray,
    store,
    item,
    last_date: pd.Timestamp,
) -> pd.DataFrame:
    """Run Chronos on one (store, item) history and return forecast rows."""
    import torch

    # Need at least 1 data point; pad very short series
    if len(history) == 0:
        history = np.array([0.0])

    context = torch.tensor(history, dtype=torch.float32).unsqueeze(0)

    # predict() returns a tensor of shape (num_samples, prediction_length)
    # quantile() gives us low / median / high
    forecast_tensor = pipeline.predict(
        context,
        prediction_length=FORECAST_DAYS,
        num_samples=20,       # more samples = smoother quantiles
    )

    low    = forecast_tensor[0].quantile(0.10, dim=0).numpy()
    median = forecast_tensor[0].quantile(0.50, dim=0).numpy()
    high   = forecast_tensor[0].quantile(0.90, dim=0).numpy()

    # Clip negatives (sales can't be negative)
    low    = np.clip(low,    0, None)
    median = np.clip(median, 0, None)
    high   = np.clip(high,   0, None)

    # Build future date range starting the day AFTER this pair's actual
    # last observed date — not "today". Falls back to today only when a
    # pair has no dated history at all (handled by the caller).
    future_dates = pd.date_range(
        start=pd.Timestamp(last_date).normalize() + pd.Timedelta(days=1),
        periods=FORECAST_DAYS,
        freq="D",
    )

    return pd.DataFrame({
        "date":             future_dates,
        "store":            store,
        "item":             item,
        "pred_sales":       np.round(median, 2),
        "pred_sales_low":   np.round(low,    2),
        "pred_sales_high":  np.round(high,   2),
    })


# ── Exceptions ────────────────────────────────────────────────────────────────

class ModelLoadError(Exception):
    """Raised when the Chronos pipeline cannot be loaded."""