"""Door sensor manager helper normalisation tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOOR_SENSOR,
    CONF_DOOR_SENSOR_SETTINGS,
)
from custom_components.pawcontrol.door_sensor_manager import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_DOOR_CLOSED_DELAY,
    DEFAULT_DOOR_SENSOR_SETTINGS,
    DEFAULT_MAXIMUM_WALK_DURATION,
    DEFAULT_MINIMUM_WALK_DURATION,
    DEFAULT_WALK_DETECTION_TIMEOUT,
    DoorSensorConfig,
    DoorSensorManager,
    DoorSensorSettingsConfig,
    WalkDetectionState,
    _coerce_bool,
    ensure_door_sensor_settings_config,
)
from custom_components.pawcontrol.types import DogConfigData


@pytest.mark.parametrize(
    "overrides,expected",
    [
        (
            None,
            DEFAULT_DOOR_SENSOR_SETTINGS,
        ),
        (
            {
                "timeout": "45",
                "minimum_duration": "90",
                "maximum_duration": 30,
                "door_closed_timeout": "-5",
                "confirmation_required": "false",
                "auto_end_walk": "off",
                "confidence": "1.4",
            },
            DoorSensorSettingsConfig(
                walk_detection_timeout=45,
                minimum_walk_duration=90,
                maximum_walk_duration=90,
                door_closed_delay=0,
                require_confirmation=False,
                auto_end_walks=False,
                confidence_threshold=1.0,
            ),
        ),
        (
            DoorSensorSettingsConfig(
                walk_detection_timeout=120,
                minimum_walk_duration=200,
                maximum_walk_duration=400,
                door_closed_delay=30,
                require_confirmation=False,
                auto_end_walks=False,
                confidence_threshold=0.5,
            ),
            DoorSensorSettingsConfig(
                walk_detection_timeout=120,
                minimum_walk_duration=200,
                maximum_walk_duration=400,
                door_closed_delay=30,
                require_confirmation=False,
                auto_end_walks=False,
                confidence_threshold=0.5,
            ),
        ),
        (
            {
                "require_confirmation": 0,
                "auto_end_walks": 1,
            },
            DoorSensorSettingsConfig(
                require_confirmation=False,
                auto_end_walks=True,
            ),
        ),
    ],
)
def test_ensure_door_sensor_settings_config(overrides, expected) -> None:
    """Normalisation should coerce aliases, clamp values, and honour dataclasses."""

    result = ensure_door_sensor_settings_config(overrides)
    assert result == expected


def test_settings_clamp_extreme_values() -> None:
    """Overrides outside the allowed bounds should clamp to safe defaults."""

    base = DoorSensorSettingsConfig(
        walk_detection_timeout=90,
        minimum_walk_duration=120,
        maximum_walk_duration=3600,
        door_closed_delay=30,
        require_confirmation=True,
        auto_end_walks=True,
        confidence_threshold=0.6,
    )

    overrides = {
        "walk_detection_timeout": "999999",
        "minimum_walk_duration": "10",
        "maximum_walk_duration": "100000",
        "door_closed_delay": "2000",
        "confidence_threshold": "-5",
    }

    result = ensure_door_sensor_settings_config(overrides, base=base)

    assert result.walk_detection_timeout == 21600
    assert result.minimum_walk_duration == 60
    assert result.maximum_walk_duration == 43200
    assert result.door_closed_delay == 1800
    assert result.confidence_threshold == 0.0


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        ("1.0", False, True),
        ("0.0", True, False),
        ("-2.5", False, True),
        (" 2 ", False, True),
        (-3.14, False, True),
        (0, True, False),
    ],
)
def test_coerce_bool_numeric_inputs(
    value: object, default: bool, expected: bool
) -> None:
    """Numeric strings and numbers should coerce using non-zero semantics."""

    assert _coerce_bool(value, default=default) is expected


def test_coerce_bool_invalid_strings_use_default() -> None:
    """Strings that are neither numeric nor keywords fall back to the default."""

    assert _coerce_bool("maybe", default=True) is True
    assert _coerce_bool("", default=False) is False


@pytest.mark.asyncio
async def test_update_settings_without_entity_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings updates should preserve the entity and restart monitoring when changed."""

    hass = Mock()
    manager = DoorSensorManager(hass, "entry")
    config = DoorSensorConfig(
        entity_id="binary_sensor.front_door",
        dog_id="dog-1",
        dog_name="Buddy",
    )
    manager._sensor_configs["dog-1"] = config
    manager._detection_states["dog-1"] = WalkDetectionState(dog_id="dog-1")

    monkeypatch.setattr(
        manager, "_validate_sensor_entity", AsyncMock(return_value=True)
    )
    stop_mock = AsyncMock()
    start_mock = AsyncMock()
    monkeypatch.setattr(manager, "_stop_sensor_monitoring", stop_mock)
    monkeypatch.setattr(manager, "_start_sensor_monitoring", start_mock)

    settings = {
        "minimum_duration": "240",
        "maximum_duration": "360",
        "door_closed_delay": "120",
        "auto_end_walk": "false",
        "confidence_threshold": "0.85",
    }

    assert await manager.async_update_dog_configuration("dog-1", None, settings)

    assert config.entity_id == "binary_sensor.front_door"
    assert config.minimum_walk_duration == 240
    assert config.maximum_walk_duration == 360
    assert config.door_closed_delay == 120
    assert config.auto_end_walks is False
    assert config.confidence_threshold == pytest.approx(0.85)
    stop_mock.assert_awaited_once()
    start_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_with_blank_sensor_removes_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Providing an empty sensor string should remove the configuration."""

    hass = Mock()
    manager = DoorSensorManager(hass, "entry")
    manager._sensor_configs["dog-1"] = DoorSensorConfig(
        entity_id="binary_sensor.back_door",
        dog_id="dog-1",
        dog_name="Buddy",
    )
    manager._detection_states["dog-1"] = WalkDetectionState(dog_id="dog-1")

    stop_mock = AsyncMock()
    monkeypatch.setattr(manager, "_stop_sensor_monitoring", stop_mock)
    start_mock = AsyncMock()
    monkeypatch.setattr(manager, "_start_sensor_monitoring", start_mock)

    assert await manager.async_update_dog_configuration("dog-1", "  ", None)
    assert "dog-1" not in manager._sensor_configs
    stop_mock.assert_awaited_once()
    start_mock.assert_not_called()


@pytest.mark.asyncio
async def test_update_without_changes_does_not_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No-op updates should avoid restarting monitoring."""

    hass = Mock()
    manager = DoorSensorManager(hass, "entry")
    config = DoorSensorConfig(
        entity_id="binary_sensor.side_door",
        dog_id="dog-1",
        dog_name="Buddy",
    )
    manager._sensor_configs["dog-1"] = config

    monkeypatch.setattr(manager, "_stop_sensor_monitoring", AsyncMock())
    monkeypatch.setattr(manager, "_start_sensor_monitoring", AsyncMock())

    assert await manager.async_update_dog_configuration("dog-1", None, {})
    manager._stop_sensor_monitoring.assert_not_called()  # type: ignore[attr-defined]
    manager._start_sensor_monitoring.assert_not_called()  # type: ignore[attr-defined]


def test_default_settings_constants() -> None:
    """Defaults should remain synchronised with the manager dataclass."""

    settings = DEFAULT_DOOR_SENSOR_SETTINGS
    assert settings.walk_detection_timeout == DEFAULT_WALK_DETECTION_TIMEOUT
    assert settings.minimum_walk_duration == DEFAULT_MINIMUM_WALK_DURATION
    assert settings.maximum_walk_duration == DEFAULT_MAXIMUM_WALK_DURATION
    assert settings.door_closed_delay == DEFAULT_DOOR_CLOSED_DELAY
    assert settings.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD
    assert settings.require_confirmation is True
    assert settings.auto_end_walks is True


@pytest.mark.asyncio
async def test_initialize_persists_trimmed_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Initialisation should persist trimmed sensor IDs and clamped settings."""

    hass = Mock()
    manager = DoorSensorManager(hass, "entry")
    data_manager = AsyncMock()
    monkeypatch.setattr(
        manager, "_validate_sensor_entity", AsyncMock(return_value=True)
    )

    dog: DogConfigData = {
        "dog_id": "dog-1",
        "dog_name": "Buddy",
        CONF_DOOR_SENSOR: " binary_sensor.garage_door ",
        CONF_DOOR_SENSOR_SETTINGS: {
            "minimum_duration": "240",
            "auto_end_walk": "false",
        },
    }

    await manager.async_initialize([dog], data_manager=data_manager)

    data_manager.async_update_dog_data.assert_awaited_once()
    persisted_dog_id, updates = data_manager.async_update_dog_data.await_args[0]
    assert persisted_dog_id == "dog-1"
    assert updates[CONF_DOOR_SENSOR] == "binary_sensor.garage_door"
    persisted_settings = updates[CONF_DOOR_SENSOR_SETTINGS]
    assert persisted_settings["minimum_walk_duration"] == 240
    assert persisted_settings["auto_end_walks"] is False


@pytest.mark.asyncio
async def test_update_persists_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime updates should push normalised payloads into the data manager."""

    hass = Mock()
    manager = DoorSensorManager(hass, "entry")
    manager._data_manager = AsyncMock()
    config = DoorSensorConfig(
        entity_id="binary_sensor.front_door",
        dog_id="dog-1",
        dog_name="Buddy",
    )
    manager._sensor_configs["dog-1"] = config
    monkeypatch.setattr(
        manager, "_validate_sensor_entity", AsyncMock(return_value=True)
    )

    await manager.async_update_dog_configuration(
        "dog-1",
        "binary_sensor.front_door",
        {"minimum_duration": "600"},
    )

    manager._data_manager.async_update_dog_data.assert_awaited_once()
    _, updates = manager._data_manager.async_update_dog_data.await_args[0]
    assert updates[CONF_DOOR_SENSOR_SETTINGS]["minimum_walk_duration"] == 600
