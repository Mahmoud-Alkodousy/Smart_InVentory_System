"""
data_agent/smart_cleaner.py
────────────────────────────
Two-phase data cleaner:

  Phase 1 — Column mapping:
    a) Fuzzy match (difflib) — handles typos and English aliases
    b) LLM mapping (optional) — handles Arabic, mixed, or unusual names
       The LLM only maps column names → no code generation, no sandbox.

  Phase 2 — Deterministic cleaning (pandas-only, no LLM):
    - Date parsing with format='mixed'
    - Sales coerce + clip negatives
    - Null filling with rolling mean / ffill
"""

from __future__ import annotations

import json
import logging
import os
import re
from difflib import get_close_matches
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED = ["date", "store", "item", "sales"]

ALIASES: dict[str, list[str]] = {
    "date": [
        "date", "Date", "DATE", "ds", "day", "period", "month", "week",
        "time", "timestamp", "order_date", "sale_date",
        "transaction_date", "trans_date", "invoice_date", "record_date",
        "تاريخ", "التاريخ",
    ],
    "store": [
        "store", "Store", "STORE", "branch", "Branch", "shop",
        "location", "outlet", "region", "store_id", "branch_id", "store_name",
        "فرع", "الفرع", "متجر",
    ],
    "item": [
        "item", "Item", "ITEM", "product", "Product", "sku", "SKU",
        "article", "code", "name", "product_id", "item_id", "product_name",
        "item_name", "commodity", "product_code", "item_code",
        "منتج", "المنتج", "صنف",
    ],
    "sales": [
        "sales", "Sales", "SALES", "qty", "quantity", "Quantity",
        "amount", "units", "sold", "revenue", "value", "volume", "demand",
        "sales_qty", "total_sales", "units_sold", "sales_amount",
        "مبيعات", "الكمية", "المبيعات",
    ],
}

MAX_NULL_PCT = 0.5


# ── Public API ────────────────────────────────────────────────────────────────

def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    # Phase 1a: fuzzy match
    col_map = _fuzzy_map(df.columns.tolist())

    # Phase 1b: LLM mapping for any still-missing columns
    missing = [r for r in REQUIRED if r not in col_map.values()]
    if missing:
        unmapped = [c for c in df.columns if c not in col_map]
        llm_map = _llm_map(unmapped, missing)
        if llm_map:
            for src, tgt in llm_map.items():
                if src in df.columns and src not in col_map:
                    col_map[src] = tgt
                    warnings.append(f"عمود '{src}' تم التعرف عليه كـ '{tgt}' بواسطة الذكاء الاصطناعي")

    # Final check
    missing = [r for r in REQUIRED if r not in col_map.values()]
    if missing:
        raise ValueError(
            f"أعمدة مفقودة ولا يمكن تحديدها: {missing}. "
            f"الأعمدة الموجودة: {list(df.columns)}"
        )

    df_original = df.copy()
    df_required = df.rename(columns=col_map)[REQUIRED]

    # Preserve recognised business columns (unit_price, current_stock,
    # supplier, supplier_lead_time_days, ...) — they're not part of the
    # required schema but the recommender/PO/supplier-risk features use
    # them when present. Without this they'd be silently dropped here.
    from data_agent.schema import attach_optional_columns
    df, added = attach_optional_columns(
        df_required, df_original, consumed_original_names=set(col_map.keys())
    )
    if added:
        warnings.append(f"تم التعرف على أعمدة إضافية مفيدة: {added}")

    # Phase 2: deterministic cleaning
    df, warnings2 = _clean_data(df)
    return df, warnings + warnings2


# ── Phase 1a: Fuzzy mapping ───────────────────────────────────────────────────

def _fuzzy_map(columns: list[str]) -> dict[str, str]:
    col_map: dict[str, str] = {}
    used: set[str] = set()

    for target, aliases in ALIASES.items():
        aliases_lower = [a.lower() for a in aliases]

        # Exact match (case-insensitive)
        for col in columns:
            if col.lower() in aliases_lower and col not in used:
                col_map[col] = target
                used.add(col)
                break
        else:
            # Fuzzy fallback
            candidates = [c for c in columns if c not in used]
            matches = get_close_matches(target, candidates, n=1, cutoff=0.6)
            if not matches:
                matches = get_close_matches(
                    target, [c.lower() for c in candidates], n=1, cutoff=0.6
                )
                if matches:
                    matches = [next(c for c in candidates if c.lower() == matches[0])]
            if matches:
                col_map[matches[0]] = target
                used.add(matches[0])

    return col_map


# ── Phase 1b: LLM column mapping ─────────────────────────────────────────────

def _llm_map(columns: list[str], missing_targets: list[str]) -> dict[str, str]:
    """
    Ask the LLM to map column names → required targets.
    Returns {original_col: target} dict, or {} if LLM unavailable.
    Only sends column names — no data rows, no code generation.
    """
    use_ollama = os.getenv("OLLAMA", "false").strip().lower() in ("true", "1", "yes")

    prompt = f"""You are a data engineer. Map these column names to the required targets.

Column names from the file: {json.dumps(columns, ensure_ascii=False)}
Required targets (only map what you can find): {json.dumps(missing_targets)}

Rules:
- Return ONLY a JSON object like: {{"original_col": "target", ...}}
- Only include columns you are confident about
- Targets must be one of: date, store, item, sales
- No explanation, no markdown, just the JSON object
"""

    try:
        if use_ollama:
            return _llm_map_ollama(prompt)
        else:
            return _llm_map_openrouter(prompt)
    except Exception as exc:
        logger.warning("LLM column mapping failed: %s", exc)
        return {}


def _llm_map_ollama(prompt: str) -> dict[str, str]:
    import requests
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_PLANNER_MODEL", "qwen3:8b")
    timeout = int(os.getenv("OLLAMA_TIMEOUT", "120"))

    resp = requests.post(
        f"{base_url}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0.0},
            "think": False,
            "stream": False,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"].strip()
    return _parse_llm_json(content)


def _llm_map_openrouter(prompt: str) -> dict[str, str]:
    import requests
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return {}

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "google/gemini-2.5-flash",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 200,
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    return _parse_llm_json(content)


def _parse_llm_json(text: str) -> dict[str, str]:
    text = text.strip()

    # Strip <think>...</think> blocks (qwen3 thinking mode)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    result = json.loads(text.strip())
    # Validate: values must be in REQUIRED
    return {k: v for k, v in result.items() if v in REQUIRED}


# ── Phase 2: Deterministic cleaning ──────────────────────────────────────────

def _clean_data(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []

    # Date parsing
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        parsed = False
        for kwargs in [
            {"format": "mixed", "dayfirst": False},
            {"format": "mixed", "dayfirst": True},
            {"infer_datetime_format": True},
        ]:
            try:
                df["date"] = pd.to_datetime(df["date"], **kwargs)
                parsed = True
                break
            except Exception:
                continue
        if not parsed:
            raise ValueError(
                f"تعذّر تحليل عمود التاريخ. عينة: {df['date'].dropna().head(5).tolist()}"
            )

    # Sales
    df["sales"] = pd.to_numeric(df["sales"], errors="coerce")
    n_neg = int((df["sales"] < 0).sum())
    if n_neg:
        warnings.append(f"{n_neg} قيمة سالبة في 'sales' تم تحويلها إلى 0")
        df["sales"] = df["sales"].clip(lower=0)

    # Nulls
    for col in REQUIRED:
        n_null = int(df[col].isna().sum())
        if n_null == 0:
            continue
        pct = n_null / len(df)
        if pct > MAX_NULL_PCT:
            raise ValueError(
                f"عمود '{col}' يحتوي على {pct:.0%} قيم فارغة — غير قابل للمعالجة."
            )
        if col == "sales":
            df["sales"] = (
                df.groupby(["store", "item"], group_keys=False)["sales"]
                .transform(lambda x: x.fillna(x.rolling(7, min_periods=1).mean()))
            )
            df["sales"] = df["sales"].fillna(0)
        else:
            df[col] = df[col].ffill().bfill()
        warnings.append(f"{n_null} قيمة فارغة في '{col}' تمت معالجتها")

    before = len(df)
    df = df.dropna(subset=REQUIRED)
    dropped = before - len(df)
    if dropped:
        warnings.append(f"تم حذف {dropped} صف يحتوي على قيم فارغة")

    if len(df) < 2:
        raise ValueError("الملف يحتوي على أقل من صفين قابلين للمعالجة.")

    df = df.sort_values("date").reset_index(drop=True)
    return df, warnings