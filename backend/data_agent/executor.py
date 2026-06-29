"""
data_agent/executor.py
───────────────────────
Executor LLM — google/gemini-2.5-flash via OpenRouter  (default)
                OR  qwen2.5-coder:7b via Ollama         (if OLLAMA=True)

Receives:
  - plan.md  produced by the Planner LLM
  - The sample payload (for context)
  - (on retry) the previous code + sandbox error

Produces:
  - A Python code string that transforms df into the 4-column clean format.
  - The code is passed directly to sandbox.execute_sandboxed().
"""

from __future__ import annotations

import os
from typing import Optional

import requests


# ── Config ────────────────────────────────────────────────────────────────────

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
EXECUTOR_MODEL     = "google/gemini-2.5-flash"
REQUEST_TIMEOUT    = 45   # seconds

OLLAMA_BASE_URL      = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EXECUTOR_MODEL = os.getenv("OLLAMA_EXECUTOR_MODEL", "qwen2.5-coder:7b")
OLLAMA_TIMEOUT        = int(os.getenv("OLLAMA_TIMEOUT", "300"))

_USE_OLLAMA = os.getenv("OLLAMA", "false").strip().lower() in ("true", "1", "yes")


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a Python data engineer. Your job is to write a single Python code block
that cleans a pandas DataFrame called `df` according to a given plan.

STRICT RULES — violating any of these will cause a runtime error:
1. The variable is ALREADY named `df`. Do NOT use pd.read_csv() or any file I/O.
2. Produce a DataFrame still named `df` with EXACTLY these 4 columns in this order:
       date (datetime64)  |  store (str or int)  |  item (str or int)  |  sales (float >= 0)
3. Do NOT print anything. Do NOT call df.to_csv(). Output is handled externally.
4. Only import from: pandas, numpy, re, json, math, datetime (already imported).
5. For date parsing ALWAYS use pd.to_datetime(df['date'], format='mixed', dayfirst=False)
   or pd.to_datetime(df['date'], infer_datetime_format=True) — NEVER hardcode a format string
   like format='%m/%d/%Y' because the actual format may differ and will cause a crash.
6. Do NOT import requests, os, sys, subprocess, or any network/file library.
7. Write clean, readable code with one comment per logical step.
8. Return ONLY the raw Python code — no markdown fences, no explanation text.
"""

_RETRY_ADDITION = """\

The previous attempt produced this error:
```
{error}
```
The previous code that failed:
```python
{previous_code}
```
Fix the error and rewrite the complete code block.
"""


# ── Public API ────────────────────────────────────────────────────────────────

def generate_fix_code(
    plan: str,
    previous_code: Optional[str] = None,
    previous_error: Optional[str] = None,
) -> str:
    """
    Call the Executor LLM and return the generated Python code string.

    Parameters
    ----------
    plan           : Markdown plan from planner.create_fix_plan()
    previous_code  : Code from the previous (failed) attempt — for retries.
    previous_error : Error message from sandbox — for retries.

    Returns
    -------
    str : Python code ready to pass to sandbox.execute_sandboxed()

    Raises
    ------
    ExecutorError : if the API call fails or returns empty code.
    """
    user_content = f"Here is the data fix plan:\n\n{plan}"

    if previous_code and previous_error:
        user_content += _RETRY_ADDITION.format(
            error=previous_error,
            previous_code=previous_code,
        )

    if _USE_OLLAMA:
        return _call_ollama(user_content)
    else:
        return _call_openrouter(user_content)


# ── OpenRouter backend ────────────────────────────────────────────────────────

def _call_openrouter(user_content: str) -> str:
    api_key = _get_openrouter_key()

    payload = {
        "model": EXECUTOR_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        "temperature": 0.0,
        "max_tokens":  2048,
    }

    try:
        response = requests.post(
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
                "HTTP-Referer":  "https://smart-inventory-manager",
                "X-Title":       "Smart Inventory Manager - Executor",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise ExecutorError("Executor LLM request timed out.")
    except requests.exceptions.HTTPError as exc:
        raise ExecutorError(f"Executor LLM HTTP error: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise ExecutorError(f"Executor LLM network error: {exc}") from exc

    data = response.json()

    try:
        code = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise ExecutorError(
            f"Unexpected response format from Executor LLM: {data}"
        ) from exc

    code = _strip_fences(code)
    code = _patch_date_parsing(code)

    if not code:
        raise ExecutorError("Executor LLM returned empty code.")

    return code


# ── Ollama backend ────────────────────────────────────────────────────────────

def _call_ollama(user_content: str) -> str:
    url = f"{OLLAMA_BASE_URL}/api/chat"

    payload = {
        "model": OLLAMA_EXECUTOR_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        "options": {"temperature": 0.0},
        "stream": False,
    }

    try:
        response = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise ExecutorError(f"Ollama Executor request timed out (model: {OLLAMA_EXECUTOR_MODEL}).")
    except requests.exceptions.HTTPError as exc:
        raise ExecutorError(f"Ollama Executor HTTP error: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise ExecutorError(
            f"Ollama Executor network error: {exc}\n"
            f"Is Ollama running? Check: {OLLAMA_BASE_URL}"
        ) from exc

    data = response.json()

    try:
        code = data["message"]["content"].strip()
    except (KeyError, TypeError) as exc:
        raise ExecutorError(
            f"Unexpected response format from Ollama Executor: {data}"
        ) from exc

    code = _strip_fences(code)
    code = _patch_date_parsing(code)

    if not code:
        raise ExecutorError("Ollama Executor returned empty code.")

    return code


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_fences(code: str) -> str:
    """Remove ```python ... ``` or ``` ... ``` wrappers if present."""
    lines = code.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _patch_date_parsing(code: str) -> str:
    """
    Safety net: replace any hardcoded to_datetime format strings with
    format='mixed' so the code never crashes on unexpected date formats.

    Handles patterns like:
      pd.to_datetime(..., format='%m/%d/%Y')
      pd.to_datetime(..., format="%Y-%m-%d")
    """
    import re
    # Replace format='...' or format="..." inside to_datetime calls
    patched = re.sub(
        r"pd\.to_datetime\(([^)]+?),\s*format=['\"][^'\"]+['\"]([^)]*?)\)",
        lambda m: f"pd.to_datetime({m.group(1)}, format='mixed', dayfirst=False{m.group(2)})",
        code,
    )
    return patched


def _get_openrouter_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise ExecutorError(
            "OPENROUTER_API_KEY environment variable is not set."
        )
    return key


class ExecutorError(Exception):
    """Raised when the Executor LLM call fails."""
