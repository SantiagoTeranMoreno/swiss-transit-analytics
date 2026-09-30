"""A tiny in-process TTL cache.

The data changes at most every few minutes (live) or once a day (history), and the
free database tier has few connections, so identical requests are answered from
memory instead of hitting Postgres again.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Hashable
from typing import TypeVar

T = TypeVar("T")

_store: dict[Hashable, tuple[float, object]] = {}
_lock = threading.Lock()


def cached(key: Hashable, ttl_s: float, compute: Callable[[], T]) -> T:
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
    if hit and hit[0] > now:
        return hit[1]  # type: ignore[return-value]
    value = compute()
    with _lock:
        _store[key] = (now + ttl_s, value)
    return value


def clear() -> None:
    with _lock:
        _store.clear()
