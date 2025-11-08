"""Unit tests for the PawControl services helpers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from custom_components.pawcontrol import compat, services
from custom_components.pawcontrol.const import (
    EVENT_FEEDING_COMPLIANCE_CHECKED,
    SERVICE_CHECK_FEEDING_COMPLIANCE,
    SERVICE_DAILY_RESET,
)
from custom_components.pawcontrol.coordinator_tasks import default_rejection_metrics
from custom_components.pawcontrol.garden_manager import GardenActivityInputPayload
from custom_components.pawcontrol.notifications import (
    NotificationChannel,
    NotificationPriority,
    NotificationType,
)
from custom_components.pawcontrol.types import (
    CacheDiagnosticsSnapshot,
    CacheRepairAggregate,
    CoordinatorRuntimeManagers,
)
from custom_components.pawcontrol.utils import async_call_hass_service_if_available

try:  # pragma: no cover - runtime fallback for stubbed environments
    from homeassistant.core import Context
except ImportError:  # pragma: no cover - ensure stubs are available for tests
    from tests.helpers.homeassistant_test_stubs import install_homeassistant_stubs

    install_homeassistant_stubs()
    from homeassistant.core import Context


def test_service_validation_error_uses_compat_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_service_validation_error`` should emit the compat-managed alias."""

    class SentinelServiceValidationError(Exception):
        pass

    monkeypatch.setattr(
        compat, "ServiceValidationError", SentinelServiceValidationError
    )
    monkeypatch.setattr(compat, "ensure_homeassistant_exception_symbols", lambda: None)

    error = services._service_validation_error("boom")

    assert isinstance(error, SentinelServiceValidationError)
    assert str(error) == "boom"


def test_service_validation_error_rejects_blank_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank messages should be rejected to preserve telemetry detail."""

    class SentinelServiceValidationError(Exception):
        pass

    monkeypatch.setattr(
        compat, "ServiceValidationError", SentinelServiceValidationError
    )
    monkeypatch.setattr(compat, "ensure_homeassistant_exception_symbols", lambda: None)

    with pytest.raises(AssertionError):
        services._service_validation_error("   ")


def test_service_validation_error_trims_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Messages should be trimmed before instantiating the compat alias."""

    class SentinelServiceValidationError(Exception):
        pass

    monkeypatch.setattr(
        compat, "ServiceValidationError", SentinelServiceValidationError
    )
    monkeypatch.setattr(compat, "ensure_homeassistant_exception_symbols", lambda: None)

    error = services._service_validation_error("  trimmed  ")

    assert isinstance(error, SentinelServiceValidationError)
    assert str(error) == "trimmed"


def test_record_service_result_merges_rejection_metrics() -> None:
    """Service telemetry should reuse the rejection metrics helper."""

    resilience_summary = {
        "total_breakers": 1,
        "states": {
            "closed": 0,
            "open": 1,
            "half_open": 0,
            "unknown": 0,
            "other": 0,
        },
        "failure_count": 2,
        "success_count": 8,
        "total_calls": 10,
        "total_failures": 2,
        "total_successes": 8,
        "rejected_call_count": 2,
        "last_failure_time": 1_700_000_000.0,
        "last_state_change": 1_700_000_001.0,
        "last_success_time": 1_700_000_002.0,
        "last_rejection_time": 1_700_000_003.0,
        "recovery_latency": 0.5,
        "recovery_breaker_id": "api",
        "recovery_breaker_name": "API Gateway",
        "last_rejection_breaker_id": "api",
        "last_rejection_breaker_name": "API Gateway",
        "rejection_rate": 0.2,
        "open_breaker_count": 1,
        "half_open_breaker_count": 0,
        "unknown_breaker_count": 0,
        "open_breakers": ["api"],
        "open_breaker_ids": ["api"],
        "half_open_breakers": [],
        "half_open_breaker_ids": [],
        "unknown_breakers": [],
        "unknown_breaker_ids": [],
        "rejection_breaker_count": 1,
        "rejection_breakers": ["api"],
        "rejection_breaker_ids": ["api"],
    }

    runtime_data = SimpleNamespace(
        performance_stats={"resilience_summary": resilience_summary}
    )

    services._record_service_result(
        runtime_data,
        service="notify.test",
        status="error",
    )

    metrics = runtime_data.performance_stats["rejection_metrics"]
    assert metrics["rejected_call_count"] == 2
    assert metrics["rejection_breaker_count"] == 1
    assert metrics["open_breakers"] == ["api"]

    last_result = runtime_data.performance_stats["last_service_result"]
    resilience_details = last_result["details"]["resilience"]
    assert resilience_details["rejected_call_count"] == 2
    assert resilience_details["rejection_breaker_count"] == 1

    diagnostics_payload = last_result["diagnostics"]
    assert diagnostics_payload["rejection_metrics"]["open_breakers"] == ["api"]
    assert runtime_data.performance_stats["service_results"][-1] is last_result


def test_record_service_result_defaults_rejection_metrics_without_breakers() -> None:
    """Circuit recovery snapshots should keep rejection metrics at defaults."""

    resilience_summary = {
        "rejected_call_count": 0,
        "rejection_breaker_count": 0,
        "rejection_rate": 0.0,
        "last_rejection_time": None,
        "last_rejection_breaker_id": None,
        "last_rejection_breaker_name": None,
        "open_breaker_count": 0,
        "half_open_breaker_count": 0,
        "unknown_breaker_count": 0,
        "open_breakers": [],
        "open_breaker_ids": [],
        "half_open_breakers": [],
        "half_open_breaker_ids": [],
        "unknown_breakers": [],
        "unknown_breaker_ids": [],
        "rejection_breaker_ids": [],
        "rejection_breakers": [],
    }

    runtime_data = SimpleNamespace(
        performance_stats={"resilience_summary": resilience_summary}
    )

    services._record_service_result(
        runtime_data,
        service="notify.test",
        status="success",
    )

    defaults = default_rejection_metrics()

    metrics = runtime_data.performance_stats["rejection_metrics"]
    assert metrics == defaults

    last_result = runtime_data.performance_stats["last_service_result"]
    assert "details" not in last_result or "resilience" not in last_result["details"]

    diagnostics_payload = last_result["diagnostics"]
    assert diagnostics_payload["rejection_metrics"] == defaults


class _DummyCoordinator:
    """Coordinator stub that records refresh requests."""

    def __init__(
        self,
        *,
        fail: bool = False,
        error: Exception | None = None,
        options: dict[str, object] | None = None,
    ) -> None:
        self.refresh_called = False
        self._fail = fail
        self._error = error or RuntimeError("refresh-failed")
        self.config_entry = SimpleNamespace(options=options or {})

    async def async_request_refresh(self) -> None:
        if self._fail:
            raise self._error
        self.refresh_called = True


class _DummyWalkManager:
    """Walk manager stub recording cleanup calls."""

    def __init__(self) -> None:
        self.cleaned = False

    async def async_cleanup(self) -> None:
        self.cleaned = True


class _DummyNotificationManager:
    """Notification manager stub recording cleanup calls."""

    def __init__(self) -> None:
        self.cleaned = False
        self.cleaned_count = 2

    async def async_cleanup_expired_notifications(self) -> int:
        self.cleaned = True
        return self.cleaned_count


class _BusStub:
    """Capture Home Assistant bus events for verification."""

    def __init__(self) -> None:
        self.fired: list[dict[str, object]] = []

    async def async_fire(
        self,
        event_type: str,
        event_data: object | None = None,
        **kwargs: object,
    ) -> None:
        self.fired.append(
            {
                "event_type": event_type,
                "event_data": event_data,
                "kwargs": dict(kwargs),
            }
        )


class _DummyDataManager:
    """Expose deterministic cache diagnostics payloads for tests."""

    def __init__(
        self,
        payload: dict[str, dict[str, object]],
        summary: CacheRepairAggregate | None = None,
    ) -> None:
        self._payload = payload
        if summary is not None and not isinstance(summary, CacheRepairAggregate):
            raise TypeError("summary must be CacheRepairAggregate or None")
        self._summary = summary

    def cache_snapshots(self) -> dict[str, dict[str, object]]:
        return self._payload

    def cache_repair_summary(
        self, snapshots: dict[str, object] | None = None
    ) -> CacheRepairAggregate | None:
        if snapshots is not None:
            self._last_snapshots = snapshots
            normalised: dict[str, object] = {}
            for key, payload in snapshots.items():
                if hasattr(payload, "to_mapping"):
                    try:
                        candidate = payload.to_mapping()  # type: ignore[call-arg]
                    except Exception:
                        candidate = None
                    else:
                        if isinstance(candidate, Mapping):
                            normalised[key] = dict(candidate)
                            continue
                if isinstance(payload, Mapping):
                    normalised[key] = dict(payload)
                else:
                    normalised[key] = payload
            self._normalised_payload = normalised
            assert normalised == self._payload
        return self._summary


class _FeedingManagerStub:
    """Provide deterministic behaviour for health snack telemetry tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_with: Exception | None = None
        self.compliance_calls: list[dict[str, object]] = []
        self.compliance_result: dict[str, object] = {
            "status": "no_data",
            "message": "No feeding data available",
        }
        self.compliance_error: Exception | None = None

    async def async_add_health_snack(
        self,
        *,
        dog_id: str,
        snack_type: str,
        amount: float,
        health_benefit: object | None,
        notes: object | None,
    ) -> None:
        if self.fail_with:
            raise self.fail_with

        self.calls.append(
            {
                "dog_id": dog_id,
                "snack_type": snack_type,
                "amount": amount,
                "health_benefit": health_benefit,
                "notes": notes,
            }
        )

    async def async_check_feeding_compliance(
        self,
        *,
        dog_id: str,
        days_to_check: int,
        notify_on_issues: bool,
    ) -> dict[str, object]:
        if self.compliance_error:
            raise self.compliance_error

        self.compliance_calls.append(
            {
                "dog_id": dog_id,
                "days_to_check": days_to_check,
                "notify_on_issues": notify_on_issues,
            }
        )
        return self.compliance_result


class _DataManagerStub:
    """Simulate grooming and poop logging calls for telemetry coverage."""

    def __init__(self) -> None:
        self.poop_calls: list[dict[str, object]] = []
        self.groom_calls: list[dict[str, object]] = []
        self.fail_log: Exception | None = None
        self.fail_groom: Exception | None = None
        self.next_session_id = "groom-session-1"

    async def async_log_poop_data(
        self, *, dog_id: str, poop_data: dict[str, object]
    ) -> None:
        if self.fail_log:
            raise self.fail_log

        self.poop_calls.append({"dog_id": dog_id, "poop_data": dict(poop_data)})

    async def async_start_grooming_session(
        self, *, dog_id: str, grooming_data: dict[str, object]
    ) -> str:
        if self.fail_groom:
            raise self.fail_groom

        self.groom_calls.append(
            {"dog_id": dog_id, "grooming_data": dict(grooming_data)}
        )
        return self.next_session_id


class _GardenManagerStub:
    """Stub the garden manager API for service telemetry assertions."""

    def __init__(self) -> None:
        self.start_calls: list[dict[str, object]] = []
        self.end_calls: list[dict[str, object]] = []
        self.activity_calls: list[dict[str, object]] = []
        self.confirm_calls: list[dict[str, object]] = []
        self.pending_confirmation = True
        self.fail_start: Exception | None = None
        self.fail_end: Exception | None = None
        self.fail_activity: Exception | None = None
        self.fail_confirm: Exception | None = None
        self.activity_success = True
        self.next_session_id = "garden-session-1"
        self.next_end_session: object | None = SimpleNamespace(
            dog_name="Buddy",
            duration_minutes=12.5,
            activities=[{"type": "play"}],
            poop_count=1,
        )

    async def async_start_garden_session(
        self,
        *,
        dog_id: str,
        dog_name: str,
        detection_method: str,
        weather_conditions: object | None,
        temperature: object | None,
    ) -> str:
        if self.fail_start:
            raise self.fail_start

        self.start_calls.append(
            {
                "dog_id": dog_id,
                "dog_name": dog_name,
                "detection_method": detection_method,
                "weather_conditions": weather_conditions,
                "temperature": temperature,
            }
        )
        return self.next_session_id

    async def async_end_garden_session(
        self,
        *,
        dog_id: str,
        notes: object | None,
        activities: Sequence[GardenActivityInputPayload] | None,
    ) -> object | None:
        if self.fail_end:
            raise self.fail_end

        self.end_calls.append(
            {"dog_id": dog_id, "notes": notes, "activities": activities}
        )
        return self.next_end_session

    async def async_add_activity(
        self,
        *,
        dog_id: str,
        activity_type: str,
        duration_seconds: object | None,
        location: object | None,
        notes: object | None,
        confirmed: bool,
    ) -> bool:
        if self.fail_activity:
            raise self.fail_activity

        self.activity_calls.append(
            {
                "dog_id": dog_id,
                "activity_type": activity_type,
                "duration_seconds": duration_seconds,
                "location": location,
                "notes": notes,
                "confirmed": confirmed,
            }
        )
        return self.activity_success

    def has_pending_confirmation(self, dog_id: str) -> bool:
        return self.pending_confirmation

    async def async_handle_poop_confirmation(
        self,
        *,
        dog_id: str,
        confirmed: bool,
        quality: object | None,
        size: object | None,
        location: object | None,
    ) -> None:
        if self.fail_confirm:
            raise self.fail_confirm

        self.confirm_calls.append(
            {
                "dog_id": dog_id,
                "confirmed": confirmed,
                "quality": quality,
                "size": size,
                "location": location,
            }
        )


class _ServiceRegistryStub:
    """Record service registrations during setup."""

    def __init__(self) -> None:
        self.handlers: dict[str, Callable[..., Awaitable[None]]] = {}

    def async_register(
        self,
        domain: str,
        service: str,
        handler: Callable[..., Awaitable[None]],
        schema: object | None = None,
    ) -> None:
        self.handlers[service] = handler


class _ResolverStub:
    """Minimal coordinator resolver for service tests."""

    def __init__(self, coordinator: object) -> None:
        self._coordinator = coordinator

    def invalidate(
        self, *, entry_id: str | None = None
    ) -> None:  # pragma: no cover - noop
        return None

    def resolve(self) -> object:
        return self._coordinator


class _NotificationManagerStub:
    """Provide deterministic notification behaviour for telemetry tests."""

    def __init__(self) -> None:
        self.fail_send = False
        self.fail_ack = False
        self.ack_exists = True
        self.sent: list[dict[str, object]] = []
        self.compliance_calls: list[dict[str, object]] = []
        self.fail_compliance = False

    async def async_send_notification(self, **kwargs: object) -> str:
        if self.fail_send:
            raise services.HomeAssistantError("send failed")
        notification_type = kwargs.get("notification_type")
        assert isinstance(notification_type, NotificationType)

        priority = kwargs.get("priority")
        if priority is not None:
            assert isinstance(priority, NotificationPriority)

        force_channels = kwargs.get("force_channels")
        if force_channels is not None:
            assert isinstance(force_channels, list)
            assert all(
                isinstance(channel, NotificationChannel) for channel in force_channels
            )
        self.sent.append(kwargs)
        return "notif-1"

    async def async_send_feeding_compliance_summary(
        self,
        *,
        dog_id: str,
        dog_name: str | None,
        compliance: dict[str, object],
    ) -> str | None:
        if self.fail_compliance:
            raise services.HomeAssistantError("compliance failed")

        status = compliance.get("status")
        if status == "completed":
            score = float(compliance.get("compliance_score", 100))
            has_issues = bool(
                compliance.get("days_with_issues")
                or compliance.get("compliance_issues")
                or compliance.get("missed_meals")
                or score < 100
            )
            if not has_issues:
                return None

        self.compliance_calls.append(
            {
                "dog_id": dog_id,
                "dog_name": dog_name,
                "compliance": compliance,
            }
        )
        return "compliance-1"

    async def async_acknowledge_notification(self, notification_id: str) -> bool:
        if self.fail_ack:
            raise services.HomeAssistantError("ack failed")
        return self.ack_exists

    async def async_cleanup_expired_notifications(self) -> None:  # pragma: no cover
        return None


class _GuardSkippingNotificationManager:
    """Notification manager stub that exercises guard skip telemetry."""

    def __init__(self) -> None:
        self.calls = 0

    async def async_send_notification(self, **kwargs: object) -> str:
        self.calls += 1
        await async_call_hass_service_if_available(
            None,
            "persistent_notification",
            "create",
            {"message": "guard"},
            description="guard-test",
            logger=logging.getLogger(__name__),
        )
        return f"guard-{self.calls}"


class _GPSManagerStub:
    """Emulate GPS configuration calls for automation service tests."""

    def __init__(self) -> None:
        self.fail_configure = False
        self.fail_safe_zone = False
        self.last_config: dict[str, object] | None = None
        self.safe_zone: dict[str, object] | None = None

    async def async_configure_dog_gps(
        self, *, dog_id: str, config: dict[str, object]
    ) -> None:
        if self.fail_configure:
            raise services.HomeAssistantError("configure failed")
        self.last_config = {"dog_id": dog_id, "config": config}

    async def async_setup_safe_zone(
        self,
        *,
        dog_id: str,
        center_lat: float,
        center_lon: float,
        radius_meters: float,
        notifications_enabled: bool,
    ) -> None:
        if self.fail_safe_zone:
            raise services.HomeAssistantError("safe zone failed")
        self.safe_zone = {
            "dog_id": dog_id,
            "center_lat": center_lat,
            "center_lon": center_lon,
            "radius": radius_meters,
            "notifications": notifications_enabled,
        }


class _CoordinatorStub:
    """Coordinator providing managers required for service telemetry tests."""

    def __init__(
        self,
        hass: object,
        *,
        notification_manager: _NotificationManagerStub | None = None,
        gps_manager: _GPSManagerStub | None = None,
        feeding_manager: _FeedingManagerStub | None = None,
        data_manager: _DataManagerStub | None = None,
        garden_manager: _GardenManagerStub | None = None,
    ) -> None:
        self.hass = hass
        self.config_entry = SimpleNamespace(entry_id="entry")
        self.notification_manager = notification_manager
        self.gps_geofence_manager = gps_manager
        self.feeding_manager = feeding_manager
        self.data_manager = data_manager
        self.garden_manager = garden_manager
        self.refresh_called = False
        self._dogs: dict[str, dict[str, object]] = {}
        self.runtime_managers = CoordinatorRuntimeManagers(
            data_manager=data_manager,
            feeding_manager=feeding_manager,
            notification_manager=notification_manager,
            gps_geofence_manager=gps_manager,
            garden_manager=garden_manager,
        )

    async def async_request_refresh(self) -> None:
        self.refresh_called = True

    def register_dog(self, dog_id: str, *, name: str | None = None) -> None:
        config = self._dogs.setdefault(dog_id, {})
        if name is not None:
            config.setdefault("name", name)

    def get_dog_config(self, dog_id: str) -> dict[str, object] | None:
        return self._dogs.get(dog_id)

    def get_configured_dog_ids(self) -> list[str]:
        return list(self._dogs.keys())

    def get_configured_dog_name(self, dog_id: str) -> str | None:
        config = self._dogs.get(dog_id)
        if not config:
            return None
        name = config.get("name")
        return name if isinstance(name, str) else None


async def _setup_service_environment(
    monkeypatch: pytest.MonkeyPatch,
    coordinator: _CoordinatorStub,
    runtime_data: SimpleNamespace,
) -> SimpleNamespace:
    """Register PawControl services against a stub Home Assistant instance."""

    hass = SimpleNamespace(
        services=_ServiceRegistryStub(),
        data={},
        config=SimpleNamespace(latitude=1.0, longitude=2.0, language="en"),
        bus=_BusStub(),
    )
    hass.config_entries = SimpleNamespace(async_entries=lambda domain: [])
    coordinator.hass = hass

    resolver = _ResolverStub(coordinator)
    monkeypatch.setattr(
        services, "_coordinator_resolver", lambda hass_instance: resolver
    )
    monkeypatch.setattr(
        services, "async_dispatcher_connect", lambda *args, **kwargs: lambda: None
    )
    monkeypatch.setattr(
        services, "async_track_time_change", lambda *args, **kwargs: lambda: None
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda hass_instance, entry: runtime_data
    )

    await services.async_setup_services(hass)  # type: ignore[arg-type]
    return hass


@pytest.mark.unit
def test_capture_cache_diagnostics_returns_snapshot() -> None:
    """Helper should normalise diagnostics payloads provided by the data manager."""

    payload = {
        "coordinator_modules": {
            "stats": {"entries": 3, "hits": 5, "misses": 1},
            "diagnostics": {"per_module": {"feeding": {"hits": 2, "misses": 0}}},
        }
    }

    summary_payload = {
        "total_caches": 1,
        "anomaly_count": 0,
        "severity": "info",
        "generated_at": "2024-01-01T00:00:00+00:00",
        "totals": {
            "entries": 3,
            "hits": 5,
            "misses": 1,
            "expired_entries": 0,
            "expired_via_override": 0,
            "pending_expired_entries": 0,
            "pending_override_candidates": 0,
            "active_override_flags": 0,
        },
    }

    summary = CacheRepairAggregate.from_mapping(summary_payload)

    runtime_data = SimpleNamespace(data_manager=_DummyDataManager(payload, summary))

    diagnostics = services._capture_cache_diagnostics(runtime_data)

    assert diagnostics is not None
    snapshots = diagnostics["snapshots"]
    assert "coordinator_modules" in snapshots
    coordinator_snapshot = snapshots["coordinator_modules"]
    assert hasattr(coordinator_snapshot, "to_mapping")
    assert coordinator_snapshot.to_mapping() == payload["coordinator_modules"]

    summary_obj = diagnostics.get("repair_summary")
    assert summary_obj is not None
    assert hasattr(summary_obj, "to_mapping")
    assert summary_obj.to_mapping() == summary_payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_perform_daily_reset_records_cache_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Daily reset should persist the latest cache diagnostics snapshot."""

    payload = {
        "coordinator_modules": {
            "stats": {"entries": 1, "hits": 1, "misses": 0, "hit_rate": 100.0},
            "diagnostics": {"per_module": {"walk": {"hits": 1, "misses": 0}}},
        }
    }

    summary_payload = {
        "total_caches": 1,
        "anomaly_count": 0,
        "severity": "info",
        "generated_at": "2024-01-01T00:00:00+00:00",
        "totals": {
            "entries": 1,
            "hits": 1,
            "misses": 0,
            "expired_entries": 0,
            "expired_via_override": 0,
            "pending_expired_entries": 0,
            "pending_override_candidates": 0,
            "active_override_flags": 0,
            "overall_hit_rate": 100.0,
        },
    }

    summary = CacheRepairAggregate.from_mapping(summary_payload)

    telemetry = {
        "requested_profile": "advanced",
        "previous_profile": "standard",
        "dogs_count": 2,
        "estimated_entities": 18,
        "timestamp": "2024-02-01T00:00:00+00:00",
        "version": 1,
        "compatibility_warnings": ["gps_disabled"],
        "health_summary": {"healthy": True, "issues": [], "warnings": []},
    }

    coordinator = _DummyCoordinator(options={"reconfigure_telemetry": telemetry})
    runtime_data = SimpleNamespace(
        coordinator=coordinator,
        walk_manager=_DummyWalkManager(),
        notification_manager=_DummyNotificationManager(),
        data_manager=_DummyDataManager(payload, summary),
        performance_stats={},
    )

    monkeypatch.setattr(
        services,
        "get_runtime_data",
        lambda hass, entry: runtime_data,
    )

    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="test-entry")

    await services._perform_daily_reset(hass, entry)

    assert coordinator.refresh_called
    assert runtime_data.walk_manager.cleaned
    assert runtime_data.notification_manager.cleaned
    buckets = runtime_data.performance_stats["performance_buckets"]
    assert "daily_reset_metrics" in buckets
    bucket_snapshot = buckets["daily_reset_metrics"]
    assert bucket_snapshot["runs"] == 1
    assert bucket_snapshot["failures"] == 0
    assert bucket_snapshot["durations_ms"]
    assert runtime_data.performance_stats["daily_resets"] == 1
    last_cache_capture = runtime_data.performance_stats["last_cache_diagnostics"]
    snapshots = last_cache_capture["snapshots"]
    assert hasattr(snapshots["coordinator_modules"], "to_mapping")
    assert (
        snapshots["coordinator_modules"].to_mapping() == payload["coordinator_modules"]
    )
    summary_obj = last_cache_capture.get("repair_summary")
    assert summary_obj is not None
    assert hasattr(summary_obj, "to_mapping")
    assert summary_obj.to_mapping() == summary_payload
    assert runtime_data.performance_stats["reconfigure_summary"]["warning_count"] == 1
    last_result = runtime_data.performance_stats["last_service_result"]
    assert last_result["service"] == SERVICE_DAILY_RESET
    assert last_result["status"] == "success"
    diagnostics = last_result.get("diagnostics")
    assert diagnostics is not None
    cache_capture = diagnostics.get("cache")
    assert cache_capture is not None
    snapshots = cache_capture["snapshots"]
    assert hasattr(snapshots["coordinator_modules"], "to_mapping")
    assert (
        snapshots["coordinator_modules"].to_mapping() == payload["coordinator_modules"]
    )
    summary_obj = cache_capture.get("repair_summary")
    assert summary_obj is not None
    assert hasattr(summary_obj, "to_mapping")
    assert summary_obj.to_mapping() == summary_payload
    metadata = diagnostics.get("metadata")
    assert metadata is not None
    assert metadata["refresh_requested"] is True
    assert metadata["reconfigure"]["requested_profile"] == "advanced"
    assert metadata["reconfigure"]["warning_count"] == 1
    assert metadata["reconfigure"]["merge_note_count"] == 0
    assert metadata["reconfigure"]["merge_notes"] == []
    assert last_result.get("details") == {
        "walk_cleanup_performed": True,
        "notifications_cleaned": 2,
        "cache_snapshot": True,
    }

    service_results = runtime_data.performance_stats["service_results"]
    assert service_results[-1] is last_result

    maintenance_results = runtime_data.performance_stats["maintenance_results"]
    assert maintenance_results
    maintenance_last = runtime_data.performance_stats["last_maintenance_result"]
    assert maintenance_last in maintenance_results
    assert maintenance_last["task"] == "daily_reset"
    assert maintenance_last["status"] == "success"
    assert maintenance_last["details"] == {
        "walk_cleanup_performed": True,
        "notifications_cleaned": 2,
        "cache_snapshot": True,
    }
    cache_metrics = maintenance_last["diagnostics"]["cache"]
    assert hasattr(cache_metrics["snapshots"]["coordinator_modules"], "to_mapping")
    assert (
        cache_metrics["snapshots"]["coordinator_modules"].to_mapping()
        == payload["coordinator_modules"]
    )
    repair_summary = cache_metrics.get("repair_summary")
    assert repair_summary is not None
    assert hasattr(repair_summary, "to_mapping")
    assert repair_summary.to_mapping() == summary_payload
    maintenance_metadata = maintenance_last["diagnostics"]["metadata"]
    assert maintenance_metadata["refresh_requested"] is True
    assert maintenance_metadata["reconfigure"]["requested_profile"] == "advanced"
    assert maintenance_metadata["reconfigure"]["merge_note_count"] == 0
    assert maintenance_metadata["reconfigure"]["merge_notes"] == []
    assert isinstance(maintenance_last["recorded_at"], str)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_perform_daily_reset_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Daily reset should capture failures in the service result log."""

    telemetry = {
        "requested_profile": "advanced",
        "previous_profile": "standard",
        "dogs_count": 2,
        "estimated_entities": 18,
        "timestamp": "2024-02-01T00:00:00+00:00",
        "version": 1,
        "compatibility_warnings": ["gps_disabled"],
        "health_summary": {"healthy": True, "issues": [], "warnings": []},
    }

    runtime_data = SimpleNamespace(
        coordinator=_DummyCoordinator(
            fail=True,
            error=RuntimeError("coordinator unavailable"),
            options={"reconfigure_telemetry": telemetry},
        ),
        walk_manager=_DummyWalkManager(),
        notification_manager=_DummyNotificationManager(),
        data_manager=_DummyDataManager({}, None),
        performance_stats={},
    )

    monkeypatch.setattr(
        services,
        "get_runtime_data",
        lambda hass, entry: runtime_data,
    )

    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="test-entry")

    with pytest.raises(RuntimeError, match="coordinator unavailable"):
        await services._perform_daily_reset(hass, entry)

    last_result = runtime_data.performance_stats["last_service_result"]
    assert last_result["service"] == SERVICE_DAILY_RESET
    assert last_result["status"] == "error"
    assert "coordinator unavailable" in last_result.get("message", "")
    assert last_result.get("details") == {
        "walk_cleanup_performed": True,
        "notifications_cleaned": 2,
        "cache_snapshot": False,
    }
    metadata = last_result.get("diagnostics", {}).get("metadata")
    assert metadata is not None
    assert metadata["refresh_requested"] is False
    assert metadata["reconfigure"]["requested_profile"] == "advanced"
    assert runtime_data.performance_stats.get("daily_resets", 0) == 0

    maintenance_last = runtime_data.performance_stats["last_maintenance_result"]
    assert maintenance_last["task"] == "daily_reset"
    assert maintenance_last["status"] == "error"
    assert maintenance_last["details"] == {
        "walk_cleanup_performed": True,
        "notifications_cleaned": 2,
        "cache_snapshot": False,
    }
    failure_metadata = maintenance_last["diagnostics"]["metadata"]
    assert failure_metadata["refresh_requested"] is False
    assert failure_metadata["reconfigure"]["requested_profile"] == "advanced"
    assert (
        runtime_data.performance_stats["reconfigure_summary"]["requested_profile"]
        == "advanced"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Notification services should record successful telemetry snapshots."""

    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(), notification_manager=notification_manager
    )
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]

    await handler(
        SimpleNamespace(
            data={
                "title": "Status",
                "message": "All good",
                "notification_type": "system_info",
                "priority": "normal",
                "channels": ["mobile"],
                "expires_in_hours": 2,
            }
        )
    )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_SEND_NOTIFICATION
    assert result["status"] == "success"
    details = result.get("details")
    assert details is not None
    assert details["priority"] == "normal"
    assert runtime_data.performance_stats["service_results"][-1] is result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_recovers_from_invalid_payloads(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Notification service should fall back to defaults for invalid inputs."""

    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(), notification_manager=notification_manager
    )
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]

    with caplog.at_level(logging.WARNING):
        await handler(
            SimpleNamespace(
                data={
                    "title": "Status",
                    "message": "All good",
                    "notification_type": "custom_type",
                    "priority": "critical",
                    "channels": ["mobile", "pager"],
                }
            )
        )

    assert "Unknown notification type" in caplog.text
    assert "Unknown notification priority" in caplog.text
    assert "Ignoring unsupported notification channel" in caplog.text

    assert notification_manager.sent, "notification manager should receive a call"
    sent_payload = notification_manager.sent[-1]
    assert sent_payload["notification_type"] is NotificationType.SYSTEM_INFO
    assert sent_payload["priority"] is NotificationPriority.NORMAL
    force_channels = sent_payload["force_channels"]
    assert isinstance(force_channels, list)
    assert force_channels == [NotificationChannel.MOBILE]

    result = runtime_data.performance_stats["last_service_result"]
    details = result.get("details")
    assert details is not None
    assert details["notification_type"] == NotificationType.SYSTEM_INFO.value
    assert details["priority"] == NotificationPriority.NORMAL.value
    assert details["channels"] == [NotificationChannel.MOBILE.value]
    assert details["ignored_channels"] == ["pager"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_records_guard_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard skips should be captured in service telemetry summaries."""

    notification_manager = _GuardSkippingNotificationManager()
    coordinator = _CoordinatorStub(
        SimpleNamespace(), notification_manager=notification_manager
    )
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]

    await handler(
        SimpleNamespace(
            data={
                "title": "Alert",
                "message": "Guard telemetry",
            }
        )
    )

    result = runtime_data.performance_stats["last_service_result"]
    guard_summary = result.get("guard")
    assert guard_summary is not None
    assert guard_summary["executed"] == 0
    assert guard_summary["skipped"] == 1
    assert guard_summary["reasons"]["missing_instance"] == 1
    guard_results = guard_summary["results"]
    assert isinstance(guard_results, list)
    assert guard_results and guard_results[-1]["executed"] is False

    guard_metrics = runtime_data.performance_stats["service_guard_metrics"]
    assert guard_metrics["executed"] == 0
    assert guard_metrics["skipped"] == 1
    assert guard_metrics["reasons"]["missing_instance"] == 1
    last_results = guard_metrics["last_results"]
    assert isinstance(last_results, list)
    assert last_results and last_results[-1]["description"] == "guard-test"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_accepts_enum_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Notification service should accept enum values directly."""

    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(), notification_manager=notification_manager
    )
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]

    await handler(
        SimpleNamespace(
            data={
                "title": "Status",
                "message": "All good",
                "notification_type": NotificationType.SYSTEM_INFO,
                "priority": NotificationPriority.HIGH,
                "channels": [NotificationChannel.MOBILE, "discord"],
            }
        )
    )

    sent_payload = notification_manager.sent[-1]
    assert sent_payload["notification_type"] is NotificationType.SYSTEM_INFO
    assert sent_payload["priority"] is NotificationPriority.HIGH
    force_channels = sent_payload["force_channels"]
    assert force_channels == [NotificationChannel.MOBILE, NotificationChannel.DISCORD]

    details = runtime_data.performance_stats["last_service_result"]["details"]
    assert details is not None
    assert details["notification_type"] == NotificationType.SYSTEM_INFO.value
    assert details["priority"] == NotificationPriority.HIGH.value
    assert details["channels"] == [
        NotificationChannel.MOBILE.value,
        NotificationChannel.DISCORD.value,
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_accepts_string_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single string channel inputs should normalise to enum lists."""

    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(), notification_manager=notification_manager
    )
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]

    await handler(
        SimpleNamespace(
            data={
                "title": "Update",
                "message": "Telemetry refreshed",
                "notification_type": NotificationType.SYSTEM_INFO,
                "priority": NotificationPriority.NORMAL,
                "channels": "mobile",
            }
        )
    )

    sent_payload = notification_manager.sent[-1]
    assert sent_payload["force_channels"] == [NotificationChannel.MOBILE]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_deduplicates_channels(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Duplicate channel inputs should collapse to a single entry."""

    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(), notification_manager=notification_manager
    )
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]

    with caplog.at_level(logging.WARNING):
        await handler(
            SimpleNamespace(
                data={
                    "title": "Alert",
                    "message": "Duplicates trimmed",
                    "notification_type": NotificationType.SYSTEM_INFO,
                    "priority": NotificationPriority.NORMAL,
                    "channels": [
                        "mobile",
                        NotificationChannel.MOBILE,
                        "discord",
                        "pager",
                        "discord",
                    ],
                }
            )
        )

    sent_payload = notification_manager.sent[-1]
    assert sent_payload["force_channels"] == [
        NotificationChannel.MOBILE,
        NotificationChannel.DISCORD,
    ]

    # Invalid channels are still reported once for diagnostics
    assert "Ignoring unsupported notification channel(s): pager" in caplog.text

    details = runtime_data.performance_stats["last_service_result"]["details"]
    assert details is not None
    assert details["channels"] == [
        NotificationChannel.MOBILE.value,
        NotificationChannel.DISCORD.value,
    ]
    assert details["ignored_channels"] == ["pager"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_ignores_invalid_expiry(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid expiry overrides should be ignored with a warning."""

    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(), notification_manager=notification_manager
    )
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]

    with caplog.at_level(logging.WARNING):
        await handler(
            SimpleNamespace(
                data={
                    "title": "Invalid expiry",
                    "message": "Ignored override",
                    "expires_in_hours": "later",
                }
            )
        )

    sent_payload = notification_manager.sent[-1]
    assert sent_payload["expires_in"] is None
    assert "Invalid expires_in_hours" in caplog.text

    details = runtime_data.performance_stats["last_service_result"]["details"]
    assert details is not None
    assert details["expires_in_hours"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_rejects_non_positive_expiry(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Non-positive expiry overrides should be ignored."""

    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(), notification_manager=notification_manager
    )
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]

    with caplog.at_level(logging.WARNING):
        await handler(
            SimpleNamespace(
                data={
                    "title": "Non-positive expiry",
                    "message": "Ignored override",
                    "expires_in_hours": -1,
                }
            )
        )

    sent_payload = notification_manager.sent[-1]
    assert sent_payload["expires_in"] is None
    assert "Non-positive expires_in_hours" in caplog.text

    details = runtime_data.performance_stats["last_service_result"]["details"]
    assert details is not None
    assert details["expires_in_hours"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_accepts_valid_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid expiry overrides should be converted to timedeltas."""

    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(), notification_manager=notification_manager
    )
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]

    await handler(
        SimpleNamespace(
            data={
                "title": "Expires soon",
                "message": "Override respected",
                "expires_in_hours": "1.5",
            }
        )
    )

    sent_payload = notification_manager.sent[-1]
    expires_in = sent_payload["expires_in"]
    assert isinstance(expires_in, timedelta)
    assert expires_in == timedelta(hours=1.5)

    details = runtime_data.performance_stats["last_service_result"]["details"]
    assert details is not None
    assert details["expires_in_hours"] == pytest.approx(1.5)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Notification telemetry should capture errors when sends fail."""

    notification_manager = _NotificationManagerStub()
    notification_manager.fail_send = True
    coordinator = _CoordinatorStub(
        SimpleNamespace(), notification_manager=notification_manager
    )
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]

    with pytest.raises(services.HomeAssistantError, match="send failed"):
        await handler(
            SimpleNamespace(
                data={
                    "title": "Status",
                    "message": "All good",
                    "notification_type": "system_info",
                    "priority": "normal",
                }
            )
        )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_SEND_NOTIFICATION
    assert result["status"] == "error"
    assert result.get("message") == "send failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_acknowledge_notification_service_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acknowledging notifications should append success telemetry."""

    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(), notification_manager=notification_manager
    )
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_ACKNOWLEDGE_NOTIFICATION]

    await handler(SimpleNamespace(data={"notification_id": "notif-1"}))

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_ACKNOWLEDGE_NOTIFICATION
    assert result["status"] == "success"
    details = result.get("details")
    assert details is not None and details.get("acknowledged") is True
    assert coordinator.refresh_called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_acknowledge_notification_records_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telemetry should capture missing notifications when acknowledgements fail."""

    notification_manager = _NotificationManagerStub()
    notification_manager.ack_exists = False
    coordinator = _CoordinatorStub(
        SimpleNamespace(), notification_manager=notification_manager
    )
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_ACKNOWLEDGE_NOTIFICATION]

    with pytest.raises(
        services.HomeAssistantError, match="No PawControl notification with ID"
    ):
        await handler(SimpleNamespace(data={"notification_id": "missing"}))

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_ACKNOWLEDGE_NOTIFICATION
    assert result["status"] == "error"
    assert "No PawControl notification" in result.get("message", "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setup_automatic_gps_service_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Automation services should capture configuration telemetry."""

    notification_manager = _NotificationManagerStub()
    gps_manager = _GPSManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(),
        notification_manager=notification_manager,
        gps_manager=gps_manager,
    )
    coordinator.register_dog("fido")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_SETUP_AUTOMATIC_GPS]

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "fido",
                "auto_start_walk": False,
                "safe_zone_radius": 75,
                "track_route": True,
                "safety_alerts": True,
                "geofence_notifications": False,
                "auto_detect_home": True,
                "gps_accuracy_threshold": 25,
                "update_interval_seconds": 30,
            }
        )
    )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_SETUP_AUTOMATIC_GPS
    assert result["status"] == "success"
    details = result.get("details")
    assert details is not None
    assert details["safe_zone_radius"] == 75
    assert gps_manager.last_config is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setup_automatic_gps_service_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Automation telemetry should note failures when configuration raises."""

    notification_manager = _NotificationManagerStub()
    gps_manager = _GPSManagerStub()
    gps_manager.fail_configure = True
    coordinator = _CoordinatorStub(
        SimpleNamespace(),
        notification_manager=notification_manager,
        gps_manager=gps_manager,
    )
    coordinator.register_dog("fido")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_SETUP_AUTOMATIC_GPS]

    with pytest.raises(services.HomeAssistantError, match="configure failed"):
        await handler(SimpleNamespace(data={"dog_id": "fido"}))

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_SETUP_AUTOMATIC_GPS
    assert result["status"] == "error"
    assert result.get("message") == "configure failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_health_snack_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health snack service should append success telemetry with details."""

    feeding_manager = _FeedingManagerStub()
    coordinator = _CoordinatorStub(SimpleNamespace(), feeding_manager=feeding_manager)
    coordinator.register_dog("buddy", name="Buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_ADD_HEALTH_SNACK]

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "buddy",
                "snack_type": "carrot",
                "amount": 12.5,
                "health_benefit": "eyes",
                "notes": "evening snack",
            }
        )
    )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_ADD_HEALTH_SNACK
    assert result["status"] == "success"
    details = result.get("details")
    assert details is not None and details["snack_type"] == "carrot"
    assert feeding_manager.calls and feeding_manager.calls[0]["dog_id"] == "buddy"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_health_snack_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health snack telemetry should capture Home Assistant errors."""

    feeding_manager = _FeedingManagerStub()
    feeding_manager.fail_with = services.HomeAssistantError("snack failed")
    coordinator = _CoordinatorStub(SimpleNamespace(), feeding_manager=feeding_manager)
    coordinator.register_dog("buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_ADD_HEALTH_SNACK]

    with pytest.raises(services.HomeAssistantError, match="snack failed"):
        await handler(
            SimpleNamespace(
                data={"dog_id": "buddy", "snack_type": "carrot", "amount": 1.0}
            )
        )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_ADD_HEALTH_SNACK
    assert result["status"] == "error"
    assert result.get("message") == "snack failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_notifies_on_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compliance service should forward typed payloads to notifications."""

    feeding_manager = _FeedingManagerStub()
    feeding_manager.compliance_result = {
        "status": "completed",
        "dog_id": "buddy",
        "compliance_score": 72,
        "compliance_rate": 72.5,
        "days_analyzed": 3,
        "days_with_issues": 2,
        "compliance_issues": [
            {
                "date": "2024-05-01",
                "issues": ["Underfed by 20%"],
                "severity": "high",
            }
        ],
        "missed_meals": [
            {"date": "2024-05-01", "expected": 2, "actual": 1},
        ],
        "daily_analysis": {
            "2024-05-01": {
                "date": "2024-05-01",
                "feedings": [
                    {
                        "time": "2024-05-01T08:00:00+00:00",
                        "amount": 100.0,
                        "meal_type": "breakfast",
                    }
                ],
                "total_amount": 200.0,
                "meal_types": ["breakfast"],
                "scheduled_feedings": 2,
            }
        },
        "recommendations": ["Consider setting up feeding reminders"],
        "summary": {
            "average_daily_amount": 210.0,
            "average_meals_per_day": 1.5,
            "expected_daily_amount": 250.0,
            "expected_meals_per_day": 2,
        },
        "checked_at": "2024-05-03T10:00:00+00:00",
    }

    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(),
        notification_manager=notification_manager,
        feeding_manager=feeding_manager,
    )
    coordinator.register_dog("buddy", name="Buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]

    context = Context(user_id="user-1", parent_id="parent-1", context_id="ctx-1")

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "buddy",
                "days_to_check": 3,
                "notify_on_issues": True,
            },
            context=context,
        )
    )

    assert feeding_manager.compliance_calls == [
        {"dog_id": "buddy", "days_to_check": 3, "notify_on_issues": True}
    ]
    assert notification_manager.compliance_calls
    compliance_payload = notification_manager.compliance_calls[0]
    assert compliance_payload["dog_id"] == "buddy"
    assert compliance_payload["dog_name"] == "Buddy"
    assert compliance_payload["compliance"]["status"] == "completed"

    fired_events = hass.bus.fired
    assert len(fired_events) == 1
    event = fired_events[0]
    assert event["event_type"] == EVENT_FEEDING_COMPLIANCE_CHECKED
    event_data = event["event_data"]
    assert isinstance(event_data, dict)
    assert event_data["dog_id"] == "buddy"
    assert event_data["dog_name"] == "Buddy"
    assert event_data["notification_sent"] is True
    assert event_data["result"] is not feeding_manager.compliance_result
    assert event_data["result"]["compliance_score"] == 72
    summary = event_data.get("localized_summary")
    assert summary is not None
    assert summary["title"].startswith("🍽️ Feeding compliance alert")
    assert summary["score_line"].startswith("Score: 72")
    assert summary["issues"] == ["2024-05-01: Underfed by 20%"]
    assert summary["missed_meals"] == ["2024-05-01: 1/2 meals"]
    kwargs = event["kwargs"]
    assert kwargs.get("context") is context
    time_fired = kwargs.get("time_fired")
    assert isinstance(time_fired, datetime)
    assert time_fired.tzinfo is not None
    assert event_data["context_id"] == context.id
    assert event_data["parent_id"] == context.parent_id
    assert event_data["user_id"] == context.user_id

    last_result = runtime_data.performance_stats["last_service_result"]
    assert last_result["service"] == services.SERVICE_CHECK_FEEDING_COMPLIANCE
    assert last_result["status"] == "success"
    details = last_result["details"]
    assert details["score"] == 72
    details_summary = details.get("localized_summary")
    assert details_summary is not None
    assert details_summary["title"] == summary["title"]
    assert details_summary["issues"] == summary["issues"]
    diagnostics = last_result.get("diagnostics")
    assert diagnostics is not None
    metadata = diagnostics.get("metadata")
    assert metadata is not None
    assert metadata["notification_sent"] is True
    assert metadata["days_to_check"] == 3
    assert metadata["context_id"] == context.id
    assert metadata["parent_id"] == context.parent_id
    assert metadata["user_id"] == context.user_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_skips_when_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clean compliance results should not trigger notifications."""

    feeding_manager = _FeedingManagerStub()
    feeding_manager.compliance_result = {
        "status": "completed",
        "dog_id": "buddy",
        "compliance_score": 100,
        "compliance_rate": 100.0,
        "days_analyzed": 5,
        "days_with_issues": 0,
        "compliance_issues": [],
        "missed_meals": [],
        "daily_analysis": {},
        "recommendations": [],
        "summary": {
            "average_daily_amount": 250.0,
            "average_meals_per_day": 2.0,
            "expected_daily_amount": 250.0,
            "expected_meals_per_day": 2,
        },
        "checked_at": "2024-05-03T12:00:00+00:00",
    }

    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(),
        notification_manager=notification_manager,
        feeding_manager=feeding_manager,
    )
    coordinator.register_dog("buddy", name="Buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "buddy",
                "days_to_check": 5,
                "notify_on_issues": True,
            }
        )
    )

    assert notification_manager.compliance_calls == []

    fired_events = hass.bus.fired
    assert len(fired_events) == 1
    event = fired_events[0]
    assert event["event_type"] == EVENT_FEEDING_COMPLIANCE_CHECKED
    event_data = event["event_data"]
    assert isinstance(event_data, dict)
    assert event_data["dog_id"] == "buddy"
    assert event_data["notification_sent"] is False
    assert event_data["result"]["compliance_score"] == 100
    summary = event_data.get("localized_summary")
    assert summary is not None
    assert summary["score_line"].startswith("Score: 100")
    assert summary["issues"] == []
    assert summary["missed_meals"] == []

    last_result = runtime_data.performance_stats["last_service_result"]
    assert last_result["service"] == services.SERVICE_CHECK_FEEDING_COMPLIANCE
    assert last_result["status"] == "success"
    details_summary = last_result["details"].get("localized_summary")
    assert details_summary is not None
    assert details_summary["score_line"].startswith("Score: 100")
    assert last_result["details"]["score"] == 100


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_respects_notify_toggle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Notifications are skipped when notify_on_issues is False."""

    feeding_manager = _FeedingManagerStub()
    feeding_manager.compliance_result = {
        "status": "completed",
        "dog_id": "buddy",
        "compliance_score": 50,
        "compliance_rate": 50.0,
        "days_analyzed": 2,
        "days_with_issues": 2,
        "compliance_issues": [
            {
                "date": "2024-05-01",
                "issues": ["Missed scheduled lunch"],
                "severity": "medium",
            }
        ],
        "missed_meals": [{"date": "2024-05-01", "expected": 2, "actual": 1}],
        "daily_analysis": {},
        "recommendations": ["Enable reminders"],
        "summary": {
            "average_daily_amount": 150.0,
            "average_meals_per_day": 1.0,
            "expected_daily_amount": 300.0,
            "expected_meals_per_day": 2,
        },
        "checked_at": "2024-05-03T15:00:00+00:00",
    }

    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(),
        notification_manager=notification_manager,
        feeding_manager=feeding_manager,
    )
    coordinator.register_dog("buddy", name="Buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "buddy",
                "days_to_check": 2,
                "notify_on_issues": False,
            }
        )
    )

    assert notification_manager.compliance_calls == []

    fired_events = hass.bus.fired
    assert len(fired_events) == 1
    event = fired_events[0]
    assert event["event_type"] == EVENT_FEEDING_COMPLIANCE_CHECKED
    event_data = event["event_data"]
    assert isinstance(event_data, dict)
    assert event_data["notify_on_issues"] is False
    assert event_data["notification_sent"] is False

    last_result = runtime_data.performance_stats["last_service_result"]
    assert last_result["status"] == "success"
    diagnostics = last_result.get("diagnostics")
    assert diagnostics is not None
    metadata = diagnostics.get("metadata")
    assert metadata is not None and metadata["notify_on_issues"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_sanitises_structured_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Structured compliance messages should be normalised to readable text."""

    feeding_manager = _FeedingManagerStub()
    feeding_manager.compliance_result = {
        "status": "no_data",
        "message": {"description": "Telemetry offline", "code": 503},
    }

    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(),
        notification_manager=notification_manager,
        feeding_manager=feeding_manager,
    )
    coordinator.register_dog("buddy", name="Buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    published_payloads: list[dict[str, object]] = []

    async def _capture_publish(
        hass: object,
        entry: object,
        payload: dict[str, object],
        *,
        context_metadata: dict[str, object] | None = None,
    ) -> None:
        published_payloads.append(payload)

    monkeypatch.setattr(
        services,
        "async_publish_feeding_compliance_issue",
        _capture_publish,
    )

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "buddy",
                "days_to_check": 3,
                "notify_on_issues": True,
            }
        )
    )

    assert notification_manager.compliance_calls
    assert published_payloads

    event = hass.bus.fired[0]
    event_data = event["event_data"]
    assert event_data["result"]["message"] == "Telemetry offline"

    summary = event_data["localized_summary"]
    assert summary["message"] == "Telemetry offline"

    recorded = runtime_data.performance_stats["last_service_result"]
    details = recorded["details"]
    assert details["message"] == "Telemetry offline"
    assert details["localized_summary"]["message"] == "Telemetry offline"

    published = published_payloads[0]
    assert published["result"]["message"] == "Telemetry offline"


@pytest.mark.unit
def test_merge_service_context_metadata_respects_include_none() -> None:
    """Helper should optionally persist ``None`` metadata values."""

    target: dict[str, object] = {"existing": True}
    metadata = {"context_id": None, "parent_id": "parent-123"}

    services._merge_service_context_metadata(target, metadata)

    assert "context_id" not in target
    assert target["parent_id"] == "parent-123"

    services._merge_service_context_metadata(target, metadata, include_none=True)

    assert target["context_id"] is None
    assert target["parent_id"] == "parent-123"


@pytest.mark.unit
def test_merge_service_context_metadata_preserves_additional_keys() -> None:
    """Additional context metadata should be forwarded unchanged."""

    target: dict[str, object] = {}
    metadata = {"context_id": "ctx-123", "source": "stub"}

    services._merge_service_context_metadata(target, metadata)

    assert target["context_id"] == "ctx-123"
    assert target["source"] == "stub"


@pytest.mark.unit
def test_merge_service_context_metadata_ignores_non_string_keys() -> None:
    """Non-string metadata keys are ignored for safety."""

    target: dict[str, object] = {}
    metadata = {"context_id": "ctx-123", 42: "skip-me"}

    services._merge_service_context_metadata(target, metadata)

    assert target == {"context_id": "ctx-123"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_builds_context_from_stub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Context metadata should be normalised when Home Assistant provides stubs."""

    feeding_manager = _FeedingManagerStub()
    feeding_manager.compliance_result = {
        "status": "completed",
        "dog_id": "buddy",
        "compliance_score": 82,
        "compliance_rate": 82.0,
        "days_analyzed": 4,
        "days_with_issues": 1,
        "compliance_issues": [],
        "missed_meals": [],
        "daily_analysis": {},
        "recommendations": [],
        "summary": {
            "average_daily_amount": 180.0,
            "average_meals_per_day": 1.5,
            "expected_daily_amount": 200.0,
            "expected_meals_per_day": 2,
        },
        "checked_at": "2024-05-04T09:00:00+00:00",
    }

    coordinator = _CoordinatorStub(
        SimpleNamespace(),
        notification_manager=_NotificationManagerStub(),
        feeding_manager=feeding_manager,
    )
    coordinator.register_dog("buddy", name="Buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]

    context_stub = SimpleNamespace(
        id="ctx-stub",
        parent_id="parent-stub",
        user_id="user-stub",
    )

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "buddy",
                "days_to_check": 4,
                "notify_on_issues": True,
            },
            context=context_stub,
        )
    )

    event = hass.bus.fired[0]
    kwargs = event["kwargs"]
    event_context = kwargs.get("context")
    assert event_context is not context_stub
    assert getattr(event_context, "id", None) == "ctx-stub"
    assert getattr(event_context, "parent_id", None) == "parent-stub"
    assert getattr(event_context, "user_id", None) == "user-stub"

    event_data = event["event_data"]
    assert event_data["context_id"] == "ctx-stub"
    assert event_data["parent_id"] == "parent-stub"
    assert event_data["user_id"] == "user-stub"

    metadata = runtime_data.performance_stats["last_service_result"]["diagnostics"][
        "metadata"
    ]
    assert metadata["context_id"] == "ctx-stub"
    assert metadata["parent_id"] == "parent-stub"
    assert metadata["user_id"] == "user-stub"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_builds_context_from_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mapping-based service contexts should be normalised for telemetry."""

    feeding_manager = _FeedingManagerStub()
    feeding_manager.compliance_result = {
        "status": "completed",
        "dog_id": "buddy",
        "compliance_score": 92,
        "compliance_rate": 92.0,
        "days_analyzed": 5,
        "days_with_issues": 0,
        "compliance_issues": [],
        "missed_meals": [],
        "daily_analysis": {},
        "recommendations": [],
        "summary": {
            "average_daily_amount": 200.0,
            "average_meals_per_day": 2.0,
            "expected_daily_amount": 200.0,
            "expected_meals_per_day": 2,
        },
        "checked_at": "2024-05-05T11:00:00+00:00",
    }

    coordinator = _CoordinatorStub(
        SimpleNamespace(),
        notification_manager=_NotificationManagerStub(),
        feeding_manager=feeding_manager,
    )
    coordinator.register_dog("buddy", name="Buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]

    context_mapping = {
        "context_id": "ctx-mapping",
        "parent_id": "parent-mapping",
        "user_id": "user-mapping",
    }

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "buddy",
                "days_to_check": 5,
                "notify_on_issues": True,
            },
            context=context_mapping,
        )
    )

    event = hass.bus.fired[0]
    kwargs = event["kwargs"]
    event_context = kwargs.get("context")
    assert event_context is not None
    assert getattr(event_context, "id", None) == "ctx-mapping"
    assert getattr(event_context, "parent_id", None) == "parent-mapping"
    assert getattr(event_context, "user_id", None) == "user-mapping"

    event_data = event["event_data"]
    assert event_data["context_id"] == "ctx-mapping"
    assert event_data["parent_id"] == "parent-mapping"
    assert event_data["user_id"] == "user-mapping"

    metadata = runtime_data.performance_stats["last_service_result"]["diagnostics"][
        "metadata"
    ]
    assert metadata["context_id"] == "ctx-mapping"
    assert metadata["parent_id"] == "parent-mapping"
    assert metadata["user_id"] == "user-mapping"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_records_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service should capture telemetry when compliance checks fail."""

    feeding_manager = _FeedingManagerStub()
    feeding_manager.compliance_error = services.HomeAssistantError("compliance failed")
    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(),
        notification_manager=notification_manager,
        feeding_manager=feeding_manager,
    )
    coordinator.register_dog("buddy", name="Buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]

    with pytest.raises(services.HomeAssistantError, match="compliance failed"):
        await handler(
            SimpleNamespace(
                data={
                    "dog_id": "buddy",
                    "days_to_check": 3,
                    "notify_on_issues": True,
                }
            )
        )

    assert hass.bus.fired == []
    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_CHECK_FEEDING_COMPLIANCE
    assert result["status"] == "error"
    assert result["message"] == "compliance failed"
    diagnostics = result.get("diagnostics")
    assert diagnostics is not None
    metadata = diagnostics.get("metadata")
    assert metadata is not None
    assert metadata["days_to_check"] == 3
    assert metadata["notify_on_issues"] is True
    assert "context_id" not in metadata


async def test_log_poop_service_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Poop logging should emit success telemetry with timestamp details."""

    data_manager = _DataManagerStub()
    coordinator = _CoordinatorStub(SimpleNamespace(), data_manager=data_manager)
    coordinator.register_dog("buddy")
    runtime_data = SimpleNamespace(performance_stats={})
    timestamp = datetime(2024, 1, 1, tzinfo=UTC)

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_LOG_POOP]

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "buddy",
                "quality": "good",
                "color": "brown",
                "size": "normal",
                "timestamp": timestamp,
            }
        )
    )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_LOG_POOP
    assert result["status"] == "success"
    details = result.get("details")
    assert details is not None and details["timestamp"].startswith(
        "2024-01-01T00:00:00"
    )
    assert data_manager.poop_calls and data_manager.poop_calls[0]["dog_id"] == "buddy"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_log_poop_service_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Poop logging telemetry should capture Home Assistant errors."""

    data_manager = _DataManagerStub()
    data_manager.fail_log = services.HomeAssistantError("poop failed")
    coordinator = _CoordinatorStub(SimpleNamespace(), data_manager=data_manager)
    coordinator.register_dog("buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_LOG_POOP]

    with pytest.raises(services.HomeAssistantError, match="poop failed"):
        await handler(SimpleNamespace(data={"dog_id": "buddy"}))

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_LOG_POOP
    assert result["status"] == "error"
    assert result.get("message") == "poop failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_grooming_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Grooming service should store telemetry for successful sessions."""

    reminder_sent_at = datetime.now(UTC)
    data_manager = _DataManagerStub()
    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(),
        notification_manager=notification_manager,
        data_manager=data_manager,
    )
    coordinator.register_dog("buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_START_GROOMING]

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "buddy",
                "grooming_type": "bath",
                "groomer": "Jamie",
                "location": "Salon",
                "estimated_duration_minutes": 45,
                "reminder_id": "rem-123",
                "reminder_type": "auto_schedule",
                "reminder_sent_at": reminder_sent_at,
            }
        )
    )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_START_GROOMING
    assert result["status"] == "success"
    details = result.get("details")
    assert details is not None and details["session_id"] == data_manager.next_session_id
    assert details["reminder_attached"] is True
    reminder_details = details.get("reminder")
    assert reminder_details is not None
    assert reminder_details["id"] == "rem-123"
    assert reminder_details["type"] == "auto_schedule"
    expected_iso = reminder_sent_at.astimezone(UTC).isoformat()
    assert reminder_details["sent_at"] == expected_iso

    diagnostics = result.get("diagnostics")
    assert diagnostics is not None
    metadata = diagnostics.get("metadata")
    assert metadata is not None
    assert metadata["reminder_attached"] is True
    assert metadata["reminder_id"] == "rem-123"
    assert metadata["reminder_type"] == "auto_schedule"
    assert metadata["reminder_sent_at"] == expected_iso
    assert data_manager.groom_calls and data_manager.groom_calls[0]["dog_id"] == "buddy"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_grooming_localizes_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Grooming notifications should respect the active Home Assistant language."""

    data_manager = _DataManagerStub()
    notification_manager = _NotificationManagerStub()
    coordinator = _CoordinatorStub(
        SimpleNamespace(),
        notification_manager=notification_manager,
        data_manager=data_manager,
    )
    coordinator.register_dog("buddy", name="Buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    hass.config.language = "de"

    handler = hass.services.handlers[services.SERVICE_START_GROOMING]

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "buddy",
                "grooming_type": "bath",
                "groomer": "Jamie",
                "estimated_duration_minutes": 45,
            }
        )
    )

    assert notification_manager.sent, "Expected localized grooming notification"
    payload = notification_manager.sent[0]
    assert payload["title"] == "🛁 Pflege gestartet: Buddy"
    assert payload["message"] == "Gestartet bath für Buddy mit Jamie (ca. 45 Min.)"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_grooming_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Grooming telemetry should track Home Assistant errors."""

    data_manager = _DataManagerStub()
    data_manager.fail_groom = services.HomeAssistantError("groom failed")
    coordinator = _CoordinatorStub(SimpleNamespace(), data_manager=data_manager)
    coordinator.register_dog("buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_START_GROOMING]

    with pytest.raises(services.HomeAssistantError, match="groom failed"):
        await handler(
            SimpleNamespace(data={"dog_id": "buddy", "grooming_type": "bath"})
        )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_START_GROOMING
    assert result["status"] == "error"
    assert result.get("message") == "groom failed"
    diagnostics = result.get("diagnostics")
    assert diagnostics is not None
    metadata = diagnostics.get("metadata")
    assert metadata is not None
    assert metadata["reminder_attached"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_garden_session_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garden session start should log telemetry with detection metadata."""

    garden_manager = _GardenManagerStub()
    coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)
    coordinator.register_dog("buddy", name="Buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_START_GARDEN]

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "buddy",
                "detection_method": "door_sensor",
                "weather_conditions": "sunny",
                "temperature": 22.5,
                "automation_fallback": True,
                "fallback_reason": "door_sensor_offline",
                "automation_source": "garden_automation",
            }
        )
    )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_START_GARDEN
    assert result["status"] == "success"
    details = result.get("details")
    assert details is not None and details["detection_method"] == "door_sensor"
    assert details["automation_fallback"] is True
    assert details["fallback_reason"] == "door_sensor_offline"
    assert details["automation_source"] == "garden_automation"
    diagnostics = result.get("diagnostics")
    assert diagnostics is not None
    metadata = diagnostics.get("metadata")
    assert metadata is not None
    assert metadata["automation_fallback"] is True
    assert metadata["fallback_reason"] == "door_sensor_offline"
    assert metadata["automation_source"] == "garden_automation"
    assert (
        garden_manager.start_calls
        and garden_manager.start_calls[0]["dog_id"] == "buddy"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_garden_session_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garden session telemetry should capture Home Assistant errors."""

    garden_manager = _GardenManagerStub()
    garden_manager.fail_start = services.HomeAssistantError("start failed")
    coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)
    coordinator.register_dog("buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_START_GARDEN]

    with pytest.raises(services.HomeAssistantError, match="start failed"):
        await handler(SimpleNamespace(data={"dog_id": "buddy"}))

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_START_GARDEN
    assert result["status"] == "error"
    assert result.get("message") == "start failed"
    diagnostics = result.get("diagnostics")
    assert diagnostics is not None
    metadata = diagnostics.get("metadata")
    assert metadata is not None
    assert metadata["automation_fallback"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_end_garden_session_records_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ending a non-existent garden session should record validation telemetry."""

    garden_manager = _GardenManagerStub()
    garden_manager.next_end_session = None
    coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)
    coordinator.register_dog("buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_END_GARDEN]

    with pytest.raises(
        Exception, match="No active garden session is currently running"
    ):
        await handler(SimpleNamespace(data={"dog_id": "buddy"}))

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_END_GARDEN
    assert result["status"] == "error"
    assert "No active garden session" in result.get("message", "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_garden_activity_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garden activity service should capture success telemetry."""

    garden_manager = _GardenManagerStub()
    coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)
    coordinator.register_dog("buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_ADD_GARDEN_ACTIVITY]

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "buddy",
                "activity_type": "play",
                "duration_seconds": 120,
                "location": "north lawn",
            }
        )
    )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_ADD_GARDEN_ACTIVITY
    assert result["status"] == "success"
    details = result.get("details")
    assert details is not None and details["activity_type"] == "play"
    assert (
        garden_manager.activity_calls
        and garden_manager.activity_calls[0]["dog_id"] == "buddy"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_garden_activity_records_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garden activity telemetry should note validation failures."""

    garden_manager = _GardenManagerStub()
    garden_manager.activity_success = False
    coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)
    coordinator.register_dog("buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_ADD_GARDEN_ACTIVITY]

    with pytest.raises(
        Exception, match="No active garden session is currently running"
    ):
        await handler(
            SimpleNamespace(data={"dog_id": "buddy", "activity_type": "play"})
        )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_ADD_GARDEN_ACTIVITY
    assert result["status"] == "error"
    assert "Start a garden session" in result.get("message", "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_confirm_garden_poop_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garden poop confirmations should capture telemetry on success."""

    garden_manager = _GardenManagerStub()
    coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)
    coordinator.register_dog("buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_CONFIRM_POOP]

    await handler(
        SimpleNamespace(
            data={
                "dog_id": "buddy",
                "confirmed": True,
                "quality": "good",
                "size": "normal",
                "location": "patio",
            }
        )
    )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_CONFIRM_POOP
    assert result["status"] == "success"
    details = result.get("details")
    assert details is not None and details["confirmed"] is True
    assert (
        garden_manager.confirm_calls
        and garden_manager.confirm_calls[0]["dog_id"] == "buddy"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_confirm_garden_poop_records_missing_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telemetry should record validation errors when no confirmation is pending."""

    garden_manager = _GardenManagerStub()
    garden_manager.pending_confirmation = False
    coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)
    coordinator.register_dog("buddy")
    runtime_data = SimpleNamespace(performance_stats={})

    hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)
    handler = hass.services.handlers[services.SERVICE_CONFIRM_POOP]

    with pytest.raises(Exception, match="No pending garden poop confirmation"):
        await handler(SimpleNamespace(data={"dog_id": "buddy", "confirmed": True}))

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_CONFIRM_POOP
    assert result["status"] == "error"
    assert "No pending garden poop" in result.get("message", "")
