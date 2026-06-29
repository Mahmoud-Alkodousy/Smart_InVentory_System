"""
data_loader/loader.py
─────────────────────
Loads sales data from CSV, Excel, or JSON into a pandas DataFrame.
Returns a standardised DataFrame — no column renaming here, that's
the Data Fixer Agent's job.

Unicode handling: tries multiple encodings automatically.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Union

import pandas as pd


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json"}

MIME_TO_EXT: dict[str, str] = {
    "text/csv":                                                        ".csv",
    "application/csv":                                                 ".csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel":                                        ".xls",
    "application/json":                                                ".json",
    "text/json":                                                       ".json",
    "application/octet-stream":                                        "",    # fallback to filename
}


class UnsupportedFormatError(Exception):
    pass


class LoadError(Exception):
    pass


def load_file(
    source: Union[bytes, str, Path],
    filename: str = "",
    mime_type: str = "",
) -> pd.DataFrame:
    ext = _resolve_extension(source, filename, mime_type)

    if isinstance(source, (str, Path)):
        source = Path(source).read_bytes()

    if not source:
        raise LoadError("Uploaded file is empty.")

    buffer = io.BytesIO(source)

    if ext == ".csv":
        return _load_csv(buffer)
    elif ext in (".xlsx", ".xls"):
        return _load_excel(buffer, ext)
    elif ext == ".json":
        return _load_json(buffer)
    else:
        raise UnsupportedFormatError(f"Unsupported extension: {ext}")


def _load_csv(buffer: io.BytesIO) -> pd.DataFrame:
    """
    Try multiple encodings — handles UTF-8, Arabic (cp1256),
    Windows (cp1252), and legacy latin-1 files automatically.
    """
    # Detect BOM first
    buffer.seek(0)
    raw = buffer.read(4)
    buffer.seek(0)

    # Check for UTF-8 BOM
    if raw.startswith(b'\xef\xbb\xbf'):
        encodings = ["utf-8-sig", "utf-8", "cp1256", "cp1252", "latin-1"]
    else:
        encodings = ["utf-8", "utf-8-sig", "cp1256", "cp1252", "latin-1", "iso-8859-6"]

    last_error = None
    for encoding in encodings:
        try:
            buffer.seek(0)
            df = pd.read_csv(buffer, encoding=encoding, low_memory=False)
            if df.empty:
                raise LoadError("CSV file has no rows after parsing.")
            return df
        except UnicodeDecodeError as e:
            last_error = e
            continue
        except Exception as e:
            # Non-encoding error — re-raise immediately
            raise LoadError(f"Failed to parse CSV: {e}") from e

    raise LoadError(
        f"Could not decode CSV — tried {encodings}. "
        f"Last error: {last_error}. "
        "Please save your file as UTF-8."
    )


def _load_excel(buffer: io.BytesIO, ext: str) -> pd.DataFrame:
    """Load Excel files — supports both .xlsx and .xls."""
    try:
        engine = "openpyxl" if ext == ".xlsx" else "xlrd"
        df = pd.read_excel(buffer, sheet_name=0, engine=engine)
    except Exception:
        # Try openpyxl as fallback for .xls too
        try:
            buffer.seek(0)
            df = pd.read_excel(buffer, sheet_name=0, engine="openpyxl")
        except Exception as exc:
            raise LoadError(f"Failed to read Excel file: {exc}") from exc

    if df.empty:
        raise LoadError("Excel file has no rows after parsing.")
    return df


def _load_json(buffer: io.BytesIO) -> pd.DataFrame:
    """Accept array of objects or pandas column-oriented dict."""
    # Try multiple encodings for JSON too
    raw = None
    for encoding in ("utf-8", "utf-8-sig", "cp1256", "latin-1"):
        try:
            buffer.seek(0)
            raw = buffer.read().decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if raw is None:
        raise LoadError("Could not decode JSON file — unknown encoding.")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LoadError(f"Invalid JSON: {exc}") from exc

    try:
        if isinstance(parsed, list):
            df = pd.DataFrame(parsed)
        elif isinstance(parsed, dict):
            df = pd.DataFrame(parsed)
        else:
            raise LoadError("JSON must be an array of objects or a column-oriented dict.")
    except Exception as exc:
        raise LoadError(f"Could not convert JSON to DataFrame: {exc}") from exc

    if df.empty:
        raise LoadError("JSON file has no rows after parsing.")
    return df


def _resolve_extension(
    source: Union[bytes, str, Path],
    filename: str,
    mime_type: str,
) -> str:
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in SUPPORTED_EXTENSIONS:
            return ext

    if mime_type:
        ext = MIME_TO_EXT.get(mime_type.split(";")[0].strip().lower(), "")
        if ext:
            return ext

    if isinstance(source, (str, Path)):
        ext = Path(source).suffix.lower()
        if ext in SUPPORTED_EXTENSIONS:
            return ext

    raise UnsupportedFormatError(
        f"Cannot determine file format from filename='{filename}', "
        f"mime_type='{mime_type}'. "
        f"Supported formats: CSV, Excel (.xlsx/.xls), JSON."
    )
