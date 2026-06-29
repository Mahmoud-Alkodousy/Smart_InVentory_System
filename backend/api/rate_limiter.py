"""
api/rate_limiter.py
────────────────────
Centralised slowapi rate-limiter instance.
"""

from __future__ import annotations
import os

os.environ.setdefault("SLOWAPI_NO_DOTENV", "1")

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute"],
)
