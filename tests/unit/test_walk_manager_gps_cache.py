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
  """The GPS cache exposes typed stats, metadata, and hit counters."""

  cache: GPSCache[CachedGPSLocation] = GPSCache(max_size=2)

  # First lookup misses, then populate and retrieve the entry to record a hit.
  assert cache.get_location("luna") is None

  now = datetime.now(UTC)
  cache.set_location("luna", 1.0, 2.0, now)
  assert cache.get_location("luna") == (1.0, 2.0, now)

  # Populate additional entries to force eviction and exercise metrics.
  cache.set_location("max", 3.0, 4.0, now)
  cache.set_location("bella", 5.0, 6.0, now)

  stats = cache.get_stats()
  assert stats["hits"] == 1
  assert stats["misses"] == 1
  assert stats["cached_locations"] == 2
  assert stats["evictions"] == 1
  assert stats["hit_rate"] == pytest.approx(50.0)

  metadata = cache.get_metadata()
  assert sorted(metadata["cached_dogs"]) == ["bella", "max"]
  assert metadata["evictions"] == 1

  snapshot: GPSCacheSnapshot = cache.coordinator_snapshot()
  assert snapshot["stats"] == stats
  assert snapshot["metadata"]["evictions"] == 1

  # Distance cache keys should deduplicate via order invariant hashing.
  distance_first = cache.calculate_distance_cached((0.0, 0.0), (1.0, 1.0))
  distance_second = cache.calculate_distance_cached((1.0, 1.0), (0.0, 0.0))
  assert distance_first == distance_second

  updated_stats = cache.get_stats()
  assert updated_stats["distance_cache_entries"] == 1
