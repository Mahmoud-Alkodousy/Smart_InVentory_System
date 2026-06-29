"""
data_loader/sheets_loader.py
Loads a public Google Sheets spreadsheet into a pandas DataFrame.
"""

from __future__ import annotations

import re
import io

import pandas as pd
import requests


class SheetsURLError(Exception):
    pass


class SheetsLoadError(Exception):
    pass


_SHEETS_ID_RE = re.compile(
    r"https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)"
)
_GID_RE = re.compile(r"[#&?]gid=(\d+)")

_REQUEST_TIMEOUT = 30


def load_google_sheet(url: str, sheet_index: int = 0) -> pd.DataFrame:
    sheet_id   = _extract_sheet_id(url)
    gid        = _extract_gid(url)
    if gid is None:
        gid = sheet_index
    export_url = _build_export_url(sheet_id, gid)

    try:
        response = requests.get(
            export_url,
            timeout=_REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise SheetsLoadError("Request timed out while fetching the Google Sheet.")
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        if status == 403:
            raise SheetsLoadError(
                "Access denied (403). Make sure the sheet is shared publicly "
                "(Share -> Anyone with the link -> Viewer)."
            )
        elif status == 404:
            raise SheetsLoadError("Sheet not found (404). Check the URL.")
        raise SheetsLoadError(f"HTTP error {status} while fetching the sheet.")
    except requests.exceptions.ConnectionError as exc:
        raise SheetsLoadError(f"Connection error: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise SheetsLoadError(f"Network error: {exc}") from exc

    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        raise SheetsLoadError(
            "Sheet is private or requires login. "
            "Go to Share -> Anyone with the link -> Viewer."
        )

    try:
        # Force UTF-8 so Arabic text is read correctly
        response.encoding = "utf-8"
        df = pd.read_csv(io.StringIO(response.text))
    except Exception as exc:
        raise SheetsLoadError(f"Could not parse sheet as CSV: {exc}") from exc

    if df.empty:
        raise SheetsLoadError("The Google Sheet is empty or has no data rows.")

    return df


def is_google_sheets_url(url: str) -> bool:
    return bool(_SHEETS_ID_RE.search(url))


def _extract_sheet_id(url: str) -> str:
    match = _SHEETS_ID_RE.search(url)
    if not match:
        raise SheetsURLError(
            f"Invalid Google Sheets URL: '{url}'. "
            "Expected: https://docs.google.com/spreadsheets/d/<ID>/..."
        )
    return match.group(1)


def _extract_gid(url: str):
    match = _GID_RE.search(url)
    return int(match.group(1)) if match else None


def _build_export_url(sheet_id: str, gid: int) -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/export?format=csv&gid={gid}"
    )