"""Unit tests for cache repair helper utilities."""

from dataclasses import dataclass
from datetime import timedelta
import sys

import pytest

from custom_components.pawcontrol.const import (
    CONF_DOGS,
    CONF_GPS_SOURCE,
    CONF_GPS_UPDATE_INTERVAL,
    CONF_MODULES,
    CONF_WEBHOOK_ENABLED,
)
from custom_components.pawcontrol.coordinator_support import (
    MANAGER_ATTRIBUTES,
    CoordinatorMetrics,
    DogConfigRegistry,
    _build_repair_telemetry,
    bind_runtime_managers,
    clear_runtime_managers,
    ensure_cache_repair_aggregate,
)
from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.types import (
    CacheRepairAggregate,
    CoordinatorRuntimeManagers,
    ModuleCacheMetrics,
)


@dataclass(slots=True)
class _AltAggregate:
    """Alternative aggregate type used to validate module-class detection."""

    total_caches: int


class _TypesModuleStub:
    """Stub module object exposing a replacement aggregate class."""

    CacheRepairAggregate = _AltAggregate


def test_build_repair_telemetry_returns_none_without_summary() -> None:
    """None or empty summaries should not produce telemetry."""
    assert _build_repair_telemetry(None) is None


def test_build_repair_telemetry_counts_only_non_empty_entries() -> None:
    """Telemetry should include only populated anomaly counters."""
    summary = CacheRepairAggregate(
        total_caches=3,
        anomaly_count=2,
        severity="warning",
        generated_at="2026-01-01T00:00:00+00:00",
        caches_with_errors=["cache-a", "", "cache-b", 0],  # type: ignore[list-item]
        caches_with_expired_entries=["cache-a"],
        caches_with_pending_expired_entries=["cache-c", ""],
        caches_with_override_flags=["cache-a"],
        caches_with_low_hit_rate=["cache-b"],
        issues=[{"cache": "cache-a"}, {"cache": "cache-b"}],
    )

    telemetry = _build_repair_telemetry(summary)

    assert telemetry == {
        "severity": "warning",
        "anomaly_count": 2,
        "total_caches": 3,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "issues": 2,
        "caches_with_errors": 2,
        "caches_with_expired_entries": 1,
        "caches_with_pending_expired_entries": 1,
        "caches_with_override_flags": 1,
        "caches_with_low_hit_rate": 1,
    }


def test_build_repair_telemetry_uses_defaults_for_sparse_summary() -> None:
    """Sparse summaries should keep defaults and omit empty optional counters."""
    summary = CacheRepairAggregate(
        total_caches=1, anomaly_count=0, severity="", generated_at=""
    )

    assert _build_repair_telemetry(summary) == {
        "severity": "info",
        "anomaly_count": 0,
        "total_caches": 1,
        "generated_at": "",
        "issues": 0,
    }


def test_ensure_cache_repair_aggregate_supports_runtime_rebound_class(
    monkeypatch,
) -> None:
    """When types module is rebound, helper should still accept that class."""
    summary = _AltAggregate(total_caches=1)
    monkeypatch.setitem(
        sys.modules,
        "custom_components.pawcontrol.types",
        _TypesModuleStub(),
    )

    assert ensure_cache_repair_aggregate(summary) is summary


def test_ensure_cache_repair_aggregate_rejects_non_matching_object() -> None:
    """Unknown summary objects should be discarded."""
    assert ensure_cache_repair_aggregate(object()) is None


def test_ensure_cache_repair_aggregate_accepts_none_input() -> None:
    """A missing repair summary should pass through as None."""
    assert ensure_cache_repair_aggregate(None) is None


class _BindAwareCoordinator:
    """Coordinator stub that records manager bindings on attributes."""

    def __init__(self) -> None:
        for attribute in (
            "data_manager",
            "feeding_manager",
            "garden_manager",
            "geofencing_manager",
            "gps_geofence_manager",
            "notification_manager",
            "walk_manager",
            "weather_health_manager",
        ):
            setattr(self, attribute, "bound")


class _BindAwareModulesAdapter:
    """Modules adapter stub capturing attachment and detachment calls."""

    def __init__(self) -> None:
        self.attach_calls: list[dict[str, object | None]] = []
        self.detached = False

    def attach_managers(self, **kwargs: object | None) -> None:
        self.attach_calls.append(dict(kwargs))

    def detach_managers(self) -> None:
        self.detached = True


class _GpsManagerStub:
    """GPS manager stub exposing notification-manager wiring."""

    def __init__(self) -> None:
        self.notification_manager: object | None = None

    def set_notification_manager(self, notification_manager: object) -> None:
        self.notification_manager = notification_manager


class _NotificationManagerStub:
    """Notification manager stub that records cache registration calls."""

    def __init__(self) -> None:
        self.cache_monitor_payloads: list[object] = []

    def register_cache_monitors(self, data_manager: object) -> None:
        self.cache_monitor_payloads.append(data_manager)


class _CacheAwareDataManager:
    """Registrar-compatible cache monitor stub for coordinator binding tests."""

    def register_cache_monitor(self, name: str, cache: object) -> None:
        self.last_registration = (name, cache)


def test_bind_runtime_managers_wires_notification_and_cache_registration() -> None:
    """Binding should connect GPS notifications and cache monitor registration."""
    coordinator = _BindAwareCoordinator()
    modules = _BindAwareModulesAdapter()
    data_manager = _CacheAwareDataManager()
    gps_manager = _GpsManagerStub()
    notification_manager = _NotificationManagerStub()
    managers = CoordinatorRuntimeManagers(
        data_manager=data_manager,
        gps_geofence_manager=gps_manager,
        notification_manager=notification_manager,
    )

    bind_runtime_managers(coordinator, modules, managers)

    assert coordinator.data_manager is data_manager
    assert coordinator.gps_geofence_manager is gps_manager
    assert coordinator.notification_manager is notification_manager
    assert gps_manager.notification_manager is notification_manager
    assert modules.attach_calls == [
        {
            "data_manager": data_manager,
            "feeding_manager": None,
            "walk_manager": None,
            "gps_geofence_manager": gps_manager,
            "weather_health_manager": None,
            "garden_manager": None,
        }
    ]
    assert notification_manager.cache_monitor_payloads == [data_manager]


def test_bind_runtime_managers_skips_optional_hooks_when_dependencies_missing() -> None:
    """Binding should tolerate managers without optional registration helpers."""
    coordinator = _BindAwareCoordinator()
    modules = _BindAwareModulesAdapter()
    gps_manager = object()
    notification_manager = object()

    bind_runtime_managers(
        coordinator,
        modules,
        CoordinatorRuntimeManagers(
            gps_geofence_manager=gps_manager,
            notification_manager=notification_manager,
        ),
    )

    assert coordinator.gps_geofence_manager is gps_manager
    assert coordinator.notification_manager is notification_manager
    assert modules.attach_calls == [
        {
            "data_manager": None,
            "feeding_manager": None,
            "walk_manager": None,
            "gps_geofence_manager": gps_manager,
            "weather_health_manager": None,
            "garden_manager": None,
        }
    ]


def test_clear_runtime_managers_resets_all_attributes_and_detaches() -> None:
    """Clearing runtime managers should null every tracked attribute."""
    coordinator = _BindAwareCoordinator()
    modules = _BindAwareModulesAdapter()

    clear_runtime_managers(coordinator, modules)

    for attribute in MANAGER_ATTRIBUTES:
        assert getattr(coordinator, attribute) is None
    assert modules.detached is True


def test_dog_config_registry_normalizes_configs_and_module_cache() -> None:
    """Registry should discard invalid dogs and cache enabled module lookups."""
    registry = DogConfigRegistry([
        {"dog_id": " buddy ", "dog_name": " Buddy ", "modules": {"gps": 1}},
        {"dog_id": "buddy", "dog_name": "Duplicate"},
        {"dog_id": "skip-empty-name", "dog_name": "   "},
        "broken",
    ])

    assert registry.ids() == ["buddy"]
    assert registry.get(" buddy ") == {
        "dog_id": "buddy",
        "dog_name": "Buddy",
        "modules": {"gps": 1},
    }
    assert registry.get(None) is None
    assert registry.get_name("buddy") == "Buddy"
    assert registry.get_name("missing") is None
    assert registry.enabled_modules("buddy") == frozenset({"gps"})
    assert registry.enabled_modules("missing") == frozenset()
    assert registry.has_module("gps") is True
    assert registry.has_module("feeding") is False
    assert registry.module_count() == 1
    assert registry.empty_payload()["status"] == "unknown"


def test_dog_config_registry_get_name_returns_none_for_blank_or_non_string() -> None:
    """Dog names must be non-empty strings to be returned by the registry."""
    registry = DogConfigRegistry([
        {"dog_id": "numeric-name", "dog_name": 123},
    ])
    registry._by_id["missing-name"] = {"dog_id": "missing-name"}
    registry._ids.append("missing-name")

    assert registry.get_name("numeric-name") is None
    assert registry.get_name("missing-name") is None


def test_coordinator_metrics_resets_consecutive_errors_after_healthy_cycle() -> None:
    """A healthy cycle should reset consecutive error counters."""
    metrics = CoordinatorMetrics(consecutive_errors=3)

    success_rate, failed = metrics.record_cycle(total=4, errors=1)

    assert failed is False
    assert success_rate == pytest.approx(0.75)
    assert metrics.consecutive_errors == 0


def test_dog_config_registry_from_entry_and_interval_paths() -> None:
    """Registry helpers should validate entries and derive polling intervals."""
    registry = DogConfigRegistry.from_entry(
        type(
            "Entry",
            (),
            {"data": {CONF_DOGS: [{"dog_id": "buddy", "dog_name": "Buddy"}]}},
        )()
    )
    assert registry.ids() == ["buddy"]

    empty_registry = DogConfigRegistry([])
    assert empty_registry.calculate_update_interval({}) == 300

    gps_registry = DogConfigRegistry([
        {"dog_id": "buddy", "dog_name": "Buddy", "modules": {"gps": True}}
    ])
    assert (
        gps_registry.calculate_update_interval({
            CONF_GPS_SOURCE: "webhook",
            CONF_WEBHOOK_ENABLED: True,
            CONF_GPS_UPDATE_INTERVAL: "450",
        })
        == 450
    )
    assert gps_registry.calculate_update_interval({CONF_GPS_UPDATE_INTERVAL: 75}) == 75

    weather_registry = DogConfigRegistry([
        {"dog_id": "buddy", "dog_name": "Buddy", CONF_MODULES: {"weather": True}}
    ])
    weather_registry._modules_cache["buddy"] = frozenset({"weather"})
    # BUG FIX (Patch 11): Weather data in HA is subscription-based, not polled.
    # Interval corrected from 60 s (frequent) to 120 s (balanced).
    assert weather_registry.calculate_update_interval({}) == 120

    balanced_registry = DogConfigRegistry([
        {
            "dog_id": f"dog-{index}",
            "dog_name": f"Dog {index}",
            CONF_MODULES: {"feeding": True, "walk": True, "garden": True},
        }
        for index in range(4)
    ])
    assert balanced_registry.calculate_update_interval({}) == 120

    realtime_registry = DogConfigRegistry([
        {
            "dog_id": f"dog-{index}",
            "dog_name": f"Dog {index}",
            CONF_MODULES: {
                "feeding": True,
                "walk": True,
                "garden": True,
                "health": True,
            },
        }
        for index in range(4)
    ])
    assert realtime_registry.calculate_update_interval({}) == 30


def test_dog_config_registry_handles_string_entry_payload_variants() -> None:
    """Empty string and None payloads should normalize to an empty registry."""
    none_registry = DogConfigRegistry.from_entry(
        type("Entry", (), {"data": {CONF_DOGS: None}})()
    )
    empty_string_registry = DogConfigRegistry.from_entry(
        type("Entry", (), {"data": {CONF_DOGS: ""}})()
    )

    assert none_registry.ids() == []
    assert empty_string_registry.ids() == []


def test_dog_config_registry_enabled_modules_populates_cache_on_demand() -> None:
    """Enabled module lookups should populate the lazy cache for uncached IDs."""
    registry = DogConfigRegistry([
        {"dog_id": "buddy", "dog_name": "Buddy", CONF_MODULES: {"walk": True}},
        {"dog_id": "luna", "dog_name": 42, CONF_MODULES: {"feeding": True}},
    ])

    registry._modules_cache.pop("buddy")

    assert registry.get_name("luna") is None
    assert registry.enabled_modules("buddy") == frozenset({"walk"})
    assert registry._modules_cache["buddy"] == frozenset({"walk"})
    assert registry.calculate_update_interval({}) == 300


def test_dog_config_registry_get_name_rejects_blank_string_values() -> None:
    """Dog names containing only whitespace should be treated as missing."""
    registry = DogConfigRegistry([
        {"dog_id": "blank", "dog_name": "   ", CONF_MODULES: {"walk": True}},
    ])

    assert registry.get_name("blank") is None


def test_dog_config_registry_get_name_handles_missing_name_field() -> None:
    """Registry should return None when legacy entries omit dog_name."""
    registry = DogConfigRegistry([
        {"dog_id": "buddy", "dog_name": "Buddy", CONF_MODULES: {"walk": True}}
    ])
    registry._by_id["buddy"] = {"dog_id": "buddy"}  # type: ignore[assignment]

    assert registry.get_name("buddy") is None


@pytest.mark.parametrize(
    ("entry_data", "value", "field"),
    [
        ({"data": {CONF_DOGS: "broken"}}, None, "dogs_config"),
        (None, True, "gps_update_interval"),
        (None, " ", "gps_update_interval"),
        (None, 1.5, "gps_update_interval"),
        (None, 0, "gps_update_interval"),
        (None, None, "update_interval"),
        (None, 0, "update_interval"),
    ],
)
def test_dog_config_registry_validation_errors(
    entry_data: dict[str, object] | None,
    value: object,
    field: str,
) -> None:
    """Registry validators should fail closed for malformed interval inputs."""
    with pytest.raises(ValidationError) as err:
        if entry_data is not None:
            DogConfigRegistry.from_entry(type("Entry", (), entry_data)())
        elif field == "gps_update_interval":
            DogConfigRegistry._validate_gps_interval(value)
        else:
            DogConfigRegistry._enforce_polling_limits(value)  # type: ignore[arg-type]

    assert err.value.field == field


def test_coordinator_metrics_zero_defaults_without_timings_or_updates() -> None:
    """Fresh metrics should report optimistic defaults before any updates."""
    metrics = CoordinatorMetrics()

    assert metrics.success_rate_percent == 100.0
    assert metrics.average_statistics_runtime_ms == 0.0
    assert metrics.average_visitor_runtime_ms == 0.0


def test_coordinator_metrics_cover_cycle_and_statistics_paths() -> None:
    """Coordinator metrics should track timing, failures, and repair telemetry."""
    metrics = CoordinatorMetrics()

    metrics.start_cycle()
    assert metrics.record_cycle(total=0, errors=0) == (1.0, False)
    assert metrics.record_cycle(total=2, errors=2) == (0.0, True)
    assert metrics.record_cycle(total=4, errors=3) == (0.25, False)
    assert metrics.record_cycle(total=4, errors=2) == (0.5, False)
    metrics.reset_consecutive()
    metrics.record_statistics_timing(0.05)
    metrics.record_statistics_timing(-1.0)
    metrics.record_visitor_timing(0.02)
    metrics.record_visitor_timing(-1.0)

    repair_summary = CacheRepairAggregate(
        total_caches=2,
        anomaly_count=1,
        severity="warning",
        generated_at="2026-01-01T00:00:00+00:00",
        issues=[{"cache": "weather"}],
    )
    stats = metrics.update_statistics(
        cache_entries=5,
        cache_hit_rate=87.654,
        last_update="now",
        interval=timedelta(seconds=90),
        repair_summary=repair_summary,
    )
    runtime_stats = metrics.runtime_statistics(
        cache_metrics=ModuleCacheMetrics(hits=9, misses=1, entries=4),
        total_dogs=3,
        last_update="now",
        interval=timedelta(seconds=30),
        repair_summary=repair_summary,
    )

    assert metrics.failed_cycles == 1
    assert metrics.successful_cycles == 0
    assert metrics.success_rate_percent == 0.0
    assert metrics.average_statistics_runtime_ms == 25.0
    assert metrics.average_visitor_runtime_ms == 10.0
    assert stats["repairs"]["issues"] == 1
    assert stats["performance_metrics"]["cache_hit_rate"] == 87.65
    assert runtime_stats["repairs"]["severity"] == "warning"
    assert runtime_stats["cache_performance"]["hit_rate"] == 90.0


def test_coordinator_metrics_record_cycle_resets_consecutive_errors() -> None:
    """Healthy cycles should clear consecutive error counters."""
    metrics = CoordinatorMetrics(consecutive_errors=3)

    assert metrics.record_cycle(total=4, errors=1) == (0.75, False)
    assert metrics.consecutive_errors == 0
