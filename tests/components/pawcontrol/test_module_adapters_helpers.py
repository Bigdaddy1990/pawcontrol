from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from aiohttp import ClientSession
import pytest

from custom_components.pawcontrol import module_adapters
from custom_components.pawcontrol.module_adapters import (
    CoordinatorModuleAdapters,
    FeedingModuleAdapter,
    NetworkError,
    WalkModuleAdapter,
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


class _FakeFeedingManager:
    def __init__(self) -> None:
        self.calls = 0

    async def async_get_feeding_data(self, dog_id: str) -> dict[str, object]:
        self.calls += 1
        return {"dog_id": dog_id}


class _FailingDeviceClient:
    async def async_get_feeding_payload(self, _: str) -> dict[str, object]:
        raise RuntimeError("boom")


class _FakeWalkManager:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.calls = 0

    async def async_get_walk_data(self, _: str) -> dict[str, object]:
        self.calls += 1
        return self._payload


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


def test_base_module_adapter_cache_helpers_with_disabled_ttl() -> None:
    adapter = _DummyAdapter(ttl=None)

    adapter._remember("dog-1", {"state": "cached"})

    assert adapter._cached("dog-1") is None
    assert adapter.cache_metrics() == module_adapters.ModuleCacheMetrics()


def test_base_module_adapter_snapshot_sets_ttl_metadata(monkeypatch) -> None:
    adapter = _DummyAdapter(ttl=timedelta(seconds=30))
    assert adapter._cache is not None

    monkeypatch.setattr(
        module_adapters._ExpiringCache,
        "snapshot",
        lambda self: {
            "stats": {"entries": 1, "hits": 0, "misses": 0, "hit_rate": 0.0},
            "metadata": {},
        },
    )

    assert adapter.cache_snapshot() == {
        "stats": {"entries": 1, "hits": 0, "misses": 0, "hit_rate": 0.0},
        "metadata": {"ttl_seconds": 30.0},
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
async def test_coordinator_module_adapters_build_tasks_for_walk_and_garden_only() -> (
    None
):
    config_entry = SimpleNamespace(data={"dogs": []}, options={})
    async with ClientSession() as session:
        adapters = CoordinatorModuleAdapters(
            session=session,
            config_entry=config_entry,
            use_external_api=False,
            cache_ttl=timedelta(minutes=5),
            api_client=None,
        )

        tasks = adapters.build_tasks(
            "dog-1",
            {
                "feeding": False,
                "walk": True,
                "gps": False,
                "health": False,
                "weather": False,
                "garden": True,
            },
        )

        assert [task.module for task in tasks] == ["walk", "garden"]
        for task in tasks:
            task.coroutine.close()


@pytest.mark.asyncio
async def test_coordinator_module_adapters_cache_lifecycle_and_detach(
    monkeypatch,
) -> None:
    config_entry = SimpleNamespace(data={"dogs": []}, options={})
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(module_adapters, "dt_util", _FrozenTime(now))

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

        await adapters.feeding.async_get_data("dog-1")
        await adapters.walk.async_get_data("dog-1")
        await adapters.geofencing.async_get_data("dog-1")
        await adapters.health.async_get_data("dog-1")
        await adapters.weather.async_get_data("dog-1")
        await adapters.garden.async_get_data("dog-1")

        metrics = adapters.cache_metrics()
        assert metrics.entries == 5
        assert metrics.hits == 0
        assert metrics.misses == 6

        assert adapters.cleanup_expired(now + timedelta(minutes=4)) == 0
        assert adapters.cache_metrics().entries == 5
        assert adapters.cleanup_expired(now + timedelta(minutes=6)) == 5
        assert adapters.cache_metrics().entries == 0

        await adapters.feeding.async_get_data("dog-1")
        assert adapters.cache_metrics().entries == 1

        adapters.clear_caches()
        assert adapters.cache_metrics().entries == 0
        adapters.detach_managers()


@pytest.mark.asyncio
async def test_feeding_module_adapter_uses_manager_then_cache() -> None:
    manager = _FakeFeedingManager()
    async with ClientSession() as session:
        adapter = FeedingModuleAdapter(
            session=session,
            use_external_api=False,
            ttl=timedelta(minutes=5),
            api_client=None,
        )
        adapter.attach(manager)

        first = await adapter.async_get_data("dog-1")
        second = await adapter.async_get_data("dog-1")

    assert first == {"dog_id": "dog-1", "status": "ready"}
    assert second == first
    assert manager.calls == 1


@pytest.mark.asyncio
async def test_feeding_module_adapter_wraps_unexpected_api_errors() -> None:
    async with ClientSession() as session:
        adapter = FeedingModuleAdapter(
            session=session,
            use_external_api=True,
            ttl=timedelta(minutes=5),
            api_client=_FailingDeviceClient(),
        )

        with pytest.raises(NetworkError, match="Device API error: boom"):
            await adapter.async_get_data("dog-1")


@pytest.mark.asyncio
async def test_walk_module_adapter_handles_unavailable_empty_and_cached_payloads() -> (
    None
):
    adapter = WalkModuleAdapter(ttl=timedelta(minutes=5))

    unavailable = await adapter.async_get_data("dog-1")

    empty_manager = _FakeWalkManager(payload={})
    adapter.attach(empty_manager)
    empty_payload = await adapter.async_get_data("dog-1")

    walk_manager = _FakeWalkManager(payload={"status": "ready", "walks_today": 2})
    adapter.attach(walk_manager)
    live_payload = await adapter.async_get_data("dog-1")
    cached_payload = await adapter.async_get_data("dog-1")

    assert unavailable["status"] == "unavailable"
    assert empty_payload["status"] == "empty"
    assert live_payload == {"status": "ready", "walks_today": 2}
    assert cached_payload == live_payload
    assert walk_manager.calls == 1
