"""
monitoring_jobs/user_store.py
──────────────────────────────
Stores each user's monitoring config in Redis (or in-memory fallback).

Schema per user:
  user_id         str   — UUID
  email           str   — recipient email for notifications
  sheets_url      str   — Google Sheets URL (or "__file__" if uploaded)
  csv_data        str   — base64-encoded CSV (only when sheets_url == "__file__")
  frequency       str   — "daily" | "weekly" | "monthly" | "quarterly" | "semiannual"
  lead_time_days  int   — passed to recommender (default 7)
  extra_context   str   — optional free text hint for the LLM report
  created_at      float — unix timestamp
  last_run_at     float — unix timestamp or 0.0 if never run
  last_job_id     str   — last job_id
  enabled         bool  — pause/resume without deleting
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_PREFIX   = "monitor:user:"
_SET_KEY  = "monitor:all_users"

VALID_FREQUENCIES = ("daily", "weekly", "monthly", "quarterly", "semiannual")


class UserStore:
    def __init__(self, redis_url: str):
        import redis
        self._r = redis.from_url(redis_url, decode_responses=True)
        self._r.ping()
        logger.info("UserStore: connected to Redis at %s", redis_url)

    def _key(self, user_id: str) -> str:
        return f"{_PREFIX}{user_id}"

    def create(
        self,
        email:          str,
        sheets_url:     str,
        frequency:      str  = "weekly",
        lead_time_days: int  = 7,
        extra_context:  str  = "",
        user_id:        Optional[str] = None,
    ) -> dict:
        uid = user_id or str(uuid.uuid4())
        record = {
            "user_id":        uid,
            "email":          email.strip().lower(),
            "sheets_url":     sheets_url.strip(),
            "csv_data":       "",
            "frequency":      frequency if frequency in VALID_FREQUENCIES else "weekly",
            "lead_time_days": max(1, min(int(lead_time_days), 365)),
            "extra_context":  extra_context.strip()[:500],
            "created_at":     time.time(),
            "last_run_at":    0.0,
            "last_job_id":    "",
            "enabled":        True,
        }
        self._r.set(self._key(uid), json.dumps(record))
        self._r.sadd(_SET_KEY, uid)
        logger.info("UserStore: created user %s (freq=%s, email=%s)", uid, record["frequency"], email)
        return record

    def get(self, user_id: str) -> Optional[dict]:
        raw = self._r.get(self._key(user_id))
        return json.loads(raw) if raw else None

    def update(self, user_id: str, **fields) -> Optional[dict]:
        record = self.get(user_id)
        if record is None:
            return None
        if "frequency" in fields and fields["frequency"] not in VALID_FREQUENCIES:
            fields["frequency"] = "weekly"
        if "lead_time_days" in fields:
            fields["lead_time_days"] = max(1, min(int(fields["lead_time_days"]), 365))
        if "email" in fields:
            fields["email"] = fields["email"].strip().lower()
        record.update(fields)
        self._r.set(self._key(user_id), json.dumps(record))
        return record

    def delete(self, user_id: str) -> bool:
        deleted = self._r.delete(self._key(user_id))
        self._r.srem(_SET_KEY, user_id)
        return bool(deleted)

    def all_users(self) -> list[dict]:
        users = []
        for uid in self._r.smembers(_SET_KEY):
            record = self.get(uid)
            if record:
                users.append(record)
        return users

    def enabled_users(self) -> list[dict]:
        return [u for u in self.all_users() if u.get("enabled", True)]

    def users_by_frequency(self, frequency: str) -> list[dict]:
        return [u for u in self.enabled_users() if u.get("frequency") == frequency]

    def mark_ran(self, user_id: str, job_id: str) -> None:
        self.update(user_id, last_run_at=time.time(), last_job_id=job_id)

    def count(self) -> int:
        return self._r.scard(_SET_KEY)


class InMemoryUserStore:
    """Thread-safe fallback when Redis is unavailable."""

    def __init__(self):
        import threading
        self._store: dict[str, dict] = {}
        self._lock = threading.Lock()
        logger.warning("UserStore: Redis unavailable — using in-memory fallback.")

    def create(self, email, sheets_url, frequency="weekly",
               lead_time_days=7, extra_context="", user_id=None):
        uid = user_id or str(uuid.uuid4())
        record = {
            "user_id":        uid,
            "email":          email.strip().lower(),
            "sheets_url":     sheets_url.strip(),
            "csv_data":       "",
            "frequency":      frequency if frequency in VALID_FREQUENCIES else "weekly",
            "lead_time_days": max(1, min(int(lead_time_days), 365)),
            "extra_context":  extra_context.strip()[:500],
            "created_at":     time.time(),
            "last_run_at":    0.0,
            "last_job_id":    "",
            "enabled":        True,
        }
        with self._lock:
            self._store[uid] = record
        return record

    def get(self, user_id):
        with self._lock:
            return self._store.get(user_id)

    def update(self, user_id, **fields):
        with self._lock:
            if user_id not in self._store:
                return None
            if "frequency" in fields and fields["frequency"] not in VALID_FREQUENCIES:
                fields["frequency"] = "weekly"
            if "lead_time_days" in fields:
                fields["lead_time_days"] = max(1, min(int(fields["lead_time_days"]), 365))
            if "email" in fields:
                fields["email"] = fields["email"].strip().lower()
            self._store[user_id].update(fields)
            return self._store[user_id]

    def delete(self, user_id):
        with self._lock:
            return self._store.pop(user_id, None) is not None

    def all_users(self):
        with self._lock:
            return list(self._store.values())

    def enabled_users(self):
        return [u for u in self.all_users() if u.get("enabled", True)]

    def users_by_frequency(self, frequency: str) -> list[dict]:
        return [u for u in self.enabled_users() if u.get("frequency") == frequency]

    def mark_ran(self, user_id, job_id):
        self.update(user_id, last_run_at=time.time(), last_job_id=job_id)

    def count(self):
        with self._lock:
            return len(self._store)


def _build_user_store():
    try:
        return UserStore(REDIS_URL)
    except Exception as exc:
        logger.warning("UserStore: Redis failed (%s) — in-memory fallback", exc)
        return InMemoryUserStore()


user_store = _build_user_store()
