"""Unit tests for the GPS cache helpers in the walk manager."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.pawcontrol.walk_manager import (
  CachedGPSLocation,
  GPSCache,
  GPSCacheSnapshot,
)


def test_gps_cache_stats_and_snapshot() -> None:
  """The GPS cache exposes typed stats, metadata, and hit counters."""  # noqa: E111

  cache: GPSCache[CachedGPSLocation] = GPSCache(max_size=2)  # noqa: E111

  # First lookup misses, then populate and retrieve the entry to record a hit.  # noqa: E114
  assert cache.get_location("luna") is None  # noqa: E111

  now = datetime.now(UTC)  # noqa: E111
  cache.set_location("luna", 1.0, 2.0, now)  # noqa: E111
  assert cache.get_location("luna") == (1.0, 2.0, now)  # noqa: E111

  # Populate additional entries to force eviction and exercise metrics.  # noqa: E114
  cache.set_location("max", 3.0, 4.0, now)  # noqa: E111
  cache.set_location("bella", 5.0, 6.0, now)  # noqa: E111

  stats = cache.get_stats()  # noqa: E111
  assert stats["hits"] == 1  # noqa: E111
  assert stats["misses"] == 1  # noqa: E111
  assert stats["cached_locations"] == 2  # noqa: E111
  assert stats["evictions"] == 1  # noqa: E111
  assert stats["hit_rate"] == pytest.approx(50.0)  # noqa: E111

  metadata = cache.get_metadata()  # noqa: E111
  assert sorted(metadata["cached_dogs"]) == ["bella", "max"]  # noqa: E111
  assert metadata["evictions"] == 1  # noqa: E111

  snapshot: GPSCacheSnapshot = cache.coordinator_snapshot()  # noqa: E111
  assert snapshot["stats"] == stats  # noqa: E111
  assert snapshot["metadata"]["evictions"] == 1  # noqa: E111

  # Distance cache keys should deduplicate via order invariant hashing.  # noqa: E114
  distance_first = cache.calculate_distance_cached((0.0, 0.0), (1.0, 1.0))  # noqa: E111
  distance_second = cache.calculate_distance_cached((1.0, 1.0), (0.0, 0.0))  # noqa: E111
  assert distance_first == distance_second  # noqa: E111

  updated_stats = cache.get_stats()  # noqa: E111
  assert updated_stats["distance_cache_entries"] == 1  # noqa: E111
