from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from aiohttp import ClientSession
import pytest

from custom_components.pawcontrol import module_adapters
from custom_components.pawcontrol.module_adapters import (
    CoordinatorModuleAdapters,
    _BaseModuleAdapter,
    _ExpiringCache,
    _normalise_health_alert,
    _normalise_health_medication,
)


class _FrozenTime:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def utcnow(self) -> datetime:
        return self._now


class _DummyAdapter(_BaseModuleAdapter[dict[str, str]]):
    pass


def test_expiring_cache_tracks_hits_misses_metadata(monkeypatch) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(module_adapters, "dt_util", _FrozenTime(now))
    cache = _ExpiringCache[dict[str, str]](ttl=timedelta(minutes=5))

    cache.set("dog-1", {"status": "ok"})
    assert cache.get("dog-1") == {"status": "ok"}
    assert cache.get("missing") is None

    metrics = cache.metrics()
    assert metrics.entries == 1
    assert metrics.hits == 1
    assert metrics.misses == 1
    assert metrics.hit_rate == 50.0

    snapshot = cache.snapshot()
    assert snapshot["stats"] == {
        "entries": 1,
        "hits": 1,
        "misses": 1,
        "hit_rate": 50.0,
    }
    assert snapshot["metadata"] == {"ttl_seconds": 300.0}


def test_expiring_cache_cleanup_and_clear(monkeypatch) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(module_adapters, "dt_util", _FrozenTime(start))
    cache = _ExpiringCache[str](ttl=timedelta(seconds=10))
    cache.set("fresh", "value")

    expired = cache.cleanup(start + timedelta(seconds=11))
    assert expired == 1
    assert cache.get("fresh") is None

    metadata = cache.metadata()
    assert metadata["last_expired_count"] == 1
    assert metadata["expired_total"] == 1

    cache.clear()
    assert cache.metrics().entries == 0
    assert cache.metadata() == {"ttl_seconds": 10.0}


def test_expiring_cache_get_evicts_expired_entries(monkeypatch) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    cache = _ExpiringCache[str](ttl=timedelta(seconds=5))

    monkeypatch.setattr(module_adapters, "dt_util", _FrozenTime(start))
    cache.set("dog-1", "ready")

    monkeypatch.setattr(
        module_adapters,
        "dt_util",
        _FrozenTime(start + timedelta(seconds=6)),
    )
    assert cache.get("dog-1") is None
    assert cache.metrics().entries == 0


def test_base_module_adapter_snapshot_without_cache() -> None:
    adapter = _DummyAdapter(ttl=None)

    assert adapter.cleanup(datetime(2026, 1, 1, tzinfo=UTC)) == 0
    assert adapter.cache_snapshot() == {
        "stats": {"entries": 0, "hits": 0, "misses": 0, "hit_rate": 0.0},
        "metadata": {"ttl_seconds": None},
    }


def test_normalise_health_alert_defaults_and_details() -> None:
    payload = {
        "type": "hydration",
        "severity": "UNEXPECTED",
        "details": {"source": "sensor", "score": 9},
        "action_required": 1,
    }

    normalised = _normalise_health_alert(payload)

    assert normalised == {
        "type": "hydration",
        "message": "Hydration",
        "severity": "medium",
        "action_required": True,
        "details": {"source": "sensor", "score": 9},
    }


def test_normalise_health_medication_optional_fields_and_nulls() -> None:
    payload = {
        "medication": "Omega 3",
        "dosage": None,
        "frequency": "daily",
        "next_dose": 123,
        "notes": None,
        "with_meals": "yes",
    }

    normalised = _normalise_health_medication(payload)

    assert normalised == {
        "name": "Omega 3",
        "dosage": None,
        "frequency": "daily",
        "next_dose": "123",
        "notes": None,
        "with_meals": True,
    }


def test_normalise_health_alert_defaults_without_mapping_details() -> None:
    normalised = _normalise_health_alert({
        "message": "",
        "severity": "HIGH",
        "details": ["ignored"],
    })

    assert normalised == {
        "type": "custom",
        "message": "Custom",
        "severity": "high",
        "action_required": False,
    }


def test_normalise_health_medication_defaults_to_name_field() -> None:
    normalised = _normalise_health_medication({"name": "Joint Support"})

    assert normalised == {"name": "Joint Support"}


@pytest.mark.asyncio
async def test_coordinator_module_adapters_build_tasks_for_enabled_modules() -> None:
    config_entry = SimpleNamespace(data={"dogs": []}, options={})
    async with ClientSession() as session:
        adapters = CoordinatorModuleAdapters(
            session=session,
            config_entry=config_entry,
            use_external_api=False,
            cache_ttl=timedelta(minutes=5),
            api_client=None,
        )

        modules = {
            "feeding": True,
            "walk": False,
            "gps": True,
            "health": True,
            "weather": True,
            "garden": False,
        }

        tasks = adapters.build_tasks("dog-1", modules)

        assert [task.module for task in tasks] == [
            "feeding",
            "gps",
            "geofencing",
            "health",
            "weather",
        ]

        for task in tasks:
            task.coroutine.close()


@pytest.mark.asyncio
async def test_coordinator_module_adapters_cache_lifecycle_and_detach() -> None:
    config_entry = SimpleNamespace(data={"dogs": []}, options={})
    async with ClientSession() as session:
        adapters = CoordinatorModuleAdapters(
            session=session,
            config_entry=config_entry,
            use_external_api=False,
            cache_ttl=timedelta(minutes=5),
            api_client=None,
        )

        adapters.attach_managers(
            data_manager=object(),
            feeding_manager=object(),
            walk_manager=object(),
            gps_geofence_manager=object(),
            weather_health_manager=object(),
            garden_manager=object(),
        )
        adapters.detach_managers()

        await adapters.feeding.async_get_data("dog-1")
        await adapters.geofencing.async_get_data("dog-1")
        await adapters.health.async_get_data("dog-1")
        await adapters.weather.async_get_data("dog-1")
        await adapters.garden.async_get_data("dog-1")

        metrics = adapters.cache_metrics()
        assert metrics.entries == 5
        assert metrics.hits == 0
        assert metrics.misses == 5

        adapters.clear_caches()
        assert adapters.cache_metrics().entries == 0

        assert adapters.cleanup_expired(datetime(2026, 1, 1, tzinfo=UTC)) == 0
