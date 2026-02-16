"""Unit tests for the PawControl services helpers."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
import json
import logging
from types import MappingProxyType, SimpleNamespace
from typing import TypedDict, cast

from homeassistant.exceptions import ServiceValidationError
import pytest

from custom_components.pawcontrol import services
from custom_components.pawcontrol.const import (
  EVENT_FEEDING_COMPLIANCE_CHECKED,
  SERVICE_CHECK_FEEDING_COMPLIANCE,
  SERVICE_DAILY_RESET,
)
from custom_components.pawcontrol.coordinator_tasks import default_rejection_metrics
from custom_components.pawcontrol.feeding_manager import (
  FeedingComplianceCompleted,
  FeedingComplianceNoData,
  FeedingComplianceResult,
)
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
  FeedingComplianceEventPayload,
  GPSRouteExportJSONPayload,
  GPSRouteExportPayload,
  GPSTrackingConfigInput,
)
from custom_components.pawcontrol.utils import async_call_hass_service_if_available

try:  # pragma: no cover - runtime fallback for stubbed environments
  from homeassistant.core import Context  # noqa: E111
except ImportError:  # pragma: no cover - ensure stubs are available for tests
  from tests.helpers.homeassistant_test_stubs import install_homeassistant_stubs

  install_homeassistant_stubs()  # noqa: E111
  from homeassistant.core import Context  # noqa: E111


def test_service_validation_error_uses_homeassistant_class() -> None:
  """``_service_validation_error`` should emit ServiceValidationError."""  # noqa: E111

  error = services._service_validation_error("boom")  # noqa: E111

  assert isinstance(error, ServiceValidationError)  # noqa: E111
  assert str(error) == "boom"  # noqa: E111


def test_service_validation_error_rejects_blank_message() -> None:
  """Blank messages should be rejected to preserve telemetry detail."""  # noqa: E111

  with pytest.raises(AssertionError):  # noqa: E111
    services._service_validation_error("   ")


def test_service_validation_error_trims_whitespace() -> None:
  """Messages should be trimmed before instantiating the service error."""  # noqa: E111

  error = services._service_validation_error("  trimmed  ")  # noqa: E111

  assert isinstance(error, ServiceValidationError)  # noqa: E111
  assert str(error) == "trimmed"  # noqa: E111


@pytest.mark.unit
def test_coerce_service_details_value_handles_nested_payloads() -> None:
  """``_coerce_service_details_value`` should return JSON-safe structures."""  # noqa: E111

  payload = {  # noqa: E111
    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
    "details": {
      1: {
        "tuple": ("alpha", "beta"),
        "set_values": {1, 2},
        "proxy": MappingProxyType({("zone", 1): {"value": 5.0}}),
        "namespace": SimpleNamespace(flag=True),
      }
    },
    "sequence": (
      "first",
      {"second": SimpleNamespace(extra="value")},
    ),
    "none": None,
  }

  result = services._coerce_service_details_value(payload)  # noqa: E111

  assert result["timestamp"] == "2024-01-01 00:00:00+00:00"  # noqa: E111

  nested = result["details"]["1"]  # noqa: E111
  assert nested["tuple"] == ["alpha", "beta"]  # noqa: E111
  assert sorted(nested["set_values"]) == [1, 2]  # noqa: E111
  assert nested["proxy"]["('zone', 1)"]["value"] == 5.0  # noqa: E111
  assert nested["namespace"].startswith("namespace(flag=")  # noqa: E111

  sequence = result["sequence"]  # noqa: E111
  assert sequence[0] == "first"  # noqa: E111
  assert sequence[1]["second"].startswith("namespace(extra=")  # noqa: E111

  assert result["none"] is None  # noqa: E111

  # Ensure the coerced payload serialises to JSON without raising errors.  # noqa: E114
  json.dumps(result)  # noqa: E111


def test_record_service_result_merges_rejection_metrics() -> None:
  """Service telemetry should reuse the rejection metrics helper."""  # noqa: E111

  resilience_summary: dict[str, object] = {  # noqa: E111
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

  runtime_data = SimpleNamespace(  # noqa: E111
    performance_stats={"resilience_summary": resilience_summary}
  )

  services._record_service_result(  # noqa: E111
    runtime_data,
    service="notify.test",
    status="error",
  )

  metrics = runtime_data.performance_stats["rejection_metrics"]  # noqa: E111
  assert metrics["rejected_call_count"] == 2  # noqa: E111
  assert metrics["rejection_breaker_count"] == 1  # noqa: E111
  assert metrics["open_breakers"] == ["api"]  # noqa: E111

  last_result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  resilience_details = last_result["details"]["resilience"]  # noqa: E111
  assert resilience_details["rejected_call_count"] == 2  # noqa: E111
  assert resilience_details["rejection_breaker_count"] == 1  # noqa: E111

  diagnostics_payload = last_result["diagnostics"]  # noqa: E111
  assert diagnostics_payload["rejection_metrics"]["open_breakers"] == ["api"]  # noqa: E111
  assert runtime_data.performance_stats["service_results"][-1] is last_result  # noqa: E111


def test_record_service_result_defaults_rejection_metrics_without_breakers() -> None:
  """Circuit recovery snapshots should keep rejection metrics at defaults."""  # noqa: E111

  resilience_summary: dict[str, object] = {  # noqa: E111
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

  runtime_data = SimpleNamespace(  # noqa: E111
    performance_stats={"resilience_summary": resilience_summary}
  )

  services._record_service_result(  # noqa: E111
    runtime_data,
    service="notify.test",
    status="success",
  )

  defaults = default_rejection_metrics()  # noqa: E111

  metrics = runtime_data.performance_stats["rejection_metrics"]  # noqa: E111
  assert metrics == defaults  # noqa: E111

  last_result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert "details" not in last_result or "resilience" not in last_result["details"]  # noqa: E111

  diagnostics_payload = last_result["diagnostics"]  # noqa: E111
  assert diagnostics_payload["rejection_metrics"] == defaults  # noqa: E111


def test_classify_error_reason_detects_notification_failures() -> None:
  """Error classification should bucket auth and reachability failures."""  # noqa: E111

  from custom_components.pawcontrol.error_classification import classify_error_reason

  assert classify_error_reason("missing_notify_service") == "missing_service"  # noqa: E111
  assert classify_error_reason("exception", error="Unauthorized device") == "auth_error"  # noqa: E111
  assert (  # noqa: E111
    classify_error_reason("exception", error="Device unreachable")
    == "device_unreachable"
  )


class _DummyCoordinator:
  """Coordinator stub that records refresh requests."""  # noqa: E111

  def __init__(  # noqa: E111
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

  async def async_request_refresh(self) -> None:  # noqa: E111
    if self._fail:
      raise self._error  # noqa: E111
    self.refresh_called = True


class _DummyWalkManager:
  """Walk manager stub recording cleanup calls."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.cleaned = False

  async def async_cleanup(self) -> None:  # noqa: E111
    self.cleaned = True


class _DummyNotificationManager:
  """Notification manager stub recording cleanup calls."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.cleaned = False
    self.cleaned_count = 2

  async def async_cleanup_expired_notifications(self) -> int:  # noqa: E111
    self.cleaned = True
    return self.cleaned_count


class _BusStub:
  """Capture Home Assistant bus events for verification."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.fired: list[dict[str, object]] = []

  async def async_fire(  # noqa: E111
    self,
    event_type: str,
    event_data: object | None = None,
    **kwargs: object,
  ) -> None:
    self.fired.append({
      "event_type": event_type,
      "event_data": event_data,
      "kwargs": dict(kwargs),
    })


class _DummyDataManager:
  """Expose deterministic cache diagnostics payloads for tests."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    payload: dict[str, dict[str, object]],
    summary: CacheRepairAggregate | None = None,
  ) -> None:
    self._payload = payload
    if summary is not None and not isinstance(summary, CacheRepairAggregate):
      raise TypeError("summary must be CacheRepairAggregate or None")  # noqa: E111
    self._summary = summary

  def cache_snapshots(self) -> dict[str, dict[str, object]]:  # noqa: E111
    return self._payload

  def cache_repair_summary(  # noqa: E111
    self, snapshots: dict[str, object] | None = None
  ) -> CacheRepairAggregate | None:
    if snapshots is not None:
      self._last_snapshots = snapshots  # noqa: E111
      normalised: dict[str, object] = {}  # noqa: E111
      for key, payload in snapshots.items():  # noqa: E111
        if hasattr(payload, "to_mapping"):
          try:  # noqa: E111
            candidate = payload.to_mapping()  # type: ignore[call-arg]
          except Exception:  # noqa: E111
            candidate = None
          else:  # noqa: E111
            if isinstance(candidate, Mapping):
              normalised[key] = dict(candidate)  # noqa: E111
              continue  # noqa: E111
        if isinstance(payload, Mapping):
          normalised[key] = dict(payload)  # noqa: E111
        else:
          normalised[key] = payload  # noqa: E111
      self._normalised_payload = normalised  # noqa: E111
      assert normalised == self._payload  # noqa: E111
    return self._summary


class _ComplianceCheckCall(TypedDict):
  """Typed payload recorded for feeding compliance checks."""  # noqa: E111

  dog_id: str  # noqa: E111
  days_to_check: int  # noqa: E111
  notify_on_issues: bool  # noqa: E111


class _HealthSnackCall(TypedDict):
  """Typed payload captured for health snack submissions."""  # noqa: E111

  dog_id: str  # noqa: E111
  snack_type: str  # noqa: E111
  amount: float  # noqa: E111
  health_benefit: object | None  # noqa: E111
  notes: object | None  # noqa: E111


class _FeedingManagerStub:
  """Provide deterministic behaviour for health snack telemetry tests."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.calls: list[_HealthSnackCall] = []
    self.fail_with: Exception | None = None
    self.compliance_calls: list[_ComplianceCheckCall] = []
    self.compliance_result: FeedingComplianceResult = {
      "status": "no_data",
      "message": "No feeding data available",
    }
    self.compliance_error: Exception | None = None

  async def async_add_health_snack(  # noqa: E111
    self,
    *,
    dog_id: str,
    snack_type: str,
    amount: float,
    health_benefit: object | None,
    notes: object | None,
  ) -> None:
    if self.fail_with:
      raise self.fail_with  # noqa: E111

    call: _HealthSnackCall = {
      "dog_id": dog_id,
      "snack_type": snack_type,
      "amount": amount,
      "health_benefit": health_benefit,
      "notes": notes,
    }
    self.calls.append(call)

  async def async_check_feeding_compliance(  # noqa: E111
    self,
    *,
    dog_id: str,
    days_to_check: int,
    notify_on_issues: bool,
  ) -> FeedingComplianceResult:
    if self.compliance_error:
      raise self.compliance_error  # noqa: E111

    self.compliance_calls.append({
      "dog_id": dog_id,
      "days_to_check": days_to_check,
      "notify_on_issues": notify_on_issues,
    })
    return self.compliance_result


class _DataManagerStub:
  """Simulate grooming and poop logging calls for telemetry coverage."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.poop_calls: list[dict[str, object]] = []
    self.groom_calls: list[dict[str, object]] = []
    self.fail_log: Exception | None = None
    self.fail_groom: Exception | None = None
    self.next_session_id = "groom-session-1"

  async def async_log_poop_data(  # noqa: E111
    self, *, dog_id: str, poop_data: dict[str, object]
  ) -> None:
    if self.fail_log:
      raise self.fail_log  # noqa: E111

    self.poop_calls.append({"dog_id": dog_id, "poop_data": dict(poop_data)})

  async def async_start_grooming_session(  # noqa: E111
    self, *, dog_id: str, grooming_data: dict[str, object]
  ) -> str:
    if self.fail_groom:
      raise self.fail_groom  # noqa: E111

    self.groom_calls.append({"dog_id": dog_id, "grooming_data": dict(grooming_data)})
    return self.next_session_id


class _GardenManagerStub:
  """Stub the garden manager API for service telemetry assertions."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
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

  async def async_start_garden_session(  # noqa: E111
    self,
    *,
    dog_id: str,
    dog_name: str,
    detection_method: str,
    weather_conditions: object | None,
    temperature: object | None,
  ) -> str:
    if self.fail_start:
      raise self.fail_start  # noqa: E111

    self.start_calls.append({
      "dog_id": dog_id,
      "dog_name": dog_name,
      "detection_method": detection_method,
      "weather_conditions": weather_conditions,
      "temperature": temperature,
    })
    return self.next_session_id

  async def async_end_garden_session(  # noqa: E111
    self,
    *,
    dog_id: str,
    notes: object | None,
    activities: Sequence[GardenActivityInputPayload] | None,
  ) -> object | None:
    if self.fail_end:
      raise self.fail_end  # noqa: E111

    self.end_calls.append({"dog_id": dog_id, "notes": notes, "activities": activities})
    return self.next_end_session

  async def async_add_activity(  # noqa: E111
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
      raise self.fail_activity  # noqa: E111

    self.activity_calls.append({
      "dog_id": dog_id,
      "activity_type": activity_type,
      "duration_seconds": duration_seconds,
      "location": location,
      "notes": notes,
      "confirmed": confirmed,
    })
    return self.activity_success

  def has_pending_confirmation(self, dog_id: str) -> bool:  # noqa: E111
    return self.pending_confirmation

  async def async_handle_poop_confirmation(  # noqa: E111
    self,
    *,
    dog_id: str,
    confirmed: bool,
    quality: object | None,
    size: object | None,
    location: object | None,
  ) -> None:
    if self.fail_confirm:
      raise self.fail_confirm  # noqa: E111

    self.confirm_calls.append({
      "dog_id": dog_id,
      "confirmed": confirmed,
      "quality": quality,
      "size": size,
      "location": location,
    })


class _ServiceRegistryStub:
  """Record service registrations during setup."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.handlers: dict[str, Callable[..., Awaitable[None]]] = {}

  def async_register(  # noqa: E111
    self,
    domain: str,
    service: str,
    handler: Callable[..., Awaitable[None]],
    schema: object | None = None,
  ) -> None:
    self.handlers[service] = handler


class _ResolverStub:
  """Minimal coordinator resolver for service tests."""  # noqa: E111

  def __init__(self, coordinator: object) -> None:  # noqa: E111
    self._coordinator = coordinator

  def invalidate(  # noqa: E111
    self, *, entry_id: str | None = None
  ) -> None:  # pragma: no cover - noop
    return None

  def resolve(self) -> object:  # noqa: E111
    return self._coordinator


class _ComplianceNotificationCall(TypedDict):
  """Typed payload recorded for compliance notification requests."""  # noqa: E111

  dog_id: str  # noqa: E111
  dog_name: str | None  # noqa: E111
  compliance: FeedingComplianceResult  # noqa: E111


class _NotificationManagerStub:
  """Provide deterministic notification behaviour for telemetry tests."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.fail_send = False
    self.fail_ack = False
    self.ack_exists = True
    self.sent: list[dict[str, object]] = []
    self.compliance_calls: list[_ComplianceNotificationCall] = []
    self.fail_compliance = False

  async def async_send_notification(self, **kwargs: object) -> str:  # noqa: E111
    if self.fail_send:
      raise services.HomeAssistantError("send failed")  # noqa: E111
    notification_type = kwargs.get("notification_type")
    assert isinstance(notification_type, NotificationType)

    priority = kwargs.get("priority")
    if priority is not None:
      assert isinstance(priority, NotificationPriority)  # noqa: E111

    force_channels = kwargs.get("force_channels")
    if force_channels is not None:
      assert isinstance(force_channels, list)  # noqa: E111
      assert all(isinstance(channel, NotificationChannel) for channel in force_channels)  # noqa: E111
    self.sent.append(kwargs)
    return "notif-1"

  async def async_send_feeding_compliance_summary(  # noqa: E111
    self,
    *,
    dog_id: str,
    dog_name: str | None,
    compliance: FeedingComplianceResult,
  ) -> str | None:
    if self.fail_compliance:
      raise services.HomeAssistantError("compliance failed")  # noqa: E111

    status = compliance["status"]
    if status == "completed":
      completed = cast(FeedingComplianceCompleted, compliance)  # noqa: E111
      has_issues = bool(  # noqa: E111
        completed["days_with_issues"]
        or completed["compliance_issues"]
        or completed["missed_meals"]
        or completed["compliance_score"] < 100
      )
      if not has_issues:  # noqa: E111
        return None

    self.compliance_calls.append({
      "dog_id": dog_id,
      "dog_name": dog_name,
      "compliance": compliance,
    })
    return "compliance-1"

  async def async_acknowledge_notification(self, notification_id: str) -> bool:  # noqa: E111
    if self.fail_ack:
      raise services.HomeAssistantError("ack failed")  # noqa: E111
    return self.ack_exists

  async def async_cleanup_expired_notifications(  # noqa: E111
    self,
  ) -> None:  # pragma: no cover
    return None


class _GuardSkippingNotificationManager(_NotificationManagerStub):
  """Notification manager stub that exercises guard skip telemetry."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    super().__init__()
    self.calls = 0

  async def async_send_notification(self, **kwargs: object) -> str:  # noqa: E111
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
  """Emulate GPS configuration calls for automation service tests."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.fail_configure = False
    self.fail_safe_zone = False
    self.last_config: dict[str, object] | None = None
    self.safe_zone: dict[str, object] | None = None
    self.fail_export: Exception | None = None
    self.export_result: GPSRouteExportPayload | None = None
    self.export_calls: list[dict[str, object]] = []

  async def async_configure_dog_gps(  # noqa: E111
    self, *, dog_id: str, config: GPSTrackingConfigInput
  ) -> None:
    if self.fail_configure:
      raise services.HomeAssistantError("configure failed")  # noqa: E111
    self.last_config = {"dog_id": dog_id, "config": dict(config)}

  async def async_setup_safe_zone(  # noqa: E111
    self,
    *,
    dog_id: str,
    center_lat: float,
    center_lon: float,
    radius_meters: float,
    notifications_enabled: bool,
  ) -> None:
    if self.fail_safe_zone:
      raise services.HomeAssistantError("safe zone failed")  # noqa: E111
    self.safe_zone = {
      "dog_id": dog_id,
      "center_lat": center_lat,
      "center_lon": center_lon,
      "radius": radius_meters,
      "notifications": notifications_enabled,
    }

  async def async_export_routes(  # noqa: E111
    self,
    *,
    dog_id: str,
    export_format: str,
    last_n_routes: int,
  ) -> GPSRouteExportPayload | None:
    if self.fail_export:
      raise self.fail_export  # noqa: E111
    call: dict[str, object] = {
      "dog_id": dog_id,
      "export_format": export_format,
      "last_n_routes": last_n_routes,
    }
    self.export_calls.append(call)
    return self.export_result


class _CoordinatorStub:
  """Coordinator providing managers required for service telemetry tests."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    hass: object,
    *,
    notification_manager: _NotificationManagerStub | None = None,
    gps_manager: _GPSManagerStub | None = None,
    walk_manager: object | None = None,
    feeding_manager: _FeedingManagerStub | None = None,
    data_manager: _DataManagerStub | None = None,
    garden_manager: _GardenManagerStub | None = None,
  ) -> None:
    self.hass = hass
    self.config_entry = SimpleNamespace(entry_id="entry")
    self.notification_manager = notification_manager
    self.gps_geofence_manager = gps_manager
    self.walk_manager = walk_manager
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
      walk_manager=walk_manager,
      garden_manager=garden_manager,
    )

  async def async_request_refresh(self) -> None:  # noqa: E111
    self.refresh_called = True

  def register_dog(self, dog_id: str, *, name: str | None = None) -> None:  # noqa: E111
    config = self._dogs.setdefault(dog_id, {})
    if name is not None:
      config.setdefault("name", name)  # noqa: E111

  def get_dog_config(self, dog_id: str) -> dict[str, object] | None:  # noqa: E111
    return self._dogs.get(dog_id)

  def get_configured_dog_ids(self) -> list[str]:  # noqa: E111
    return list(self._dogs.keys())

  def get_configured_dog_name(self, dog_id: str) -> str | None:  # noqa: E111
    config = self._dogs.get(dog_id)
    if not config:
      return None  # noqa: E111
    name = config.get("name")
    return name if isinstance(name, str) else None


async def _setup_service_environment(
  monkeypatch: pytest.MonkeyPatch,
  coordinator: _CoordinatorStub,
  runtime_data: SimpleNamespace,
) -> SimpleNamespace:
  """Register PawControl services against a stub Home Assistant instance."""  # noqa: E111

  hass = SimpleNamespace(  # noqa: E111
    services=_ServiceRegistryStub(),
    data={},
    config=SimpleNamespace(latitude=1.0, longitude=2.0, language="en"),
    bus=_BusStub(),
  )
  hass.config_entries = SimpleNamespace(async_entries=lambda domain: [])  # noqa: E111
  coordinator.hass = hass  # noqa: E111

  resolver = _ResolverStub(coordinator)  # noqa: E111
  monkeypatch.setattr(services, "_coordinator_resolver", lambda hass_instance: resolver)  # noqa: E111
  monkeypatch.setattr(  # noqa: E111
    services, "async_dispatcher_connect", lambda *args, **kwargs: lambda: None
  )
  monkeypatch.setattr(  # noqa: E111
    services, "async_track_time_change", lambda *args, **kwargs: lambda: None
  )
  monkeypatch.setattr(  # noqa: E111
    services, "get_runtime_data", lambda hass_instance, entry: runtime_data
  )

  await services.async_setup_services(hass)  # type: ignore[arg-type]  # noqa: E111
  return hass  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_setup_services_registers_expected_services(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Service setup should register the documented set and skip legacy entries."""  # noqa: E111

  coordinator = _CoordinatorStub(SimpleNamespace())  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111

  expected_services = {  # noqa: E111
    services.SERVICE_ADD_FEEDING,
    services.SERVICE_ADD_GPS_POINT,
    services.SERVICE_UPDATE_HEALTH,
    services.SERVICE_LOG_HEALTH,
    services.SERVICE_LOG_MEDICATION,
    services.SERVICE_LOG_POOP,
    services.SERVICE_START_GROOMING,
    services.SERVICE_TOGGLE_VISITOR_MODE,
    services.SERVICE_GPS_START_WALK,
    services.SERVICE_GPS_END_WALK,
    services.SERVICE_GPS_POST_LOCATION,
    services.SERVICE_GPS_EXPORT_ROUTE,
    services.SERVICE_SETUP_AUTOMATIC_GPS,
    services.SERVICE_SEND_NOTIFICATION,
    services.SERVICE_ACKNOWLEDGE_NOTIFICATION,
    services.SERVICE_CALCULATE_PORTION,
    services.SERVICE_EXPORT_DATA,
    services.SERVICE_ANALYZE_PATTERNS,
    services.SERVICE_GENERATE_REPORT,
    services.SERVICE_DAILY_RESET,
    services.SERVICE_RECALCULATE_HEALTH_PORTIONS,
    services.SERVICE_ADJUST_CALORIES_FOR_ACTIVITY,
    services.SERVICE_ACTIVATE_DIABETIC_FEEDING_MODE,
    services.SERVICE_FEED_WITH_MEDICATION,
    services.SERVICE_GENERATE_WEEKLY_HEALTH_REPORT,
    services.SERVICE_ACTIVATE_EMERGENCY_FEEDING_MODE,
    services.SERVICE_START_DIET_TRANSITION,
    services.SERVICE_CHECK_FEEDING_COMPLIANCE,
    services.SERVICE_ADJUST_DAILY_PORTIONS,
    services.SERVICE_ADD_HEALTH_SNACK,
    services.SERVICE_START_GARDEN,
    services.SERVICE_END_GARDEN,
    services.SERVICE_ADD_GARDEN_ACTIVITY,
    services.SERVICE_CONFIRM_POOP,
    services.SERVICE_UPDATE_WEATHER,
    services.SERVICE_GET_WEATHER_ALERTS,
    services.SERVICE_GET_WEATHER_RECOMMENDATIONS,
  }

  assert set(hass.services.handlers) == expected_services  # noqa: E111

  assert "gps_generate_diagnostics" not in hass.services.handlers  # noqa: E111
  assert "garden_generate_diagnostics" not in hass.services.handlers  # noqa: E111
  assert "garden_history_purge" not in hass.services.handlers  # noqa: E111
  assert "recalculate_garden_stats" not in hass.services.handlers  # noqa: E111
  assert "archive_old_garden_sessions" not in hass.services.handlers  # noqa: E111


@pytest.mark.unit
def test_capture_cache_diagnostics_returns_snapshot() -> None:
  """Helper should normalise diagnostics payloads provided by the data manager."""  # noqa: E111

  payload = {  # noqa: E111
    "coordinator_modules": {
      "stats": {"entries": 3, "hits": 5, "misses": 1},
      "diagnostics": {"per_module": {"feeding": {"hits": 2, "misses": 0}}},
    }
  }

  summary_payload = {  # noqa: E111
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

  summary = CacheRepairAggregate.from_mapping(summary_payload)  # noqa: E111

  runtime_data = SimpleNamespace(data_manager=_DummyDataManager(payload, summary))  # noqa: E111

  diagnostics = services._capture_cache_diagnostics(runtime_data)  # noqa: E111

  assert diagnostics is not None  # noqa: E111
  snapshots = diagnostics["snapshots"]  # noqa: E111
  assert "coordinator_modules" in snapshots  # noqa: E111
  coordinator_snapshot = snapshots["coordinator_modules"]  # noqa: E111
  assert hasattr(coordinator_snapshot, "to_mapping")  # noqa: E111
  assert coordinator_snapshot.to_mapping() == payload["coordinator_modules"]  # noqa: E111

  summary_obj = diagnostics.get("repair_summary")  # noqa: E111
  assert summary_obj is not None  # noqa: E111
  assert hasattr(summary_obj, "to_mapping")  # noqa: E111
  assert summary_obj.to_mapping() == summary_payload  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_perform_daily_reset_records_cache_diagnostics(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Daily reset should persist the latest cache diagnostics snapshot."""  # noqa: E111

  payload = {  # noqa: E111
    "coordinator_modules": {
      "stats": {"entries": 1, "hits": 1, "misses": 0, "hit_rate": 100.0},
      "diagnostics": {"per_module": {"walk": {"hits": 1, "misses": 0}}},
    }
  }

  summary_payload = {  # noqa: E111
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

  summary = CacheRepairAggregate.from_mapping(summary_payload)  # noqa: E111

  telemetry = {  # noqa: E111
    "requested_profile": "advanced",
    "previous_profile": "standard",
    "dogs_count": 2,
    "estimated_entities": 18,
    "timestamp": "2024-02-01T00:00:00+00:00",
    "version": 1,
    "compatibility_warnings": ["gps_disabled"],
    "health_summary": {"healthy": True, "issues": [], "warnings": []},
  }

  coordinator = _DummyCoordinator(options={"reconfigure_telemetry": telemetry})  # noqa: E111
  runtime_data = SimpleNamespace(  # noqa: E111
    coordinator=coordinator,
    walk_manager=_DummyWalkManager(),
    notification_manager=_DummyNotificationManager(),
    data_manager=_DummyDataManager(payload, summary),
    performance_stats={},
  )

  monkeypatch.setattr(  # noqa: E111
    services,
    "get_runtime_data",
    lambda hass, entry: runtime_data,
  )

  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="test-entry")  # noqa: E111

  await services._perform_daily_reset(hass, entry)  # noqa: E111

  assert coordinator.refresh_called  # noqa: E111
  assert runtime_data.walk_manager.cleaned  # noqa: E111
  assert runtime_data.notification_manager.cleaned  # noqa: E111
  buckets = runtime_data.performance_stats["performance_buckets"]  # noqa: E111
  assert "daily_reset_metrics" in buckets  # noqa: E111
  bucket_snapshot = buckets["daily_reset_metrics"]  # noqa: E111
  assert bucket_snapshot["runs"] == 1  # noqa: E111
  assert bucket_snapshot["failures"] == 0  # noqa: E111
  assert bucket_snapshot["durations_ms"]  # noqa: E111
  assert runtime_data.performance_stats["daily_resets"] == 1  # noqa: E111
  last_cache_capture = runtime_data.performance_stats["last_cache_diagnostics"]  # noqa: E111
  snapshots = last_cache_capture["snapshots"]  # noqa: E111
  assert hasattr(snapshots["coordinator_modules"], "to_mapping")  # noqa: E111
  assert snapshots["coordinator_modules"].to_mapping() == payload["coordinator_modules"]  # noqa: E111
  summary_obj = last_cache_capture.get("repair_summary")  # noqa: E111
  assert summary_obj is not None  # noqa: E111
  assert hasattr(summary_obj, "to_mapping")  # noqa: E111
  assert summary_obj.to_mapping() == summary_payload  # noqa: E111
  assert runtime_data.performance_stats["reconfigure_summary"]["warning_count"] == 1  # noqa: E111
  last_result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert last_result["service"] == SERVICE_DAILY_RESET  # noqa: E111
  assert last_result["status"] == "success"  # noqa: E111
  diagnostics = last_result.get("diagnostics")  # noqa: E111
  assert diagnostics is not None  # noqa: E111
  cache_capture = diagnostics.get("cache")  # noqa: E111
  assert cache_capture is not None  # noqa: E111
  snapshots = cache_capture["snapshots"]  # noqa: E111
  assert hasattr(snapshots["coordinator_modules"], "to_mapping")  # noqa: E111
  assert snapshots["coordinator_modules"].to_mapping() == payload["coordinator_modules"]  # noqa: E111
  summary_obj = cache_capture.get("repair_summary")  # noqa: E111
  assert summary_obj is not None  # noqa: E111
  assert hasattr(summary_obj, "to_mapping")  # noqa: E111
  assert summary_obj.to_mapping() == summary_payload  # noqa: E111
  metadata = diagnostics.get("metadata")  # noqa: E111
  assert metadata is not None  # noqa: E111
  assert metadata["refresh_requested"] is True  # noqa: E111
  assert metadata["reconfigure"]["requested_profile"] == "advanced"  # noqa: E111
  assert metadata["reconfigure"]["warning_count"] == 1  # noqa: E111
  assert metadata["reconfigure"]["merge_note_count"] == 0  # noqa: E111
  assert metadata["reconfigure"]["merge_notes"] == []  # noqa: E111
  assert last_result.get("details") == {  # noqa: E111
    "walk_cleanup_performed": True,
    "notifications_cleaned": 2,
    "cache_snapshot": True,
  }

  service_results = runtime_data.performance_stats["service_results"]  # noqa: E111
  assert service_results[-1] is last_result  # noqa: E111

  maintenance_results = runtime_data.performance_stats["maintenance_results"]  # noqa: E111
  assert maintenance_results  # noqa: E111
  maintenance_last = runtime_data.performance_stats["last_maintenance_result"]  # noqa: E111
  assert maintenance_last in maintenance_results  # noqa: E111
  assert maintenance_last["task"] == "daily_reset"  # noqa: E111
  assert maintenance_last["status"] == "success"  # noqa: E111
  assert maintenance_last["details"] == {  # noqa: E111
    "walk_cleanup_performed": True,
    "notifications_cleaned": 2,
    "cache_snapshot": True,
  }
  cache_metrics = maintenance_last["diagnostics"]["cache"]  # noqa: E111
  assert hasattr(cache_metrics["snapshots"]["coordinator_modules"], "to_mapping")  # noqa: E111
  assert (  # noqa: E111
    cache_metrics["snapshots"]["coordinator_modules"].to_mapping()
    == payload["coordinator_modules"]
  )
  repair_summary = cache_metrics.get("repair_summary")  # noqa: E111
  assert repair_summary is not None  # noqa: E111
  assert hasattr(repair_summary, "to_mapping")  # noqa: E111
  assert repair_summary.to_mapping() == summary_payload  # noqa: E111
  maintenance_metadata = maintenance_last["diagnostics"]["metadata"]  # noqa: E111
  assert maintenance_metadata["refresh_requested"] is True  # noqa: E111
  assert maintenance_metadata["reconfigure"]["requested_profile"] == "advanced"  # noqa: E111
  assert maintenance_metadata["reconfigure"]["merge_note_count"] == 0  # noqa: E111
  assert maintenance_metadata["reconfigure"]["merge_notes"] == []  # noqa: E111
  assert isinstance(maintenance_last["recorded_at"], str)  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_perform_daily_reset_records_failure(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Daily reset should capture failures in the service result log."""  # noqa: E111

  telemetry = {  # noqa: E111
    "requested_profile": "advanced",
    "previous_profile": "standard",
    "dogs_count": 2,
    "estimated_entities": 18,
    "timestamp": "2024-02-01T00:00:00+00:00",
    "version": 1,
    "compatibility_warnings": ["gps_disabled"],
    "health_summary": {"healthy": True, "issues": [], "warnings": []},
  }

  runtime_data = SimpleNamespace(  # noqa: E111
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

  monkeypatch.setattr(  # noqa: E111
    services,
    "get_runtime_data",
    lambda hass, entry: runtime_data,
  )

  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="test-entry")  # noqa: E111

  with pytest.raises(RuntimeError, match="coordinator unavailable"):  # noqa: E111
    await services._perform_daily_reset(hass, entry)

  last_result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert last_result["service"] == SERVICE_DAILY_RESET  # noqa: E111
  assert last_result["status"] == "error"  # noqa: E111
  assert "coordinator unavailable" in last_result.get("message", "")  # noqa: E111
  assert last_result.get("details") == {  # noqa: E111
    "walk_cleanup_performed": True,
    "notifications_cleaned": 2,
    "cache_snapshot": False,
  }
  metadata = last_result.get("diagnostics", {}).get("metadata")  # noqa: E111
  assert metadata is not None  # noqa: E111
  assert metadata["refresh_requested"] is False  # noqa: E111
  assert metadata["reconfigure"]["requested_profile"] == "advanced"  # noqa: E111
  assert runtime_data.performance_stats.get("daily_resets", 0) == 0  # noqa: E111

  maintenance_last = runtime_data.performance_stats["last_maintenance_result"]  # noqa: E111
  assert maintenance_last["task"] == "daily_reset"  # noqa: E111
  assert maintenance_last["status"] == "error"  # noqa: E111
  assert maintenance_last["details"] == {  # noqa: E111
    "walk_cleanup_performed": True,
    "notifications_cleaned": 2,
    "cache_snapshot": False,
  }
  failure_metadata = maintenance_last["diagnostics"]["metadata"]  # noqa: E111
  assert failure_metadata["refresh_requested"] is False  # noqa: E111
  assert failure_metadata["reconfigure"]["requested_profile"] == "advanced"  # noqa: E111
  assert (  # noqa: E111
    runtime_data.performance_stats["reconfigure_summary"]["requested_profile"]
    == "advanced"
  )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_perform_daily_reset_normalises_complex_reconfigure_metadata(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Daily reset metadata should remain JSON-safe for complex summaries."""  # noqa: E111

  complex_summary = {  # noqa: E111
    "timestamp": datetime(2024, 3, 15, tzinfo=UTC),
    "warnings": {"critical": ("gps", "walk")},
    "note_sequence": (
      "restore",
      SimpleNamespace(code="501", reason={"id": 9}),
    ),
    "overrides": MappingProxyType({
      1: {
        "threshold": 5.5,
        "set": {1, 2},
        "scheduled_at": datetime(2024, 3, 15, tzinfo=UTC),
      }
    }),
  }

  coordinator = _DummyCoordinator()  # noqa: E111
  runtime_data = SimpleNamespace(  # noqa: E111
    coordinator=coordinator,
    walk_manager=_DummyWalkManager(),
    notification_manager=_DummyNotificationManager(),
    performance_stats={},
  )

  monkeypatch.setattr(services, "_capture_cache_diagnostics", lambda _: None)  # noqa: E111

  def fake_update(runtime: SimpleNamespace) -> Mapping[str, object]:  # noqa: E111
    runtime.performance_stats["reconfigure_summary"] = complex_summary
    return complex_summary

  monkeypatch.setattr(services, "update_runtime_reconfigure_summary", fake_update)  # noqa: E111
  monkeypatch.setattr(services, "get_runtime_data", lambda hass, entry: runtime_data)  # noqa: E111

  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="test-entry")  # noqa: E111

  await services._perform_daily_reset(hass, entry)  # noqa: E111

  metadata = runtime_data.performance_stats["last_service_result"]["diagnostics"][  # noqa: E111
    "metadata"
  ]
  reconfigure = metadata["reconfigure"]  # noqa: E111

  assert reconfigure["timestamp"] == "2024-03-15 00:00:00+00:00"  # noqa: E111
  assert reconfigure["warnings"]["critical"] == ["gps", "walk"]  # noqa: E111
  assert reconfigure["note_sequence"][1].startswith("namespace(code='501'")  # noqa: E111
  overrides = reconfigure["overrides"]["1"]  # noqa: E111
  assert overrides["threshold"] == 5.5  # noqa: E111
  assert overrides["scheduled_at"] == "2024-03-15 00:00:00+00:00"  # noqa: E111
  assert sorted(overrides["set"]) == [1, 2]  # noqa: E111

  maintenance_metadata = runtime_data.performance_stats["last_maintenance_result"][  # noqa: E111
    "diagnostics"
  ]["metadata"]["reconfigure"]
  assert maintenance_metadata == reconfigure  # noqa: E111

  json.dumps(reconfigure)  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_perform_daily_reset_failure_normalises_complex_metadata(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Failure telemetry should also coerce complex metadata payloads."""  # noqa: E111

  complex_summary = {  # noqa: E111
    "timestamp": datetime(2024, 4, 1, tzinfo=UTC),
    "categories": {1: {"issues": {"primary": {"ids": {42, 43}}}}},
    "notes": SimpleNamespace(message="Reset failed"),
    "history": (
      {"attempt": 1, "status": False},
      SimpleNamespace(code="retry"),
    ),
  }

  coordinator = _DummyCoordinator(fail=True, error=RuntimeError("boom"))  # noqa: E111
  runtime_data = SimpleNamespace(  # noqa: E111
    coordinator=coordinator,
    walk_manager=_DummyWalkManager(),
    notification_manager=_DummyNotificationManager(),
    performance_stats={},
  )

  monkeypatch.setattr(services, "_capture_cache_diagnostics", lambda _: None)  # noqa: E111

  def fake_update(runtime: SimpleNamespace) -> Mapping[str, object]:  # noqa: E111
    runtime.performance_stats["reconfigure_summary"] = complex_summary
    return complex_summary

  monkeypatch.setattr(services, "update_runtime_reconfigure_summary", fake_update)  # noqa: E111
  monkeypatch.setattr(services, "get_runtime_data", lambda hass, entry: runtime_data)  # noqa: E111

  hass = SimpleNamespace()  # noqa: E111
  entry = SimpleNamespace(entry_id="test-entry")  # noqa: E111

  with pytest.raises(RuntimeError):  # noqa: E111
    await services._perform_daily_reset(hass, entry)

  metadata = runtime_data.performance_stats["last_service_result"]["diagnostics"][  # noqa: E111
    "metadata"
  ]
  reconfigure = metadata["reconfigure"]  # noqa: E111

  assert reconfigure["timestamp"] == "2024-04-01 00:00:00+00:00"  # noqa: E111
  categories = reconfigure["categories"]["1"]["issues"]["primary"]  # noqa: E111
  assert sorted(categories["ids"]) == [42, 43]  # noqa: E111
  assert reconfigure["notes"].startswith("namespace(message='Reset failed'")  # noqa: E111
  assert reconfigure["history"][0] == {"attempt": 1, "status": False}  # noqa: E111
  assert reconfigure["history"][1].startswith("namespace(code='retry'")  # noqa: E111

  maintenance_metadata = runtime_data.performance_stats["last_maintenance_result"][  # noqa: E111
    "diagnostics"
  ]["metadata"]["reconfigure"]
  assert maintenance_metadata == reconfigure  # noqa: E111

  json.dumps(reconfigure)  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_records_success(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Notification services should record successful telemetry snapshots."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(), notification_manager=notification_manager
  )
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]  # noqa: E111

  await handler(  # noqa: E111
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

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_SEND_NOTIFICATION  # noqa: E111
  assert result["status"] == "success"  # noqa: E111
  details = result.get("details")  # noqa: E111
  assert details is not None  # noqa: E111
  assert details["priority"] == "normal"  # noqa: E111
  assert runtime_data.performance_stats["service_results"][-1] is result  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_recovers_from_invalid_payloads(
  monkeypatch: pytest.MonkeyPatch,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Notification service should fall back to defaults for invalid inputs."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(), notification_manager=notification_manager
  )
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]  # noqa: E111

  with caplog.at_level(logging.WARNING):  # noqa: E111
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

  assert "Unknown notification type" in caplog.text  # noqa: E111
  assert "Unknown notification priority" in caplog.text  # noqa: E111
  assert "Ignoring unsupported notification channel" in caplog.text  # noqa: E111

  assert notification_manager.sent, "notification manager should receive a call"  # noqa: E111
  sent_payload = notification_manager.sent[-1]  # noqa: E111
  assert sent_payload["notification_type"] is NotificationType.SYSTEM_INFO  # noqa: E111
  assert sent_payload["priority"] is NotificationPriority.NORMAL  # noqa: E111
  force_channels = sent_payload["force_channels"]  # noqa: E111
  assert isinstance(force_channels, list)  # noqa: E111
  assert force_channels == [NotificationChannel.MOBILE]  # noqa: E111

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  details = result.get("details")  # noqa: E111
  assert details is not None  # noqa: E111
  assert details["notification_type"] == NotificationType.SYSTEM_INFO.value  # noqa: E111
  assert details["priority"] == NotificationPriority.NORMAL.value  # noqa: E111
  assert details["channels"] == [NotificationChannel.MOBILE.value]  # noqa: E111
  assert details["ignored_channels"] == ["pager"]  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_records_guard_skip(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Guard skips should be captured in service telemetry summaries."""  # noqa: E111

  notification_manager = _GuardSkippingNotificationManager()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(), notification_manager=notification_manager
  )
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]  # noqa: E111

  await handler(  # noqa: E111
    SimpleNamespace(
      data={
        "title": "Alert",
        "message": "Guard telemetry",
      }
    )
  )

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  guard_summary = result.get("guard")  # noqa: E111
  assert guard_summary is not None  # noqa: E111
  assert guard_summary["executed"] == 0  # noqa: E111
  assert guard_summary["skipped"] == 1  # noqa: E111
  assert guard_summary["reasons"]["missing_instance"] == 1  # noqa: E111
  guard_results = guard_summary["results"]  # noqa: E111
  assert isinstance(guard_results, list)  # noqa: E111
  assert guard_results and guard_results[-1]["executed"] is False  # noqa: E111

  guard_metrics = runtime_data.performance_stats["service_guard_metrics"]  # noqa: E111
  assert guard_metrics["executed"] == 0  # noqa: E111
  assert guard_metrics["skipped"] == 1  # noqa: E111
  assert guard_metrics["reasons"]["missing_instance"] == 1  # noqa: E111
  last_results = guard_metrics["last_results"]  # noqa: E111
  assert isinstance(last_results, list)  # noqa: E111
  assert last_results and last_results[-1]["description"] == "guard-test"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_accepts_enum_inputs(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Notification service should accept enum values directly."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(), notification_manager=notification_manager
  )
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]  # noqa: E111

  await handler(  # noqa: E111
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

  sent_payload = notification_manager.sent[-1]  # noqa: E111
  assert sent_payload["notification_type"] is NotificationType.SYSTEM_INFO  # noqa: E111
  assert sent_payload["priority"] is NotificationPriority.HIGH  # noqa: E111
  force_channels = sent_payload["force_channels"]  # noqa: E111
  assert force_channels == [NotificationChannel.MOBILE, NotificationChannel.DISCORD]  # noqa: E111

  details = runtime_data.performance_stats["last_service_result"]["details"]  # noqa: E111
  assert details is not None  # noqa: E111
  assert details["notification_type"] == NotificationType.SYSTEM_INFO.value  # noqa: E111
  assert details["priority"] == NotificationPriority.HIGH.value  # noqa: E111
  assert details["channels"] == [  # noqa: E111
    NotificationChannel.MOBILE.value,
    NotificationChannel.DISCORD.value,
  ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_accepts_string_channel(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Single string channel inputs should normalise to enum lists."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(), notification_manager=notification_manager
  )
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]  # noqa: E111

  await handler(  # noqa: E111
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

  sent_payload = notification_manager.sent[-1]  # noqa: E111
  assert sent_payload["force_channels"] == [NotificationChannel.MOBILE]  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_deduplicates_channels(
  monkeypatch: pytest.MonkeyPatch,
  caplog: pytest.LogCaptureFixture,
) -> None:
  """Duplicate channel inputs should collapse to a single entry."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(), notification_manager=notification_manager
  )
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]  # noqa: E111

  with caplog.at_level(logging.WARNING):  # noqa: E111
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

  sent_payload = notification_manager.sent[-1]  # noqa: E111
  assert sent_payload["force_channels"] == [  # noqa: E111
    NotificationChannel.MOBILE,
    NotificationChannel.DISCORD,
  ]

  # Invalid channels are still reported once for diagnostics  # noqa: E114
  assert "Ignoring unsupported notification channel(s): pager" in caplog.text  # noqa: E111

  details = runtime_data.performance_stats["last_service_result"]["details"]  # noqa: E111
  assert details is not None  # noqa: E111
  assert details["channels"] == [  # noqa: E111
    NotificationChannel.MOBILE.value,
    NotificationChannel.DISCORD.value,
  ]
  assert details["ignored_channels"] == ["pager"]  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_rejects_invalid_expiry(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Invalid expiry overrides should raise service validation errors."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(), notification_manager=notification_manager
  )
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]  # noqa: E111

  with pytest.raises(  # noqa: E111
    ServiceValidationError,
    match="expires_in_hours must be a number",
  ):
    await handler(
      SimpleNamespace(
        data={
          "title": "Invalid expiry",
          "message": "Rejected override",
          "expires_in_hours": "later",
        }
      )
    )

  assert notification_manager.sent == []  # noqa: E111
  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert result["message"] == "expires_in_hours must be a number"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_rejects_non_positive_expiry(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Non-positive expiry overrides should raise service validation errors."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(), notification_manager=notification_manager
  )
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]  # noqa: E111

  with pytest.raises(  # noqa: E111
    ServiceValidationError,
    match="expires_in_hours must be greater than 0",
  ):
    await handler(
      SimpleNamespace(
        data={
          "title": "Non-positive expiry",
          "message": "Rejected override",
          "expires_in_hours": -1,
        }
      )
    )

  assert notification_manager.sent == []  # noqa: E111
  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert result["message"] == "expires_in_hours must be greater than 0"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_rejects_blank_title(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Blank titles should raise service validation errors."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(), notification_manager=notification_manager
  )
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]  # noqa: E111

  with pytest.raises(  # noqa: E111
    ServiceValidationError,
    match="title must be a non-empty string",
  ):
    await handler(
      SimpleNamespace(
        data={
          "title": "   ",
          "message": "Rejected override",
        }
      )
    )

  assert notification_manager.sent == []  # noqa: E111
  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert result["message"] == "title must be a non-empty string"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_accepts_valid_expiry(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Valid expiry overrides should be converted to timedeltas."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(), notification_manager=notification_manager
  )
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]  # noqa: E111

  await handler(  # noqa: E111
    SimpleNamespace(
      data={
        "title": "Expires soon",
        "message": "Override respected",
        "expires_in_hours": "1.5",
      }
    )
  )

  sent_payload = notification_manager.sent[-1]  # noqa: E111
  expires_in = sent_payload["expires_in"]  # noqa: E111
  assert isinstance(expires_in, timedelta)  # noqa: E111
  assert expires_in == timedelta(hours=1.5)  # noqa: E111

  details = runtime_data.performance_stats["last_service_result"]["details"]  # noqa: E111
  assert details is not None  # noqa: E111
  assert details["expires_in_hours"] == pytest.approx(1.5)  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_notification_service_records_failure(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Notification telemetry should capture errors when sends fail."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  notification_manager.fail_send = True  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(), notification_manager=notification_manager
  )
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SEND_NOTIFICATION]  # noqa: E111

  with pytest.raises(services.HomeAssistantError, match="send failed"):  # noqa: E111
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

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_SEND_NOTIFICATION  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert result.get("message") == "send failed"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_acknowledge_notification_service_records_success(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Acknowledging notifications should append success telemetry."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(), notification_manager=notification_manager
  )
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_ACKNOWLEDGE_NOTIFICATION]  # noqa: E111

  await handler(SimpleNamespace(data={"notification_id": "notif-1"}))  # noqa: E111

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_ACKNOWLEDGE_NOTIFICATION  # noqa: E111
  assert result["status"] == "success"  # noqa: E111
  details = result.get("details")  # noqa: E111
  assert details is not None and details.get("acknowledged") is True  # noqa: E111
  assert coordinator.refresh_called  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_acknowledge_notification_records_not_found(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Telemetry should capture missing notifications when acknowledgements fail."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  notification_manager.ack_exists = False  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(), notification_manager=notification_manager
  )
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_ACKNOWLEDGE_NOTIFICATION]  # noqa: E111

  with pytest.raises(  # noqa: E111
    services.HomeAssistantError, match="No PawControl notification with ID"
  ):
    await handler(SimpleNamespace(data={"notification_id": "missing"}))

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_ACKNOWLEDGE_NOTIFICATION  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert "No PawControl notification" in result.get("message", "")  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_gps_start_walk_service_rejects_invalid_boolean_toggle(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """GPS walk start should reject non-boolean toggle values."""  # noqa: E111

  gps_manager = _GPSManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), gps_manager=gps_manager)  # noqa: E111
  coordinator.register_dog("fido")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_GPS_START_WALK]  # noqa: E111

  with pytest.raises(  # noqa: E111
    ServiceValidationError,
    match=r"track_route must be a boolean \(got str\)",
  ):
    await handler(SimpleNamespace(data={"dog_id": "fido", "track_route": "maybe"}))

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_GPS_START_WALK  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert "track_route must be a boolean (got str)" in result.get("message", "")  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
  ("service_value", "expected"),
  [
    pytest.param("true", True, id="str-true"),
    pytest.param("false", False, id="str-false"),
    pytest.param(1, True, id="int-1"),
    pytest.param(0, False, id="int-0"),
  ],
)
async def test_gps_start_walk_service_coerces_common_boolean_inputs(
  monkeypatch: pytest.MonkeyPatch,
  service_value: object,
  expected: bool,
) -> None:
  """GPS walk start should accept common Home Assistant boolean shapes."""  # noqa: E111

  gps_manager = _GPSManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), gps_manager=gps_manager)  # noqa: E111
  coordinator.register_dog("fido")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_GPS_START_WALK]  # noqa: E111

  await handler(SimpleNamespace(data={"dog_id": "fido", "track_route": service_value}))  # noqa: E111

  assert gps_manager.last_start_tracking["track_route"] is expected  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setup_automatic_gps_service_records_success(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Automation services should capture configuration telemetry."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  gps_manager = _GPSManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    gps_manager=gps_manager,
  )
  coordinator.register_dog("fido")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SETUP_AUTOMATIC_GPS]  # noqa: E111

  await handler(  # noqa: E111
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

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_SETUP_AUTOMATIC_GPS  # noqa: E111
  assert result["status"] == "success"  # noqa: E111
  details = result.get("details")  # noqa: E111
  assert details is not None  # noqa: E111
  assert details["safe_zone_radius"] == 75  # noqa: E111
  assert gps_manager.last_config is not None  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setup_automatic_gps_service_rejects_invalid_interval(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """GPS setup should reject invalid update intervals with clear errors."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  gps_manager = _GPSManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    gps_manager=gps_manager,
  )
  coordinator.register_dog("fido")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SETUP_AUTOMATIC_GPS]  # noqa: E111

  with pytest.raises(  # noqa: E111
    ServiceValidationError,
    match="update_interval_seconds must be a whole number",
  ):
    await handler(
      SimpleNamespace(data={"dog_id": "fido", "update_interval_seconds": "fast"})
    )

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_SETUP_AUTOMATIC_GPS  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert "update_interval_seconds must be a whole number" in result.get("message", "")  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setup_automatic_gps_service_rejects_invalid_safe_zone_radius(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """GPS setup should route safe-zone validation through shared validators."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  gps_manager = _GPSManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    gps_manager=gps_manager,
  )
  coordinator.register_dog("fido")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SETUP_AUTOMATIC_GPS]  # noqa: E111

  with pytest.raises(  # noqa: E111
    ServiceValidationError,
    match="safe_zone_radius must be a number",
  ):
    await handler(SimpleNamespace(data={"dog_id": "fido", "safe_zone_radius": "wide"}))

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_SETUP_AUTOMATIC_GPS  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert "safe_zone_radius must be a number" in result.get("message", "")  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setup_automatic_gps_service_rejects_out_of_range_safe_zone_radius(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """GPS setup should reject safe-zone radius values outside allowed bounds."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  gps_manager = _GPSManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    gps_manager=gps_manager,
  )
  coordinator.register_dog("fido")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SETUP_AUTOMATIC_GPS]  # noqa: E111

  with pytest.raises(  # noqa: E111
    ServiceValidationError,
    match="safe_zone_radius must be between 10.0 and 10000.0 m",
  ):
    await handler(SimpleNamespace(data={"dog_id": "fido", "safe_zone_radius": 1}))

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_SETUP_AUTOMATIC_GPS  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert "safe_zone_radius must be between 10.0 and 10000.0 m" in result.get(  # noqa: E111
    "message", ""
  )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setup_automatic_gps_service_rejects_invalid_boolean_toggle(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """GPS setup should reject non-boolean toggle values."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  gps_manager = _GPSManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    gps_manager=gps_manager,
  )
  coordinator.register_dog("fido")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SETUP_AUTOMATIC_GPS]  # noqa: E111

  with pytest.raises(  # noqa: E111
    ServiceValidationError,
    match=r"auto_start_walk must be a boolean \(got str\)",
  ):
    await handler(
      SimpleNamespace(data={"dog_id": "fido", "auto_start_walk": "perhaps"})
    )

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_SETUP_AUTOMATIC_GPS  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert "auto_start_walk must be a boolean (got str)" in result.get("message", "")  # noqa: E111


async def test_setup_automatic_gps_service_records_failure(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Automation telemetry should note failures when configuration raises."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  gps_manager = _GPSManagerStub()  # noqa: E111
  gps_manager.fail_configure = True  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    gps_manager=gps_manager,
  )
  coordinator.register_dog("fido")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_SETUP_AUTOMATIC_GPS]  # noqa: E111

  with pytest.raises(services.HomeAssistantError, match="configure failed"):  # noqa: E111
    await handler(SimpleNamespace(data={"dog_id": "fido"}))

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_SETUP_AUTOMATIC_GPS  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert result.get("message") == "configure failed"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_gps_export_route_service_records_success(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """GPS export service should notify and log telemetry for multi-route payloads."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  gps_manager = _GPSManagerStub()  # noqa: E111
  export_payload: GPSRouteExportJSONPayload = {  # noqa: E111
    "format": "json",
    "filename": "fido_routes.json",
    "routes_count": 2,
    "content": {
      "dog_id": "fido",
      "export_timestamp": "2024-05-01T12:00:00+00:00",
      "routes": [
        {
          "start_time": "2024-05-01T11:30:00+00:00",
          "end_time": "2024-05-01T12:00:00+00:00",
          "duration_minutes": 30.0,
          "distance_km": 2.5,
          "avg_speed_kmh": 5.0,
          "route_quality": "excellent",
          "gps_points": [
            {
              "latitude": 40.0,
              "longitude": -73.0,
              "timestamp": "2024-05-01T11:30:00+00:00",
            }
          ],
          "geofence_events": [
            {
              "event_type": "enter",
              "zone_name": "Home",
              "timestamp": "2024-05-01T11:30:00+00:00",
            }
          ],
        },
        {
          "start_time": "2024-05-02T08:15:00+00:00",
          "end_time": "2024-05-02T08:45:00+00:00",
          "duration_minutes": 30.0,
          "distance_km": 2.0,
          "avg_speed_kmh": 4.0,
          "route_quality": "good",
          "gps_points": [
            {
              "latitude": 41.0,
              "longitude": -74.0,
              "timestamp": "2024-05-02T08:15:00+00:00",
            }
          ],
          "geofence_events": [
            {
              "event_type": "exit",
              "zone_name": "Park",
              "timestamp": "2024-05-02T08:45:00+00:00",
            }
          ],
        },
      ],
    },
  }
  gps_manager.export_result = export_payload  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    gps_manager=gps_manager,
  )
  coordinator.register_dog("fido", name="Fido")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_GPS_EXPORT_ROUTE]  # noqa: E111

  await handler(  # noqa: E111
    SimpleNamespace(data={"dog_id": "fido", "format": "json", "last_n_walks": 3})
  )

  assert gps_manager.export_calls == [  # noqa: E111
    {
      "dog_id": "fido",
      "export_format": "json",
      "last_n_routes": 3,
    }
  ]
  assert len(notification_manager.sent) == 1  # noqa: E111
  notification_payload = notification_manager.sent[0]  # noqa: E111
  assert notification_payload["title"] == "Route Export Complete"  # noqa: E111
  assert notification_payload["dog_id"] == "fido"  # noqa: E111
  assert (  # noqa: E111
    notification_payload["message"] == "Exported 2 route(s) for fido in json format"
  )

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_GPS_EXPORT_ROUTE  # noqa: E111
  assert result["status"] == "success"  # noqa: E111
  details = result.get("details")  # noqa: E111
  assert details is not None  # noqa: E111
  assert details["routes_count"] == 2  # noqa: E111
  assert details["result"] == "exported"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_gps_export_route_service_records_no_routes(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """GPS export service should log telemetry when no history is present."""  # noqa: E111

  notification_manager = _NotificationManagerStub()  # noqa: E111
  gps_manager = _GPSManagerStub()  # noqa: E111
  gps_manager.export_result = None  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    gps_manager=gps_manager,
  )
  coordinator.register_dog("luna")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_GPS_EXPORT_ROUTE]  # noqa: E111

  await handler(SimpleNamespace(data={"dog_id": "luna"}))  # noqa: E111

  assert gps_manager.export_calls == [  # noqa: E111
    {
      "dog_id": "luna",
      "export_format": "gpx",
      "last_n_routes": 1,
    }
  ]
  assert notification_manager.sent == []  # noqa: E111

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_GPS_EXPORT_ROUTE  # noqa: E111
  assert result["status"] == "success"  # noqa: E111
  details = result.get("details")  # noqa: E111
  assert details is not None  # noqa: E111
  assert details["routes_count"] == 0  # noqa: E111
  assert details["result"] == "no_routes"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_health_snack_records_success(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Health snack service should append success telemetry with details."""  # noqa: E111

  feeding_manager = _FeedingManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), feeding_manager=feeding_manager)  # noqa: E111
  coordinator.register_dog("buddy", name="Buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_ADD_HEALTH_SNACK]  # noqa: E111

  await handler(  # noqa: E111
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

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_ADD_HEALTH_SNACK  # noqa: E111
  assert result["status"] == "success"  # noqa: E111
  details = result.get("details")  # noqa: E111
  assert details is not None and details["snack_type"] == "carrot"  # noqa: E111
  assert feeding_manager.calls and feeding_manager.calls[0]["dog_id"] == "buddy"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_health_snack_records_failure(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Health snack telemetry should capture Home Assistant errors."""  # noqa: E111

  feeding_manager = _FeedingManagerStub()  # noqa: E111
  feeding_manager.fail_with = services.HomeAssistantError("snack failed")  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), feeding_manager=feeding_manager)  # noqa: E111
  coordinator.register_dog("buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_ADD_HEALTH_SNACK]  # noqa: E111

  with pytest.raises(services.HomeAssistantError, match="snack failed"):  # noqa: E111
    await handler(
      SimpleNamespace(data={"dog_id": "buddy", "snack_type": "carrot", "amount": 1.0})
    )

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_ADD_HEALTH_SNACK  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert result.get("message") == "snack failed"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_notifies_on_issues(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Compliance service should forward typed payloads to notifications."""  # noqa: E111

  feeding_manager = _FeedingManagerStub()  # noqa: E111
  feeding_manager.compliance_result = {  # noqa: E111
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

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    feeding_manager=feeding_manager,
  )
  coordinator.register_dog("buddy", name="Buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]  # noqa: E111

  context = Context(user_id="user-1", parent_id="parent-1", context_id="ctx-1")  # noqa: E111

  await handler(  # noqa: E111
    SimpleNamespace(
      data={
        "dog_id": "buddy",
        "days_to_check": 3,
        "notify_on_issues": True,
      },
      context=context,
    )
  )

  assert feeding_manager.compliance_calls == [  # noqa: E111
    {"dog_id": "buddy", "days_to_check": 3, "notify_on_issues": True}
  ]
  assert notification_manager.compliance_calls  # noqa: E111
  compliance_payload = notification_manager.compliance_calls[0]  # noqa: E111
  assert compliance_payload["dog_id"] == "buddy"  # noqa: E111
  assert compliance_payload["dog_name"] == "Buddy"  # noqa: E111
  compliance_result = cast(FeedingComplianceCompleted, compliance_payload["compliance"])  # noqa: E111
  assert compliance_result["status"] == "completed"  # noqa: E111

  fired_events = hass.bus.fired  # noqa: E111
  assert len(fired_events) == 1  # noqa: E111
  event = fired_events[0]  # noqa: E111
  assert event["event_type"] == EVENT_FEEDING_COMPLIANCE_CHECKED  # noqa: E111
  event_data = cast(FeedingComplianceEventPayload, event["event_data"])  # noqa: E111
  assert event_data["dog_id"] == "buddy"  # noqa: E111
  assert event_data["dog_name"] == "Buddy"  # noqa: E111
  assert event_data["notification_sent"] is True  # noqa: E111
  assert event_data["result"] is not feeding_manager.compliance_result  # noqa: E111
  assert event_data["result"]["compliance_score"] == 72  # noqa: E111
  summary = event_data.get("localized_summary")  # noqa: E111
  assert summary is not None  # noqa: E111
  assert summary["title"].startswith("🍽️ Feeding compliance alert")  # noqa: E111
  assert summary["score_line"].startswith("Score: 72")  # noqa: E111
  assert summary["issues"] == ["2024-05-01: Underfed by 20%"]  # noqa: E111
  assert summary["missed_meals"] == ["2024-05-01: 1/2 meals"]  # noqa: E111
  kwargs = event["kwargs"]  # noqa: E111
  assert kwargs.get("context") is context  # noqa: E111
  time_fired = kwargs.get("time_fired")  # noqa: E111
  assert isinstance(time_fired, datetime)  # noqa: E111
  assert time_fired.tzinfo is not None  # noqa: E111
  assert event_data["context_id"] == context.id  # noqa: E111
  assert event_data["parent_id"] == context.parent_id  # noqa: E111
  assert event_data["user_id"] == context.user_id  # noqa: E111

  last_result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert last_result["service"] == services.SERVICE_CHECK_FEEDING_COMPLIANCE  # noqa: E111
  assert last_result["status"] == "success"  # noqa: E111
  details = last_result["details"]  # noqa: E111
  assert details["score"] == 72  # noqa: E111
  details_summary = details.get("localized_summary")  # noqa: E111
  assert details_summary is not None  # noqa: E111
  assert details_summary["title"] == summary["title"]  # noqa: E111
  assert details_summary["issues"] == summary["issues"]  # noqa: E111
  diagnostics = last_result.get("diagnostics")  # noqa: E111
  assert diagnostics is not None  # noqa: E111
  metadata = diagnostics.get("metadata")  # noqa: E111
  assert metadata is not None  # noqa: E111
  assert metadata["notification_sent"] is True  # noqa: E111
  assert metadata["days_to_check"] == 3  # noqa: E111
  assert metadata["context_id"] == context.id  # noqa: E111
  assert metadata["parent_id"] == context.parent_id  # noqa: E111
  assert metadata["user_id"] == context.user_id  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_skips_when_clean(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Clean compliance results should not trigger notifications."""  # noqa: E111

  feeding_manager = _FeedingManagerStub()  # noqa: E111
  feeding_manager.compliance_result = {  # noqa: E111
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

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    feeding_manager=feeding_manager,
  )
  coordinator.register_dog("buddy", name="Buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]  # noqa: E111

  await handler(  # noqa: E111
    SimpleNamespace(
      data={
        "dog_id": "buddy",
        "days_to_check": 5,
        "notify_on_issues": True,
      }
    )
  )

  assert notification_manager.compliance_calls == []  # noqa: E111

  fired_events = hass.bus.fired  # noqa: E111
  assert len(fired_events) == 1  # noqa: E111
  event = fired_events[0]  # noqa: E111
  assert event["event_type"] == EVENT_FEEDING_COMPLIANCE_CHECKED  # noqa: E111
  event_data = cast(FeedingComplianceEventPayload, event["event_data"])  # noqa: E111
  assert isinstance(event_data, dict)  # noqa: E111
  assert event_data["dog_id"] == "buddy"  # noqa: E111
  assert event_data["notification_sent"] is False  # noqa: E111
  assert event_data["result"]["compliance_score"] == 100  # noqa: E111
  summary = event_data.get("localized_summary")  # noqa: E111
  assert summary is not None  # noqa: E111
  assert summary["score_line"].startswith("Score: 100")  # noqa: E111
  assert summary["issues"] == []  # noqa: E111
  assert summary["missed_meals"] == []  # noqa: E111

  last_result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert last_result["service"] == services.SERVICE_CHECK_FEEDING_COMPLIANCE  # noqa: E111
  assert last_result["status"] == "success"  # noqa: E111
  details_summary = last_result["details"].get("localized_summary")  # noqa: E111
  assert details_summary is not None  # noqa: E111
  assert details_summary["score_line"].startswith("Score: 100")  # noqa: E111
  assert last_result["details"]["score"] == 100  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_respects_notify_toggle(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Notifications are skipped when notify_on_issues is False."""  # noqa: E111

  feeding_manager = _FeedingManagerStub()  # noqa: E111
  feeding_manager.compliance_result = {  # noqa: E111
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

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    feeding_manager=feeding_manager,
  )
  coordinator.register_dog("buddy", name="Buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]  # noqa: E111

  await handler(  # noqa: E111
    SimpleNamespace(
      data={
        "dog_id": "buddy",
        "days_to_check": 2,
        "notify_on_issues": False,
      }
    )
  )

  assert notification_manager.compliance_calls == []  # noqa: E111

  fired_events = hass.bus.fired  # noqa: E111
  assert len(fired_events) == 1  # noqa: E111
  event = fired_events[0]  # noqa: E111
  assert event["event_type"] == EVENT_FEEDING_COMPLIANCE_CHECKED  # noqa: E111
  event_data = cast(FeedingComplianceEventPayload, event["event_data"])  # noqa: E111
  assert isinstance(event_data, dict)  # noqa: E111
  assert event_data["notify_on_issues"] is False  # noqa: E111
  assert event_data["notification_sent"] is False  # noqa: E111

  last_result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert last_result["status"] == "success"  # noqa: E111
  diagnostics = last_result.get("diagnostics")  # noqa: E111
  assert diagnostics is not None  # noqa: E111
  metadata = diagnostics.get("metadata")  # noqa: E111
  assert metadata is not None and metadata["notify_on_issues"] is False  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_sanitises_structured_messages(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Structured compliance messages should be normalised to readable text."""  # noqa: E111

  feeding_manager = _FeedingManagerStub()  # noqa: E111
  feeding_manager.compliance_result = {  # noqa: E111
    "status": "no_data",
    "message": {"description": "Telemetry offline", "code": 503},
  }

  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    feeding_manager=feeding_manager,
  )
  coordinator.register_dog("buddy", name="Buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  published_payloads: list[FeedingComplianceEventPayload] = []  # noqa: E111

  async def _capture_publish(  # noqa: E111
    hass: object,
    entry: object,
    payload: FeedingComplianceEventPayload,
    *,
    context_metadata: dict[str, object] | None = None,
  ) -> None:
    published_payloads.append(payload)

  monkeypatch.setattr(  # noqa: E111
    services,
    "async_publish_feeding_compliance_issue",
    _capture_publish,
  )

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]  # noqa: E111

  await handler(  # noqa: E111
    SimpleNamespace(
      data={
        "dog_id": "buddy",
        "days_to_check": 3,
        "notify_on_issues": True,
      }
    )
  )

  assert notification_manager.compliance_calls  # noqa: E111
  assert published_payloads  # noqa: E111

  event = hass.bus.fired[0]  # noqa: E111
  event_data = cast(FeedingComplianceEventPayload, event["event_data"])  # noqa: E111
  assert event_data["result"]["message"] == "Telemetry offline"  # noqa: E111

  summary = event_data["localized_summary"]  # noqa: E111
  assert summary["message"] == "Telemetry offline"  # noqa: E111

  recorded = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  details = recorded["details"]  # noqa: E111
  assert details["message"] == "Telemetry offline"  # noqa: E111
  assert details["localized_summary"]["message"] == "Telemetry offline"  # noqa: E111

  published = published_payloads[0]  # noqa: E111
  published_result = cast(FeedingComplianceNoData, published["result"])  # noqa: E111
  assert published_result["message"] == "Telemetry offline"  # noqa: E111


@pytest.mark.unit
def test_merge_service_context_metadata_respects_include_none() -> None:
  """Helper should optionally persist ``None`` metadata values."""  # noqa: E111

  target: dict[str, object] = {"existing": True}  # noqa: E111
  metadata = {"context_id": None, "parent_id": "parent-123"}  # noqa: E111

  services._merge_service_context_metadata(target, metadata)  # noqa: E111

  assert "context_id" not in target  # noqa: E111
  assert target["parent_id"] == "parent-123"  # noqa: E111

  services._merge_service_context_metadata(target, metadata, include_none=True)  # noqa: E111

  assert target["context_id"] is None  # noqa: E111
  assert target["parent_id"] == "parent-123"  # noqa: E111


@pytest.mark.unit
def test_merge_service_context_metadata_preserves_additional_keys() -> None:
  """Additional context metadata should be forwarded unchanged."""  # noqa: E111

  target: dict[str, object] = {}  # noqa: E111
  metadata = {"context_id": "ctx-123", "source": "stub"}  # noqa: E111

  services._merge_service_context_metadata(target, metadata)  # noqa: E111

  assert target["context_id"] == "ctx-123"  # noqa: E111
  assert target["source"] == "stub"  # noqa: E111


@pytest.mark.unit
def test_merge_service_context_metadata_ignores_non_string_keys() -> None:
  """Non-string metadata keys are ignored for safety."""  # noqa: E111

  target: dict[str, object] = {}  # noqa: E111
  metadata = {"context_id": "ctx-123", 42: "skip-me"}  # noqa: E111

  services._merge_service_context_metadata(target, metadata)  # noqa: E111

  assert target == {"context_id": "ctx-123"}  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_builds_context_from_stub(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Context metadata should be normalised when Home Assistant provides stubs."""  # noqa: E111

  feeding_manager = _FeedingManagerStub()  # noqa: E111
  feeding_manager.compliance_result = {  # noqa: E111
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

  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=_NotificationManagerStub(),
    feeding_manager=feeding_manager,
  )
  coordinator.register_dog("buddy", name="Buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]  # noqa: E111

  context_stub = SimpleNamespace(  # noqa: E111
    id="ctx-stub",
    parent_id="parent-stub",
    user_id="user-stub",
  )

  await handler(  # noqa: E111
    SimpleNamespace(
      data={
        "dog_id": "buddy",
        "days_to_check": 4,
        "notify_on_issues": True,
      },
      context=context_stub,
    )
  )

  event = hass.bus.fired[0]  # noqa: E111
  kwargs = event["kwargs"]  # noqa: E111
  event_context = kwargs.get("context")  # noqa: E111
  assert event_context is not context_stub  # noqa: E111
  assert getattr(event_context, "id", None) == "ctx-stub"  # noqa: E111
  assert getattr(event_context, "parent_id", None) == "parent-stub"  # noqa: E111
  assert getattr(event_context, "user_id", None) == "user-stub"  # noqa: E111

  event_data = cast(FeedingComplianceEventPayload, event["event_data"])  # noqa: E111
  assert event_data["context_id"] == "ctx-stub"  # noqa: E111
  assert event_data["parent_id"] == "parent-stub"  # noqa: E111
  assert event_data["user_id"] == "user-stub"  # noqa: E111

  metadata = runtime_data.performance_stats["last_service_result"]["diagnostics"][  # noqa: E111
    "metadata"
  ]
  assert metadata["context_id"] == "ctx-stub"  # noqa: E111
  assert metadata["parent_id"] == "parent-stub"  # noqa: E111
  assert metadata["user_id"] == "user-stub"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_builds_context_from_mapping(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Mapping-based service contexts should be normalised for telemetry."""  # noqa: E111

  feeding_manager = _FeedingManagerStub()  # noqa: E111
  feeding_manager.compliance_result = {  # noqa: E111
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

  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=_NotificationManagerStub(),
    feeding_manager=feeding_manager,
  )
  coordinator.register_dog("buddy", name="Buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]  # noqa: E111

  context_mapping = {  # noqa: E111
    "context_id": "ctx-mapping",
    "parent_id": "parent-mapping",
    "user_id": "user-mapping",
  }

  await handler(  # noqa: E111
    SimpleNamespace(
      data={
        "dog_id": "buddy",
        "days_to_check": 5,
        "notify_on_issues": True,
      },
      context=context_mapping,
    )
  )

  event = hass.bus.fired[0]  # noqa: E111
  kwargs = event["kwargs"]  # noqa: E111
  event_context = kwargs.get("context")  # noqa: E111
  assert event_context is not None  # noqa: E111
  assert getattr(event_context, "id", None) == "ctx-mapping"  # noqa: E111
  assert getattr(event_context, "parent_id", None) == "parent-mapping"  # noqa: E111
  assert getattr(event_context, "user_id", None) == "user-mapping"  # noqa: E111

  event_data = cast(FeedingComplianceEventPayload, event["event_data"])  # noqa: E111
  assert event_data["context_id"] == "ctx-mapping"  # noqa: E111
  assert event_data["parent_id"] == "parent-mapping"  # noqa: E111
  assert event_data["user_id"] == "user-mapping"  # noqa: E111

  metadata = runtime_data.performance_stats["last_service_result"]["diagnostics"][  # noqa: E111
    "metadata"
  ]
  assert metadata["context_id"] == "ctx-mapping"  # noqa: E111
  assert metadata["parent_id"] == "parent-mapping"  # noqa: E111
  assert metadata["user_id"] == "user-mapping"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_feeding_compliance_records_errors(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Service should capture telemetry when compliance checks fail."""  # noqa: E111

  feeding_manager = _FeedingManagerStub()  # noqa: E111
  feeding_manager.compliance_error = services.HomeAssistantError("compliance failed")  # noqa: E111
  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    feeding_manager=feeding_manager,
  )
  coordinator.register_dog("buddy", name="Buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[SERVICE_CHECK_FEEDING_COMPLIANCE]  # noqa: E111

  with pytest.raises(services.HomeAssistantError, match="compliance failed"):  # noqa: E111
    await handler(
      SimpleNamespace(
        data={
          "dog_id": "buddy",
          "days_to_check": 3,
          "notify_on_issues": True,
        }
      )
    )

  assert hass.bus.fired == []  # noqa: E111
  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_CHECK_FEEDING_COMPLIANCE  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert result["message"] == "compliance failed"  # noqa: E111
  diagnostics = result.get("diagnostics")  # noqa: E111
  assert diagnostics is not None  # noqa: E111
  metadata = diagnostics.get("metadata")  # noqa: E111
  assert metadata is not None  # noqa: E111
  assert metadata["days_to_check"] == 3  # noqa: E111
  assert metadata["notify_on_issues"] is True  # noqa: E111
  assert "context_id" not in metadata  # noqa: E111


async def test_log_poop_service_records_success(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Poop logging should emit success telemetry with timestamp details."""  # noqa: E111

  data_manager = _DataManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), data_manager=data_manager)  # noqa: E111
  coordinator.register_dog("buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111
  timestamp = datetime(2024, 1, 1, tzinfo=UTC)  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_LOG_POOP]  # noqa: E111

  await handler(  # noqa: E111
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

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_LOG_POOP  # noqa: E111
  assert result["status"] == "success"  # noqa: E111
  details = result.get("details")  # noqa: E111
  assert details is not None and details["timestamp"].startswith("2024-01-01T00:00:00")  # noqa: E111
  assert data_manager.poop_calls and data_manager.poop_calls[0]["dog_id"] == "buddy"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_log_poop_service_records_failure(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Poop logging telemetry should capture Home Assistant errors."""  # noqa: E111

  data_manager = _DataManagerStub()  # noqa: E111
  data_manager.fail_log = services.HomeAssistantError("poop failed")  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), data_manager=data_manager)  # noqa: E111
  coordinator.register_dog("buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_LOG_POOP]  # noqa: E111

  with pytest.raises(services.HomeAssistantError, match="poop failed"):  # noqa: E111
    await handler(SimpleNamespace(data={"dog_id": "buddy"}))

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_LOG_POOP  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert result.get("message") == "poop failed"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_grooming_records_success(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Grooming service should store telemetry for successful sessions."""  # noqa: E111

  reminder_sent_at = datetime.now(UTC)  # noqa: E111
  data_manager = _DataManagerStub()  # noqa: E111
  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    data_manager=data_manager,
  )
  coordinator.register_dog("buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_START_GROOMING]  # noqa: E111

  await handler(  # noqa: E111
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

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_START_GROOMING  # noqa: E111
  assert result["status"] == "success"  # noqa: E111
  details = result.get("details")  # noqa: E111
  assert details is not None and details["session_id"] == data_manager.next_session_id  # noqa: E111
  assert details["reminder_attached"] is True  # noqa: E111
  reminder_details = details.get("reminder")  # noqa: E111
  assert reminder_details is not None  # noqa: E111
  assert reminder_details["id"] == "rem-123"  # noqa: E111
  assert reminder_details["type"] == "auto_schedule"  # noqa: E111
  expected_iso = reminder_sent_at.astimezone(UTC).isoformat()  # noqa: E111
  assert reminder_details["sent_at"] == expected_iso  # noqa: E111

  diagnostics = result.get("diagnostics")  # noqa: E111
  assert diagnostics is not None  # noqa: E111
  metadata = diagnostics.get("metadata")  # noqa: E111
  assert metadata is not None  # noqa: E111
  assert metadata["reminder_attached"] is True  # noqa: E111
  assert metadata["reminder_id"] == "rem-123"  # noqa: E111
  assert metadata["reminder_type"] == "auto_schedule"  # noqa: E111
  assert metadata["reminder_sent_at"] == expected_iso  # noqa: E111
  assert data_manager.groom_calls and data_manager.groom_calls[0]["dog_id"] == "buddy"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_grooming_localizes_notification(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Grooming notifications should respect the active Home Assistant language."""  # noqa: E111

  data_manager = _DataManagerStub()  # noqa: E111
  notification_manager = _NotificationManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(  # noqa: E111
    SimpleNamespace(),
    notification_manager=notification_manager,
    data_manager=data_manager,
  )
  coordinator.register_dog("buddy", name="Buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  hass.config.language = "de"  # noqa: E111

  handler = hass.services.handlers[services.SERVICE_START_GROOMING]  # noqa: E111

  await handler(  # noqa: E111
    SimpleNamespace(
      data={
        "dog_id": "buddy",
        "grooming_type": "bath",
        "groomer": "Jamie",
        "estimated_duration_minutes": 45,
      }
    )
  )

  assert notification_manager.sent, "Expected localized grooming notification"  # noqa: E111
  payload = notification_manager.sent[0]  # noqa: E111
  assert payload["title"] == "🛁 Pflege gestartet: Buddy"  # noqa: E111
  assert payload["message"] == "Gestartet bath für Buddy mit Jamie (ca. 45 Min.)"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_grooming_records_failure(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Grooming telemetry should track Home Assistant errors."""  # noqa: E111

  data_manager = _DataManagerStub()  # noqa: E111
  data_manager.fail_groom = services.HomeAssistantError("groom failed")  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), data_manager=data_manager)  # noqa: E111
  coordinator.register_dog("buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_START_GROOMING]  # noqa: E111

  with pytest.raises(services.HomeAssistantError, match="groom failed"):  # noqa: E111
    await handler(SimpleNamespace(data={"dog_id": "buddy", "grooming_type": "bath"}))

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_START_GROOMING  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert result.get("message") == "groom failed"  # noqa: E111
  diagnostics = result.get("diagnostics")  # noqa: E111
  assert diagnostics is not None  # noqa: E111
  metadata = diagnostics.get("metadata")  # noqa: E111
  assert metadata is not None  # noqa: E111
  assert metadata["reminder_attached"] is False  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_garden_session_records_success(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Garden session start should log telemetry with detection metadata."""  # noqa: E111

  garden_manager = _GardenManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)  # noqa: E111
  coordinator.register_dog("buddy", name="Buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_START_GARDEN]  # noqa: E111

  await handler(  # noqa: E111
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

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_START_GARDEN  # noqa: E111
  assert result["status"] == "success"  # noqa: E111
  details = result.get("details")  # noqa: E111
  assert details is not None and details["detection_method"] == "door_sensor"  # noqa: E111
  assert details["automation_fallback"] is True  # noqa: E111
  assert details["fallback_reason"] == "door_sensor_offline"  # noqa: E111
  assert details["automation_source"] == "garden_automation"  # noqa: E111
  diagnostics = result.get("diagnostics")  # noqa: E111
  assert diagnostics is not None  # noqa: E111
  metadata = diagnostics.get("metadata")  # noqa: E111
  assert metadata is not None  # noqa: E111
  assert metadata["automation_fallback"] is True  # noqa: E111
  assert metadata["fallback_reason"] == "door_sensor_offline"  # noqa: E111
  assert metadata["automation_source"] == "garden_automation"  # noqa: E111
  assert (  # noqa: E111
    garden_manager.start_calls and garden_manager.start_calls[0]["dog_id"] == "buddy"
  )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_garden_session_records_failure(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Garden session telemetry should capture Home Assistant errors."""  # noqa: E111

  garden_manager = _GardenManagerStub()  # noqa: E111
  garden_manager.fail_start = services.HomeAssistantError("start failed")  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)  # noqa: E111
  coordinator.register_dog("buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_START_GARDEN]  # noqa: E111

  with pytest.raises(services.HomeAssistantError, match="start failed"):  # noqa: E111
    await handler(SimpleNamespace(data={"dog_id": "buddy"}))

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_START_GARDEN  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert result.get("message") == "start failed"  # noqa: E111
  diagnostics = result.get("diagnostics")  # noqa: E111
  assert diagnostics is not None  # noqa: E111
  metadata = diagnostics.get("metadata")  # noqa: E111
  assert metadata is not None  # noqa: E111
  assert metadata["automation_fallback"] is False  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_end_garden_session_records_validation_error(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Ending a non-existent garden session should record validation telemetry."""  # noqa: E111

  garden_manager = _GardenManagerStub()  # noqa: E111
  garden_manager.next_end_session = None  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)  # noqa: E111
  coordinator.register_dog("buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_END_GARDEN]  # noqa: E111

  with pytest.raises(Exception, match="No active garden session is currently running"):  # noqa: E111
    await handler(SimpleNamespace(data={"dog_id": "buddy"}))

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_END_GARDEN  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert "No active garden session" in result.get("message", "")  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_garden_activity_records_success(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Garden activity service should capture success telemetry."""  # noqa: E111

  garden_manager = _GardenManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)  # noqa: E111
  coordinator.register_dog("buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_ADD_GARDEN_ACTIVITY]  # noqa: E111

  await handler(  # noqa: E111
    SimpleNamespace(
      data={
        "dog_id": "buddy",
        "activity_type": "play",
        "duration_seconds": 120,
        "location": "north lawn",
      }
    )
  )

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_ADD_GARDEN_ACTIVITY  # noqa: E111
  assert result["status"] == "success"  # noqa: E111
  details = result.get("details")  # noqa: E111
  assert details is not None and details["activity_type"] == "play"  # noqa: E111
  assert (  # noqa: E111
    garden_manager.activity_calls
    and garden_manager.activity_calls[0]["dog_id"] == "buddy"
  )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_garden_activity_records_validation_error(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Garden activity telemetry should note validation failures."""  # noqa: E111

  garden_manager = _GardenManagerStub()  # noqa: E111
  garden_manager.activity_success = False  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)  # noqa: E111
  coordinator.register_dog("buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_ADD_GARDEN_ACTIVITY]  # noqa: E111

  with pytest.raises(Exception, match="No active garden session is currently running"):  # noqa: E111
    await handler(SimpleNamespace(data={"dog_id": "buddy", "activity_type": "play"}))

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_ADD_GARDEN_ACTIVITY  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert "Start a garden session" in result.get("message", "")  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_confirm_garden_poop_records_success(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Garden poop confirmations should capture telemetry on success."""  # noqa: E111

  garden_manager = _GardenManagerStub()  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)  # noqa: E111
  coordinator.register_dog("buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_CONFIRM_POOP]  # noqa: E111

  await handler(  # noqa: E111
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

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_CONFIRM_POOP  # noqa: E111
  assert result["status"] == "success"  # noqa: E111
  details = result.get("details")  # noqa: E111
  assert details is not None and details["confirmed"] is True  # noqa: E111
  assert (  # noqa: E111
    garden_manager.confirm_calls
    and garden_manager.confirm_calls[0]["dog_id"] == "buddy"
  )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_confirm_garden_poop_records_missing_pending(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Telemetry should record validation errors when no confirmation is pending."""  # noqa: E111

  garden_manager = _GardenManagerStub()  # noqa: E111
  garden_manager.pending_confirmation = False  # noqa: E111
  coordinator = _CoordinatorStub(SimpleNamespace(), garden_manager=garden_manager)  # noqa: E111
  coordinator.register_dog("buddy")  # noqa: E111
  runtime_data = SimpleNamespace(performance_stats={})  # noqa: E111

  hass = await _setup_service_environment(monkeypatch, coordinator, runtime_data)  # noqa: E111
  handler = hass.services.handlers[services.SERVICE_CONFIRM_POOP]  # noqa: E111

  with pytest.raises(Exception, match="No pending garden poop confirmation"):  # noqa: E111
    await handler(SimpleNamespace(data={"dog_id": "buddy", "confirmed": True}))

  result = runtime_data.performance_stats["last_service_result"]  # noqa: E111
  assert result["service"] == services.SERVICE_CONFIRM_POOP  # noqa: E111
  assert result["status"] == "error"  # noqa: E111
  assert "No pending garden poop" in result.get("message", "")  # noqa: E111
