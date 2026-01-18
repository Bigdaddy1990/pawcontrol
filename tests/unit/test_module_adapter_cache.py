"""Unit tests for module adapter cache telemetry helpers."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest
from custom_components.pawcontrol.types import ModuleCacheMetrics

MODULE_PATH = (
  Path(__file__).resolve().parents[2]
  / "custom_components"
  / "pawcontrol"
  / "module_adapters.py"
)


def _load_module() -> ModuleType:
  """Import ``module_adapters`` with the lightweight test shims."""

  custom_components_pkg = ModuleType("custom_components")
  custom_components_pkg.__path__ = [
    str(Path(__file__).resolve().parents[2] / "custom_components")
  ]
  sys.modules.setdefault("custom_components", custom_components_pkg)

  pawcontrol_pkg = ModuleType("custom_components.pawcontrol")
  pawcontrol_pkg.__path__ = [
    str(Path(__file__).resolve().parents[2] / "custom_components" / "pawcontrol")
  ]
  sys.modules.setdefault("custom_components.pawcontrol", pawcontrol_pkg)

  # ``module_adapters`` depends on Home Assistant time helpers; provide a shim
  # that mirrors the API surface the cache relies upon.
  ha_pkg = ModuleType("homeassistant")
  ha_pkg.__path__ = []
  sys.modules.setdefault("homeassistant", ha_pkg)

  ha_util = ModuleType("homeassistant.util")
  ha_util_dt = ModuleType("homeassistant.util.dt")
  ha_util_dt.utcnow = lambda: datetime.now(UTC)
  ha_util.dt = ha_util_dt
  sys.modules.setdefault("homeassistant.util", ha_util)
  sys.modules.setdefault("homeassistant.util.dt", ha_util_dt)

  # ``aiohttp`` is only used for typing, so a minimal shim is sufficient.
  aiohttp_pkg = ModuleType("aiohttp")

  class _ClientSession:  # pragma: no cover - trivial shim for imports
    pass

  aiohttp_pkg.ClientSession = _ClientSession
  sys.modules.setdefault("aiohttp", aiohttp_pkg)

  spec = importlib.util.spec_from_file_location(
    "custom_components.pawcontrol.module_adapters",
    MODULE_PATH,
  )
  if spec is None or spec.loader is None:  # pragma: no cover - defensive guard
    raise RuntimeError("Unable to load module_adapters for testing")

  module = importlib.util.module_from_spec(spec)
  sys.modules.setdefault("custom_components.pawcontrol.module_adapters", module)
  spec.loader.exec_module(module)
  return module


MODULE = _load_module()


def _load_monitor() -> type:
  from custom_components.pawcontrol.data_manager import _CoordinatorModuleCacheMonitor

  return _CoordinatorModuleCacheMonitor


COORDINATOR_MONITOR = _load_monitor()


def test_expiring_cache_snapshot_tracks_hits_and_metadata() -> None:
  """The cache snapshot should expose typed statistics and metadata."""

  cache = MODULE._ExpiringCache[int](timedelta(seconds=5))
  cache.set("alpha", 1)
  assert cache.get("alpha") == 1
  assert cache.get("missing") is None

  snapshot = cache.snapshot()
  stats = snapshot["stats"]
  metadata = snapshot["metadata"]

  assert stats == {
    "entries": 1,
    "hits": 1,
    "misses": 1,
    "hit_rate": pytest.approx(50.0),
  }
  assert metadata["ttl_seconds"] == pytest.approx(5.0)
  assert "last_cleanup" not in metadata

  now = datetime.now(UTC) + timedelta(seconds=10)
  assert cache.cleanup(now) == 1

  post_cleanup = cache.snapshot()
  post_stats = post_cleanup["stats"]
  post_metadata = post_cleanup["metadata"]

  assert post_stats == {
    "entries": 0,
    "hits": 1,
    "misses": 1,
    "hit_rate": pytest.approx(50.0),
  }
  assert post_metadata["ttl_seconds"] == pytest.approx(5.0)
  assert post_metadata["last_cleanup"] == now
  assert post_metadata["last_expired_count"] == 1
  assert post_metadata["expired_total"] == 1


def test_base_adapter_snapshot_without_cache() -> None:
  """Adapters without caching still expose a typed snapshot."""

  adapter = MODULE._BaseModuleAdapter[int](ttl=None)
  snapshot = adapter.cache_snapshot()

  assert snapshot == {
    "stats": {"entries": 0, "hits": 0, "misses": 0, "hit_rate": 0.0},
    "metadata": {"ttl_seconds": None},
  }


class _DummyAdapter:
  """Adapter stub that returns fixed cache telemetry."""

  def __init__(self, entries: int, hits: int, misses: int) -> None:
    self._metrics = ModuleCacheMetrics(entries=entries, hits=hits, misses=misses)
    self._snapshot = {
      "stats": {
        "entries": entries,
        "hits": hits,
        "misses": misses,
        "hit_rate": self._metrics.hit_rate,
      },
      "metadata": {"ttl_seconds": 5.0},
    }

  def cache_metrics(self) -> ModuleCacheMetrics:
    return self._metrics

  def cache_snapshot(self) -> dict[str, object]:
    return self._snapshot


class _ErrorAdapter(_DummyAdapter):
  """Adapter stub that raises when snapshotting telemetry."""

  def cache_snapshot(self) -> dict[str, object]:  # type: ignore[override]
    raise RuntimeError("broken snapshot")


class _Container:
  """Container stub that mimics ``CoordinatorModuleAdapters``."""

  def __init__(self, **adapters: object) -> None:
    self._adapters = adapters
    for name, adapter in adapters.items():
      setattr(self, name, adapter)

  def cache_metrics(self) -> ModuleCacheMetrics:
    aggregate = ModuleCacheMetrics()
    for adapter in self._adapters.values():
      metrics = adapter.cache_metrics()
      aggregate.entries += metrics.entries
      aggregate.hits += metrics.hits
      aggregate.misses += metrics.misses
    return aggregate


def test_coordinator_module_cache_monitor_exposes_typed_snapshots() -> None:
  """Coordinator telemetry should surface typed per-module snapshots."""

  adapters = {
    "feeding": _DummyAdapter(entries=2, hits=4, misses=1),
    "walk": _DummyAdapter(entries=1, hits=1, misses=0),
    "geofencing": _DummyAdapter(entries=0, hits=0, misses=0),
    "health": _DummyAdapter(entries=3, hits=1, misses=2),
    "weather": _DummyAdapter(entries=1, hits=0, misses=1),
    "garden": _DummyAdapter(entries=1, hits=0, misses=1),
  }
  monitor = COORDINATOR_MONITOR(_Container(**adapters))

  snapshot = monitor.coordinator_snapshot()
  assert snapshot.stats == {
    "entries": 8,
    "hits": 6,
    "misses": 5,
    "hit_rate": pytest.approx(54.55, rel=1e-3),
  }

  diagnostics = snapshot.diagnostics
  assert diagnostics is not None
  per_module = diagnostics.get("per_module", {})

  assert set(per_module.keys()) == set(adapters.keys())
  for payload in per_module.values():
    assert payload["metadata"]["ttl_seconds"] == pytest.approx(5.0)
    assert set(payload["stats"]) == {"entries", "hits", "misses", "hit_rate"}


def test_coordinator_module_cache_monitor_records_snapshot_errors() -> None:
  """Errors when collecting snapshots should be preserved in diagnostics."""

  adapters = {
    "feeding": _DummyAdapter(entries=1, hits=1, misses=1),
    "walk": _ErrorAdapter(entries=0, hits=0, misses=1),
    "geofencing": _DummyAdapter(entries=0, hits=0, misses=0),
    "health": _DummyAdapter(entries=0, hits=0, misses=0),
    "weather": _DummyAdapter(entries=0, hits=0, misses=0),
    "garden": _DummyAdapter(entries=0, hits=0, misses=0),
  }
  monitor = COORDINATOR_MONITOR(_Container(**adapters))

  diagnostics = monitor.get_diagnostics()
  per_module = diagnostics["per_module"]

  assert per_module["walk"] == {"error": "broken snapshot"}
