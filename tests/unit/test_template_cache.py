"""Tests for the template cache diagnostics helpers."""

from __future__ import annotations

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
  """The template cache returns typed stats and metadata snapshots."""

  cache: TemplateCache[TemplatePayload] = TemplateCache(maxsize=2)

  template: CardConfig = {"type": "button", "name": "Test"}
  await cache.set("button", template)

  cached_template = await cache.get("button")
  assert cached_template == template
  assert cached_template is not template

  # Trigger a miss so we can verify hit-rate calculations.
  missing_template = await cache.get("missing")
  assert missing_template is None

  stats = cache.get_stats()
  assert stats["hits"] == 1
  assert stats["misses"] == 1
  assert stats["cached_items"] == 1
  assert stats["evictions"] == 0
  assert stats["hit_rate"] == pytest.approx(50.0)

  metadata = cache.get_metadata()
  assert metadata["cached_keys"] == ["button"]
  assert metadata["ttl_seconds"] == TEMPLATE_TTL_SECONDS
  assert metadata["max_size"] == 2

  snapshot: TemplateCacheSnapshot = cache.coordinator_snapshot()
  assert snapshot["stats"] == stats
  assert snapshot["metadata"]["cached_keys"] == ["button"]

  # Confirm evictions update stats and metadata coherently.
  await cache.set("secondary", {"type": "grid", "cards": []})
  await cache.set("tertiary", {"type": "entities", "entities": []})
  updated_stats = cache.get_stats()
  assert updated_stats["evictions"] == 1


@pytest.mark.asyncio
async def test_template_cache_ttl_invalidation(monkeypatch: pytest.MonkeyPatch) -> None:
  """Entries expire when accessed beyond their configured TTL."""

  cache: TemplateCache[TemplatePayload] = TemplateCache(maxsize=1)

  now = datetime.now(UTC)
  monkeypatch.setattr(
    "custom_components.pawcontrol.dashboard_templates.dt_util.utcnow",
    lambda: now,
  )

  template: CardConfig = {"type": "entities"}
  await cache.set("expiring", template)

  # Advance beyond the TTL and ensure the cached value is purged on access.
  monkeypatch.setattr(
    "custom_components.pawcontrol.dashboard_templates.dt_util.utcnow",
    lambda: now + timedelta(seconds=TEMPLATE_TTL_SECONDS + 1),
  )

  expired = await cache.get("expiring")
  assert expired is None

  stats = cache.get_stats()
  assert stats["misses"] >= 1
