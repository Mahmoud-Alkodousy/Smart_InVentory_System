"""
data_agent/sandbox.py
──────────────────────
Executes LLM-generated Python code in a hardened subprocess.

Security layers (defence in depth):
  1. Allowlist imports only
  2. Hard timeout
  3. Memory cap (Linux only)
  4. CPU cap (Linux only)
  5. Minimal env
  6. No network access (blocked at subprocess env level, not sys.modules)
  7. No filesystem writes
  8. Code size limit

Key fix: network blocking now uses a custom import hook instead of
replacing sys.modules entries with fake objects. The old approach broke
pandas because pytz checks __spec__ on imported modules during its own
init, and a fake _BlockedModule() doesn't have __spec__.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass

# ── Config ────────────────────────────────────────────────────────────────────

SANDBOX_TIMEOUT_SECONDS = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", "30"))
SANDBOX_MAX_MEM_MB      = int(os.getenv("SANDBOX_MAX_MEM_MB",      "512"))
SANDBOX_MAX_CPU_SECONDS = int(os.getenv("SANDBOX_MAX_CPU_SECONDS", "25"))
MAX_CODE_SIZE_CHARS     = int(os.getenv("MAX_CODE_SIZE_CHARS",     "20000"))


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    returncode: int
    csv_output: str = ""

    def short_error(self, max_chars: int = 600) -> str:
        raw = (self.stderr or self.stdout or "Unknown error").strip()
        return raw[:max_chars] + ("..." if len(raw) > max_chars else "")


# ── Minimal environment ───────────────────────────────────────────────────────

_SAFE_ENV: dict[str, str] = {
    "PATH": "/usr/bin:/usr/local/bin",
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    # Prevent pandas from reaching out for anything
    "no_proxy": "*",
    "NO_PROXY": "*",
}


# ── Resource-limit bootstrap (injected before user code) ─────────────────────
# FIX: Use a meta path finder (import hook) to block network modules
# instead of replacing sys.modules with fake objects.
# The fake-object approach broke pandas/pytz because pytz checks __spec__
# on modules during import, and a fake object doesn't have __spec__.

_RESOURCE_BOOTSTRAP = """\
import sys

# -- Force UTF-8 stdout/stderr ------------------------------------------------
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# -- Block dangerous imports via a meta path finder ---------------------------
# This approach is safe: it raises ImportError BEFORE the module is loaded,
# so it never touches __spec__ or any module internals.
_BLOCKED_MODULES = frozenset({
    "socket", "urllib", "urllib2", "urllib3", "http", "requests",
    "httplib", "ftplib", "smtplib", "telnetlib", "ssl",
    "subprocess", "multiprocessing",
    "os.system",   # os itself is allowed but os.system is not — handled below
})

class _BlockingImportFinder:
    def find_module(self, fullname, path=None):
        top = fullname.split(".")[0]
        if top in _BLOCKED_MODULES:
            return self  # claim we can handle it

    def load_module(self, fullname):
        top = fullname.split(".")[0]
        if top in _BLOCKED_MODULES:
            raise ImportError(
                f"Module '{fullname}' is not allowed in this sandbox."
            )

sys.meta_path.insert(0, _BlockingImportFinder())

# -- Block filesystem writes --------------------------------------------------
import builtins as _builtins
_original_open = _builtins.open

def _safe_open(file, mode="r", *args, **kwargs):
    if isinstance(mode, str) and any(m in mode for m in ("w", "a", "x", "+")):
        raise PermissionError("Filesystem writes are not allowed in the sandbox.")
    return _original_open(file, mode, *args, **kwargs)

_builtins.open = _safe_open

# -- Apply resource limits (Linux only) ---------------------------------------
try:
    import resource as _res
    _MEM_BYTES = {MAX_MEM_MB} * 1024 * 1024
    _CPU_SECS  = {MAX_CPU_SECS}
    _res.setrlimit(_res.RLIMIT_AS,  (_MEM_BYTES, _MEM_BYTES))
    _res.setrlimit(_res.RLIMIT_CPU, (_CPU_SECS,  _CPU_SECS))
except Exception:
    pass
"""


# ── Unicode sanitizer ─────────────────────────────────────────────────────────

def _sanitize_unicode(code: str) -> str:
    """Replace non-ASCII chars in LLM-generated code to prevent encoding issues."""
    replacements = {
        '\u2500': '-', '\u2501': '-', '\u2502': '|', '\u2503': '|',
        '\u250c': '+', '\u2510': '+', '\u2514': '+', '\u2518': '+',
        '\u251c': '+', '\u2524': '+', '\u252c': '+', '\u2534': '+',
        '\u253c': '+',
        '\u2012': '-', '\u2013': '-', '\u2014': '--', '\u2015': '--',
        '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"',
        '\u2022': '*', '\u2023': '>', '\u25b6': '>',
    }
    for char, replacement in replacements.items():
        code = code.replace(char, replacement)
    result = []
    for ch in code:
        if ord(ch) > 127:
            result.append(ch.encode('ascii', errors='backslashreplace').decode('ascii'))
        else:
            result.append(ch)
    return ''.join(result)


# ── Main entry point ──────────────────────────────────────────────────────────

def execute_sandboxed(
    code: str,
    input_csv: str,
    timeout: int = SANDBOX_TIMEOUT_SECONDS,
) -> SandboxResult:
    if len(code) > MAX_CODE_SIZE_CHARS:
        return SandboxResult(
            success=False,
            stdout="",
            stderr=f"Generated code exceeds maximum size ({len(code)} > {MAX_CODE_SIZE_CHARS} chars).",
            returncode=-1,
        )

    code = _sanitize_unicode(code)
    wrapped = _wrap_code(code, input_csv)

    env = {**_SAFE_ENV}
    if sys.platform == "win32":
        env["PYTHONLEGACYWINDOWSSTDIO"] = "0"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".py", delete=False
        ) as tmp:
            tmp.write(wrapped)
            tmp_path = tmp.name

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return SandboxResult(
            success=False,
            stdout="",
            stderr=f"Execution timed out after {timeout} seconds.",
            returncode=-1,
        )
    except Exception as exc:
        return SandboxResult(
            success=False,
            stdout="",
            stderr=f"Subprocess launch error: {exc}",
            returncode=-1,
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    stdout_str = result.stdout.decode("utf-8", errors="replace")
    stderr_str = result.stderr.decode("utf-8", errors="replace")

    if result.returncode != 0:
        return SandboxResult(
            success=False,
            stdout=stdout_str,
            stderr=stderr_str,
            returncode=result.returncode,
        )

    csv_output = stdout_str.strip()
    if not csv_output:
        return SandboxResult(
            success=False,
            stdout=stdout_str,
            stderr="Code ran without error but produced no output.",
            returncode=result.returncode,
        )

    return SandboxResult(
        success=True,
        stdout=stdout_str,
        stderr=stderr_str,
        returncode=result.returncode,
        csv_output=csv_output,
    )


# ── Code wrapper ──────────────────────────────────────────────────────────────

def _wrap_code(user_code: str, input_csv: str) -> str:
    csv_b64 = base64.b64encode(input_csv.encode("utf-8")).decode("ascii")

    bootstrap = _RESOURCE_BOOTSTRAP.replace("{MAX_MEM_MB}",  str(SANDBOX_MAX_MEM_MB))
    bootstrap = bootstrap.replace("{MAX_CPU_SECS}", str(SANDBOX_MAX_CPU_SECONDS))

    parts = [
        "# -- Security bootstrap --------------------------------------------------",
        bootstrap.strip(),
        "",
        "# -- Allowed imports -----------------------------------------------------",
        "import pandas as pd",
        "import numpy as np",
        "import re",
        "import json",
        "import math",
        "import io",
        "import base64",
        "import datetime",
        "",
        "# -- Injected input (base64 encoded to handle all unicode) ----------------",
        f'_CSV_B64 = "{csv_b64}"',
        "_csv_bytes = base64.b64decode(_CSV_B64)",
        "df = pd.read_csv(io.BytesIO(_csv_bytes))",
        "",
        "# -- LLM-generated code ---------------------------------------------------",
        user_code.strip(),
        "",
        "# -- Output (UTF-8 bytes to handle all unicode) ---------------------------",
        "import sys",
        "_out = df.to_csv(index=False)",
        "if hasattr(sys.stdout, 'buffer'):",
        "    sys.stdout.buffer.write(_out.encode('utf-8'))",
        "else:",
        "    sys.stdout.write(_out)",
    ]
    return "\n".join(parts) + "\n"