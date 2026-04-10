"""Matrix tests validating common entity properties across all entity platforms."""

from collections.abc import Mapping
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.binary_sensor import PawControlOnlineBinarySensor
from custom_components.pawcontrol.button import PawControlStartWalkButton
from custom_components.pawcontrol.date import PawControlBirthdateDate
from custom_components.pawcontrol.datetime import PawControlBirthdateDateTime
from custom_components.pawcontrol.device_tracker import PawControlGPSTracker
from custom_components.pawcontrol.number import PawControlDogWeightNumber
from custom_components.pawcontrol.select import PawControlFeedingModeSelect
from custom_components.pawcontrol.sensor import PawControlDogStatusSensor
from custom_components.pawcontrol.switch import PawControlMainPowerSwitch
from custom_components.pawcontrol.text import PawControlDogNotesText


@pytest.fixture
def coordinator_stub() -> MagicMock:
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.available = True
    coordinator.data = {
        "rex": {
            "status": "online",
            "feeding": {},
            "walk": {},
            "gps": {},
            "health": {},
        }
    }
    coordinator.get_dog_data = MagicMock(return_value=coordinator.data["rex"])
    coordinator.get_module_data = MagicMock(return_value={})
    coordinator.get_enabled_modules = MagicMock(return_value=[])
    coordinator.hass = MagicMock()
    coordinator.config_entry = MagicMock(entry_id="entry-id")
    return coordinator


@pytest.mark.parametrize(
    "entity",
    [
        pytest.param(lambda c: PawControlDogStatusSensor(c, "rex", "Rex"), id="sensor"),
        pytest.param(
            lambda c: PawControlOnlineBinarySensor(c, "rex", "Rex"),
            id="binary_sensor",
        ),
        pytest.param(lambda c: PawControlMainPowerSwitch(c, "rex", "Rex"), id="switch"),
        pytest.param(lambda c: PawControlDogWeightNumber(c, "rex", "Rex"), id="number"),
        pytest.param(
            lambda c: PawControlFeedingModeSelect(c, "rex", "Rex"),
            id="select",
        ),
        pytest.param(lambda c: PawControlDogNotesText(c, "rex", "Rex"), id="text"),
        pytest.param(lambda c: PawControlBirthdateDate(c, "rex", "Rex"), id="date"),
        pytest.param(
            lambda c: PawControlBirthdateDateTime(c, "rex", "Rex"), id="datetime"
        ),
        pytest.param(lambda c: PawControlGPSTracker(c, "rex", "Rex"), id="tracker"),
        pytest.param(
            lambda c: PawControlStartWalkButton(c, "rex", "Rex"),
            id="button",
        ),
    ],
)
def test_entity_common_properties(
    coordinator_stub: MagicMock,
    entity: Any,
) -> None:
    instance = entity(coordinator_stub)

    if hasattr(instance, "available"):
        assert isinstance(instance.available, bool)

    if hasattr(instance, "device_info"):
        assert instance.device_info is not None

    if hasattr(instance, "extra_state_attributes"):
        attrs = instance.extra_state_attributes
        assert attrs is None or isinstance(attrs, Mapping)

    unique_id = getattr(instance, "unique_id", None) or getattr(
        instance, "_attr_unique_id", None
    )
    assert isinstance(unique_id, str) and unique_id

    if hasattr(instance, "is_on"):
        assert instance.is_on is None or isinstance(instance.is_on, bool)
    elif hasattr(instance, "native_value"):
        _ = instance.native_value
    elif hasattr(instance, "state"):
        _ = instance.state
