"""Unit tests for module adapter cache telemetry helpers."""

from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
import sys
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
  """Import ``module_adapters`` with the lightweight test shims."""  # noqa: E111

  custom_components_pkg = ModuleType("custom_components")  # noqa: E111
  custom_components_pkg.__path__ = [  # noqa: E111
    str(Path(__file__).resolve().parents[2] / "custom_components")
  ]
  sys.modules.setdefault("custom_components", custom_components_pkg)  # noqa: E111

  pawcontrol_pkg = ModuleType("custom_components.pawcontrol")  # noqa: E111
  pawcontrol_pkg.__path__ = [  # noqa: E111
    str(Path(__file__).resolve().parents[2] / "custom_components" / "pawcontrol")
  ]
  sys.modules.setdefault("custom_components.pawcontrol", pawcontrol_pkg)  # noqa: E111

  # ``module_adapters`` depends on Home Assistant time helpers; provide a shim  # noqa: E114, E501
  # that mirrors the API surface the cache relies upon.  # noqa: E114
  ha_pkg = ModuleType("homeassistant")  # noqa: E111
  ha_pkg.__path__ = []  # noqa: E111
  sys.modules.setdefault("homeassistant", ha_pkg)  # noqa: E111

  ha_util = ModuleType("homeassistant.util")  # noqa: E111
  ha_util_dt = ModuleType("homeassistant.util.dt")  # noqa: E111
  ha_util_dt.utcnow = lambda: datetime.now(UTC)  # noqa: E111
  ha_util.dt = ha_util_dt  # noqa: E111
  sys.modules.setdefault("homeassistant.util", ha_util)  # noqa: E111
  sys.modules.setdefault("homeassistant.util.dt", ha_util_dt)  # noqa: E111

  # ``aiohttp`` is only used for typing, so a minimal shim is sufficient.  # noqa: E114
  aiohttp_pkg = ModuleType("aiohttp")  # noqa: E111

  class _ClientSession:  # pragma: no cover - trivial shim for imports  # noqa: E111
    pass

  aiohttp_pkg.ClientSession = _ClientSession  # noqa: E111
  sys.modules.setdefault("aiohttp", aiohttp_pkg)  # noqa: E111

  spec = importlib.util.spec_from_file_location(  # noqa: E111
    "custom_components.pawcontrol.module_adapters",
    MODULE_PATH,
  )
  if (  # noqa: E111
    spec is None or spec.loader is None
  ):  # pragma: no cover - defensive guard
    raise RuntimeError("Unable to load module_adapters for testing")

  module = importlib.util.module_from_spec(spec)  # noqa: E111
  sys.modules.setdefault("custom_components.pawcontrol.module_adapters", module)  # noqa: E111
  spec.loader.exec_module(module)  # noqa: E111
  return module  # noqa: E111


MODULE = _load_module()


def _load_monitor() -> type:
  from custom_components.pawcontrol.data_manager import _CoordinatorModuleCacheMonitor

  return _CoordinatorModuleCacheMonitor  # noqa: E111


COORDINATOR_MONITOR = _load_monitor()


def test_expiring_cache_snapshot_tracks_hits_and_metadata() -> None:
  """The cache snapshot should expose typed statistics and metadata."""  # noqa: E111

  cache = MODULE._ExpiringCache[int](timedelta(seconds=5))  # noqa: E111
  cache.set("alpha", 1)  # noqa: E111
  assert cache.get("alpha") == 1  # noqa: E111
  assert cache.get("missing") is None  # noqa: E111

  snapshot = cache.snapshot()  # noqa: E111
  stats = snapshot["stats"]  # noqa: E111
  metadata = snapshot["metadata"]  # noqa: E111

  assert stats == {  # noqa: E111
    "entries": 1,
    "hits": 1,
    "misses": 1,
    "hit_rate": pytest.approx(50.0),
  }
  assert metadata["ttl_seconds"] == pytest.approx(5.0)  # noqa: E111
  assert "last_cleanup" not in metadata  # noqa: E111

  now = datetime.now(UTC) + timedelta(seconds=10)  # noqa: E111
  assert cache.cleanup(now) == 1  # noqa: E111

  post_cleanup = cache.snapshot()  # noqa: E111
  post_stats = post_cleanup["stats"]  # noqa: E111
  post_metadata = post_cleanup["metadata"]  # noqa: E111

  assert post_stats == {  # noqa: E111
    "entries": 0,
    "hits": 1,
    "misses": 1,
    "hit_rate": pytest.approx(50.0),
  }
  assert post_metadata["ttl_seconds"] == pytest.approx(5.0)  # noqa: E111
  assert post_metadata["last_cleanup"] == now  # noqa: E111
  assert post_metadata["last_expired_count"] == 1  # noqa: E111
  assert post_metadata["expired_total"] == 1  # noqa: E111


def test_base_adapter_snapshot_without_cache() -> None:
  """Adapters without caching still expose a typed snapshot."""  # noqa: E111

  adapter = MODULE._BaseModuleAdapter[int](ttl=None)  # noqa: E111
  snapshot = adapter.cache_snapshot()  # noqa: E111

  assert snapshot == {  # noqa: E111
    "stats": {"entries": 0, "hits": 0, "misses": 0, "hit_rate": 0.0},
    "metadata": {"ttl_seconds": None},
  }


class _DummyAdapter:
  """Adapter stub that returns fixed cache telemetry."""  # noqa: E111

  def __init__(self, entries: int, hits: int, misses: int) -> None:  # noqa: E111
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

  def cache_metrics(self) -> ModuleCacheMetrics:  # noqa: E111
    return self._metrics

  def cache_snapshot(self) -> dict[str, object]:  # noqa: E111
    return self._snapshot


class _ErrorAdapter(_DummyAdapter):
  """Adapter stub that raises when snapshotting telemetry."""  # noqa: E111

  def cache_snapshot(self) -> dict[str, object]:  # type: ignore[override]  # noqa: E111
    raise RuntimeError("broken snapshot")


class _Container:
  """Container stub that mimics ``CoordinatorModuleAdapters``."""  # noqa: E111

  def __init__(self, **adapters: object) -> None:  # noqa: E111
    self._adapters = adapters
    for name, adapter in adapters.items():
      setattr(self, name, adapter)  # noqa: E111

  def cache_metrics(self) -> ModuleCacheMetrics:  # noqa: E111
    aggregate = ModuleCacheMetrics()
    for adapter in self._adapters.values():
      metrics = adapter.cache_metrics()  # noqa: E111
      aggregate.entries += metrics.entries  # noqa: E111
      aggregate.hits += metrics.hits  # noqa: E111
      aggregate.misses += metrics.misses  # noqa: E111
    return aggregate


def test_coordinator_module_cache_monitor_exposes_typed_snapshots() -> None:
  """Coordinator telemetry should surface typed per-module snapshots."""  # noqa: E111

  adapters = {  # noqa: E111
    "feeding": _DummyAdapter(entries=2, hits=4, misses=1),
    "walk": _DummyAdapter(entries=1, hits=1, misses=0),
    "geofencing": _DummyAdapter(entries=0, hits=0, misses=0),
    "health": _DummyAdapter(entries=3, hits=1, misses=2),
    "weather": _DummyAdapter(entries=1, hits=0, misses=1),
    "garden": _DummyAdapter(entries=1, hits=0, misses=1),
  }
  monitor = COORDINATOR_MONITOR(_Container(**adapters))  # noqa: E111

  snapshot = monitor.coordinator_snapshot()  # noqa: E111
  assert snapshot.stats == {  # noqa: E111
    "entries": 8,
    "hits": 6,
    "misses": 5,
    "hit_rate": pytest.approx(54.55, rel=1e-3),
  }

  diagnostics = snapshot.diagnostics  # noqa: E111
  assert diagnostics is not None  # noqa: E111
  per_module = diagnostics.get("per_module", {})  # noqa: E111

  assert set(per_module.keys()) == set(adapters.keys())  # noqa: E111
  for payload in per_module.values():  # noqa: E111
    assert payload["metadata"]["ttl_seconds"] == pytest.approx(5.0)
    assert set(payload["stats"]) == {"entries", "hits", "misses", "hit_rate"}


def test_coordinator_module_cache_monitor_records_snapshot_errors() -> None:
  """Errors when collecting snapshots should be preserved in diagnostics."""  # noqa: E111

  adapters = {  # noqa: E111
    "feeding": _DummyAdapter(entries=1, hits=1, misses=1),
    "walk": _ErrorAdapter(entries=0, hits=0, misses=1),
    "geofencing": _DummyAdapter(entries=0, hits=0, misses=0),
    "health": _DummyAdapter(entries=0, hits=0, misses=0),
    "weather": _DummyAdapter(entries=0, hits=0, misses=0),
    "garden": _DummyAdapter(entries=0, hits=0, misses=0),
  }
  monitor = COORDINATOR_MONITOR(_Container(**adapters))  # noqa: E111

  diagnostics = monitor.get_diagnostics()  # noqa: E111
  per_module = diagnostics["per_module"]  # noqa: E111

  assert per_module["walk"] == {"error": "broken snapshot"}  # noqa: E111
