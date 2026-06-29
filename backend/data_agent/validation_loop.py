"""
data_agent/validation_loop.py
──────────────────────────────
Re-validates the DataFrame produced by the sandbox after each execution attempt.
Max 3 attempts total (1 initial + 2 retries).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from data_agent.fast_validator import validate, ValidationResult


MAX_ATTEMPTS = 3


@dataclass
class LoopResult:
    success: bool
    df: Optional[pd.DataFrame] = None
    validation: Optional[ValidationResult] = None
    attempts_used: int = 0
    failure_reason: str = ""
    attempt_errors: list = field(default_factory=list)


def run_validation_loop(
    plan: str,
    input_csv: str,
) -> LoopResult:
    from data_agent.executor import generate_fix_code, ExecutorError
    from data_agent.sandbox  import execute_sandboxed

    previous_code:  Optional[str] = None
    previous_error: Optional[str] = None
    attempt_errors: list[str]     = []

    for attempt in range(1, MAX_ATTEMPTS + 1):

        # ── 1. Generate code ──────────────────────────────────────────────────
        try:
            code = generate_fix_code(
                plan=plan,
                previous_code=previous_code,
                previous_error=previous_error,
            )
        except ExecutorError as exc:
            reason = f"Attempt {attempt}: Executor LLM failed — {exc}"
            attempt_errors.append(reason)
            return LoopResult(
                success=False,
                attempts_used=attempt,
                failure_reason=reason,
                attempt_errors=attempt_errors,
            )

        # ── 2. Run in sandbox ─────────────────────────────────────────────────
        sandbox_result = execute_sandboxed(code=code, input_csv=input_csv)

        if not sandbox_result.success:
            error_msg = sandbox_result.short_error()
            attempt_errors.append(
                f"Attempt {attempt}: Sandbox error — {error_msg}"
            )
            previous_code  = code
            previous_error = error_msg
            continue

        # ── 3. Parse sandbox output ───────────────────────────────────────────
        try:
            # StringIO is already a decoded string; encoding param has no effect here.
            df_out = pd.read_csv(io.StringIO(sandbox_result.csv_output))
        except Exception as exc:
            error_msg = f"Could not parse sandbox CSV output: {exc}"
            attempt_errors.append(f"Attempt {attempt}: {error_msg}")
            previous_code  = code
            previous_error = error_msg
            continue

        # ── 4. Validate output ────────────────────────────────────────────────
        val_result = validate(df_out)

        if val_result.passed:
            return LoopResult(
                success=True,
                df=df_out,
                validation=val_result,
                attempts_used=attempt,
                attempt_errors=attempt_errors,
            )

        error_msg = "Validation failed after execution:\n" + "\n".join(
            f"  - {e}" for e in val_result.errors
        )
        attempt_errors.append(f"Attempt {attempt}: {error_msg}")
        previous_code  = code
        previous_error = error_msg

    return LoopResult(
        success=False,
        attempts_used=MAX_ATTEMPTS,
        failure_reason=(
            f"Data could not be fixed after {MAX_ATTEMPTS} attempts. "
            "Please check your file manually and ensure it contains: "
            "date, store, item, sales columns."
        ),
        attempt_errors=attempt_errors,
    )
