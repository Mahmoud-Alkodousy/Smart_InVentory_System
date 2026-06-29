"""
data_agent/planner.py
──────────────────────
Planner LLM — google/gemini-2.5-pro via OpenRouter  (default)
                OR  qwen3:8b via Ollama              (if OLLAMA=True)

Receives the stratified sample payload from sampler.py and
produces a structured plan.md describing exactly what needs
to be fixed in the user's data to produce 4 clean columns:
  date | store | item | sales
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests


# ── Config ────────────────────────────────────────────────────────────────────

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
PLANNER_MODEL      = "google/gemini-2.5-pro"
REQUEST_TIMEOUT    = 60   # seconds

OLLAMA_BASE_URL      = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# Override via env: OLLAMA_PLANNER_MODEL=qwen3:1.7b or llama3.2:3b for faster inference
OLLAMA_PLANNER_MODEL = os.getenv("OLLAMA_PLANNER_MODEL", "qwen3:8b")
# Ollama on CPU can be slow — allow up to 5 min (override with OLLAMA_TIMEOUT=N)
OLLAMA_TIMEOUT       = int(os.getenv("OLLAMA_TIMEOUT", "300"))

_USE_OLLAMA = os.getenv("OLLAMA", "false").strip().lower() in ("true", "1", "yes")


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior data engineer specialising in cleaning sales data for machine learning pipelines.

You will receive a JSON payload describing a user's uploaded sales file.
The payload contains:
  - columns       : list of column names as they appear in the file
  - dtypes        : pandas dtype per column
  - total_rows    : total row count
  - null_counts   : null count per column
  - null_pct      : null fraction per column
  - unique_counts : unique value count per column
  - numeric_stats : {mean, std, min, max} for numeric columns
  - sample_rows   : 15 representative rows sampled from across the file

Your goal is to write a DATA FIX PLAN in Markdown that describes ALL steps
needed to transform this file into a clean DataFrame with exactly these 4 columns:

  date   — datetime, no nulls, format YYYY-MM-DD
  store  — string or int, no nulls, identifies the store/branch
  item   — string or int, no nulls, identifies the product/SKU
  sales  — float >= 0, no nulls

The plan MUST follow this exact structure:

## Column Mapping
- List every rename/merge needed to produce the 4 required columns.
- If a required column is already present with the correct name and clean, write "No change needed".
- If a required column does not exist, write "MISSING — cannot be fixed automatically" and stop.

## Data Quality Fixes
- List every transformation needed: type casting, null filling, negative value handling, deduplication, etc.
- Be specific: name the column, describe the issue, and describe the fix.
- If null filling is needed, specify the strategy (e.g., "fill with 7-day rolling mean per store/item group").

## Columns to Drop
- List any columns that are NOT one of the 4 required columns and should be removed.
- If there are none, write "None".

## Warnings
- List any concerns that cannot be auto-fixed but the user should know about.
- Examples: very high null rates, suspicious value ranges, duplicate rows.

## Confidence
- State your confidence that this plan will fully fix the data: HIGH / MEDIUM / LOW
- If LOW, explain why.

Be concise. Do not include Python code in the plan — that is the Executor's job.
Do not add any text before the first ## heading.
"""


# ── Public API ────────────────────────────────────────────────────────────────

def create_fix_plan(sample_payload: dict[str, Any]) -> str:
    """
    Call the Planner LLM and return the fix plan as a Markdown string.

    Parameters
    ----------
    sample_payload : Output of sampler.build_sample_payload()

    Returns
    -------
    str : Markdown plan (starts with "## Column Mapping")

    Raises
    ------
    PlannerError : if the API call fails or returns an empty plan.
    """
    user_message = (
        "Here is the data file metadata and sample. "
        "Please write the data fix plan.\n\n"
        f"```json\n{json.dumps(sample_payload, indent=2, ensure_ascii=False)}\n```"
    )

    if _USE_OLLAMA:
        return _call_ollama(user_message)
    else:
        return _call_openrouter(user_message)


# ── OpenRouter backend ────────────────────────────────────────────────────────

def _call_openrouter(user_message: str) -> str:
    api_key = _get_openrouter_key()

    payload = {
        "model": PLANNER_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        "temperature": 0.1,
        "max_tokens":  2048,
    }

    try:
        response = requests.post(
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
                "HTTP-Referer":  "https://smart-inventory-manager",
                "X-Title":       "Smart Inventory Manager - Planner",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise PlannerError("Planner LLM request timed out.")
    except requests.exceptions.HTTPError as exc:
        raise PlannerError(f"Planner LLM HTTP error: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise PlannerError(f"Planner LLM network error: {exc}") from exc

    data = response.json()

    try:
        plan = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise PlannerError(
            f"Unexpected response format from Planner LLM: {data}"
        ) from exc

    if not plan:
        raise PlannerError("Planner LLM returned an empty plan.")

    return plan


# ── Ollama backend ────────────────────────────────────────────────────────────

def _call_ollama(user_message: str) -> str:
    url = f"{OLLAMA_BASE_URL}/api/chat"

    payload = {
        "model": OLLAMA_PLANNER_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        "options": {"temperature": 0.1},
        "stream": False,
    }

    try:
        response = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise PlannerError(f"Ollama Planner request timed out after {OLLAMA_TIMEOUT}s (model: {OLLAMA_PLANNER_MODEL}). Try a smaller model via OLLAMA_PLANNER_MODEL env var, e.g. qwen3:1.7b")
    except requests.exceptions.HTTPError as exc:
        raise PlannerError(f"Ollama Planner HTTP error: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise PlannerError(
            f"Ollama Planner network error: {exc}\n"
            f"Is Ollama running? Check: {OLLAMA_BASE_URL}"
        ) from exc

    data = response.json()

    try:
        plan = data["message"]["content"].strip()
    except (KeyError, TypeError) as exc:
        raise PlannerError(
            f"Unexpected response format from Ollama Planner: {data}"
        ) from exc

    if not plan:
        raise PlannerError("Ollama Planner returned an empty plan.")

    return plan


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_openrouter_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise PlannerError(
            "OPENROUTER_API_KEY environment variable is not set."
        )
    return key


class PlannerError(Exception):
    """Raised when the Planner LLM call fails."""
