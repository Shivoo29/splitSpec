"""Tiny in-process read cache with explicit invalidation.

A write bumps the version and clears the store, so no stale entry can survive.
"""
from __future__ import annotations


class Cache:
    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._version = 0

    def get(self, key: str) -> object | None:
        entry = self._data.get(key)
        if entry is None or entry["version"] != self._version:
            return None
        return entry["value"]

    def set(self, key: str, value: object) -> None:
        self._data[key] = {"version": self._version, "value": value}

    def invalidate(self) -> None:
        self._version += 1
        self._data.clear()