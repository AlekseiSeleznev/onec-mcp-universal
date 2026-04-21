"""
In-memory metadata cache with TTL for get_metadata responses.
Avoids repeated slow queries to 1C for the same metadata structure.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time

log = logging.getLogger(__name__)

DEFAULT_TTL = 600  # 10 minutes


class MetadataCache:
    """Simple TTL cache for metadata tool responses."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}
        self._hits = 0
        self._misses = 0

    @property
    def ttl(self) -> int:
        try:
            from .config import settings
            return settings.metadata_cache_ttl
        except Exception:
            return DEFAULT_TTL

    def _key(self, arguments: dict) -> str:
        """Deterministic cache key from tool arguments."""
        canonical = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(canonical.encode()).hexdigest()

    def get(self, arguments: dict) -> str | None:
        """Return cached response or None if miss/expired."""
        key = self._key(arguments)
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        expires_at, response = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            self._misses += 1
            return None
        self._hits += 1
        return response

    def put(self, arguments: dict, response: str) -> None:
        """Store response with TTL."""
        key = self._key(arguments)
        self._store[key] = (time.monotonic() + self.ttl, response)

    def invalidate(self) -> str:
        """Clear all cached entries."""
        count = len(self._store)
        self._store.clear()
        self._hits = 0
        self._misses = 0
        return f"Кеш метаданных очищен ({count} записей удалено)."

    def stats(self) -> dict:
        """Return cache statistics."""
        # Clean expired entries
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
        return {
            "entries": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits / max(1, self._hits + self._misses) * 100:.0f}%",
            "ttl_seconds": self.ttl,
        }


# Singleton
metadata_cache = MetadataCache()
