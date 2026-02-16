"""Focused unit tests for the PawControl coordinator."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.pawcontrol import coordinator as coordinator_module
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.coordinator_runtime import (
  EntityBudgetSnapshot,
  RuntimeCycleInfo,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialisation_builds_registry(
  mock_hass, mock_config_entry, mock_session
):
  """The registry should expose configured dog identifiers."""  # noqa: E111

  coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)  # noqa: E111

  assert coordinator.registry.ids() == ["test_dog"]  # noqa: E111
  assert coordinator.get_dog_ids() == ["test_dog"]  # noqa: E111
  assert coordinator.get_dog_config("test_dog")["dog_name"] == "Buddy"  # noqa: E111


@pytest.mark.unit
def test_initialisation_rejects_missing_session(mock_hass, mock_config_entry) -> None:
  """A helpful error should be raised when no session is provided."""  # noqa: E111

  with pytest.raises(ValueError):  # noqa: E111
    PawControlCoordinator(  # type: ignore[arg-type]
      mock_hass,
      mock_config_entry,
      None,
    )


@pytest.mark.unit
def test_initialisation_rejects_closed_session(
  mock_hass, mock_config_entry, session_factory
) -> None:
  """Closed sessions must be rejected at construction time."""  # noqa: E111

  closed_session = session_factory(closed=True)  # noqa: E111

  with pytest.raises(ValueError):  # noqa: E111
    PawControlCoordinator(
      mock_hass,
      mock_config_entry,
      closed_session,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_data_uses_runtime(
  mock_hass, mock_config_entry, mock_session
):
  """Runtime results should be surfaced as coordinator data and adjust polling."""  # noqa: E111

  coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)  # noqa: E111
  runtime_cycle = RuntimeCycleInfo(  # noqa: E111
    dog_count=1,
    errors=0,
    success_rate=1.0,
    duration=0.05,
    new_interval=1.5,
    error_ratio=0.0,
    success=True,
  )
  coordinator._runtime.execute_cycle = AsyncMock(  # noqa: E111
    return_value=({"test_dog": {"status": "online"}}, runtime_cycle)
  )

  data = await coordinator._async_update_data()  # noqa: E111

  assert data == {"test_dog": {"status": "online"}}  # noqa: E111
  assert coordinator.data == data  # noqa: E111
  assert coordinator.update_interval.total_seconds() == pytest.approx(1.5)  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_data_awaits_set_updated_data(
  mock_hass, mock_config_entry, mock_session
):
  """The coordinator should await async_set_updated_data when available."""  # noqa: E111

  coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)  # noqa: E111
  runtime_cycle = RuntimeCycleInfo(  # noqa: E111
    dog_count=1,
    errors=0,
    success_rate=1.0,
    duration=0.05,
    new_interval=2.0,
    error_ratio=0.0,
    success=True,
  )
  coordinator._runtime.execute_cycle = AsyncMock(  # noqa: E111
    return_value=({"test_dog": {"status": "online"}}, runtime_cycle)
  )

  async_setter = AsyncMock()  # noqa: E111
  coordinator.async_set_updated_data = async_setter  # type: ignore[assignment]  # noqa: E111

  await coordinator._async_update_data()  # noqa: E111

  async_setter.assert_awaited_once()  # noqa: E111
  args, kwargs = async_setter.await_args  # noqa: E111
  assert args[0] == {"test_dog": {"status": "online"}}  # noqa: E111
  assert kwargs == {}  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_apply_module_updates_merges_data(
  mock_hass, mock_config_entry, mock_session
) -> None:
  """Module updates should merge into the coordinator cache."""  # noqa: E111

  coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)  # noqa: E111
  coordinator._data = {  # noqa: E111
    "test_dog": {
      "feeding": {"mode": "manual", "config": {"portion": 1}},
    }
  }

  await coordinator.async_apply_module_updates(  # noqa: E111
    "test_dog",
    "feeding",
    {"mode": "scheduled", "config": {"portion": 2, "note": "evening"}},
  )

  assert coordinator.data["test_dog"]["feeding"]["mode"] == "scheduled"  # noqa: E111
  assert coordinator.data["test_dog"]["feeding"]["config"] == {  # noqa: E111
    "portion": 2,
    "note": "evening",
  }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_data_without_dogs(
  mock_hass, mock_config_entry, mock_session
):
  """When no dogs are configured the coordinator should return an empty payload."""  # noqa: E111

  mock_config_entry.data = {"dogs": []}  # noqa: E111
  coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)  # noqa: E111

  assert await coordinator._async_update_data() == {}  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_report_entity_budget_updates_snapshot(
  mock_hass, mock_config_entry, mock_session
):
  """Entity budget snapshots feed the performance snapshot."""  # noqa: E111

  coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)  # noqa: E111
  coordinator._metrics.update_count = 2  # noqa: E111
  coordinator._metrics.failed_cycles = 1  # noqa: E111
  coordinator.last_update_success = True  # noqa: E111
  coordinator.last_update_time = datetime(2024, 1, 1, 12, 0, 0)  # noqa: E111

  snapshot = EntityBudgetSnapshot(  # noqa: E111
    dog_id="test_dog",
    profile="standard",
    capacity=10,
    base_allocation=4,
    dynamic_allocation=2,
    requested_entities=("sensor.a", "sensor.b"),
    denied_requests=("sensor.c",),
    recorded_at=datetime(2024, 1, 1, 12, 0, 0),
  )

  controller_cls = type(coordinator._adaptive_polling)  # noqa: E111
  expected_saturation = snapshot.saturation  # noqa: E111
  with patch.object(  # noqa: E111
    controller_cls,
    "update_entity_saturation",
    autospec=True,
    wraps=controller_cls.update_entity_saturation,
  ) as mock_update:
    coordinator.report_entity_budget(snapshot)
    mock_update.assert_called_once_with(
      coordinator._adaptive_polling, expected_saturation
    )

  performance = coordinator.get_performance_snapshot()  # noqa: E111

  assert performance["entity_budget"]["active_dogs"] == 1  # noqa: E111
  assert performance["performance_metrics"]["last_update_success"] is True  # noqa: E111
  assert performance["update_counts"]["failed"] == 1  # noqa: E111


@pytest.mark.unit
def test_performance_snapshot_includes_guard_metrics(
  mock_hass, mock_config_entry, mock_session, monkeypatch: pytest.MonkeyPatch
) -> None:
  """Service execution metrics mirror the runtime guard telemetry."""  # noqa: E111

  coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)  # noqa: E111

  raw_guard_metrics = {  # noqa: E111
    "service_guard_metrics": {
      "executed": 2,
      "skipped": 1,
      "reasons": {"missing_instance": 1, "": 4},
      "last_results": [
        {
          "domain": "notify",
          "service": "send",
          "executed": False,
          "reason": "missing_instance",
        },
        "invalid",
      ],
    }
  }

  runtime_data = SimpleNamespace(performance_stats=raw_guard_metrics)  # noqa: E111
  mock_config_entry.runtime_data = runtime_data  # noqa: E111

  resilience_summary = {  # noqa: E111
    "summary": {
      "rejected_call_count": 1,
      "rejection_breaker_count": 1,
      "rejection_rate": 0.5,
      "open_breakers": ["automation"],
      "open_breaker_ids": ["automation"],
    }
  }
  monkeypatch.setattr(  # noqa: E111
    coordinator_module,
    "collect_resilience_diagnostics",
    lambda *_: resilience_summary,
  )

  snapshot = coordinator.get_performance_snapshot()  # noqa: E111

  service_execution = snapshot["service_execution"]  # noqa: E111
  guard_metrics = service_execution["guard_metrics"]  # noqa: E111
  assert guard_metrics["executed"] == 2  # noqa: E111
  assert guard_metrics["skipped"] == 1  # noqa: E111
  assert guard_metrics["reasons"] == {"missing_instance": 1}  # noqa: E111
  assert guard_metrics["last_results"] == [  # noqa: E111
    {
      "domain": "notify",
      "service": "send",
      "executed": False,
      "reason": "missing_instance",
    }
  ]

  rejection_metrics = service_execution["rejection_metrics"]  # noqa: E111
  assert rejection_metrics is snapshot["rejection_metrics"]  # noqa: E111
  assert rejection_metrics["rejected_call_count"] == 1  # noqa: E111
  assert rejection_metrics["rejection_breaker_count"] == 1  # noqa: E111
  assert rejection_metrics["open_breakers"] == ["automation"]  # noqa: E111

  sanitised_metrics = runtime_data.performance_stats["service_guard_metrics"]  # noqa: E111
  assert sanitised_metrics["reasons"] == {"missing_instance": 1}  # noqa: E111
  assert sanitised_metrics["last_results"] == guard_metrics["last_results"]  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_security_scorecard_detects_insecure_webhooks(
  mock_hass, mock_config_entry, mock_session
):
  """Insecure webhook configurations should fail the scorecard."""  # noqa: E111

  coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)  # noqa: E111

  class InsecureWebhookManager:  # noqa: E111
    @staticmethod
    def webhook_security_status() -> dict[str, object]:
      return {  # noqa: E111
        "configured": True,
        "secure": False,
        "hmac_ready": False,
        "insecure_configs": ("dog1",),
      }

  coordinator.notification_manager = InsecureWebhookManager()  # noqa: E111

  scorecard = coordinator.get_security_scorecard()  # noqa: E111

  assert scorecard["status"] == "fail"  # noqa: E111
  assert scorecard["checks"]["webhooks"]["pass"] is False  # noqa: E111
  assert "dog1" in scorecard["checks"]["webhooks"]["insecure_configs"]  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_manager_lifecycle(mock_hass, mock_config_entry, mock_session):
  """Managers can be attached and cleared without leaking references."""  # noqa: E111

  coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)  # noqa: E111

  managers = {  # noqa: E111
    "data_manager": Mock(),
    "feeding_manager": Mock(),
    "walk_manager": Mock(),
    "notification_manager": Mock(),
  }

  coordinator.attach_runtime_managers(**managers)  # noqa: E111
  container = coordinator.runtime_managers  # noqa: E111
  assert container.data_manager is managers["data_manager"]  # noqa: E111
  assert container.notification_manager is managers["notification_manager"]  # noqa: E111

  coordinator.clear_runtime_managers()  # noqa: E111
  empty_container = coordinator.runtime_managers  # noqa: E111
  assert empty_container.data_manager is None  # noqa: E111
  assert empty_container.notification_manager is None  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_availability_threshold(mock_hass, mock_config_entry, mock_session):
  """Availability respects the consecutive error guardrail."""  # noqa: E111

  coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)  # noqa: E111
  coordinator.last_update_success = True  # noqa: E111
  coordinator._metrics.consecutive_errors = 5  # noqa: E111

  assert coordinator.available is False  # noqa: E111

  coordinator._metrics.consecutive_errors = 1  # noqa: E111
  assert coordinator.available is True  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_statistics_records_runtime(
  mock_hass, mock_config_entry, mock_session
):
  """Generating statistics should capture and expose timing samples."""  # noqa: E111

  coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)  # noqa: E111
  coordinator._metrics.update_count = 2  # noqa: E111

  with patch.object(coordinator.logger, "debug") as debug_mock:  # noqa: E111
    stats = coordinator.get_statistics()

  assert "update_counts" in stats  # noqa: E111
  assert coordinator._metrics.statistics_timings  # noqa: E111
  # The diagnostics helpers build nested statistics payloads which can take  # noqa: E114, E501
  # tens of milliseconds on slower CI runners. Keep the assertion generous so  # noqa: E114, E501
  # we still catch pathological slowdowns without flaking due to instrumentation.  # noqa: E114, E501
  assert coordinator._metrics.average_statistics_runtime_ms < 100.0  # noqa: E111
  debug_mock.assert_called()  # noqa: E111
