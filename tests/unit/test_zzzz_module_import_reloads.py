"""Import-reload coverage tests for modules loaded during test bootstrap."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    ("module_name", "sentinel_attribute"),
    [
        ("custom_components.pawcontrol.types", "ensure_json_mapping"),
        ("custom_components.pawcontrol.feeding_manager", "FeedingManager"),
        ("custom_components.pawcontrol.entity_factory", "EntityFactory"),
        ("custom_components.pawcontrol.door_sensor_manager", "DoorSensorConfig"),
        ("custom_components.pawcontrol.sensor", "async_setup_entry"),
        ("custom_components.pawcontrol.services", "_service_validation_error"),
        ("custom_components.pawcontrol.diagnostics", "_resolve_data_manager"),
        ("custom_components.pawcontrol.repairs", "async_check_for_issues"),
        ("custom_components.pawcontrol.helpers", "PerformanceCounters"),
        ("custom_components.pawcontrol.error_classification", "classify_error_reason"),
    ],
)
def test_reload_module_re_executes_public_definitions(
    module_name: str,
    sentinel_attribute: str,
) -> None:
    """Reloading should re-run module definitions and keep public symbols available."""
    module = importlib.import_module(module_name)
    reloaded = importlib.reload(module)

    assert reloaded is module
    assert hasattr(reloaded, sentinel_attribute)

