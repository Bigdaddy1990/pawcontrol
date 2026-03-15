from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from aiohttp import ClientSession
import pytest

from custom_components.pawcontrol import module_adapters
from custom_components.pawcontrol.module_adapters import (
    CoordinatorModuleAdapters,
    FeedingModuleAdapter,
    GardenModuleAdapter,
    NetworkError,
    WalkModuleAdapter,
    WeatherModuleAdapter,
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
async def test_weather_module_adapter_builds_ready_payload_and_caches() -> None:
    config_entry = SimpleNamespace(
        data={
            "dogs": [
                {
                    "dog_id": "dog-1",
                    "dog_breed": "Border Collie",
                    "dog_age": "36",
                    "health_conditions": ["arthritis", ""],
                },
                "ignored",
            ],
        },
        options={"weather_entity": "weather.home"},
    )
    adapter = WeatherModuleAdapter(
        config_entry=config_entry,
        ttl=timedelta(minutes=5),
    )

    now = datetime(2026, 1, 2, tzinfo=UTC)
    update_calls: list[str] = []
    recommendation_calls: list[tuple[str | None, int | None, list[str] | None]] = []

    class _Manager:
        async def async_update_weather_data(self, entity_id: str) -> None:
            update_calls.append(entity_id)

        def get_active_alerts(self) -> list[SimpleNamespace]:
            return [
                SimpleNamespace(
                    alert_type=SimpleNamespace(value="heat"),
                    severity=SimpleNamespace(value="high"),
                    title="Heat warning",
                    message="Avoid midday walks",
                    recommendations=("walk at dawn",),
                    duration_hours=5,
                    affected_breeds=("Border Collie",),
                    age_considerations=("puppy",),
                ),
            ]

        def get_recommendations_for_dog(
            self,
            *,
            dog_breed: str | None,
            dog_age_months: int | None,
            health_conditions: list[str] | None,
        ) -> list[str]:
            recommendation_calls.append(
                (dog_breed, dog_age_months, health_conditions),
            )
            return ["Hydration first"]

        def get_weather_health_score(self) -> int:
            return 82

        def get_current_conditions(self) -> SimpleNamespace:
            return SimpleNamespace(
                temperature_c=22.5,
                humidity_percent=50,
                uv_index=4,
                wind_speed_kmh=12.0,
                condition="sunny",
                last_updated=now,
            )

    adapter.attach(_Manager())

    payload = await adapter.async_get_data("dog-1")
    cached = await adapter.async_get_data("dog-1")

    assert update_calls == ["weather.home"]
    assert recommendation_calls == [("Border Collie", 36, ["arthritis"])]
    assert payload["status"] == "ready"
    assert payload["health_score"] == 82
    assert payload["conditions"]["last_updated"] == now.isoformat()
    assert payload["alerts"][0]["severity"] == "high"
    assert cached is payload


@pytest.mark.asyncio
async def test_weather_module_adapter_returns_error_payload_on_manager_failure() -> (
    None
):
    config_entry = SimpleNamespace(
        data={"dogs": [{"dog_id": "dog-1", "dog_age": "not-a-number"}]},
        options={"weather_entity": "weather.home"},
    )
    adapter = WeatherModuleAdapter(
        config_entry=config_entry,
        ttl=timedelta(minutes=5),
    )

    class _BrokenManager:
        async def async_update_weather_data(self, entity_id: str) -> None:
            raise RuntimeError(f"cannot refresh {entity_id}")

        def get_active_alerts(self) -> list[SimpleNamespace]:
            raise RuntimeError("alerts unavailable")

    adapter.attach(_BrokenManager())

    payload = await adapter.async_get_data("dog-1")

    assert payload == {
        "status": "error",
        "alerts": [],
        "recommendations": [],
        "message": "alerts unavailable",
        "health_score": None,
    }


@pytest.mark.asyncio
async def test_garden_module_adapter_default_error_and_idle_payloads() -> None:
    adapter = GardenModuleAdapter(ttl=timedelta(minutes=5))

    disabled_payload = await adapter.async_get_data("dog-1")
    assert disabled_payload["status"] == "disabled"

    class _BrokenManager:
        def build_garden_snapshot(self, dog_id: str) -> dict[str, object]:
            raise RuntimeError(f"snapshot failed for {dog_id}")

    adapter.attach(_BrokenManager())
    error_payload = await adapter.async_get_data("dog-2")
    assert error_payload["status"] == "error"
    assert error_payload["message"] == "snapshot failed for dog-2"

    class _SnapshotManager:
        def build_garden_snapshot(self, dog_id: str) -> dict[str, object]:
            return {
                "sessions_today": 2,
                "time_today_minutes": 8.0,
                "poop_today": 1,
                "activities_today": 2,
                "activities_total": 20,
                "active_session": None,
                "last_session": None,
                "hours_since_last_session": 1.2,
                "stats": {},
                "pending_confirmations": [],
                "weather_summary": None,
            }

    adapter.attach(_SnapshotManager())
    idle_payload = await adapter.async_get_data("dog-3")

    assert idle_payload["status"] == "idle"
    assert idle_payload["sessions_today"] == 2
