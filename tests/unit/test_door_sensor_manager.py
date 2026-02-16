"""Door sensor manager helper normalisation tests."""

from typing import cast
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
from custom_components.pawcontrol.types import (
  DogConfigData,
  DoorSensorConfigUpdate,
  DoorSensorOverrideScalar,
  DoorSensorSettingsInput,
  DoorSensorSettingsPayload,
)


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
def test_ensure_door_sensor_settings_config(
  overrides: DoorSensorSettingsInput | None, expected: DoorSensorSettingsConfig
) -> None:
  """Normalisation should coerce aliases, clamp values, and honour dataclasses."""  # noqa: E111

  result = ensure_door_sensor_settings_config(overrides)  # noqa: E111
  assert result == expected  # noqa: E111


def test_settings_clamp_extreme_values() -> None:
  """Overrides outside the allowed bounds should clamp to safe defaults."""  # noqa: E111

  base = DoorSensorSettingsConfig(  # noqa: E111
    walk_detection_timeout=90,
    minimum_walk_duration=120,
    maximum_walk_duration=3600,
    door_closed_delay=30,
    require_confirmation=True,
    auto_end_walks=True,
    confidence_threshold=0.6,
  )

  overrides = {  # noqa: E111
    "walk_detection_timeout": "999999",
    "minimum_walk_duration": "10",
    "maximum_walk_duration": "100000",
    "door_closed_delay": "2000",
    "confidence_threshold": "-5",
  }

  result = ensure_door_sensor_settings_config(overrides, base=base)  # noqa: E111

  assert result.walk_detection_timeout == 21600  # noqa: E111
  assert result.minimum_walk_duration == 60  # noqa: E111
  assert result.maximum_walk_duration == 43200  # noqa: E111
  assert result.door_closed_delay == 1800  # noqa: E111
  assert result.confidence_threshold == 0.0  # noqa: E111


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
  value: DoorSensorOverrideScalar, default: bool, expected: bool
) -> None:
  """Numeric strings and numbers should coerce using non-zero semantics."""  # noqa: E111

  assert _coerce_bool(value, default=default) is expected  # noqa: E111


def test_coerce_bool_invalid_strings_use_default() -> None:
  """Strings that are neither numeric nor keywords fall back to the default."""  # noqa: E111

  assert _coerce_bool("maybe", default=True) is True  # noqa: E111
  assert _coerce_bool("", default=False) is False  # noqa: E111


@pytest.mark.asyncio
async def test_update_settings_without_entity_change(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Settings updates should preserve the entity and restart monitoring when changed."""  # noqa: E111

  hass = Mock()  # noqa: E111
  manager = DoorSensorManager(hass, "entry")  # noqa: E111
  config = DoorSensorConfig(  # noqa: E111
    entity_id="binary_sensor.front_door",
    dog_id="dog-1",
    dog_name="Buddy",
  )
  manager._sensor_configs["dog-1"] = config  # noqa: E111
  manager._detection_states["dog-1"] = WalkDetectionState(dog_id="dog-1")  # noqa: E111

  monkeypatch.setattr(manager, "_validate_sensor_entity", AsyncMock(return_value=True))  # noqa: E111
  stop_mock = AsyncMock()  # noqa: E111
  start_mock = AsyncMock()  # noqa: E111
  monkeypatch.setattr(manager, "_stop_sensor_monitoring", stop_mock)  # noqa: E111
  monkeypatch.setattr(manager, "_start_sensor_monitoring", start_mock)  # noqa: E111

  settings = {  # noqa: E111
    "minimum_duration": "240",
    "maximum_duration": "360",
    "door_closed_delay": "120",
    "auto_end_walk": "false",
    "confidence_threshold": "0.85",
  }

  assert await manager.async_update_dog_configuration("dog-1", None, settings)  # noqa: E111

  assert config.entity_id == "binary_sensor.front_door"  # noqa: E111
  assert config.minimum_walk_duration == 240  # noqa: E111
  assert config.maximum_walk_duration == 360  # noqa: E111
  assert config.door_closed_delay == 120  # noqa: E111
  assert config.auto_end_walks is False  # noqa: E111
  assert config.confidence_threshold == pytest.approx(0.85)  # noqa: E111
  stop_mock.assert_awaited_once()  # noqa: E111
  start_mock.assert_awaited_once()  # noqa: E111


@pytest.mark.asyncio
async def test_update_with_blank_sensor_removes_configuration(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Providing an empty sensor string should remove the configuration."""  # noqa: E111

  hass = Mock()  # noqa: E111
  manager = DoorSensorManager(hass, "entry")  # noqa: E111
  manager._sensor_configs["dog-1"] = DoorSensorConfig(  # noqa: E111
    entity_id="binary_sensor.back_door",
    dog_id="dog-1",
    dog_name="Buddy",
  )
  manager._detection_states["dog-1"] = WalkDetectionState(dog_id="dog-1")  # noqa: E111

  stop_mock = AsyncMock()  # noqa: E111
  monkeypatch.setattr(manager, "_stop_sensor_monitoring", stop_mock)  # noqa: E111
  start_mock = AsyncMock()  # noqa: E111
  monkeypatch.setattr(manager, "_start_sensor_monitoring", start_mock)  # noqa: E111

  assert await manager.async_update_dog_configuration("dog-1", "  ", None)  # noqa: E111
  assert "dog-1" not in manager._sensor_configs  # noqa: E111
  stop_mock.assert_awaited_once()  # noqa: E111
  start_mock.assert_not_called()  # noqa: E111


@pytest.mark.asyncio
async def test_update_without_changes_does_not_restart(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """No-op updates should avoid restarting monitoring."""  # noqa: E111

  hass = Mock()  # noqa: E111
  manager = DoorSensorManager(hass, "entry")  # noqa: E111
  config = DoorSensorConfig(  # noqa: E111
    entity_id="binary_sensor.side_door",
    dog_id="dog-1",
    dog_name="Buddy",
  )
  manager._sensor_configs["dog-1"] = config  # noqa: E111

  monkeypatch.setattr(manager, "_stop_sensor_monitoring", AsyncMock())  # noqa: E111
  monkeypatch.setattr(manager, "_start_sensor_monitoring", AsyncMock())  # noqa: E111

  assert await manager.async_update_dog_configuration("dog-1", None, {})  # noqa: E111
  manager._stop_sensor_monitoring.assert_not_called()  # type: ignore[attr-defined]  # noqa: E111
  manager._start_sensor_monitoring.assert_not_called()  # type: ignore[attr-defined]  # noqa: E111


def test_default_settings_constants() -> None:
  """Defaults should remain synchronised with the manager dataclass."""  # noqa: E111

  settings = DEFAULT_DOOR_SENSOR_SETTINGS  # noqa: E111
  assert settings.walk_detection_timeout == DEFAULT_WALK_DETECTION_TIMEOUT  # noqa: E111
  assert settings.minimum_walk_duration == DEFAULT_MINIMUM_WALK_DURATION  # noqa: E111
  assert settings.maximum_walk_duration == DEFAULT_MAXIMUM_WALK_DURATION  # noqa: E111
  assert settings.door_closed_delay == DEFAULT_DOOR_CLOSED_DELAY  # noqa: E111
  assert settings.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD  # noqa: E111
  assert settings.require_confirmation is True  # noqa: E111
  assert settings.auto_end_walks is True  # noqa: E111


@pytest.mark.asyncio
async def test_initialize_persists_trimmed_payload(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Initialisation should persist trimmed sensor IDs and clamped settings."""  # noqa: E111

  hass = Mock()  # noqa: E111
  manager = DoorSensorManager(hass, "entry")  # noqa: E111
  data_manager = AsyncMock()  # noqa: E111
  monkeypatch.setattr(manager, "_validate_sensor_entity", AsyncMock(return_value=True))  # noqa: E111

  dog = cast(  # noqa: E111
    DogConfigData,
    {
      "dog_id": "dog-1",
      "dog_name": "Buddy",
      CONF_DOOR_SENSOR: " binary_sensor.garage_door ",
      CONF_DOOR_SENSOR_SETTINGS: {
        "minimum_duration": "240",
        "auto_end_walk": "false",
      },
    },
  )

  await manager.async_initialize([dog], data_manager=data_manager)  # noqa: E111

  data_manager.async_update_dog_data.assert_awaited_once()  # noqa: E111
  persisted_dog_id, updates_raw = data_manager.async_update_dog_data.await_args[0]  # noqa: E111
  updates = cast(DoorSensorConfigUpdate, updates_raw)  # noqa: E111
  assert persisted_dog_id == "dog-1"  # noqa: E111
  assert updates[CONF_DOOR_SENSOR] == "binary_sensor.garage_door"  # noqa: E111
  persisted_settings_raw = updates[CONF_DOOR_SENSOR_SETTINGS]  # noqa: E111
  assert isinstance(persisted_settings_raw, dict)  # noqa: E111
  persisted_settings = cast(DoorSensorSettingsPayload, persisted_settings_raw)  # noqa: E111
  assert persisted_settings["minimum_walk_duration"] == 240  # noqa: E111
  assert persisted_settings["auto_end_walks"] is False  # noqa: E111


@pytest.mark.asyncio
async def test_initialize_ignores_non_string_sensor(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Non-string sensor entries should be ignored safely."""  # noqa: E111

  hass = Mock()  # noqa: E111
  manager = DoorSensorManager(hass, "entry")  # noqa: E111
  data_manager = AsyncMock()  # noqa: E111
  validate_mock = AsyncMock(side_effect=AssertionError("should not validate"))  # noqa: E111
  monkeypatch.setattr(manager, "_validate_sensor_entity", validate_mock)  # noqa: E111

  dog = cast(  # noqa: E111
    DogConfigData,
    {
      "dog_id": "dog-1",
      "dog_name": "Buddy",
      CONF_DOOR_SENSOR: 42,
    },
  )

  await manager.async_initialize([dog], data_manager=data_manager)  # noqa: E111

  validate_mock.assert_not_called()  # noqa: E111
  data_manager.async_update_dog_data.assert_not_awaited()  # noqa: E111
  assert "dog-1" not in manager._sensor_configs  # noqa: E111


@pytest.mark.asyncio
async def test_initialize_discards_non_mapping_settings(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Settings objects that are not mappings should be ignored."""  # noqa: E111

  hass = Mock()  # noqa: E111
  manager = DoorSensorManager(hass, "entry")  # noqa: E111
  data_manager = AsyncMock()  # noqa: E111
  monkeypatch.setattr(manager, "_validate_sensor_entity", AsyncMock(return_value=True))  # noqa: E111

  dog = cast(  # noqa: E111
    DogConfigData,
    {
      "dog_id": "dog-1",
      "dog_name": "Buddy",
      CONF_DOOR_SENSOR: "binary_sensor.back_door",
      CONF_DOOR_SENSOR_SETTINGS: object(),
    },
  )

  await manager.async_initialize([dog], data_manager=data_manager)  # noqa: E111

  data_manager.async_update_dog_data.assert_not_awaited()  # noqa: E111
  assert manager._sensor_configs["dog-1"].entity_id == "binary_sensor.back_door"  # noqa: E111


@pytest.mark.asyncio
async def test_update_persists_changes(monkeypatch: pytest.MonkeyPatch) -> None:
  """Runtime updates should push normalised payloads into the data manager."""  # noqa: E111

  hass = Mock()  # noqa: E111
  manager = DoorSensorManager(hass, "entry")  # noqa: E111
  manager._data_manager = AsyncMock()  # noqa: E111
  config = DoorSensorConfig(  # noqa: E111
    entity_id="binary_sensor.front_door",
    dog_id="dog-1",
    dog_name="Buddy",
  )
  manager._sensor_configs["dog-1"] = config  # noqa: E111
  monkeypatch.setattr(manager, "_validate_sensor_entity", AsyncMock(return_value=True))  # noqa: E111

  await manager.async_update_dog_configuration(  # noqa: E111
    "dog-1",
    "binary_sensor.front_door",
    {"minimum_duration": "600"},
  )

  manager._data_manager.async_update_dog_data.assert_awaited_once()  # noqa: E111
  _, updates_raw = manager._data_manager.async_update_dog_data.await_args[0]  # noqa: E111
  updates = cast(DoorSensorConfigUpdate, updates_raw)  # noqa: E111
  updated_settings_raw = updates[CONF_DOOR_SENSOR_SETTINGS]  # noqa: E111
  assert isinstance(updated_settings_raw, dict)  # noqa: E111
  updated_settings = cast(DoorSensorSettingsPayload, updated_settings_raw)  # noqa: E111
  assert updated_settings["minimum_walk_duration"] == 600  # noqa: E111
