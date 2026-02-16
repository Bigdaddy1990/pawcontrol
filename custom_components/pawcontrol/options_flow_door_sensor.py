"""Door sensor configuration steps for the PawControl options flow."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict
from importlib import import_module
import logging
from typing import TYPE_CHECKING, Any, Protocol, cast

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import (
  CONF_DOG_NAME,
  CONF_DOGS,
  CONF_DOOR_SENSOR,
  CONF_DOOR_SENSOR_SETTINGS,
  DOOR_SENSOR_DEVICE_CLASSES,
)
from .door_sensor_manager import ensure_door_sensor_settings_config
from .flows.walk_helpers import WALK_SETTINGS_FIELDS
from .repairs import ISSUE_DOOR_SENSOR_PERSISTENCE_FAILURE, async_create_issue
from .runtime_data import RuntimeDataUnavailableError, require_runtime_data
from .selector_shim import selector
from .telemetry import record_door_sensor_persistence_failure
from .types import (
  DEFAULT_DOOR_SENSOR_SETTINGS,
  DOG_ID_FIELD,
  DOG_NAME_FIELD,
  DogConfigData,
  DoorSensorSettingsPayload,
  JSONLikeMapping,
  JSONMutableMapping,
  JSONValue,
  OptionsDogSelectionInput,
  OptionsDoorSensorInput,
  PawControlRuntimeData,
  ensure_dog_config_data,
)
from .validation import ValidationError, validate_sensor_entity_id

if TYPE_CHECKING:
  from homeassistant.config_entries import ConfigEntry  # noqa: E111

_LOGGER = logging.getLogger(__name__)

RuntimeDataResolver = Callable[[Any, Any], PawControlRuntimeData]
IssueCreator = Callable[..., Awaitable[None]]


def _resolve_require_runtime_data() -> RuntimeDataResolver:
  """Return the patched runtime data helper when available."""  # noqa: E111

  try:  # noqa: E111
    options_flow_module = import_module(
      "custom_components.pawcontrol.options_flow_support"
    )
    patched = getattr(options_flow_module, "require_runtime_data", None)
    if callable(patched):
      return patched  # noqa: E111
  except Exception:  # noqa: E111
    pass
  return require_runtime_data  # noqa: E111


def _resolve_async_create_issue() -> IssueCreator:
  """Return the patched repairs helper when available."""  # noqa: E111

  try:  # noqa: E111
    options_flow_module = import_module(
      "custom_components.pawcontrol.options_flow_support"
    )
    patched = getattr(options_flow_module, "async_create_issue", None)
    if callable(patched):
      return patched  # noqa: E111
  except Exception:  # noqa: E111
    pass
  return async_create_issue  # noqa: E111


if TYPE_CHECKING:

  class DoorSensorOptionsHost(Protocol):  # noqa: E111
    _current_dog: DogConfigData | None
    _dogs: list[DogConfigData]

    @property
    def _entry(self) -> ConfigEntry: ...

    hass: Any

    def __getattr__(self, name: str) -> Any: ...

else:  # pragma: no cover
  DoorSensorOptionsHost = object  # noqa: E111


class DoorSensorOptionsMixin(DoorSensorOptionsHost):
  _current_dog: DogConfigData | None  # noqa: E111
  _dogs: list[DogConfigData]  # noqa: E111

  async def async_step_select_dog_for_door_sensor(  # noqa: E111
    self,
    user_input: OptionsDogSelectionInput | None = None,
  ) -> ConfigFlowResult:
    """Select a dog for door sensor configuration."""

    current_dogs = list(self._dogs)
    if not current_dogs:
      return await self.async_step_manage_dogs()  # noqa: E111

    if user_input is not None:
      selected_dog_id = user_input.get("dog_id")  # noqa: E111
      self._current_dog = next(  # noqa: E111
        (dog for dog in current_dogs if dog.get(DOG_ID_FIELD) == selected_dog_id),
        None,
      )
      if self._current_dog:  # noqa: E111
        return await self.async_step_configure_door_sensor()
      return await self.async_step_manage_dogs()  # noqa: E111

    dog_options = [
      {
        "value": dog.get(DOG_ID_FIELD),
        "label": f"{dog.get(DOG_NAME_FIELD)} ({dog.get(DOG_ID_FIELD)})",
      }
      for dog in current_dogs
    ]

    return self.async_show_form(
      step_id="select_dog_for_door_sensor",
      data_schema=vol.Schema(
        {
          vol.Required("dog_id"): selector.SelectSelector(
            selector.SelectSelectorConfig(
              options=dog_options,
              mode=selector.SelectSelectorMode.DROPDOWN,
            ),
          ),
        },
      ),
    )

  async def async_step_configure_door_sensor(  # noqa: E111
    self,
    user_input: OptionsDoorSensorInput | None = None,
  ) -> ConfigFlowResult:
    """Configure door sensor entity and overrides for the current dog."""

    if not self._current_dog:
      return await self.async_step_manage_dogs()  # noqa: E111

    dog_id = cast(str | None, self._current_dog.get(DOG_ID_FIELD))
    if not isinstance(dog_id, str) or not dog_id:
      return await self.async_step_manage_dogs()  # noqa: E111

    raw_dog_name = self._current_dog.get(CONF_DOG_NAME)
    if isinstance(raw_dog_name, str) and raw_dog_name.strip():
      dog_name = raw_dog_name.strip()  # noqa: E111
    else:
      dog_name = dog_id  # noqa: E111

    available_sensors = self._get_available_door_sensors()
    existing_sensor = cast(
      str | None,
      self._current_dog.get(CONF_DOOR_SENSOR),
    )
    existing_payload = self._current_dog.get(CONF_DOOR_SENSOR_SETTINGS)
    existing_settings: Mapping[str, bool | int | float | str | None] | None = None
    if isinstance(existing_payload, Mapping):
      filtered_settings: dict[str, bool | int | float | str | None] = {}  # noqa: E111
      for key, value in existing_payload.items():  # noqa: E111
        if isinstance(value, bool | int | float | str) or value is None:
          filtered_settings[str(key)] = value  # noqa: E111
      existing_settings = filtered_settings  # noqa: E111
    base_settings = (
      ensure_door_sensor_settings_config(existing_settings)
      if isinstance(existing_settings, Mapping)
      else ensure_door_sensor_settings_config(None)
    )
    default_payload = asdict(DEFAULT_DOOR_SENSOR_SETTINGS)

    errors: dict[str, str] = {}

    if user_input is not None:
      sensor_value = user_input.get(CONF_DOOR_SENSOR)  # noqa: E111
      trimmed_sensor: str | None  # noqa: E111
      if isinstance(sensor_value, str):  # noqa: E111
        trimmed_sensor = sensor_value.strip()
        if not trimmed_sensor:
          trimmed_sensor = None  # noqa: E111
      else:  # noqa: E111
        trimmed_sensor = None

      if trimmed_sensor:  # noqa: E111
        try:
          trimmed_sensor = validate_sensor_entity_id(  # noqa: E111
            self.hass,
            trimmed_sensor,
            field=CONF_DOOR_SENSOR,
            domain="binary_sensor",
            device_classes=set(DOOR_SENSOR_DEVICE_CLASSES),
            not_found_constraint="door_sensor_not_found",
          )
        except ValidationError:
          errors[CONF_DOOR_SENSOR] = "door_sensor_not_found"  # noqa: E111

      settings_overrides: dict[str, bool | int | float | str | None] = {}  # noqa: E111
      for key in (  # noqa: E111
        *WALK_SETTINGS_FIELDS,
        "door_closed_delay",
        "require_confirmation",
        "confidence_threshold",
      ):
        value = user_input.get(key)
        if isinstance(value, bool | int | float | str) or value is None:
          settings_overrides[key] = value  # noqa: E111

      if not errors:  # noqa: E111
        normalised_settings = ensure_door_sensor_settings_config(
          cast(
            Mapping[str, bool | int | float | str | None],
            settings_overrides,
          ),
          base=base_settings,
        )
        settings_payload = asdict(normalised_settings)

        sensor_store = trimmed_sensor
        settings_store: DoorSensorSettingsPayload | None
        if not sensor_store or settings_payload == default_payload:
          settings_store = None  # noqa: E111
        else:
          settings_store = cast(  # noqa: E111
            DoorSensorSettingsPayload,
            settings_payload,
          )

        existing_sensor_trimmed = (
          existing_sensor.strip()
          if isinstance(existing_sensor, str) and existing_sensor.strip()
          else None
        )

        updated_dog: JSONMutableMapping = cast(
          JSONMutableMapping,
          dict(self._current_dog),
        )
        if sensor_store is None:
          updated_dog.pop(CONF_DOOR_SENSOR, None)  # noqa: E111
          updated_dog.pop(CONF_DOOR_SENSOR_SETTINGS, None)  # noqa: E111
        else:
          updated_dog[CONF_DOOR_SENSOR] = sensor_store  # noqa: E111
          if settings_store is None:  # noqa: E111
            updated_dog.pop(CONF_DOOR_SENSOR_SETTINGS, None)
          else:  # noqa: E111
            updated_dog[CONF_DOOR_SENSOR_SETTINGS] = cast(
              JSONValue,
              settings_store,
            )

        try:
          normalised_dog = ensure_dog_config_data(updated_dog)  # noqa: E111
          if normalised_dog is None:  # noqa: E111
            errors["base"] = "door_sensor_not_found"
        except ValueError:
          errors["base"] = "door_sensor_not_found"  # noqa: E111
        else:
          persist_updates: JSONMutableMapping = {}  # noqa: E111
          if existing_sensor_trimmed != sensor_store:  # noqa: E111
            persist_updates[CONF_DOOR_SENSOR] = sensor_store

          existing_settings_payload = existing_settings  # noqa: E111
          if isinstance(existing_settings_payload, Mapping):  # noqa: E111
            existing_settings_payload = dict(
              existing_settings_payload,
            )

          if (  # noqa: E111
            existing_settings_payload is not None or settings_store is not None
          ) and existing_settings_payload != settings_store:
            persist_updates[CONF_DOOR_SENSOR_SETTINGS] = cast(
              JSONValue,
              settings_store,
            )

          data_manager = None  # noqa: E111
          if persist_updates:  # noqa: E111
            try:
              runtime = _resolve_require_runtime_data()(  # noqa: E111
                self.hass,
                self._entry,
              )
            except RuntimeDataUnavailableError:
              _LOGGER.error(  # noqa: E111
                f"Runtime data unavailable while updating door sensor overrides for dog {dog_id}",  # noqa: E501
              )
              errors["base"] = "runtime_cache_unavailable"  # noqa: E111
            else:
              data_manager = getattr(  # noqa: E111
                runtime,
                "data_manager",
                None,
              )
              if data_manager is None:  # noqa: E111
                _LOGGER.error(
                  f"Door sensor overrides require an active data manager; runtime payload missing data_manager for dog {dog_id}",  # noqa: E501
                )
                errors["base"] = "runtime_cache_unavailable"
          if data_manager and persist_updates and "base" not in errors:  # noqa: E111
            try:
              await data_manager.async_update_dog_data(  # noqa: E111
                dog_id,
                persist_updates,
              )
            except Exception as err:  # pragma: no cover - defensive
              _LOGGER.error(  # noqa: E111
                "Failed to persist door sensor overrides for %s: %s",
                dog_id,
                err,
              )
              failure = record_door_sensor_persistence_failure(  # noqa: E111
                runtime,
                dog_id=dog_id,
                dog_name=dog_name,
                door_sensor=sensor_store or existing_sensor_trimmed,
                settings=settings_store,
                error=err,
              )
              issue_timestamp = (  # noqa: E111
                failure["recorded_at"]
                if failure and "recorded_at" in failure
                else dt_util.utcnow().isoformat()
              )
              issue_payload: JSONMutableMapping = {  # noqa: E111
                "dog_id": dog_id,
                "dog_name": dog_name,
                "door_sensor": sensor_store or existing_sensor_trimmed or "",
                "settings": cast(JSONValue, settings_store),
                "error": str(err),
                "timestamp": issue_timestamp,
              }
              try:  # noqa: E111
                await _resolve_async_create_issue()(
                  self.hass,
                  self._entry,
                  f"{self._entry.entry_id}_door_sensor_{dog_id}",
                  ISSUE_DOOR_SENSOR_PERSISTENCE_FAILURE,
                  cast(JSONLikeMapping, issue_payload),
                  severity="error",
                )
              except Exception as issue_err:  # pragma: no cover  # noqa: E111
                _LOGGER.debug(
                  "Skipping repair issue publication for %s: %s",
                  dog_id,
                  issue_err,
                )
              errors["base"] = "door_sensor_update_failed"  # noqa: E111
          elif persist_updates and "base" not in errors:  # noqa: E111
            _LOGGER.debug(
              "Data manager unavailable while updating door sensor for %s",
              dog_id,
            )

          if not errors:  # noqa: E111
            dog_index = next(
              (
                i for i, dog in enumerate(self._dogs) if dog.get(DOG_ID_FIELD) == dog_id
              ),
              -1,
            )
            if dog_index >= 0:
              self._dogs[dog_index] = normalised_dog  # noqa: E111
              typed_dogs = self._normalise_entry_dogs(self._dogs)  # noqa: E111
              self._dogs = typed_dogs  # noqa: E111
              self._current_dog = typed_dogs[dog_index]  # noqa: E111

              new_data = {**self._entry.data, CONF_DOGS: typed_dogs}  # noqa: E111
              self.hass.config_entries.async_update_entry(  # noqa: E111
                self._entry,
                data=new_data,
              )
              self._invalidate_profile_caches()  # noqa: E111
            return await self.async_step_manage_dogs()

    description_placeholders = {
      "dog_name": self._current_dog.get(CONF_DOG_NAME, dog_id),
      "current_sensor": existing_sensor or "None",
    }

    return self.async_show_form(
      step_id="configure_door_sensor",
      data_schema=self._get_door_sensor_settings_schema(
        available_sensors,
        current_sensor=existing_sensor,
        defaults=base_settings,
        user_input=user_input,
      ),
      errors=errors,
      description_placeholders=description_placeholders,
    )
