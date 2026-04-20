from datetime import UTC, datetime, timedelta  # noqa: D100
from types import SimpleNamespace

from aiohttp import ClientSession
import pytest

from custom_components.pawcontrol import module_adapters
from custom_components.pawcontrol.module_adapters import (
    CoordinatorModuleAdapters,
    FeedingModuleAdapter,
    GardenModuleAdapter,
    HealthModuleAdapter,
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


def test_expiring_cache_tracks_hits_misses_metadata(monkeypatch) -> None:  # noqa: D103
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


def test_expiring_cache_cleanup_and_clear(monkeypatch) -> None:  # noqa: D103
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


def test_expiring_cache_cleanup_reports_last_cleanup_when_nothing_expires(  # noqa: D103
    monkeypatch,
) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(module_adapters, "dt_util", _FrozenTime(start))
    cache = _ExpiringCache[str](ttl=timedelta(seconds=10))
    cache.set("fresh", "value")

    expired = cache.cleanup(start + timedelta(seconds=5))

    assert expired == 0
    assert cache.metadata() == {
        "ttl_seconds": 10.0,
        "last_cleanup": start + timedelta(seconds=5),
        "last_expired_count": 0,
    }


def test_expiring_cache_get_evicts_expired_entries(monkeypatch) -> None:  # noqa: D103
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


def test_base_module_adapter_snapshot_without_cache() -> None:  # noqa: D103
    adapter = _DummyAdapter(ttl=None)

    assert adapter.cleanup(datetime(2026, 1, 1, tzinfo=UTC)) == 0
    assert adapter.cache_snapshot() == {
        "stats": {"entries": 0, "hits": 0, "misses": 0, "hit_rate": 0.0},
        "metadata": {"ttl_seconds": None},
    }


def test_base_module_adapter_cache_helpers_with_disabled_ttl() -> None:  # noqa: D103
    adapter = _DummyAdapter(ttl=None)

    adapter._remember("dog-1", {"state": "cached"})

    assert adapter._cached("dog-1") is None
    assert adapter.cache_metrics() == module_adapters.ModuleCacheMetrics()


def test_base_module_adapter_clear_is_noop_without_cache() -> None:  # noqa: D103
    adapter = _DummyAdapter(ttl=None)

    adapter.clear()

    assert adapter.cache_metrics() == module_adapters.ModuleCacheMetrics()


def test_base_module_adapter_snapshot_sets_ttl_metadata(monkeypatch) -> None:  # noqa: D103
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


def test_base_module_adapter_snapshot_keeps_existing_ttl_metadata(monkeypatch) -> None:  # noqa: D103
    adapter = _DummyAdapter(ttl=timedelta(seconds=30))
    assert adapter._cache is not None

    monkeypatch.setattr(
        module_adapters._ExpiringCache,
        "snapshot",
        lambda self: {
            "stats": {"entries": 1, "hits": 0, "misses": 0, "hit_rate": 0.0},
            "metadata": {"ttl_seconds": 5.0},
        },
    )

    assert adapter.cache_snapshot()["metadata"]["ttl_seconds"] == 5.0


def test_normalise_health_alert_defaults_and_details() -> None:  # noqa: D103
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


def test_normalise_health_medication_optional_fields_and_nulls() -> None:  # noqa: D103
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


def test_normalise_health_alert_defaults_without_mapping_details() -> None:  # noqa: D103
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


def test_normalise_health_medication_defaults_to_name_field() -> None:  # noqa: D103
    normalised = _normalise_health_medication({"name": "Joint Support"})

    assert normalised == {"name": "Joint Support"}


@pytest.mark.asyncio
async def test_coordinator_module_adapters_build_tasks_for_enabled_modules() -> None:  # noqa: D103
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
async def test_coordinator_module_adapters_build_tasks_for_walk_and_garden_only() -> (  # noqa: D103
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
async def test_coordinator_module_adapters_cache_lifecycle_and_detach(  # noqa: D103
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
async def test_weather_module_adapter_builds_ready_payload_and_caches() -> None:  # noqa: D103
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
async def test_weather_module_adapter_returns_error_payload_on_manager_failure() -> (  # noqa: D103
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
async def test_garden_module_adapter_default_error_and_idle_payloads() -> None:  # noqa: D103
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


@pytest.mark.asyncio
async def test_health_module_adapter_merges_stored_feeding_and_walk_context() -> None:  # noqa: D103
    adapter = HealthModuleAdapter(ttl=timedelta(minutes=5))

    class _DataManager:
        async def async_get_module_history(
            self,
            module: str,
            dog_id: str,
            *,
            limit: int,
        ) -> list[dict[str, object]]:
            assert module == "health"
            assert dog_id == "dog-1"
            assert limit == 1
            return [
                {
                    "status": "monitor",
                    "medications": [
                        "joint_support",
                        {"name": "omega", "with_meals": False},
                    ],
                    "health_alerts": [
                        "hydration",
                        {"type": "weight", "severity": "low"},
                    ],
                },
            ]

    class _FeedingManager:
        async def async_get_feeding_data(self, dog_id: str) -> dict[str, object]:
            assert dog_id == "dog-1"
            return {
                "health_summary": {
                    "current_weight": 19.5,
                    "ideal_weight": 20.0,
                    "life_stage": "adult",
                    "body_condition_score": 5,
                    "health_conditions": ["arthritis"],
                },
                "health_emergency": True,
                "emergency_mode": {"reason": "low appetite"},
                "medication_with_meals": True,
                "health_feeding_status": "watch",
                "daily_calorie_target": 900,
                "total_calories_today": 500,
                "weight_goal_progress": 62,
                "weight_goal": "maintain",
                "daily_activity_level": "moderate",
            }

    class _WalkManager:
        async def async_get_walk_data(self, _: str) -> dict[str, object]:
            pytest.fail(
                "walk manager should not be consulted when feeding sets activity"
            )

    adapter.attach(
        feeding_manager=_FeedingManager(),
        data_manager=_DataManager(),
        walk_manager=_WalkManager(),
    )

    payload = await adapter.async_get_data("dog-1")

    assert payload["status"] == "attention"
    assert payload["health_status"] == "watch"
    assert payload["activity_level"] == "moderate"
    assert payload["weight"] == 19.5
    assert payload["medications"][-1] == {"name": "meal_medication", "with_meals": True}
    assert payload["health_alerts"][0]["message"] == "Hydration"
    assert payload["health_alerts"][-1]["type"] == "emergency_feeding"


@pytest.mark.asyncio
async def test_health_module_adapter_walk_fallback_without_feeding_context() -> None:  # noqa: D103
    adapter = HealthModuleAdapter(ttl=timedelta(minutes=5))

    class _WalkManager:
        async def async_get_walk_data(self, _: str) -> dict[str, object]:
            return {"daily_walks": []}

    adapter.attach(
        feeding_manager=None,
        data_manager=None,
        walk_manager=_WalkManager(),
    )

    payload = await adapter.async_get_data("dog-2")

    assert payload["status"] == "healthy"
    assert payload["activity_level"] == "low"


@pytest.mark.asyncio
async def test_feeding_module_adapter_uses_manager_then_cache() -> None:  # noqa: D103
    async with ClientSession() as session:
        adapter = FeedingModuleAdapter(
            session=session,
            ttl=timedelta(minutes=5),
            use_external_api=False,
            api_client=None,
        )
        manager = _FakeFeedingManager()
        adapter.attach(manager)

        payload = await adapter.async_get_data("dog-1")
        cached = await adapter.async_get_data("dog-1")

        assert payload["status"] == "ready"
        assert manager.calls == 1
        assert cached is payload


@pytest.mark.asyncio
async def test_feeding_module_adapter_wraps_unexpected_api_errors() -> None:  # noqa: D103
    async with ClientSession() as session:
        adapter = FeedingModuleAdapter(
            session=session,
            ttl=timedelta(minutes=5),
            use_external_api=True,
            api_client=_FailingDeviceClient(),
        )

        with pytest.raises(NetworkError, match="Device API error: boom"):
            await adapter.async_get_data("dog-1")


@pytest.mark.asyncio
async def test_walk_module_adapter_defaults_for_missing_or_empty_manager_data() -> None:  # noqa: D103
    adapter = WalkModuleAdapter(ttl=timedelta(minutes=5))

    disabled = await adapter.async_get_data("dog-1")
    assert disabled["status"] == "unavailable"

    adapter.attach(_FakeWalkManager(payload={}))
    empty = await adapter.async_get_data("dog-1")
    assert empty["status"] == "empty"


@pytest.mark.asyncio
async def test_gps_module_adapter_reports_unavailable_and_tracking_payload() -> None:  # noqa: D103
    adapter = module_adapters.GPSModuleAdapter()

    with pytest.raises(module_adapters.GPSUnavailableError, match="dog-1"):
        await adapter.async_get_data("dog-1")

    now = datetime(2026, 1, 2, tzinfo=UTC)

    class _GPSManager:
        async def async_get_current_location(self, dog_id: str) -> SimpleNamespace:
            assert dog_id == "dog-1"
            return SimpleNamespace(
                latitude=40.123,
                longitude=-74.987,
                accuracy=4.5,
                timestamp=now,
                source=SimpleNamespace(value="gps"),
            )

        async def async_get_active_route(self, dog_id: str) -> SimpleNamespace:
            assert dog_id == "dog-1"
            return SimpleNamespace(
                is_active=True,
                start_time=now,
                duration_minutes=12,
                distance_km=1.7,
                gps_points=[(1, 1), (2, 2)],
            )

    adapter.attach(_GPSManager())

    payload = await adapter.async_get_data("dog-1")

    assert payload["status"] == "tracking"
    assert payload["source"] == "gps"
    assert payload["active_route"]["points_count"] == 2


@pytest.mark.asyncio
async def test_feeding_adapter_reraises_rate_limit_and_network_errors() -> None:  # noqa: D103
    class _RateLimitedClient:
        async def async_get_feeding_payload(self, _: str) -> dict[str, object]:
            raise module_adapters.RateLimitError("slow down")

    class _NetworkFailingClient:
        async def async_get_feeding_payload(self, _: str) -> dict[str, object]:
            raise module_adapters.NetworkError("offline")

    async with ClientSession() as session:
        rate_limited = FeedingModuleAdapter(
            session=session,
            ttl=timedelta(minutes=5),
            use_external_api=True,
            api_client=_RateLimitedClient(),
        )
        with pytest.raises(module_adapters.RateLimitError, match="slow down"):
            await rate_limited.async_get_data("dog-1")

        network_failing = FeedingModuleAdapter(
            session=session,
            ttl=timedelta(minutes=5),
            use_external_api=True,
            api_client=_NetworkFailingClient(),
        )
        with pytest.raises(module_adapters.NetworkError, match="offline"):
            await network_failing.async_get_data("dog-1")


@pytest.mark.asyncio
async def test_feeding_adapter_external_api_success_sets_ready_and_caches() -> None:  # noqa: D103
    class _OkClient:
        async def async_get_feeding_payload(self, dog_id: str) -> dict[str, object]:
            return {"dog_id": dog_id}

    async with ClientSession() as session:
        adapter = FeedingModuleAdapter(
            session=session,
            ttl=timedelta(minutes=5),
            use_external_api=True,
            api_client=_OkClient(),
        )
        payload = await adapter.async_get_data("dog-1")
        assert payload["status"] == "ready"
        assert await adapter.async_get_data("dog-1") is payload


@pytest.mark.asyncio
async def test_walk_and_garden_adapters_return_cached_payloads() -> None:  # noqa: D103
    walk_adapter = WalkModuleAdapter(ttl=timedelta(minutes=5))
    walk_adapter.attach(_FakeWalkManager(payload={"status": "ready", "daily_walks": 2}))
    walk_first = await walk_adapter.async_get_data("dog-cache")
    walk_second = await walk_adapter.async_get_data("dog-cache")
    assert walk_second is walk_first

    garden_adapter = GardenModuleAdapter(ttl=timedelta(minutes=5))

    class _GardenManager:
        def build_garden_snapshot(self, _: str) -> dict[str, object]:
            return {
                "status": "ready",
                "sessions_today": 1,
                "time_today_minutes": 5.0,
                "poop_today": 1,
                "activities_today": 1,
                "activities_total": 1,
                "active_session": None,
                "last_session": None,
                "hours_since_last_session": 1.0,
                "stats": {},
                "pending_confirmations": [],
                "weather_summary": None,
            }

    garden_adapter.attach(_GardenManager())
    garden_first = await garden_adapter.async_get_data("dog-cache")
    garden_second = await garden_adapter.async_get_data("dog-cache")
    assert garden_second is garden_first


@pytest.mark.asyncio
async def test_geofencing_adapter_disabled_active_and_cached_paths() -> None:  # noqa: D103
    adapter = module_adapters.GeofencingModuleAdapter(ttl=timedelta(minutes=5))
    disabled = await adapter.async_get_data("dog-1")
    assert disabled["status"] == "unavailable"

    class _GeoManager:
        async def async_get_geofence_status(self, _: str) -> dict[str, object]:
            return {
                "zones_configured": 2,
                "zone_status": {"home": "inside"},
                "current_location": {"lat": 1.0, "lon": 2.0},
                "safe_zone_breaches": 0,
                "last_update": "2026-01-01T00:00:00+00:00",
            }

    adapter.attach(_GeoManager())
    active = await adapter.async_get_data("dog-2")
    assert active["status"] == "active"
    cached = await adapter.async_get_data("dog-2")
    assert cached is active


@pytest.mark.asyncio
async def test_health_and_weather_adapters_cover_cache_and_optional_branches() -> None:  # noqa: D103
    health_adapter = HealthModuleAdapter(ttl=timedelta(minutes=5))

    class _FeedingManager:
        async def async_get_feeding_data(self, _: str) -> dict[str, object]:
            return {
                "health_conditions": ["allergy"],
                "daily_activity_level": None,
            }

    class _WalkManager:
        async def async_get_walk_data(self, _: str) -> dict[str, object]:
            return {"daily_walks": [1]}

    health_adapter.attach(
        feeding_manager=_FeedingManager(),
        data_manager=None,
        walk_manager=_WalkManager(),
    )
    health_payload = await health_adapter.async_get_data("dog-1")
    assert health_payload["health_conditions"] == ["allergy"]
    assert health_payload["activity_level"] == "active"
    assert await health_adapter.async_get_data("dog-1") is health_payload

    weather_adapter = WeatherModuleAdapter(
        config_entry=SimpleNamespace(data={"dogs": "invalid"}, options={}),
        ttl=timedelta(minutes=5),
    )
    disabled_weather = await weather_adapter.async_get_data("dog-1")
    assert disabled_weather == {
        "status": "disabled",
        "health_score": None,
        "alerts": [],
        "recommendations": [],
    }

    weather_adapter = WeatherModuleAdapter(
        config_entry=SimpleNamespace(
            data={"dogs": ["skip", {"dog_id": "dog-1", "dog_age": 7}]},
            options={},
        ),
        ttl=timedelta(minutes=5),
    )

    class _WeatherManager:
        def get_active_alerts(self) -> list[SimpleNamespace]:
            return []

        def get_recommendations_for_dog(
            self,
            *,
            dog_breed: str | None,
            dog_age_months: int | None,
            health_conditions: list[str] | None,
        ) -> list[str]:
            assert dog_breed is None
            assert dog_age_months == 7
            assert health_conditions is None
            return []

        def get_weather_health_score(self) -> int:
            return 100

        def get_current_conditions(self) -> None:
            return None

    weather_adapter.attach(_WeatherManager())
    ready = await weather_adapter.async_get_data("dog-1")
    assert ready["status"] == "ready"

    weather_adapter = WeatherModuleAdapter(
        config_entry=SimpleNamespace(data={"dogs": "invalid"}, options={}),
        ttl=timedelta(minutes=5),
    )

    class _WeatherManagerNoDogConfig:
        def get_active_alerts(self) -> list[SimpleNamespace]:
            return []

        def get_recommendations_for_dog(
            self,
            *,
            dog_breed: str | None,
            dog_age_months: int | None,
            health_conditions: list[str] | None,
        ) -> list[str]:
            assert dog_breed is None
            assert dog_age_months is None
            assert health_conditions is None
            return []

        def get_weather_health_score(self) -> int:
            return 100

        def get_current_conditions(self) -> None:
            return None

    weather_adapter.attach(_WeatherManagerNoDogConfig())
    ready_with_invalid_dogs = await weather_adapter.async_get_data("dog-2")
    assert ready_with_invalid_dogs["status"] == "ready"


@pytest.mark.asyncio
async def test_health_adapter_branch_paths_for_empty_and_non_mapping_history() -> None:  # noqa: D103
    class _PseudoLatest:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def get(self, key: str, default=None):  # type: ignore[no-untyped-def]
            return self._payload.get(key, default)

    class _HistoryManager:
        async def async_get_module_history(
            self,
            _module: str,
            dog_id: str,
            *,
            limit: int,
        ) -> list[object]:
            assert limit == 1
            if dog_id == "dog-empty":
                return []
            return [
                _PseudoLatest(
                    {
                        "medications": "unexpected",
                        "health_alerts": "unexpected",
                    },
                ),
            ]

    class _WalkManager:
        async def async_get_walk_data(self, _dog_id: str) -> dict[str, object]:
            return {}

    adapter = HealthModuleAdapter(ttl=timedelta(minutes=5))
    adapter.attach(
        feeding_manager=None,
        data_manager=_HistoryManager(),
        walk_manager=_WalkManager(),
    )

    empty_payload = await adapter.async_get_data("dog-empty")
    assert empty_payload["status"] == "healthy"

    odd_payload = await adapter.async_get_data("dog-odd")
    assert odd_payload["status"] == "healthy"
    assert odd_payload.get("activity_level") is None
    assert odd_payload["medications"] == []
    assert odd_payload["health_alerts"] == []


@pytest.mark.asyncio
async def test_health_adapter_ignores_unknown_items_in_stored_lists() -> None:  # noqa: D103
    class _HistoryManager:
        async def async_get_module_history(
            self,
            _module: str,
            _dog_id: str,
            *,
            limit: int,
        ) -> list[dict[str, object]]:
            assert limit == 1
            return [
                {
                    "medications": [1, {"name": "omega"}, "joint_support"],
                    "health_alerts": [0, {"type": "hydration"}, "weight_alert"],
                },
            ]

    adapter = HealthModuleAdapter(ttl=timedelta(minutes=5))
    adapter.attach(
        feeding_manager=None,
        data_manager=_HistoryManager(),
        walk_manager=None,
    )

    payload = await adapter.async_get_data("dog-lists")
    assert payload["medications"][0]["name"] == "omega"
    assert payload["medications"][1]["name"] == "joint_support"
    assert payload["health_alerts"][0]["type"] == "hydration"
    assert payload["health_alerts"][1]["type"] == "weight_alert"


def test_weather_adapter_resolve_dog_config_continues_after_non_matching_string_id() -> (  # noqa: D103
    None
):
    adapter = WeatherModuleAdapter(
        config_entry=SimpleNamespace(
            data={
                "dogs": [
                    {"dog_id": "other"},
                    {"dog_id": "target"},
                ],
            },
            options={},
        ),
        ttl=timedelta(minutes=5),
    )

    resolved = adapter._resolve_dog_config("target")
    assert resolved is not None
    assert resolved["dog_id"] == "target"


@pytest.mark.asyncio
async def test_weather_adapter_parses_string_age_when_building_recommendations() -> (  # noqa: D103
    None
):
    recommendations_calls: list[tuple[str | None, int | None, list[str] | None]] = []

    class _WeatherManager:
        def get_active_alerts(self) -> list[SimpleNamespace]:
            return []

        def get_recommendations_for_dog(
            self,
            *,
            dog_breed: str | None,
            dog_age_months: int | None,
            health_conditions: list[str] | None,
        ) -> list[str]:
            recommendations_calls.append((dog_breed, dog_age_months, health_conditions))
            return []

        def get_weather_health_score(self) -> int:
            return 99

        def get_current_conditions(self) -> None:
            return None

    adapter = WeatherModuleAdapter(
        config_entry=SimpleNamespace(
            data={"dogs": [{"dog_id": "dog-1", "dog_age": "12"}]},
            options={},
        ),
        ttl=timedelta(minutes=5),
    )
    adapter.attach(_WeatherManager())

    payload = await adapter.async_get_data("dog-1")

    assert payload["status"] == "ready"
    assert recommendations_calls == [(None, 12, None)]


@pytest.mark.asyncio
async def test_weather_adapter_ignores_non_scalar_age_values() -> None:  # noqa: D103
    recommendations_calls: list[tuple[str | None, int | None, list[str] | None]] = []

    class _WeatherManager:
        def get_active_alerts(self) -> list[SimpleNamespace]:
            return []

        def get_recommendations_for_dog(
            self,
            *,
            dog_breed: str | None,
            dog_age_months: int | None,
            health_conditions: list[str] | None,
        ) -> list[str]:
            recommendations_calls.append((dog_breed, dog_age_months, health_conditions))
            return []

        def get_weather_health_score(self) -> int:
            return 95

        def get_current_conditions(self) -> None:
            return None

    adapter = WeatherModuleAdapter(
        config_entry=SimpleNamespace(
            data={"dogs": [{"dog_id": "dog-2", "dog_age": {"months": 12}}]},
            options={},
        ),
        ttl=timedelta(minutes=5),
    )
    adapter.attach(_WeatherManager())

    payload = await adapter.async_get_data("dog-2")

    assert payload["status"] == "ready"
    assert recommendations_calls == [(None, None, None)]
