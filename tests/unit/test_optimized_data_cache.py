"""Tests for the OptimizedDataCache helper."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from tests.helpers.homeassistant_test_stubs import install_homeassistant_stubs

# Ensure Home Assistant stubs are available for helper imports.
install_homeassistant_stubs()

from homeassistant.util import dt as dt_util

if not hasattr(dt_util, "utcnow"):
    dt_util.utcnow = lambda: datetime.now(UTC)

from custom_components.pawcontrol import helpers as helpers_module
from custom_components.pawcontrol.helpers import OptimizedDataCache


def test_get_handles_expiration(monkeypatch) -> None:
    """The cache should respect TTL values when retrieving entries."""

    async def _run() -> None:
        cache = OptimizedDataCache(default_ttl_seconds=5)
        base_time = dt_util.utcnow()

        monkeypatch.setattr(dt_util, "utcnow", lambda: base_time)
        monkeypatch.setattr(helpers_module.dt_util, "utcnow", lambda: base_time)
        await cache.set("active", "value", ttl_seconds=5)
        await cache.set("expired", "value", ttl_seconds=5)

        # Not expired yet
        monkeypatch.setattr(dt_util, "utcnow", lambda: base_time + timedelta(seconds=4))
        monkeypatch.setattr(
            helpers_module.dt_util,
            "utcnow",
            lambda: base_time + timedelta(seconds=4),
        )
        assert await cache.get("active") == "value"

        # Expired entry should be removed and return the default
        monkeypatch.setattr(dt_util, "utcnow", lambda: base_time + timedelta(seconds=6))
        monkeypatch.setattr(
            helpers_module.dt_util,
            "utcnow",
            lambda: base_time + timedelta(seconds=6),
        )
        assert await cache.get("expired", default="missing") == "missing"

    asyncio.run(_run())


def test_set_normalizes_ttl(monkeypatch) -> None:
    """Ensure TTL normalization keeps non-positive values from expiring immediately."""

    async def _run() -> None:
        cache = OptimizedDataCache(default_ttl_seconds=5)
        base_time = dt_util.utcnow()

        monkeypatch.setattr(dt_util, "utcnow", lambda: base_time)
        monkeypatch.setattr(helpers_module.dt_util, "utcnow", lambda: base_time)
        await cache.set("positive", "value", ttl_seconds=10)
        await cache.set("zero", "value", ttl_seconds=0)
        await cache.set("negative", "value", ttl_seconds=-10)

        assert cache._ttls["positive"] == 10
        assert cache._ttls["zero"] == 0
        assert cache._ttls["negative"] == 0

        # Entries with normalized zero TTLs should persist.
        monkeypatch.setattr(dt_util, "utcnow", lambda: base_time + timedelta(hours=1))
        monkeypatch.setattr(
            helpers_module.dt_util,
            "utcnow",
            lambda: base_time + timedelta(hours=1),
        )
        assert await cache.get("zero") == "value"
        assert await cache.get("negative") == "value"

    asyncio.run(_run())


def test_cleanup_expired_respects_override(monkeypatch) -> None:
    """cleanup_expired should remove entries based on stored and override TTLs."""

    async def _run() -> None:
        cache = OptimizedDataCache(default_ttl_seconds=5)
        base_time = dt_util.utcnow()

        monkeypatch.setattr(dt_util, "utcnow", lambda: base_time)
        monkeypatch.setattr(helpers_module.dt_util, "utcnow", lambda: base_time)
        await cache.set("short", "value", ttl_seconds=5)
        await cache.set("long", "value", ttl_seconds=20)

        # Without override TTL only the short-lived entry should expire.
        monkeypatch.setattr(dt_util, "utcnow", lambda: base_time + timedelta(seconds=7))
        monkeypatch.setattr(
            helpers_module.dt_util,
            "utcnow",
            lambda: base_time + timedelta(seconds=7),
        )
        assert await cache.cleanup_expired() == 1
        assert "long" in cache._cache

        # Override TTL should force expiration even if the stored TTL is longer.
        monkeypatch.setattr(dt_util, "utcnow", lambda: base_time + timedelta(seconds=8))
        monkeypatch.setattr(
            helpers_module.dt_util,
            "utcnow",
            lambda: base_time + timedelta(seconds=8),
        )
        assert await cache.cleanup_expired(ttl_seconds=6) == 1
        assert await cache.get("long", default=None) is None

    asyncio.run(_run())


def test_cleanup_expired_does_not_extend_ttl(monkeypatch) -> None:
    """An override longer than the stored TTL should not prolong cache life."""

    async def _run() -> None:
        cache = OptimizedDataCache(default_ttl_seconds=5)
        base_time = dt_util.utcnow()

        monkeypatch.setattr(dt_util, "utcnow", lambda: base_time)
        monkeypatch.setattr(helpers_module.dt_util, "utcnow", lambda: base_time)
        await cache.set("short", "value", ttl_seconds=5)

        # Advance beyond the stored TTL but supply a longer override.
        monkeypatch.setattr(dt_util, "utcnow", lambda: base_time + timedelta(seconds=8))
        monkeypatch.setattr(
            helpers_module.dt_util,
            "utcnow",
            lambda: base_time + timedelta(seconds=8),
        )
        assert await cache.cleanup_expired(ttl_seconds=30) == 1
        assert await cache.get("short") is None

    asyncio.run(_run())


def test_cleanup_diagnostics_reports_override_activity(monkeypatch) -> None:
    """Diagnostics should surface override-driven cleanup metrics."""

    async def _run() -> None:
        cache = OptimizedDataCache(default_ttl_seconds=300)
        base_time = dt_util.utcnow()

        monkeypatch.setattr(dt_util, "utcnow", lambda: base_time)
        monkeypatch.setattr(helpers_module.dt_util, "utcnow", lambda: base_time)

        await cache.set("dog", {"name": "Nova"}, ttl_seconds=300)

        diagnostics = cache.get_diagnostics()
        assert diagnostics["cleanup_invocations"] == 0
        assert diagnostics["expired_entries"] == 0

        monkeypatch.setattr(
            dt_util,
            "utcnow",
            lambda: base_time + timedelta(seconds=360),
        )
        monkeypatch.setattr(
            helpers_module.dt_util,
            "utcnow",
            lambda: base_time + timedelta(seconds=360),
        )

        removed = await cache.cleanup_expired(ttl_seconds=90)
        assert removed == 1

        diagnostics = cache.get_diagnostics()
        assert diagnostics["cleanup_invocations"] == 1
        assert diagnostics["expired_entries"] == 1
        assert diagnostics["expired_via_override"] == 1
        assert diagnostics["last_expired_count"] == 1
        assert diagnostics["last_override_ttl"] == 90
        assert diagnostics["last_cleanup"] is not None

    asyncio.run(_run())
