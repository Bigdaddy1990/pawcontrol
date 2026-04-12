"""Runtime-heavy coverage tests for ``optimized_entity_base.py``."""

import asyncio
from collections.abc import Mapping
from datetime import timedelta
import gc
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import weakref

from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util
import pytest

from custom_components.pawcontrol import optimized_entity_base as oeb
from custom_components.pawcontrol.optimized_entity_base import (
    _ATTRIBUTES_CACHE,
    _AVAILABILITY_CACHE,
    _PERFORMANCE_METRICS,
    _STATE_CACHE,
    EntityRegistry,
    OptimizedBinarySensorBase,
    OptimizedEntityBase,
    OptimizedSensorBase,
    OptimizedSwitchBase,
    PerformanceTracker,
    _AttributesCacheEntry,
    _AvailabilityCacheEntry,
    _cleanup_global_caches,
    _coordinator_is_available,
    _register_entity,
    _RegistrySentinelCoordinator,
    _StateCacheEntry,
    clear_global_entity_registry,
    create_optimized_entities_batched,
    get_global_performance_stats,
)

pytestmark = pytest.mark.unit


class _DummyCoordinator:
    """Simple coordinator double with configurable payload methods."""

    def __init__(self) -> None:
        self.available = True
        self.last_update_success = True
        self._dog_payload: dict[str, Mapping[str, Any] | None] = {}
        self._module_payload: dict[tuple[str, str], Mapping[str, Any] | Any] = {}
        self.refresh_calls = 0

    def get_dog_data(self, dog_id: str) -> Mapping[str, Any] | None:
        return self._dog_payload.get(dog_id)

    def get_module_data(self, dog_id: str, module: str) -> Mapping[str, Any] | Any:
        return self._module_payload.get((dog_id, module), {})

    async def async_request_refresh(self) -> None:
        self.refresh_calls += 1

    async def async_refresh(self) -> None:
        self.refresh_calls += 1


class _RefreshOnlyCoordinator:
    """Coordinator exposing only ``async_refresh`` for branch coverage."""

    def __init__(self) -> None:
        self.available = True
        self.last_update_success = True
        self.refresh_calls = 0

    def get_dog_data(self, dog_id: str) -> Mapping[str, Any] | None:
        _ = dog_id
        return None

    def get_module_data(self, dog_id: str, module: str) -> Mapping[str, Any]:
        _ = dog_id, module
        return {}

    async def async_refresh(self) -> None:
        self.refresh_calls += 1


class _DummyEntity(OptimizedEntityBase):
    """Concrete entity implementation for exercising base-class behavior."""

    def __init__(
        self,
        coordinator: Any,
        *,
        dog_id: str = "dog-1",
        dog_name: str = "Buddy",
        entity_type: str = "status",
        unique_id_suffix: str | None = None,
        name_suffix: str | None = None,
        device_class: str | None = None,
        entity_category: EntityCategory | None = None,
        icon: str | None = None,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
            dog_id=dog_id,
            dog_name=dog_name,
            entity_type=entity_type,
            unique_id_suffix=unique_id_suffix,
            name_suffix=name_suffix,
            device_class=device_class,
            entity_category=entity_category,
            icon=icon,
        )

    def _get_entity_state(self) -> str:
        return "ok"


@pytest.fixture(autouse=True)
def _reset_optimized_entity_globals() -> None:
    """Keep global caches isolated for each test."""
    _STATE_CACHE.clear()
    _ATTRIBUTES_CACHE.clear()
    _AVAILABILITY_CACHE.clear()
    _PERFORMANCE_METRICS.clear()
    OptimizedEntityBase._performance_registry.clear()
    OptimizedEntityBase._last_cache_cleanup = 0
    clear_global_entity_registry()


def test_coordinator_is_available_typeerror_and_awaitable() -> None:
    """Callable availability failures and awaitables should default to True."""

    class _TypeErrorAvailable:
        def available(self) -> bool:
            raise TypeError("bad call")

    class _AwaitableAvailable:
        async def available(self) -> bool:
            return False

    assert _coordinator_is_available(_TypeErrorAvailable()) is True
    assert _coordinator_is_available(_AwaitableAvailable()) is True


def test_entity_configuration_defaults_and_properties() -> None:
    """Default and explicit naming/configuration branches should be reflected."""
    coordinator = _DummyCoordinator()
    default_entity = _DummyEntity(coordinator, entity_type="water_level")
    explicit_entity = _DummyEntity(
        coordinator,
        entity_type="water_level",
        unique_id_suffix="custom",
        name_suffix="Custom Name",
        device_class="moisture",
        icon="mdi:water",
    )

    assert default_entity._attr_name == "Buddy Water Level"
    assert default_entity.suggested_area == "Pet Area - Buddy"
    assert default_entity.device_class is None
    assert default_entity.icon is None

    assert explicit_entity._attr_unique_id.endswith("_custom")
    assert explicit_entity._attr_name == "Buddy Custom Name"
    assert explicit_entity.device_class == "moisture"
    assert explicit_entity.icon == "mdi:water"


def test_device_link_details_adds_breed_and_age_suggested_area() -> None:
    """Device metadata should include breed and age-derived suggested area."""
    coordinator = _DummyCoordinator()
    coordinator._dog_payload["dog-1"] = {
        "dog_info": {"dog_breed": "Beagle", "dog_age": 5},
        "status": "online",
    }
    entity = _DummyEntity(coordinator)

    details = entity._device_link_details()

    assert details["breed"] == "Beagle"
    assert details["suggested_area"] == "Pet Area - Buddy (5yo)"
    assert entity.suggested_area == "Pet Area - Buddy (5yo)"


def test_device_link_details_handles_missing_optional_dog_info_fields() -> None:
    """Device link details should gracefully skip missing breed/age branches."""
    coordinator = _DummyCoordinator()
    coordinator._dog_payload["dog-1"] = {"dog_info": {"dog_name": "Buddy"}}
    entity = _DummyEntity(coordinator)

    details = entity._device_link_details()

    assert "breed" not in details
    assert "suggested_area" not in details


def test_device_link_details_when_no_dog_data_uses_base_details() -> None:
    """When no dog payload exists, detail generation should keep base metadata."""
    entity = _DummyEntity(_DummyCoordinator())
    details = entity._device_link_details()
    assert "breed" not in details


def test_device_link_details_with_empty_dog_info_mapping() -> None:
    """Empty dog-info payload should skip optional enrichment paths."""
    entity = _DummyEntity(_DummyCoordinator())
    entity._get_dog_data_cached = MagicMock(return_value={"dog_info": {}})

    details = entity._device_link_details()

    assert "breed" not in details


def test_get_or_create_tracker_reuses_existing_instances() -> None:
    """Tracker factory should create once and reuse for identical keys."""
    first = OptimizedEntityBase._get_or_create_tracker("dog-status")
    second = OptimizedEntityBase._get_or_create_tracker("dog-status")
    third = OptimizedEntityBase._get_or_create_tracker("dog-other")

    assert first is second
    assert first is not third


def test_maybe_cleanup_caches_respects_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache cleanup should run only when the configured interval has elapsed."""
    entity = _DummyEntity(_DummyCoordinator())
    now = dt_util.utcnow().timestamp()
    cleanup_spy = MagicMock()
    monkeypatch.setattr(oeb, "_cleanup_global_caches", cleanup_spy)
    monkeypatch.setattr(oeb, "_utcnow_timestamp", lambda: now)

    type(entity)._last_cache_cleanup = now
    entity._maybe_cleanup_caches()
    cleanup_spy.assert_not_called()

    type(entity)._last_cache_cleanup = now - (
        oeb.MEMORY_OPTIMIZATION["weak_ref_cleanup_interval"] + 1
    )
    entity._maybe_cleanup_caches()
    cleanup_spy.assert_called_once()


@pytest.mark.asyncio
async def test_getattribute_wraps_mocked_async_update_and_records_error() -> None:
    """Mocked async_update access should preserve tracker error accounting."""
    entity = _DummyEntity(_DummyCoordinator())
    entity.async_update = AsyncMock(side_effect=RuntimeError("update boom"))

    with pytest.raises(RuntimeError):
        await entity.async_update()

    assert entity._performance_tracker._error_count == 1


@pytest.mark.asyncio
async def test_getattribute_wrapper_returns_non_awaitable_mock_result() -> None:
    """Wrapped async_update should also return plain synchronous mock values."""
    entity = _DummyEntity(_DummyCoordinator())
    entity.async_update = MagicMock(return_value="sync-ok")

    result = await entity.async_update()

    assert result == "sync-ok"


@pytest.mark.asyncio
async def test_async_added_to_hass_success_and_failure_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entity add lifecycle should record success timing and failure errors."""
    entity = _DummyEntity(_DummyCoordinator())

    async def _ok_super(_self: Any) -> None:
        return None

    monkeypatch.setattr(
        oeb.CoordinatorEntity,
        "async_added_to_hass",
        _ok_super,
        raising=False,
    )
    entity._async_restore_state = AsyncMock()

    await entity.async_added_to_hass()
    entity._async_restore_state.assert_awaited_once()
    assert entity._performance_tracker._operation_times

    async def _failing_super(_self: Any) -> None:
        raise RuntimeError("add failed")

    monkeypatch.setattr(
        oeb.CoordinatorEntity,
        "async_added_to_hass",
        _failing_super,
        raising=False,
    )
    with pytest.raises(RuntimeError):
        await entity.async_added_to_hass()
    assert entity._performance_tracker._error_count >= 1


@pytest.mark.asyncio
async def test_async_restore_state_and_base_restoration_noop() -> None:
    """State restoration should handle none, success, and restoration failures."""
    entity = _DummyEntity(_DummyCoordinator())
    state = State("sensor.test", "on")

    entity.async_get_last_state = AsyncMock(return_value=None)
    await entity._async_restore_state()

    entity.async_get_last_state = AsyncMock(return_value=state)
    entity._handle_state_restoration = AsyncMock()
    await entity._async_restore_state()
    entity._handle_state_restoration.assert_awaited_once_with(state)

    entity._handle_state_restoration = AsyncMock(side_effect=RuntimeError("restore"))
    await entity._async_restore_state()

    await oeb.OptimizedEntityBase._handle_state_restoration(entity, state)


def test_calculate_availability_branch_matrix() -> None:
    """Availability calculator should cover offline, stale, and valid branches."""
    entity = _DummyEntity(_DummyCoordinator())

    assert entity._calculate_availability(coordinator_available=False) is False

    entity._get_dog_data_cached = MagicMock(return_value=None)
    assert entity._calculate_availability(coordinator_available=True) is False

    for status in ("offline", "error", "missing"):
        entity._get_dog_data_cached = MagicMock(
            return_value={"status": status, "last_update": None},
        )
        assert entity._calculate_availability(coordinator_available=True) is False

    entity._get_dog_data_cached = MagicMock(
        return_value={"status": "recovering", "last_update": None},
    )
    assert entity._calculate_availability(coordinator_available=True) is True

    entity._get_dog_data_cached = MagicMock(
        return_value={"status": "online", "last_update": "invalid"},
    )
    assert entity._calculate_availability(coordinator_available=True) is False

    stale = (dt_util.utcnow() - timedelta(minutes=30)).isoformat()
    entity._get_dog_data_cached = MagicMock(
        return_value={"status": "online", "last_update": stale},
    )
    assert entity._calculate_availability(coordinator_available=True) is False

    recent = dt_util.utcnow().isoformat()
    entity._get_dog_data_cached = MagicMock(
        return_value={"status": "online", "last_update": recent},
    )
    assert entity._calculate_availability(coordinator_available=True) is True


def test_calculate_availability_implicit_coordinator_flag_and_no_last_update() -> None:
    """Implicit coordinator check should succeed with online status/no timestamp."""
    coordinator = _DummyCoordinator()
    entity = _DummyEntity(coordinator)
    entity._get_dog_data_cached = MagicMock(return_value={"status": "online"})

    assert entity._calculate_availability() is True


def test_available_property_uses_cache_hits_and_misses() -> None:
    """Availability property should memoize values and increment cache metrics."""
    entity = _DummyEntity(_DummyCoordinator())
    entity._calculate_availability = MagicMock(return_value=True)

    first = entity.available
    second = entity.available

    assert first is True and second is True
    assert entity._calculate_availability.call_count == 1
    assert entity._performance_tracker._cache_misses >= 1
    assert entity._performance_tracker._cache_hits >= 1


def test_available_cache_timestamp_normalization_and_mismatch_recalculation() -> None:
    """Availability cache should normalize future timestamps and recalc on mismatch."""
    entity = _DummyEntity(_DummyCoordinator())
    cache_key = f"available_{entity._dog_id}_{entity._entity_type}"
    now = dt_util.utcnow().timestamp()
    future_ts = now + 100
    _AVAILABILITY_CACHE[cache_key] = _AvailabilityCacheEntry(
        available=True,
        timestamp=future_ts,
        coordinator_available=False,
    )

    entity._calculate_availability = MagicMock(return_value=True)
    assert entity.available is True
    assert entity._calculate_availability.called
    assert _AVAILABILITY_CACHE[cache_key].timestamp < future_ts


def test_extra_state_attributes_success_cache_and_fallback() -> None:
    """Attribute generation should cache on success and fallback on failure."""
    entity = _DummyEntity(_DummyCoordinator())
    entity._generate_state_attributes = MagicMock(return_value={"hello": "world"})

    attrs_first = entity.extra_state_attributes
    attrs_second = entity.extra_state_attributes
    assert attrs_first["hello"] == "world"
    assert attrs_second["hello"] == "world"

    _ATTRIBUTES_CACHE.clear()
    entity._generate_state_attributes = MagicMock(side_effect=RuntimeError("attrs"))
    fallback = entity.extra_state_attributes
    assert fallback["status"] == "error"


def test_extra_state_attributes_cache_normalization_and_expiry() -> None:
    """Attribute cache should normalize future timestamps and regenerate when stale."""
    entity = _DummyEntity(_DummyCoordinator())
    cache_key = f"attrs_{entity._attr_unique_id}"
    now = dt_util.utcnow().timestamp()
    future_ts = now + 100
    _ATTRIBUTES_CACHE[cache_key] = _AttributesCacheEntry(
        attributes={"cached": True},
        timestamp=future_ts,
    )

    cached = entity.extra_state_attributes
    assert cached["cached"] is True
    assert _ATTRIBUTES_CACHE[cache_key].timestamp < future_ts

    _ATTRIBUTES_CACHE[cache_key] = _AttributesCacheEntry(
        attributes={"stale": True},
        timestamp=0,
    )
    entity._generate_state_attributes = MagicMock(return_value={"fresh": True})
    fresh = entity.extra_state_attributes
    assert fresh["fresh"] is True


def test_generate_state_attributes_and_availability_transition_tracking() -> None:
    """Generated attributes should include dog info, perf data, and transitions."""
    coordinator = _DummyCoordinator()
    coordinator._dog_payload["dog-1"] = {
        "status": "online",
        "last_update": dt_util.utcnow().isoformat(),
        "dog_info": {
            "dog_breed": "Labrador",
            "dog_age": 3,
            "dog_size": "large",
            "dog_weight": 30,
        },
    }
    entity = _DummyEntity(coordinator)
    entity._performance_tracker.record_operation_time(0.2)

    attrs_online = entity._generate_state_attributes()
    assert attrs_online["status"] == "online"
    assert "performance_metrics" in attrs_online
    assert attrs_online["dog_breed"] == "Labrador"

    previous = entity._update_coordinator_availability(False)
    assert previous is True
    coordinator.available = False
    attrs_offline = entity._generate_state_attributes()
    assert attrs_offline["coordinator_available"] is False

    fallback = entity._get_fallback_attributes()
    assert fallback["status"] == "error"


def test_generate_state_attributes_recovering_and_sparse_dog_info() -> None:
    """Recovering base status and sparse dog-data branches should be emitted."""
    entity = _DummyEntity(_DummyCoordinator())
    entity._last_coordinator_available = False
    entity._previous_coordinator_available = False
    entity._get_dog_data_cached = MagicMock(return_value=None)
    attrs = entity._generate_state_attributes()
    assert attrs["status"] == "recovering"
    assert "performance_metrics" not in attrs

    sparse = _DummyEntity(_DummyCoordinator())
    sparse._get_dog_data_cached = MagicMock(
        return_value={"last_update": dt_util.utcnow().isoformat(), "dog_info": {}},
    )
    sparse_attrs = sparse._generate_state_attributes()
    assert sparse_attrs["data_last_update"]


def test_update_coordinator_availability_initializes_previous_marker() -> None:
    """When previous marker is absent, update helper should initialize it."""
    entity = _DummyEntity(_DummyCoordinator())
    del entity._previous_coordinator_available
    previous = entity._update_coordinator_availability(
        entity._last_coordinator_available,
    )
    assert previous == entity._last_coordinator_available


def test_get_dog_data_cached_for_direct_and_fallback_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dog payload caching should support direct fetch and fallback statuses."""
    coordinator = _DummyCoordinator()
    entity = _DummyEntity(coordinator)

    monkeypatch.setattr(
        oeb,
        "_call_coordinator_method",
        lambda _coord, _method, _dog_id: {
            "status": "online",
            "dog_info": {"dog_name": "Buddy"},
        },
    )

    payload = entity._get_dog_data_cached()
    assert payload is not None
    assert payload["status"] == "online"
    assert entity._get_dog_data_cached()["status"] == "online"

    _STATE_CACHE.clear()
    coordinator.available = False
    offline = entity._get_dog_data_cached()
    assert offline is not None
    assert offline["status"] == "offline"

    _STATE_CACHE.clear()
    coordinator.available = True
    monkeypatch.setattr(oeb, "_call_coordinator_method", lambda *_args, **_kwargs: None)
    recovering = entity._get_dog_data_cached()
    assert recovering is not None
    assert recovering["status"] in {"recovering", "missing"}

    class _AsPawControl(_DummyCoordinator):
        pass

    monkeypatch.setattr(oeb, "PawControlCoordinator", _AsPawControl)
    direct_coordinator = _AsPawControl()
    direct_coordinator._dog_payload["dog-2"] = {"status": "online"}
    direct_entity = _DummyEntity(direct_coordinator, dog_id="dog-2")
    direct = direct_entity._get_dog_data_cached()
    assert direct is not None
    assert direct["status"] == "online"


def test_get_dog_data_cached_normalized_cache_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Future cache timestamps should be normalized when re-used."""
    entity = _DummyEntity(_DummyCoordinator())
    cache_key = f"dog_data_{entity._dog_id}"
    now = dt_util.utcnow().timestamp()
    _STATE_CACHE[cache_key] = _StateCacheEntry(
        payload={"status": "online"},
        timestamp=now + 100,
        coordinator_available=True,
    )
    monkeypatch.setattr(oeb, "_utcnow_timestamp", lambda: now)

    payload = entity._get_dog_data_cached()
    assert payload is not None
    assert _STATE_CACHE[cache_key].timestamp <= now


def test_get_dog_data_cached_bypasses_cache_when_cached_was_offline() -> None:
    """Cached offline marker should be ignored once coordinator reports available."""
    coordinator = _DummyCoordinator()
    entity = _DummyEntity(coordinator)
    cache_key = f"dog_data_{entity._dog_id}"
    now = dt_util.utcnow().timestamp()
    _STATE_CACHE[cache_key] = _StateCacheEntry(
        payload={"status": "offline"},
        timestamp=now,
        coordinator_available=False,
    )

    coordinator._dog_payload["dog-1"] = {"status": "online"}
    payload = entity._get_dog_data_cached()

    assert payload is not None
    assert payload["status"] == "online"


def test_get_module_data_cached_for_typed_and_untyped_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Module payload caching should handle typed and untyped modules."""
    coordinator = _DummyCoordinator()
    entity = _DummyEntity(coordinator)

    monkeypatch.setattr(
        oeb,
        "_call_coordinator_method",
        lambda _coord, _method, _dog_id, module: (
            {"status": "ok", "foo": "bar"}
            if module == "garden"
            else {"value": 10, "ok": True}
        ),
    )

    typed = entity._get_module_data_cached("garden")
    assert typed["status"] == "ok"
    typed_cached = entity._get_module_data_cached("garden")
    assert typed_cached["status"] == "ok"

    untyped = entity._get_module_data_cached("custom_module")
    assert untyped["value"] == 10

    monkeypatch.setattr(
        oeb,
        "_call_coordinator_method",
        lambda *_args, **_kwargs: "not-a-mapping",
    )
    typed_unknown = entity._get_module_data_cached("weather")
    assert typed_unknown["status"] == "unknown"

    coordinator.available = False
    typed_offline = entity._get_module_data_cached("health")
    assert typed_offline["status"] == "unknown"

    class _AsPawControl(_DummyCoordinator):
        pass

    monkeypatch.setattr(oeb, "PawControlCoordinator", _AsPawControl)
    direct_coordinator = _AsPawControl()
    direct_coordinator._module_payload[("dog-3", "garden")] = {"status": "online"}
    direct_entity = _DummyEntity(direct_coordinator, dog_id="dog-3")
    direct = direct_entity._get_module_data_cached("garden")
    assert direct["status"] == "online"


def test_get_module_data_cached_untyped_cache_and_unavailable_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Module cache should return untyped cached payloads and handle stale paths."""
    entity = _DummyEntity(_DummyCoordinator())
    cache_key = f"module_{entity._dog_id}_custom"
    now = dt_util.utcnow().timestamp()
    _STATE_CACHE[cache_key] = _StateCacheEntry(
        payload={"cached": "value"},
        timestamp=now + 200,
        coordinator_available=True,
    )
    monkeypatch.setattr(oeb, "_utcnow_timestamp", lambda: now)

    cached = entity._get_module_data_cached("custom")
    assert cached["cached"] == "value"
    assert _STATE_CACHE[cache_key].timestamp <= now

    entity.coordinator.available = False
    stale_untyped = entity._get_module_data_cached("custom")
    assert isinstance(stale_untyped, dict)


def test_get_module_data_cached_nonmapping_untyped_and_unavailable_untyped() -> None:
    """Untyped non-mapping and unavailable branches should return empty mappings."""
    coordinator = _DummyCoordinator()
    entity = _DummyEntity(coordinator)
    coordinator._module_payload[("dog-1", "custom")] = "boom"

    non_mapping = entity._get_module_data_cached("custom")
    assert non_mapping == {}

    coordinator.available = False
    unavailable = entity._get_module_data_cached("custom")
    assert unavailable == {}


def test_get_module_data_cached_bypasses_cache_after_offline_marker() -> None:
    """Module cache should be ignored if cached coordinator availability was False."""
    coordinator = _DummyCoordinator()
    entity = _DummyEntity(coordinator)
    cache_key = f"module_{entity._dog_id}_garden"
    now = dt_util.utcnow().timestamp()
    _STATE_CACHE[cache_key] = _StateCacheEntry(
        payload={"status": "cached"},
        timestamp=now,
        coordinator_available=False,
    )
    coordinator._module_payload[("dog-1", "garden")] = {"status": "online"}

    payload = entity._get_module_data_cached("garden")
    assert payload["status"] == "online"


def test_get_module_data_cached_unavailable_untyped_without_cache() -> None:
    """Unavailable coordinator with untyped module should keep empty mapping."""
    coordinator = _DummyCoordinator()
    coordinator.available = False
    entity = _DummyEntity(coordinator)

    payload = entity._get_module_data_cached("custom_untyped")
    assert payload == {}


@pytest.mark.asyncio
async def test_async_update_and_refresh_dispatcher_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Update methods should cover parent, request-refresh, and refresh fallback."""
    entity = _DummyEntity(_DummyCoordinator())

    entity._async_request_refresh = AsyncMock()
    entity._async_invalidate_caches = AsyncMock()
    await entity.async_update()
    entity._async_request_refresh.assert_awaited_once()
    entity._async_invalidate_caches.assert_awaited_once()

    entity._async_request_refresh = AsyncMock(side_effect=RuntimeError("update"))
    with pytest.raises(RuntimeError):
        await entity.async_update()

    async def _parent_update(_self: Any) -> None:
        return None

    monkeypatch.setattr(
        oeb.CoordinatorEntity,
        "async_update",
        _parent_update,
        raising=False,
    )
    parent_entity = _DummyEntity(_DummyCoordinator())
    await parent_entity._async_request_refresh()

    request_entity = _DummyEntity(_DummyCoordinator())
    monkeypatch.setattr(oeb.CoordinatorEntity, "async_update", None, raising=False)
    await request_entity._async_request_refresh()
    assert request_entity.coordinator.refresh_calls == 1

    refresh_entity = _DummyEntity(_RefreshOnlyCoordinator())
    await refresh_entity._async_request_refresh()
    assert refresh_entity.coordinator.refresh_calls == 1


@pytest.mark.asyncio
async def test_async_request_refresh_non_awaitable_and_no_method_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh dispatcher should support sync callables and no-op fallback."""

    class _SyncParentCoordinator(_DummyCoordinator):
        pass

    async def _never_awaited_parent(_self: Any) -> None:
        return None

    sync_entity = _DummyEntity(_SyncParentCoordinator())
    monkeypatch.setattr(
        oeb.CoordinatorEntity,
        "async_update",
        lambda _self: None,
        raising=False,
    )
    await sync_entity._async_request_refresh()

    monkeypatch.setattr(
        oeb.CoordinatorEntity,
        "async_update",
        _never_awaited_parent,
        raising=False,
    )
    await sync_entity._async_request_refresh()

    class _NoRefreshCoordinator:
        def __init__(self) -> None:
            self.available = True
            self.last_update_success = True

        def get_dog_data(self, dog_id: str) -> Mapping[str, Any] | None:
            _ = dog_id
            return None

        def get_module_data(self, dog_id: str, module: str) -> Mapping[str, Any]:
            _ = dog_id, module
            return {}

    no_refresh_entity = _DummyEntity(_NoRefreshCoordinator())
    monkeypatch.setattr(oeb.CoordinatorEntity, "async_update", None, raising=False)
    await no_refresh_entity._async_request_refresh()


@pytest.mark.asyncio
async def test_async_request_refresh_sync_return_from_request_and_refresh() -> None:
    """Coordinator refresh helpers returning sync values should be accepted."""

    class _SyncRequestCoordinator:
        def __init__(self) -> None:
            self.available = True
            self.last_update_success = True

        def get_dog_data(self, dog_id: str) -> Mapping[str, Any] | None:
            _ = dog_id
            return None

        def get_module_data(self, dog_id: str, module: str) -> Mapping[str, Any]:
            _ = dog_id, module
            return {}

        def async_request_refresh(self) -> None:
            return None

    class _SyncRefreshCoordinator:
        def __init__(self) -> None:
            self.available = True
            self.last_update_success = True

        def get_dog_data(self, dog_id: str) -> Mapping[str, Any] | None:
            _ = dog_id
            return None

        def get_module_data(self, dog_id: str, module: str) -> Mapping[str, Any]:
            _ = dog_id, module
            return {}

        def async_refresh(self) -> None:
            return None

    request_entity = _DummyEntity(_SyncRequestCoordinator())
    refresh_entity = _DummyEntity(_SyncRefreshCoordinator())
    await request_entity._async_request_refresh()
    await refresh_entity._async_request_refresh()


@pytest.mark.asyncio
async def test_cache_invalidation_and_metrics_helpers() -> None:
    """Cache purging and metric helpers should expose stable payloads."""
    entity = _DummyEntity(_DummyCoordinator(), dog_id="dog-77")
    _STATE_CACHE["dog_data_dog-77"] = _StateCacheEntry(payload={}, timestamp=0)
    _STATE_CACHE["module_dog-77_garden"] = _StateCacheEntry(payload={}, timestamp=0)
    _ATTRIBUTES_CACHE[f"attrs_{entity._attr_unique_id}"] = _AttributesCacheEntry(
        attributes={},
        timestamp=0,
    )
    _AVAILABILITY_CACHE["available_dog-77_status"] = _AvailabilityCacheEntry(
        available=True,
        timestamp=0,
        coordinator_available=True,
    )

    entity._purge_entity_cache_entries()
    assert "dog_data_dog-77" not in _STATE_CACHE
    assert f"attrs_{entity._attr_unique_id}" not in _ATTRIBUTES_CACHE
    assert "available_dog-77_status" not in _AVAILABILITY_CACHE

    _STATE_CACHE["dog_data_dog-77"] = _StateCacheEntry(payload={}, timestamp=0)
    _ATTRIBUTES_CACHE[f"attrs_{entity._attr_unique_id}"] = _AttributesCacheEntry(
        attributes={},
        timestamp=0,
    )
    _AVAILABILITY_CACHE["available_dog-77_status"] = _AvailabilityCacheEntry(
        available=True,
        timestamp=0,
        coordinator_available=True,
    )
    await entity._async_invalidate_caches()
    assert _STATE_CACHE == {}
    assert _ATTRIBUTES_CACHE == {}
    assert _AVAILABILITY_CACHE == {}

    task = entity.async_invalidate_cache()
    await task

    oeb.OptimizedEntityBase._get_entity_state(entity)

    metrics = entity.get_performance_metrics()
    assert metrics["entity_id"] == entity._attr_unique_id
    _STATE_CACHE["other-key"] = _StateCacheEntry(payload={}, timestamp=0)
    memory = entity._estimate_memory_usage()
    assert memory["estimated_total_bytes"] >= memory["base_entity_bytes"]


def test_estimate_memory_usage_counts_matching_cache_keys() -> None:
    """Matching dog-id keys should contribute to cache memory estimates."""
    entity = _DummyEntity(_DummyCoordinator(), dog_id="dog-mem")
    _STATE_CACHE["dog-mem-state"] = _StateCacheEntry(payload={}, timestamp=0)
    _ATTRIBUTES_CACHE["dog-mem-attrs"] = _AttributesCacheEntry(
        attributes={},
        timestamp=0,
    )

    estimate = entity._estimate_memory_usage()
    assert estimate["cache_contribution_bytes"] > 0


@pytest.mark.asyncio
async def test_sensor_binary_and_switch_subclasses_behaviour() -> None:
    """Subclass helpers should expose expected state and icon behavior."""
    coordinator = _DummyCoordinator()

    sensor = OptimizedSensorBase(
        coordinator,
        "dog-1",
        "Buddy",
        "temperature",
    )
    assert sensor.native_value is None
    assert sensor._get_entity_state() is None

    binary = OptimizedBinarySensorBase(
        coordinator,
        "dog-1",
        "Buddy",
        "door",
        icon_on="mdi:door-open",
        icon_off="mdi:door-closed",
    )
    assert binary.is_on is False
    assert binary.icon == "mdi:door-closed"
    binary._attr_is_on = True
    assert binary.icon == "mdi:door-open"
    assert binary._get_entity_state() is True

    binary_default = OptimizedBinarySensorBase(
        coordinator,
        "dog-1",
        "Buddy",
        "window",
    )
    assert binary_default.icon is None

    switch = OptimizedSwitchBase(
        coordinator,
        "dog-1",
        "Buddy",
        "automation",
        initial_state=False,
    )
    assert switch.is_on is False
    await switch._handle_state_restoration(State("switch.test", "on"))
    assert switch.is_on is True
    await switch._handle_state_restoration(State("switch.test", "unknown"))
    assert switch.is_on is True

    switch.async_write_ha_state = MagicMock(return_value=None)
    await switch.async_turn_on()
    assert switch.is_on is True
    await switch.async_turn_off()
    assert switch.is_on is False

    failing = OptimizedSwitchBase(coordinator, "dog-1", "Buddy", "failing")
    failing._async_turn_on_implementation = AsyncMock(side_effect=RuntimeError("on"))
    with pytest.raises(HomeAssistantError):
        await failing.async_turn_on()

    failing._async_turn_off_implementation = AsyncMock(side_effect=RuntimeError("off"))
    with pytest.raises(HomeAssistantError):
        await failing.async_turn_off()

    await switch._async_turn_on_implementation()
    await switch._async_turn_off_implementation()
    assert switch._get_entity_state() is False
    attrs = switch._generate_state_attributes()
    assert "last_changed" in attrs
    assert "switch_type" in attrs


@pytest.mark.asyncio
async def test_switch_turn_on_off_write_state_awaitable_and_disabled() -> None:
    """Switch methods should handle awaitable write-state and disabled callbacks."""
    coordinator = _DummyCoordinator()
    awaitable_switch = OptimizedSwitchBase(
        coordinator,
        "dog-2",
        "Max",
        "awaitable",
    )
    awaitable_switch.async_write_ha_state = AsyncMock(return_value=None)
    await awaitable_switch.async_turn_on()
    await awaitable_switch.async_turn_off()

    disabled_switch = OptimizedSwitchBase(
        coordinator,
        "dog-3",
        "Luna",
        "disabled",
    )
    disabled_switch.async_write_ha_state = None
    await disabled_switch.async_turn_on()
    await disabled_switch.async_turn_off()


def test_entity_registry_lifecycle_and_dead_ref_pruning() -> None:
    """Registry should prune dead refs, track sentinel, and expose iterators."""
    registry = EntityRegistry()
    coordinator = _DummyCoordinator()
    entity = _DummyEntity(coordinator, dog_id="dog-reg")
    ref = weakref.ref(entity)
    registry.add(ref)

    assert bool(registry) is True
    assert len(list(registry)) >= 1
    assert len(registry) >= 1
    assert registry.all_refs()

    registry.discard(ref)
    assert len(registry) == 0

    class _WeakObj:
        pass

    weak_obj = _WeakObj()
    dead_ref = weakref.ref(weak_obj)
    registry.add(dead_ref)  # type: ignore[arg-type]
    del weak_obj
    gc.collect()

    assert len(registry) == 0

    registry.set_sentinel(entity)
    assert bool(registry) is True
    registry.clear()
    assert bool(registry) is False


def test_cleanup_global_caches_and_register_entity_callbacks() -> None:
    """Global cache cleanup should evict expired entries and dead refs."""
    now = dt_util.utcnow().timestamp()
    _STATE_CACHE["state-old"] = _StateCacheEntry(payload={}, timestamp=now - 9999)
    _ATTRIBUTES_CACHE["attrs-old"] = _AttributesCacheEntry(attributes={}, timestamp=0)
    _AVAILABILITY_CACHE["available-old"] = _AvailabilityCacheEntry(
        available=True,
        timestamp=0,
        coordinator_available=True,
    )

    class _WeakObj:
        pass

    weak_obj = _WeakObj()
    dead_ref = weakref.ref(weak_obj)
    oeb._ENTITY_REGISTRY.add(dead_ref)  # type: ignore[arg-type]
    del weak_obj
    gc.collect()

    _cleanup_global_caches()
    assert "state-old" not in _STATE_CACHE
    assert "attrs-old" not in _ATTRIBUTES_CACHE
    assert "available-old" not in _AVAILABILITY_CACHE

    entity = _DummyEntity(_DummyCoordinator(), dog_id="dog-cb")
    assert len(oeb._ENTITY_REGISTRY) >= 1
    entity_ref = weakref.ref(entity)
    assert entity_ref() is not None
    del entity
    gc.collect()
    _cleanup_global_caches()

    sentinel_entity = oeb._REGISTRY_SENTINEL_ENTITY
    _register_entity(sentinel_entity)
    assert oeb._ENTITY_REGISTRY._sentinel_alive() is True


def test_cleanup_global_caches_removes_dead_refs_branch_forced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force dead-ref list path to exercise explicit registry discard loop."""

    class _WeakObj:
        pass

    weak_obj = _WeakObj()
    dead_ref = weakref.ref(weak_obj)
    _ = hash(dead_ref)
    del weak_obj
    gc.collect()

    monkeypatch.setattr(EntityRegistry, "all_refs", lambda _self: (dead_ref,))
    _cleanup_global_caches()


@pytest.mark.asyncio
async def test_registry_sentinel_coordinator_methods_and_entity_state() -> None:
    """Sentinel coordinator helper methods should behave as no-op utilities."""
    coordinator = _RegistrySentinelCoordinator()
    observed: list[str] = []

    def _listener() -> None:
        observed.append("called")

    remove = coordinator.async_add_listener(_listener)
    coordinator.async_update_listeners()
    assert observed == ["called"]
    remove()
    coordinator.async_remove_listener(_listener)
    await coordinator.async_request_refresh()
    await coordinator.async_refresh()
    assert coordinator.get_dog_data("dog-1") == {}
    assert coordinator.get_module_data("dog-1", "garden") == {}

    assert oeb._REGISTRY_SENTINEL_ENTITY._get_entity_state()["status"] == "sentinel"
    assert oeb._REGISTRY_SENTINEL_ENTITY._generate_state_attributes()["registry"] == (
        "sentinel"
    )


@pytest.mark.asyncio
async def test_create_optimized_entities_batched_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entity batching should handle guard clauses and delay modes."""
    add_entities = AsyncMock()
    sleep_mock = AsyncMock()
    monkeypatch.setattr(oeb, "async_call_add_entities", add_entities)
    monkeypatch.setattr(oeb.asyncio, "sleep", sleep_mock)

    await create_optimized_entities_batched([], add_entities)
    add_entities.assert_not_called()

    entities = [
        _DummyEntity(_DummyCoordinator(), dog_id=f"dog-{idx}") for idx in range(3)
    ]

    await create_optimized_entities_batched(
        entities,
        add_entities,
        batch_size=0,
        delay_between_batches=-1,
    )
    assert add_entities.await_count == 3
    assert sleep_mock.await_count >= 1

    add_entities.reset_mock()
    sleep_mock.reset_mock()
    await create_optimized_entities_batched(
        entities,
        add_entities,
        batch_size=2,
        delay_between_batches=0.01,
    )
    assert add_entities.await_count == 2
    sleep_mock.assert_awaited()


def test_get_global_performance_stats_with_and_without_data() -> None:
    """Global performance stats should aggregate tracker samples correctly."""
    empty = get_global_performance_stats()
    assert empty["total_entities_registered"] >= 0
    assert empty["entities_with_performance_data"] == 0

    tracker = PerformanceTracker("entity.one")
    tracker.record_operation_time(0.2)
    tracker.record_cache_hit()
    tracker.record_cache_miss()
    tracker.record_error()
    OptimizedEntityBase._performance_registry["entity.one"] = tracker

    rich = get_global_performance_stats()
    assert rich["entities_with_performance_data"] == 1
    assert rich["average_operation_time_ms"] > 0
    assert rich["average_cache_hit_rate"] >= 0
    assert rich["total_errors"] >= 1
