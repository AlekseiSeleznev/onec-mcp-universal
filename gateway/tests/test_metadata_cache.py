"""Tests for metadata cache."""

import builtins
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.metadata_cache import MetadataCache


def _make_cache(ttl=60):
    """Create a MetadataCache with a fixed TTL (bypass settings property)."""
    class _FixedTtlCache(MetadataCache):
        @property
        def ttl(self):
            return ttl

    return _FixedTtlCache()


def test_put_and_get():
    c = _make_cache(ttl=60)
    c.put({"filter": "Справочник.Контрагенты"}, '{"data": "test"}')
    result = c.get({"filter": "Справочник.Контрагенты"})
    assert result == '{"data": "test"}'


def test_miss():
    c = _make_cache(ttl=60)
    assert c.get({"filter": "Справочник.Контрагенты"}) is None


def test_ttl_expiry():
    c = _make_cache(ttl=0)  # immediate expiry
    c.put({"filter": "test"}, "value")
    # TTL=0 means expires at monotonic + 0
    time.sleep(0.01)
    assert c.get({"filter": "test"}) is None


def test_invalidate():
    c = _make_cache(ttl=60)
    c.put({"a": 1}, "v1")
    c.put({"b": 2}, "v2")
    result = c.invalidate()
    assert "2" in result  # 2 entries removed
    assert c.get({"a": 1}) is None


def test_stats():
    c = _make_cache(ttl=60)
    c.put({"a": 1}, "v")
    c.get({"a": 1})  # hit
    c.get({"b": 2})  # miss
    stats = c.stats()
    assert stats["entries"] == 1
    assert stats["hits"] == 1
    assert stats["misses"] == 1


def test_same_args_different_order():
    c = _make_cache(ttl=60)
    c.put({"b": 2, "a": 1}, "value")
    # Same args, different order → same key
    assert c.get({"a": 1, "b": 2}) == "value"


def test_stats_expired_cleanup():
    c = _make_cache(ttl=0)
    c.put({"a": 1}, "v")
    time.sleep(0.01)
    stats = c.stats()
    assert stats["entries"] == 0  # expired entry cleaned up


def test_stats_hit_rate_format():
    c = _make_cache(ttl=60)
    c.put({"a": 1}, "v")
    c.get({"a": 1})  # hit
    c.get({"a": 1})  # hit
    c.get({"b": 2})  # miss
    stats = c.stats()
    assert stats["hit_rate"] == "67%"


def test_ttl_in_stats():
    c = _make_cache(ttl=3600)
    stats = c.stats()
    assert stats["ttl_seconds"] == 3600


def test_ttl_reads_from_settings_when_available():
    c = MetadataCache()

    with patch("gateway.config.settings") as settings:
        settings.metadata_cache_ttl = 123
        assert c.ttl == 123


def test_ttl_falls_back_to_default_when_settings_import_fails(monkeypatch):
    real_import = builtins.__import__

    def _raising_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "gateway.config" or (level and fromlist and name == "config"):
            raise RuntimeError("boom")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _raising_import)
    assert MetadataCache().ttl == 600
