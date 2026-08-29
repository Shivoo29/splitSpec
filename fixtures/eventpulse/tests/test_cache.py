"""Cache module: set/get roundtrip and explicit invalidation."""
from __future__ import annotations

from app.cache import Cache


def test_get_set_roundtrip():
    cache = Cache()
    cache.set("events:1", {"items": [1]})
    assert cache.get("events:1") == {"items": [1]}


def test_missing_key_returns_none():
    assert Cache().get("nope") is None


def test_invalidate_clears_everything():
    cache = Cache()
    cache.set("a", 1)
    cache.invalidate()
    assert cache.get("a") is None


def test_writes_after_invalidate_do_not_resurrect_old_entries():
    cache = Cache()
    cache.set("a", 1)
    cache.invalidate()
    cache.set("b", 2)
    assert cache.get("a") is None
    assert cache.get("b") == 2