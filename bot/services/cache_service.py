"""In-memory TTL cache for user data to reduce DB load."""
from __future__ import annotations

from typing import Any, Optional

from cachetools import TTLCache


class CacheService:
    """Thread-safe TTL cache with namespacing."""

    def __init__(self, maxsize: int = 10000, ttl: int = 300) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)

    def get(self, key: str) -> Optional[Any]:
        try:
            return self._cache.get(key)
        except Exception:
            return None

    def set(self, key: str, value: Any) -> None:
        try:
            self._cache[key] = value
        except Exception:
            pass

    def delete(self, key: str) -> None:
        try:
            self._cache.pop(key, None)
        except Exception:
            pass

    def clear_namespace(self, prefix: str) -> None:
        try:
            keys = [k for k in self._cache.keys() if k.startswith(prefix)]
            for k in keys:
                self._cache.pop(k, None)
        except Exception:
            pass


# Global singletons by TTL
user_cache = CacheService(maxsize=10000, ttl=300)       # 5 min
subscription_cache = CacheService(maxsize=10000, ttl=60)  # 1 min
usage_cache = CacheService(maxsize=10000, ttl=30)       # 30 sec
