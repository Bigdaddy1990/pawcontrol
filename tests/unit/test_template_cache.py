"""Tests for the template cache diagnostics helpers."""

from datetime import UTC, datetime, timedelta
from typing import TypeAlias

import pytest

from custom_components.pawcontrol.dashboard_shared import CardCollection, CardConfig
from custom_components.pawcontrol.dashboard_templates import (
    TEMPLATE_TTL_SECONDS,
    TemplateCache,
    TemplateCacheSnapshot,
)

type TemplatePayload = CardConfig | CardCollection


@pytest.mark.asyncio
async def test_template_cache_stats_and_snapshot() -> None:
    """The template cache returns typed stats and metadata snapshots."""  # noqa: E111

    cache: TemplateCache[TemplatePayload] = TemplateCache(maxsize=2)  # noqa: E111

    template: CardConfig = {"type": "button", "name": "Test"}  # noqa: E111
    await cache.set("button", template)  # noqa: E111

    cached_template = await cache.get("button")  # noqa: E111
    assert cached_template == template  # noqa: E111
    assert cached_template is not template  # noqa: E111

    # Trigger a miss so we can verify hit-rate calculations.  # noqa: E114
    missing_template = await cache.get("missing")  # noqa: E111
    assert missing_template is None  # noqa: E111

    stats = cache.get_stats()  # noqa: E111
    assert stats["hits"] == 1  # noqa: E111
    assert stats["misses"] == 1  # noqa: E111
    assert stats["cached_items"] == 1  # noqa: E111
    assert stats["evictions"] == 0  # noqa: E111
    assert stats["hit_rate"] == pytest.approx(50.0)  # noqa: E111

    metadata = cache.get_metadata()  # noqa: E111
    assert metadata["cached_keys"] == ["button"]  # noqa: E111
    assert metadata["ttl_seconds"] == TEMPLATE_TTL_SECONDS  # noqa: E111
    assert metadata["max_size"] == 2  # noqa: E111

    snapshot: TemplateCacheSnapshot = cache.coordinator_snapshot()  # noqa: E111
    assert snapshot["stats"] == stats  # noqa: E111
    assert snapshot["metadata"]["cached_keys"] == ["button"]  # noqa: E111

    # Confirm evictions update stats and metadata coherently.  # noqa: E114
    await cache.set("secondary", {"type": "grid", "cards": []})  # noqa: E111
    await cache.set("tertiary", {"type": "entities", "entities": []})  # noqa: E111
    updated_stats = cache.get_stats()  # noqa: E111
    assert updated_stats["evictions"] == 1  # noqa: E111


@pytest.mark.asyncio
async def test_template_cache_ttl_invalidation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Entries expire when accessed beyond their configured TTL."""  # noqa: E111

    cache: TemplateCache[TemplatePayload] = TemplateCache(maxsize=1)  # noqa: E111

    now = datetime.now(UTC)  # noqa: E111
    monkeypatch.setattr(  # noqa: E111
        "custom_components.pawcontrol.dashboard_templates.dt_util.utcnow",
        lambda: now,
    )

    template: CardConfig = {"type": "entities"}  # noqa: E111
    await cache.set("expiring", template)  # noqa: E111

    # Advance beyond the TTL and ensure the cached value is purged on access.  # noqa: E114, E501
    monkeypatch.setattr(  # noqa: E111
        "custom_components.pawcontrol.dashboard_templates.dt_util.utcnow",
        lambda: now + timedelta(seconds=TEMPLATE_TTL_SECONDS + 1),
    )

    expired = await cache.get("expiring")  # noqa: E111
    assert expired is None  # noqa: E111

    stats = cache.get_stats()  # noqa: E111
    assert stats["misses"] >= 1  # noqa: E111
