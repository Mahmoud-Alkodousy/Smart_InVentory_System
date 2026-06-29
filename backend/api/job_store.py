"""
api/job_store.py
─────────────────
Job store backed by Redis (primary) with automatic fallback to
in-memory when Redis is unavailable (dev / CI).

Redis keys:
  job:{job_id}  →  JSON blob  (TTL = JOB_TTL_SECONDS)

Why Redis?
  - Survives server restarts / crashes
  - Works across multiple app instances (horizontal scaling)
  - Built-in TTL prevents memory leaks — jobs expire automatically

Environment variables:
  REDIS_URL        Redis connection URL (default: redis://localhost:6379/0)
  JOB_TTL_SECONDS  How long to keep job results (default: 3600 = 1 hour)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

REDIS_URL       = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JOB_TTL_SECONDS = int(os.getenv("JOB_TTL_SECONDS", "3600"))  # 1 hour default


# ── Status constants ──────────────────────────────────────────────────────────

class JobStatus:
    PROCESSING = "processing"
    DONE       = "done"
    FAILED     = "failed"

# Step keys — must match STEPS order in the frontend
STEP_LOAD       = "load"
STEP_CLEAN      = "clean"
STEP_VALIDATE   = "validate"
STEP_FORECAST   = "forecast"
STEP_RECOMMEND  = "recommend"
STEP_DRIFT      = "drift"
STEP_REPORT     = "report"


# ── Redis backend ─────────────────────────────────────────────────────────────

class RedisJobStore:
    """Redis-backed store. Each job is a JSON blob with a TTL."""

    def __init__(self, redis_url: str, ttl: int):
        import redis
        self._r   = redis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl
        self._r.ping()
        logger.info("JobStore: connected to Redis at %s (TTL=%ds)", redis_url, ttl)

    def _key(self, job_id: str) -> str:
        return f"job:{job_id}"

    def create(self, job_id: str) -> None:
        payload = json.dumps({"status": JobStatus.PROCESSING, "created_at": time.time()})
        self._r.setex(self._key(job_id), self._ttl, payload)

    def get(self, job_id: str) -> Optional[dict]:
        raw = self._r.get(self._key(job_id))
        return json.loads(raw) if raw else None

    def complete(self, job_id: str, **kwargs) -> None:
        existing = self.get(job_id)
        if existing is None:
            return
        existing.update({"status": JobStatus.DONE, **kwargs})
        self._r.setex(self._key(job_id), self._ttl, json.dumps(existing, default=str))

    def update_step(self, job_id: str, step: str) -> None:
        existing = self.get(job_id)
        if existing is None:
            return
        existing["current_step"] = step
        self._r.setex(self._key(job_id), self._ttl, json.dumps(existing, default=str))

    def fail(self, job_id: str, error: str = "", attempt_errors: Optional[list] = None) -> None:
        existing = self.get(job_id)
        if existing is None:
            return
        existing.update({
            "status":         JobStatus.FAILED,
            "error":          error,
            "attempt_errors": attempt_errors or [],
        })
        self._r.setex(self._key(job_id), self._ttl, json.dumps(existing, default=str))

    def delete(self, job_id: str) -> None:
        self._r.delete(self._key(job_id))

    def count(self) -> int:
        return sum(1 for _ in self._r.scan_iter("job:*"))


# ── In-memory fallback ────────────────────────────────────────────────────────

class InMemoryJobStore:
    """
    Thread-safe in-memory store used when Redis is unavailable.
    Background reaper evicts expired jobs to prevent unbounded memory growth.
    """

    def __init__(self, ttl: int):
        self._store: dict[str, dict]   = {}
        self._expiry: dict[str, float] = {}
        self._lock  = threading.Lock()
        self._ttl   = ttl
        self._reaper = threading.Thread(target=self._reap_loop, daemon=True)
        self._reaper.start()
        logger.warning(
            "JobStore: Redis unavailable — using in-memory fallback. "
            "Jobs will be lost on restart. Set REDIS_URL to enable persistence."
        )

    def create(self, job_id: str) -> None:
        with self._lock:
            self._store[job_id]  = {"status": JobStatus.PROCESSING, "created_at": time.time()}
            self._expiry[job_id] = time.time() + self._ttl

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            if self._is_expired(job_id):
                self._evict(job_id)
                return None
            return self._store.get(job_id)

    def complete(self, job_id: str, **kwargs) -> None:
        with self._lock:
            if job_id in self._store:
                self._store[job_id].update({"status": JobStatus.DONE, **kwargs})
                self._expiry[job_id] = time.time() + self._ttl

    def update_step(self, job_id: str, step: str) -> None:
        with self._lock:
            if job_id in self._store:
                self._store[job_id]["current_step"] = step
                self._expiry[job_id] = time.time() + self._ttl

    def fail(self, job_id: str, error: str = "", attempt_errors: Optional[list] = None) -> None:
        with self._lock:
            if job_id in self._store:
                self._store[job_id].update({
                    "status":         JobStatus.FAILED,
                    "error":          error,
                    "attempt_errors": attempt_errors or [],
                })
                self._expiry[job_id] = time.time() + self._ttl

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._evict(job_id)

    def count(self) -> int:
        with self._lock:
            return len(self._store)

    def _is_expired(self, job_id: str) -> bool:
        exp = self._expiry.get(job_id)
        return exp is not None and time.time() > exp

    def _evict(self, job_id: str) -> None:
        self._store.pop(job_id, None)
        self._expiry.pop(job_id, None)

    def _reap_loop(self) -> None:
        while True:
            time.sleep(300)
            with self._lock:
                expired = [jid for jid in list(self._store) if self._is_expired(jid)]
                for jid in expired:
                    self._evict(jid)
            if expired:
                logger.debug("JobStore reaper: evicted %d expired jobs", len(expired))


# ── Factory ───────────────────────────────────────────────────────────────────

def _build_store() -> RedisJobStore | InMemoryJobStore:
    try:
        return RedisJobStore(REDIS_URL, JOB_TTL_SECONDS)
    except Exception as exc:
        logger.warning("JobStore: Redis connection failed (%s) — falling back to in-memory", exc)
        return InMemoryJobStore(JOB_TTL_SECONDS)


# ── Singleton ─────────────────────────────────────────────────────────────────
job_store = _build_store()
