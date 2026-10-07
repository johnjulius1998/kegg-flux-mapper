"""Thread-safe bounded LRU cache with single-flight computation."""

import threading
from collections import OrderedDict
from typing import Callable, Generic, Hashable, TypeVar

V = TypeVar("V")
_MISSING = object()


class LRUCache(Generic[V]):
    """Least-recently-used cache; concurrent misses on one key compute it only once."""

    def __init__(self, maxsize: int):
        self.maxsize = maxsize
        self._data: OrderedDict[Hashable, V] = OrderedDict()
        self._lock = threading.Lock()
        self._inflight: dict[Hashable, threading.Lock] = {}

    def get(self, key: Hashable, default=None):
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                return self._data[key]
        return default

    def get_or_compute(self, key: Hashable, compute: Callable[[], V]) -> V:
        value = self.get(key, _MISSING)
        if value is not _MISSING:
            return value
        with self._lock:
            key_lock = self._inflight.setdefault(key, threading.Lock())
        with key_lock:
            value = self.get(key, _MISSING)
            if value is not _MISSING:
                return value
            try:
                value = compute()
                with self._lock:
                    self._data[key] = value
                    self._data.move_to_end(key)
                    while len(self._data) > self.maxsize:
                        self._data.popitem(last=False)
            finally:
                with self._lock:
                    self._inflight.pop(key, None)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
