"""Tests for metadata cache."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.metadata_cache import MetadataCache


def test_put_and_get():
    c = MetadataCache(ttl=60)
    c.put({"filter": "Справочник.Контрагенты"}, '{"data": "test"}')
    result = c.get({"filter": "Справочник.Контрагенты"})
    assert result == '{"data": "test"}'


def test_miss():
    c = MetadataCache(ttl=60)
    assert c.get({"filter": "Справочник.Контрагенты"}) is None


def test_ttl_expiry():
    c = MetadataCache(ttl=0)  # immediate expiry
    c.put({"filter": "test"}, "value")
    # TTL=0 means expires at monotonic + 0
    time.sleep(0.01)
    assert c.get({"filter": "test"}) is None


def test_invalidate():
    c = MetadataCache(ttl=60)
    c.put({"a": 1}, "v1")
    c.put({"b": 2}, "v2")
    result = c.invalidate()
    assert "2" in result  # 2 entries removed
    assert c.get({"a": 1}) is None


def test_stats():
    c = MetadataCache(ttl=60)
    c.put({"a": 1}, "v")
    c.get({"a": 1})  # hit
    c.get({"b": 2})  # miss
    stats = c.stats()
    assert stats["entries"] == 1
    assert stats["hits"] == 1
    assert stats["misses"] == 1


def test_same_args_different_order():
    c = MetadataCache(ttl=60)
    c.put({"b": 2, "a": 1}, "value")
    # Same args, different order → same key
    assert c.get({"a": 1, "b": 2}) == "value"
