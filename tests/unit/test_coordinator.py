"""Focused unit tests for the PawControl coordinator."""

from __future__ import annotations

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
    """The registry should expose configured dog identifiers."""

    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    assert coordinator.registry.ids() == ["test_dog"]
    assert coordinator.get_dog_ids() == ["test_dog"]
    assert coordinator.get_dog_config("test_dog")["dog_name"] == "Buddy"


@pytest.mark.unit
def test_initialisation_rejects_missing_session(mock_hass, mock_config_entry) -> None:
    """A helpful error should be raised when no session is provided."""

    with pytest.raises(ValueError):
        PawControlCoordinator(  # type: ignore[arg-type]
            mock_hass,
            mock_config_entry,
            None,
        )


@pytest.mark.unit
def test_initialisation_rejects_closed_session(
    mock_hass, mock_config_entry, session_factory
) -> None:
    """Closed sessions must be rejected at construction time."""

    closed_session = session_factory(closed=True)

    with pytest.raises(ValueError):
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
    """Runtime results should be surfaced as coordinator data and adjust polling."""

    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    runtime_cycle = RuntimeCycleInfo(
        dog_count=1,
        errors=0,
        success_rate=1.0,
        duration=0.05,
        new_interval=1.5,
        error_ratio=0.0,
        success=True,
    )
    coordinator._runtime.execute_cycle = AsyncMock(
        return_value=({"test_dog": {"status": "online"}}, runtime_cycle)
    )

    data = await coordinator._async_update_data()

    assert data == {"test_dog": {"status": "online"}}
    assert coordinator.data == data
    assert coordinator.update_interval.total_seconds() == pytest.approx(1.5)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_data_awaits_set_updated_data(
    mock_hass, mock_config_entry, mock_session
):
    """The coordinator should await async_set_updated_data when available."""

    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    runtime_cycle = RuntimeCycleInfo(
        dog_count=1,
        errors=0,
        success_rate=1.0,
        duration=0.05,
        new_interval=2.0,
        error_ratio=0.0,
        success=True,
    )
    coordinator._runtime.execute_cycle = AsyncMock(
        return_value=({"test_dog": {"status": "online"}}, runtime_cycle)
    )

    async_setter = AsyncMock()
    coordinator.async_set_updated_data = async_setter  # type: ignore[assignment]

    await coordinator._async_update_data()

    async_setter.assert_awaited_once()
    args, kwargs = async_setter.await_args
    assert args[0] == {"test_dog": {"status": "online"}}
    assert kwargs == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_data_without_dogs(
    mock_hass, mock_config_entry, mock_session
):
    """When no dogs are configured the coordinator should return an empty payload."""

    mock_config_entry.data = {"dogs": []}
    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    assert await coordinator._async_update_data() == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_report_entity_budget_updates_snapshot(
    mock_hass, mock_config_entry, mock_session
):
    """Entity budget snapshots feed the performance snapshot."""

    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coordinator._metrics.update_count = 2
    coordinator._metrics.failed_cycles = 1
    coordinator.last_update_success = True
    coordinator.last_update_time = datetime(2024, 1, 1, 12, 0, 0)

    snapshot = EntityBudgetSnapshot(
        dog_id="test_dog",
        profile="standard",
        capacity=10,
        base_allocation=4,
        dynamic_allocation=2,
        requested_entities=("sensor.a", "sensor.b"),
        denied_requests=("sensor.c",),
        recorded_at=datetime(2024, 1, 1, 12, 0, 0),
    )

    controller_cls = type(coordinator._adaptive_polling)
    expected_saturation = snapshot.saturation
    with patch.object(
        controller_cls,
        "update_entity_saturation",
        autospec=True,
        wraps=controller_cls.update_entity_saturation,
    ) as mock_update:
        coordinator.report_entity_budget(snapshot)
        mock_update.assert_called_once_with(
            coordinator._adaptive_polling, expected_saturation
        )

    performance = coordinator.get_performance_snapshot()

    assert performance["entity_budget"]["active_dogs"] == 1
    assert performance["performance_metrics"]["last_update_success"] is True
    assert performance["update_counts"]["failed"] == 1


@pytest.mark.unit
def test_performance_snapshot_includes_guard_metrics(
    mock_hass, mock_config_entry, mock_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Service execution metrics mirror the runtime guard telemetry."""

    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    raw_guard_metrics = {
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

    runtime_data = SimpleNamespace(performance_stats=raw_guard_metrics)
    mock_config_entry.runtime_data = runtime_data

    resilience_summary = {
        "summary": {
            "rejected_call_count": 1,
            "rejection_breaker_count": 1,
            "rejection_rate": 0.5,
            "open_breakers": ["automation"],
            "open_breaker_ids": ["automation"],
        }
    }
    monkeypatch.setattr(
        coordinator_module,
        "collect_resilience_diagnostics",
        lambda *_: resilience_summary,
    )

    snapshot = coordinator.get_performance_snapshot()

    service_execution = snapshot["service_execution"]
    guard_metrics = service_execution["guard_metrics"]
    assert guard_metrics["executed"] == 2
    assert guard_metrics["skipped"] == 1
    assert guard_metrics["reasons"] == {"missing_instance": 1}
    assert guard_metrics["last_results"] == [
        {
            "domain": "notify",
            "service": "send",
            "executed": False,
            "reason": "missing_instance",
        }
    ]

    rejection_metrics = service_execution["rejection_metrics"]
    assert rejection_metrics is snapshot["rejection_metrics"]
    assert rejection_metrics["rejected_call_count"] == 1
    assert rejection_metrics["rejection_breaker_count"] == 1
    assert rejection_metrics["open_breakers"] == ["automation"]

    sanitised_metrics = runtime_data.performance_stats["service_guard_metrics"]
    assert sanitised_metrics["reasons"] == {"missing_instance": 1}
    assert sanitised_metrics["last_results"] == guard_metrics["last_results"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_security_scorecard_detects_insecure_webhooks(
    mock_hass, mock_config_entry, mock_session
):
    """Insecure webhook configurations should fail the scorecard."""

    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    class InsecureWebhookManager:
        @staticmethod
        def webhook_security_status() -> dict[str, object]:
            return {
                "configured": True,
                "secure": False,
                "hmac_ready": False,
                "insecure_configs": ("dog1",),
            }

    coordinator.notification_manager = InsecureWebhookManager()

    scorecard = coordinator.get_security_scorecard()

    assert scorecard["status"] == "fail"
    assert scorecard["checks"]["webhooks"]["pass"] is False
    assert "dog1" in scorecard["checks"]["webhooks"]["insecure_configs"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_manager_lifecycle(mock_hass, mock_config_entry, mock_session):
    """Managers can be attached and cleared without leaking references."""

    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    managers = {
        "data_manager": Mock(),
        "feeding_manager": Mock(),
        "walk_manager": Mock(),
        "notification_manager": Mock(),
    }

    coordinator.attach_runtime_managers(**managers)
    container = coordinator.runtime_managers
    assert container.data_manager is managers["data_manager"]
    assert container.notification_manager is managers["notification_manager"]

    coordinator.clear_runtime_managers()
    empty_container = coordinator.runtime_managers
    assert empty_container.data_manager is None
    assert empty_container.notification_manager is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_availability_threshold(mock_hass, mock_config_entry, mock_session):
    """Availability respects the consecutive error guardrail."""

    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coordinator.last_update_success = True
    coordinator._metrics.consecutive_errors = 5

    assert coordinator.available is False

    coordinator._metrics.consecutive_errors = 1
    assert coordinator.available is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_statistics_records_runtime(
    mock_hass, mock_config_entry, mock_session
):
    """Generating statistics should capture and expose timing samples."""

    coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coordinator._metrics.update_count = 2

    with patch.object(coordinator.logger, "debug") as debug_mock:
        stats = coordinator.get_statistics()

    assert "update_counts" in stats
    assert coordinator._metrics.statistics_timings
    assert coordinator._metrics.average_statistics_runtime_ms < 5.0
    debug_mock.assert_called()
