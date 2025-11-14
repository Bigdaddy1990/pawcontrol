"""End-to-end integration regression tests for Platinum compliance.

These scenarios simulate the documented validation steps for the
Home Assistant 2025.9.3 nightly build and the supervised installation
smoke run.  They exercise the public setup/unload contracts while
capturing the runtime telemetry that Platinum reviewers expect to see
in the traceability matrix.

Quality Scale: Platinum target
Home Assistant: 2025.9.3+
Python: 3.12+
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from contextlib import ExitStack, suppress
from dataclasses import dataclass
from importlib import import_module
from types import ModuleType
from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("homeassistant")
AwesomeVersion = pytest.importorskip("awesomeversion").AwesomeVersion

# The integration expects the bluetooth_adapters helper to be importable in HA
# test environments.  Provide a stub to mirror other end-to-end suites.
import sys

from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_MODULES,
    DOMAIN,
)
from custom_components.pawcontrol.coordinator_tasks import run_maintenance
from custom_components.pawcontrol.runtime_data import get_runtime_data
from custom_components.pawcontrol.types import (
    ConfigEntryDataPayload,
    PawControlOptionsData,
    PawControlRuntimeData,
)

ha_module = import_module("homeassistant")
ha_version = getattr(ha_module, "__version__", "0.0.0")
try:
    from homeassistant.const import CONF_TOKEN
except (AttributeError, ImportError):
    CONF_TOKEN = "token"
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

sys.modules.setdefault("bluetooth_adapters", ModuleType("bluetooth_adapters"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.usefixtures("enable_custom_integrations"),
]


REQUIRED_NIGHTLY = AwesomeVersion("2025.9.3")


@dataclass(slots=True)
class IntegrationMocks:
    """Container for patched integration dependencies used in the tests."""

    prepare_entry: AsyncMock
    first_refresh: AsyncMock
    forward_entry_setups: AsyncMock
    unload_platforms: AsyncMock
    start_background_tasks: Mock
    clear_runtime_managers: Mock
    helper_create: AsyncMock
    helper_cleanup: AsyncMock
    script_generate: AsyncMock
    script_cleanup: AsyncMock
    data_initialize: AsyncMock
    data_shutdown: AsyncMock
    notification_initialize: AsyncMock
    notification_shutdown: AsyncMock
    notification_send: AsyncMock
    feeding_initialize: AsyncMock
    feeding_shutdown: AsyncMock
    walk_initialize: AsyncMock
    walk_shutdown: AsyncMock
    door_initialize: AsyncMock
    door_cleanup: AsyncMock
    door_detection_status: AsyncMock
    garden_initialize: AsyncMock
    garden_cleanup: AsyncMock
    daily_reset_setup: AsyncMock
    service_shutdown: AsyncMock


@pytest.fixture
def nightly_config_entry_data() -> ConfigEntryDataPayload:
    """Return a compact config entry payload used for end-to-end tests."""

    return ConfigEntryDataPayload(
        name="Nightly QA",
        dogs=[
            {
                CONF_DOG_ID: "buddy",
                CONF_DOG_NAME: "Buddy",
                CONF_MODULES: {
                    "feeding": True,
                    "walk": True,
                    "health": True,
                    "notifications": True,
                },
            }
        ],
        entity_profile="standard",
        setup_timestamp="2024-01-01T00:00:00+00:00",
    )


@pytest.fixture
def nightly_config_entry_options() -> PawControlOptionsData:
    """Return typed config entry options for the platinum flow."""

    return PawControlOptionsData(
        entity_profile="standard",
        external_integrations=False,
        api_token="",
        api_endpoint="",
    )


@pytest.fixture
def integration_patches(hass: HomeAssistant) -> Generator[IntegrationMocks]:
    """Patch expensive integration helpers for deterministic e2e runs."""

    with ExitStack() as stack:
        prepare_entry = stack.enter_context(
            patch(
                "custom_components.pawcontrol.coordinator.PawControlCoordinator.async_prepare_entry",
                new_callable=AsyncMock,
            )
        )
        prepare_entry.return_value = None

        first_refresh = stack.enter_context(
            patch(
                "custom_components.pawcontrol.coordinator.PawControlCoordinator.async_config_entry_first_refresh",
                new_callable=AsyncMock,
            )
        )
        first_refresh.return_value = None

        start_background_tasks = stack.enter_context(
            patch(
                "custom_components.pawcontrol.coordinator.PawControlCoordinator.async_start_background_tasks",
                new=Mock(),
            )
        )

        clear_runtime_managers = stack.enter_context(
            patch(
                "custom_components.pawcontrol.coordinator.PawControlCoordinator.clear_runtime_managers",
                new=Mock(),
            )
        )

        forward_entry_setups = AsyncMock(return_value=None)
        stack.enter_context(
            patch.object(
                hass.config_entries,
                "async_forward_entry_setups",
                forward_entry_setups,
            )
        )

        unload_platforms = AsyncMock(return_value=True)
        stack.enter_context(
            patch.object(
                hass.config_entries,
                "async_unload_platforms",
                unload_platforms,
            )
        )

        data_initialize = stack.enter_context(
            patch(
                "custom_components.pawcontrol.data_manager.PawControlDataManager.async_initialize",
                new_callable=AsyncMock,
            )
        )
        data_initialize.return_value = None

        data_shutdown = stack.enter_context(
            patch(
                "custom_components.pawcontrol.data_manager.PawControlDataManager.async_shutdown",
                new_callable=AsyncMock,
            )
        )
        data_shutdown.return_value = None

        notification_initialize = stack.enter_context(
            patch(
                "custom_components.pawcontrol.notifications.PawControlNotificationManager.async_initialize",
                new_callable=AsyncMock,
            )
        )
        notification_initialize.return_value = None

        notification_shutdown = stack.enter_context(
            patch(
                "custom_components.pawcontrol.notifications.PawControlNotificationManager.async_shutdown",
                new_callable=AsyncMock,
            )
        )
        notification_shutdown.return_value = None

        notification_send = stack.enter_context(
            patch(
                "custom_components.pawcontrol.notifications.PawControlNotificationManager.async_send_notification",
                new_callable=AsyncMock,
            )
        )
        notification_send.return_value = None

        feeding_initialize = stack.enter_context(
            patch(
                "custom_components.pawcontrol.feeding_manager.FeedingManager.async_initialize",
                new_callable=AsyncMock,
            )
        )
        feeding_initialize.return_value = None

        feeding_shutdown = stack.enter_context(
            patch(
                "custom_components.pawcontrol.feeding_manager.FeedingManager.async_shutdown",
                new_callable=AsyncMock,
            )
        )
        feeding_shutdown.return_value = None

        walk_initialize = stack.enter_context(
            patch(
                "custom_components.pawcontrol.walk_manager.WalkManager.async_initialize",
                new_callable=AsyncMock,
            )
        )
        walk_initialize.return_value = None

        walk_shutdown = stack.enter_context(
            patch(
                "custom_components.pawcontrol.walk_manager.WalkManager.async_shutdown",
                new_callable=AsyncMock,
            )
        )
        walk_shutdown.return_value = None

        door_initialize = stack.enter_context(
            patch(
                "custom_components.pawcontrol.door_sensor_manager.DoorSensorManager.async_initialize",
                new_callable=AsyncMock,
            )
        )
        door_initialize.return_value = None

        door_cleanup = stack.enter_context(
            patch(
                "custom_components.pawcontrol.door_sensor_manager.DoorSensorManager.async_cleanup",
                new_callable=AsyncMock,
            )
        )
        door_cleanup.return_value = None

        door_detection_status = stack.enter_context(
            patch(
                "custom_components.pawcontrol.door_sensor_manager.DoorSensorManager.async_get_detection_status",
                new_callable=AsyncMock,
            )
        )
        door_detection_status.return_value = {
            "configured_dogs": 0,
            "active_detections": 0,
            "detection_states": {},
            "statistics": {
                "total_detections": 0,
                "successful_walks": 0,
                "false_positives": 0,
                "false_negatives": 0,
                "average_confidence": 0.0,
            },
        }

        garden_initialize = stack.enter_context(
            patch(
                "custom_components.pawcontrol.garden_manager.GardenManager.async_initialize",
                new_callable=AsyncMock,
            )
        )
        garden_initialize.return_value = None

        garden_cleanup = stack.enter_context(
            patch(
                "custom_components.pawcontrol.garden_manager.GardenManager.async_cleanup",
                new_callable=AsyncMock,
            )
        )
        garden_cleanup.return_value = None

        helper_create = stack.enter_context(
            patch(
                "custom_components.pawcontrol.helper_manager.PawControlHelperManager.async_create_helpers_for_dogs",
                new_callable=AsyncMock,
            )
        )
        helper_create.return_value = {"buddy": []}

        helper_cleanup = stack.enter_context(
            patch(
                "custom_components.pawcontrol.helper_manager.PawControlHelperManager.async_cleanup",
                new_callable=AsyncMock,
            )
        )
        helper_cleanup.return_value = None

        script_generate = stack.enter_context(
            patch(
                "custom_components.pawcontrol.script_manager.PawControlScriptManager.async_generate_scripts_for_dogs",
                new_callable=AsyncMock,
            )
        )
        script_generate.return_value = {"buddy": []}

        script_cleanup = stack.enter_context(
            patch(
                "custom_components.pawcontrol.script_manager.PawControlScriptManager.async_cleanup",
                new_callable=AsyncMock,
            )
        )
        script_cleanup.return_value = None

        daily_reset_setup = stack.enter_context(
            patch(
                "custom_components.pawcontrol.services.async_setup_daily_reset_scheduler",
                new_callable=AsyncMock,
            )
        )
        daily_reset_setup.return_value = lambda: None

        service_shutdown = stack.enter_context(
            patch(
                "custom_components.pawcontrol.services.PawControlServiceManager.async_shutdown",
                new_callable=AsyncMock,
            )
        )
        service_shutdown.return_value = None

        yield IntegrationMocks(
            prepare_entry=prepare_entry,
            first_refresh=first_refresh,
            forward_entry_setups=forward_entry_setups,
            unload_platforms=unload_platforms,
            start_background_tasks=start_background_tasks,
            clear_runtime_managers=clear_runtime_managers,
            helper_create=helper_create,
            helper_cleanup=helper_cleanup,
            script_generate=script_generate,
            script_cleanup=script_cleanup,
            data_initialize=data_initialize,
            data_shutdown=data_shutdown,
            notification_initialize=notification_initialize,
            notification_shutdown=notification_shutdown,
            notification_send=notification_send,
            feeding_initialize=feeding_initialize,
            feeding_shutdown=feeding_shutdown,
            walk_initialize=walk_initialize,
            walk_shutdown=walk_shutdown,
            door_initialize=door_initialize,
            door_cleanup=door_cleanup,
            door_detection_status=door_detection_status,
            garden_initialize=garden_initialize,
            garden_cleanup=garden_cleanup,
            daily_reset_setup=daily_reset_setup,
            service_shutdown=service_shutdown,
        )


async def _async_cancel_background(runtime_data: PawControlRuntimeData) -> None:
    """Cancel background monitor tasks created during setup."""

    monitor_task = getattr(runtime_data, "background_monitor_task", None)
    if monitor_task:
        monitor_task.cancel()
        with suppress(asyncio.CancelledError):
            await monitor_task
        runtime_data.background_monitor_task = None


def _require_nightly() -> None:
    """Skip tests when the HA runtime is older than the required nightly build."""

    if AwesomeVersion(ha_version) < REQUIRED_NIGHTLY:
        pytest.skip(
            "Requires Home Assistant 2025.9.3 nightly build or newer for Platinum QA"
        )


async def _async_setup_runtime(
    hass: HomeAssistant,
    entry: MockConfigEntry,
) -> PawControlRuntimeData:
    """Run the integration setup and return the stored runtime data."""

    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    runtime_data = get_runtime_data(hass, entry)
    assert runtime_data is not None
    return runtime_data


async def _async_unload_runtime(
    hass: HomeAssistant,
    entry: MockConfigEntry,
) -> bool:
    """Unload the integration and confirm teardown succeeded."""

    unload_ok = await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    return unload_ok


async def test_full_integration_nightly_build(
    hass: HomeAssistant,
    nightly_config_entry_data: ConfigEntryDataPayload,
    nightly_config_entry_options: PawControlOptionsData,
    integration_patches: IntegrationMocks,
) -> None:
    """Validate the documented nightly-build regression scenario."""

    _require_nightly()

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=nightly_config_entry_data,
        options=nightly_config_entry_options,
    )

    runtime_data = await _async_setup_runtime(hass, entry)

    assert integration_patches.prepare_entry.await_count == 1
    assert integration_patches.first_refresh.await_count == 1
    assert integration_patches.forward_entry_setups.await_count == 1
    assert integration_patches.helper_create.await_count == 1
    assert integration_patches.script_generate.await_count == 1
    assert integration_patches.daily_reset_setup.await_count == 1

    assert runtime_data.dogs[0][CONF_DOG_ID] == "buddy"
    assert runtime_data.entity_profile == "standard"

    await _async_cancel_background(runtime_data)

    unload_ok = await _async_unload_runtime(hass, entry)
    assert unload_ok is True

    assert integration_patches.unload_platforms.await_count == 1
    assert integration_patches.clear_runtime_managers.call_count == 1
    assert integration_patches.data_shutdown.await_count == 1
    assert integration_patches.notification_shutdown.await_count == 1
    assert integration_patches.feeding_shutdown.await_count == 1
    assert integration_patches.walk_shutdown.await_count == 1

    assert get_runtime_data(hass, entry) is None


async def test_supervised_smoke_analytics_snapshot(
    hass: HomeAssistant,
    nightly_config_entry_data: ConfigEntryDataPayload,
    nightly_config_entry_options: PawControlOptionsData,
    integration_patches: IntegrationMocks,
) -> None:
    """Ensure supervised smoke tests capture analytics collector telemetry."""

    _require_nightly()

    # Mimic a supervised installation by loading the supervisor component.
    hass.config.components.add("hassio")

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=nightly_config_entry_data,
        options=nightly_config_entry_options,
    )

    runtime_data = await _async_setup_runtime(hass, entry)

    # Simulate the hourly maintenance collector invoked on supervised builds.
    with patch.object(
        runtime_data.coordinator._modules,
        "cleanup_expired",
        return_value=0,
    ):
        await run_maintenance(runtime_data.coordinator)

    metrics = runtime_data.performance_stats.get("analytics_collector_metrics")
    assert metrics is not None
    assert metrics["runs"] == 1
    assert metrics["failures"] == 0
    assert metrics["durations_ms"]
    assert metrics["last_run"] is not None

    await _async_cancel_background(runtime_data)

    unload_ok = await _async_unload_runtime(hass, entry)
    assert unload_ok is True

    assert integration_patches.unload_platforms.await_count >= 1
    assert get_runtime_data(hass, entry) is None
