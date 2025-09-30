"""Focused unit tests for the PawControl coordinator."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
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

    with patch.object(
        coordinator._adaptive_polling,
        "update_entity_saturation",
        wraps=coordinator._adaptive_polling.update_entity_saturation,
    ) as mock_update:
        coordinator.report_entity_budget(snapshot)
        mock_update.assert_called_once()

    performance = coordinator.get_performance_snapshot()

    assert performance["entity_budget"]["active_dogs"] == 1
    assert performance["performance_metrics"]["last_update_success"] is True
    assert performance["update_counts"]["failed"] == 1


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
    assert coordinator.data_manager is managers["data_manager"]

    coordinator.clear_runtime_managers()
    assert coordinator.data_manager is None
    assert coordinator.notification_manager is None


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
