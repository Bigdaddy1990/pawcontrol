"""Unit tests for cache repair helper utilities."""

from dataclasses import dataclass
import sys

from custom_components.pawcontrol.coordinator_support import (
    MANAGER_ATTRIBUTES,
    _build_repair_telemetry,
    bind_runtime_managers,
    clear_runtime_managers,
    ensure_cache_repair_aggregate,
)
from custom_components.pawcontrol.types import (
    CacheRepairAggregate,
    CoordinatorRuntimeManagers,
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
