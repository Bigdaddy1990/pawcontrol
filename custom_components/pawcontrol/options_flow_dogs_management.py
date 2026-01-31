"""Dog management steps for the PawControl options flow."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from .const import (
  CONF_DOG_AGE,
  CONF_DOG_BREED,
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOG_SIZE,
  CONF_DOG_WEIGHT,
  CONF_DOGS,
  CONF_DOOR_SENSOR,
  DOOR_SENSOR_DEVICE_CLASSES,
  MAX_DOGS_PER_ENTRY,
  MODULE_FEEDING,
  MODULE_GARDEN,
  MODULE_GPS,
  MODULE_HEALTH,
  MODULE_WALK,
)
from .exceptions import FlowValidationError
from .flow_validation import validate_dog_setup_input, validate_dog_update_input
from .flows.garden import GardenModuleSelectorMixin
from .flows.walk_schemas import (
  build_auto_end_walks_field,
  build_walk_timing_schema_fields,
)
from .grooming_translations import translated_grooming_label
from .selector_shim import selector
from .types import (
  DOG_AGE_FIELD,
  DOG_BREED_FIELD,
  DOG_ID_FIELD,
  DOG_MODULES_FIELD,
  DOG_NAME_FIELD,
  DOG_OPTIONS_FIELD,
  DOG_SIZE_FIELD,
  DOG_WEIGHT_FIELD,
  ConfigFlowPlaceholders,
  DogConfigData,
  DoorSensorSettingsConfig,
  JSONLikeMapping,
  JSONMutableMapping,
  JSONValue,
  ensure_dog_config_data,
  ensure_dog_modules_config,
  ensure_dog_modules_mapping,
  ensure_dog_options_entry,
  freeze_placeholders,
)

if TYPE_CHECKING:
  from .compat import ConfigEntry

_LOGGER = logging.getLogger(__name__)


if TYPE_CHECKING:

  class DogManagementOptionsHost(Protocol):
    _current_dog: DogConfigData | None
    _dogs: list[DogConfigData]

    @property
    def _entry(self) -> ConfigEntry: ...

    hass: Any

    def __getattr__(self, name: str) -> Any: ...

else:  # pragma: no cover
  DogManagementOptionsHost = object


class DogManagementOptionsMixin(GardenModuleSelectorMixin, DogManagementOptionsHost):
  _current_dog: DogConfigData | None
  _dogs: list[DogConfigData]

  async def async_step_manage_dogs(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Manage dogs - add, edit, or remove dogs."""
    if user_input is not None:
      action = user_input.get("action")
      if action == "add_dog":
        return await self.async_step_add_new_dog()
      if action == "edit_dog":
        return await self.async_step_select_dog_to_edit()
      if action == "remove_dog":
        return await self.async_step_select_dog_to_remove()
      if action == "configure_modules":  # NEW: Module configuration
        return await self.async_step_select_dog_for_modules()
      if action == "configure_door_sensor":
        return await self.async_step_select_dog_for_door_sensor()
      return await self.async_step_init()

    # Show dog management menu
    dogs_raw = self._entry.data.get(CONF_DOGS, [])
    current_dogs: list[JSONLikeMapping] = (
      list(cast(Sequence[JSONLikeMapping], dogs_raw))
      if isinstance(dogs_raw, Sequence) and not isinstance(dogs_raw, str | bytes)
      else []
    )

    return self.async_show_form(
      step_id="manage_dogs",
      data_schema=vol.Schema(
        {
          vol.Required("action", default="add_dog"): vol.In(
            {
              "add_dog": "Add new dog",
              "edit_dog": "Edit existing dog" if current_dogs else "No dogs to edit",
              "configure_modules": "Configure dog modules"  # NEW
              if current_dogs
              else "No dogs to configure",
              "configure_door_sensor": "Configure door sensors"
              if current_dogs
              else "No door sensors to configure",
              "remove_dog": "Remove dog" if current_dogs else "No dogs to remove",
              "back": "Back to main menu",
            },
          ),
        },
      ),
      description_placeholders=dict(
        freeze_placeholders(
          {
            "current_dogs_count": str(len(current_dogs)),
            "dogs_list": "\n".join(
              [
                f"• {dog.get(CONF_DOG_NAME, 'Unknown')} ({dog.get(CONF_DOG_ID, 'unknown')})"
                for dog in current_dogs
                if isinstance(dog, Mapping)
              ],
            )
            if current_dogs
            else "No dogs configured",
          },
        ),
      ),
    )

  async def async_step_select_dog_for_modules(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select which dog to configure modules for.

    NEW: Allows per-dog module configuration
    """
    current_dogs = list(self._dogs)

    if not current_dogs:
      return await self.async_step_manage_dogs()

    if user_input is not None:
      selected_dog_id = user_input.get("dog_id")
      self._current_dog = next(
        (dog for dog in current_dogs if dog.get(DOG_ID_FIELD) == selected_dog_id),
        None,
      )
      if self._current_dog:
        return await self.async_step_configure_dog_modules()
      return await self.async_step_manage_dogs()

    # Create selection options
    dog_options = [
      {
        "value": dog.get(DOG_ID_FIELD),
        "label": f"{dog.get(DOG_NAME_FIELD)} ({dog.get(DOG_ID_FIELD)})",
      }
      for dog in current_dogs
    ]

    return self.async_show_form(
      step_id="select_dog_for_modules",
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

  async def async_step_configure_dog_modules(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure modules for the selected dog.

    NEW: Per-dog module configuration with entity count preview
    """
    if not self._current_dog:
      return await self.async_step_manage_dogs()

    if user_input is not None:
      dog_id = self._current_dog.get(DOG_ID_FIELD)
      if not isinstance(dog_id, str):
        return self.async_show_form(
          step_id="configure_dog_modules",
          data_schema=self._get_dog_modules_schema(),
          errors={"base": "invalid_dog"},
        )

      updated_modules = {
        MODULE_FEEDING: bool(user_input.get("module_feeding", True)),
        MODULE_WALK: bool(user_input.get("module_walk", True)),
        MODULE_GPS: bool(user_input.get("module_gps", False)),
        MODULE_GARDEN: bool(user_input.get("module_garden", False)),
        MODULE_HEALTH: bool(user_input.get("module_health", True)),
        "notifications": bool(user_input.get("module_notifications", True)),
        "dashboard": bool(user_input.get("module_dashboard", True)),
        "visitor": bool(user_input.get("module_visitor", False)),
        "grooming": bool(user_input.get("module_grooming", False)),
        "medication": bool(user_input.get("module_medication", False)),
        "training": bool(user_input.get("module_training", False)),
      }

      try:
        modules_payload = ensure_dog_modules_config(updated_modules)
        dog_index = next(
          (i for i, dog in enumerate(self._dogs) if dog.get(DOG_ID_FIELD) == dog_id),
          -1,
        )

        if dog_index >= 0:
          candidate = cast(
            DogConfigData,
            {
              **self._dogs[dog_index],
              DOG_MODULES_FIELD: modules_payload,
            },
          )
          normalised = ensure_dog_config_data(
            cast(Mapping[str, JSONValue], candidate),
          )
          if normalised is None:
            raise FlowValidationError(
              base_errors=["invalid_dog_config"],
            )

          self._dogs[dog_index] = normalised
          self._current_dog = normalised

          typed_dogs = self._normalise_entry_dogs(self._dogs)
          new_data = {**self._entry.data, CONF_DOGS: typed_dogs}

          self.hass.config_entries.async_update_entry(
            self._entry,
            data=new_data,
          )
          self._dogs = typed_dogs
      except FlowValidationError as err:
        return self.async_show_form(
          step_id="configure_dog_modules",
          data_schema=self._get_dog_modules_schema(),
          errors=err.as_form_errors(),
        )
      except Exception as err:
        _LOGGER.error("Error configuring dog modules: %s", err)
        return self.async_show_form(
          step_id="configure_dog_modules",
          data_schema=self._get_dog_modules_schema(),
          errors={"base": "module_config_failed"},
        )

      dog_options = self._current_dog_options()
      existing = dog_options.get(dog_id, {})
      entry = ensure_dog_options_entry(
        cast(JSONLikeMapping, dict(existing)),
        dog_id=dog_id,
      )
      entry[DOG_ID_FIELD] = dog_id
      entry[DOG_MODULES_FIELD] = modules_payload
      dog_options[dog_id] = entry

      new_options = self._clone_options()
      new_options[DOG_OPTIONS_FIELD] = dog_options
      self._invalidate_profile_caches()

      return self.async_create_entry(title="", data=new_options)

    return self.async_show_form(
      step_id="configure_dog_modules",
      data_schema=self._get_dog_modules_schema(),
      description_placeholders=dict(
        await self._get_module_description_placeholders(),
      ),
    )

  def _get_door_sensor_settings_schema(
    self,
    available: Mapping[str, str],
    *,
    current_sensor: str | None,
    defaults: DoorSensorSettingsConfig,
    user_input: dict[str, Any] | None = None,
  ) -> vol.Schema:
    """Build schema for configuring per-dog door sensor overrides."""

    values = dict(user_input or {})
    sensor_default = values.get(CONF_DOOR_SENSOR)
    if not isinstance(sensor_default, str):
      sensor_default = current_sensor or ""

    schema_dict: dict[Any, Any] = {}

    if available:
      options = [{"value": "", "label": "None (disable)"}]
      options.extend(
        {
          "value": entity_id,
          "label": f"🚪 {name}",
        }
        for entity_id, name in sorted(available.items())
      )
      schema_dict[vol.Optional(CONF_DOOR_SENSOR, default=sensor_default)] = (
        selector.SelectSelector(
          selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
          ),
        )
      )
    else:
      schema_dict[vol.Optional(CONF_DOOR_SENSOR, default=sensor_default)] = (
        selector.TextSelector(
          selector.TextSelectorConfig(
            type=selector.TextSelectorType.TEXT,
            autocomplete="off",
          ),
        )
      )

    def _value(key: str, fallback: Any) -> Any:
      return values.get(key, fallback)

    schema_dict.update(
      build_walk_timing_schema_fields(values, defaults),
    )
    schema_dict[
      vol.Optional(
        "door_closed_delay",
        default=_value(
          "door_closed_delay",
          defaults.door_closed_delay,
        ),
      )
    ] = selector.NumberSelector(
      selector.NumberSelectorConfig(
        min=0,
        max=1800,
        step=5,
        mode=selector.NumberSelectorMode.BOX,
        unit_of_measurement="seconds",
      ),
    )
    schema_dict[
      vol.Optional(
        "require_confirmation",
        default=_value(
          "require_confirmation",
          defaults.require_confirmation,
        ),
      )
    ] = selector.BooleanSelector()
    schema_dict.update(
      build_auto_end_walks_field(values, defaults),
    )
    schema_dict[
      vol.Optional(
        "confidence_threshold",
        default=_value(
          "confidence_threshold",
          defaults.confidence_threshold,
        ),
      )
    ] = selector.NumberSelector(
      selector.NumberSelectorConfig(
        min=0.0,
        max=1.0,
        step=0.05,
        mode=selector.NumberSelectorMode.BOX,
      ),
    )

    return vol.Schema(schema_dict)

  def _get_dog_modules_schema(self) -> vol.Schema:
    """Get modules configuration schema for current dog."""
    if not self._current_dog:
      return vol.Schema({})

    current_modules = ensure_dog_modules_mapping(self._current_dog)

    schema_fields: dict[vol.Optional, selector.BooleanSelector] = {
      vol.Optional(
        "module_feeding",
        default=current_modules.get(MODULE_FEEDING, True),
      ): selector.BooleanSelector(),
      vol.Optional(
        "module_walk",
        default=current_modules.get(MODULE_WALK, True),
      ): selector.BooleanSelector(),
      vol.Optional(
        "module_gps",
        default=current_modules.get(MODULE_GPS, False),
      ): selector.BooleanSelector(),
      vol.Optional(
        "module_health",
        default=current_modules.get(MODULE_HEALTH, True),
      ): selector.BooleanSelector(),
      vol.Optional(
        "module_notifications",
        default=current_modules.get("notifications", True),
      ): selector.BooleanSelector(),
      vol.Optional(
        "module_dashboard",
        default=current_modules.get("dashboard", True),
      ): selector.BooleanSelector(),
      vol.Optional(
        "module_visitor",
        default=current_modules.get("visitor", False),
      ): selector.BooleanSelector(),
      vol.Optional(
        "module_grooming",
        default=current_modules.get("grooming", False),
      ): selector.BooleanSelector(),
      vol.Optional(
        "module_medication",
        default=current_modules.get("medication", False),
      ): selector.BooleanSelector(),
      vol.Optional(
        "module_training",
        default=current_modules.get("training", False),
      ): selector.BooleanSelector(),
    }
    schema_fields.update(
      self._build_garden_module_selector(
        field="module_garden",
        default=current_modules.get(MODULE_GARDEN, False),
      ),
    )

    return vol.Schema(schema_fields)

  def _get_available_door_sensors(self) -> dict[str, str]:
    """Return mapping of available door sensors by friendly name."""

    sensors: dict[str, str] = {}
    for entity_id in self.hass.states.async_entity_ids("binary_sensor"):
      state = self.hass.states.get(entity_id)
      if state is None:
        continue
      device_class = state.attributes.get("device_class")
      if device_class not in DOOR_SENSOR_DEVICE_CLASSES:
        continue
      friendly_name = state.attributes.get("friendly_name", entity_id)
      sensors[entity_id] = str(friendly_name)
    return sensors

  async def _get_module_description_placeholders(
    self,
  ) -> ConfigFlowPlaceholders:
    """Get description placeholders for module configuration."""
    if not self._current_dog:
      return freeze_placeholders({})

    profile_value = self._entry.options.get("entity_profile", "standard")
    current_profile = (
      profile_value
      if isinstance(
        profile_value,
        str,
      )
      else str(profile_value)
    )
    current_modules_dict = ensure_dog_modules_config(self._current_dog)

    hass_language: str | None = None
    if self.hass is not None:
      hass_config = getattr(self.hass, "config", None)
      if hass_config is not None:
        hass_language = getattr(hass_config, "language", None)

    # Calculate current entity count
    current_estimate = await self._entity_factory.estimate_entity_count_async(
      current_profile,
      current_modules_dict,
    )

    # Module descriptions
    module_descriptions = {
      MODULE_FEEDING: "Food tracking, scheduling, portion control",
      MODULE_WALK: "Walk tracking, duration, distance monitoring",
      MODULE_GPS: "Location tracking, geofencing, route recording",
      MODULE_HEALTH: "Weight tracking, vet reminders, medication",
      "notifications": "Alerts, reminders, status notifications",
      "dashboard": "Custom dashboard generation",
      "visitor": "Visitor mode for reduced monitoring",
      "grooming": translated_grooming_label(
        hass_language,
        "module_summary_description",
      ),
      "medication": "Medication reminders and tracking",
      "training": "Training progress and notes",
    }

    module_labels = {
      "grooming": translated_grooming_label(
        hass_language,
        "module_summary_label",
      ),
    }

    enabled_modules = [
      f"• {module_labels.get(module, module)}: {module_descriptions.get(module, 'Module functionality')}"
      for module, enabled in current_modules_dict.items()
      if enabled
    ]
    enabled_summary = (
      "\n".join(
        enabled_modules,
      )
      if enabled_modules
      else "None"
    )

    dog_name = str(self._current_dog.get(CONF_DOG_NAME, "Unknown"))

    return freeze_placeholders(
      {
        "dog_name": dog_name,
        "current_profile": str(current_profile),
        "current_entities": str(current_estimate),
        "enabled_modules": enabled_summary,
      },
    )

  # Rest of the existing methods (add_new_dog, edit_dog, etc.) remain the same...

  async def async_step_add_new_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Add a new dog to the configuration."""
    errors: dict[str, str] = {}
    if user_input is not None:
      try:
        validated = validate_dog_setup_input(
          user_input,
          existing_ids={
            str(dog.get(DOG_ID_FIELD)).strip().lower()
            for dog in self._dogs
            if isinstance(dog.get(DOG_ID_FIELD), str)
          },
          existing_names={
            str(dog.get(DOG_NAME_FIELD)).strip().lower()
            for dog in self._dogs
            if isinstance(dog.get(DOG_NAME_FIELD), str)
            and str(dog.get(DOG_NAME_FIELD)).strip()
          },
          current_dog_count=len(self._dogs),
          max_dogs=MAX_DOGS_PER_ENTRY,
        )

        modules_config = ensure_dog_modules_config(
          {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_HEALTH: True,
            MODULE_GPS: False,
            MODULE_GARDEN: False,
            "notifications": True,
            "dashboard": True,
            "visitor": False,
            "grooming": False,
            "medication": False,
            "training": False,
          },
        )

        candidate: JSONMutableMapping = {
          DOG_ID_FIELD: validated["dog_id"],
          DOG_NAME_FIELD: validated["dog_name"],
          DOG_MODULES_FIELD: cast(JSONValue, modules_config),
          DOG_AGE_FIELD: validated.get("dog_age", 3),
          DOG_WEIGHT_FIELD: validated["dog_weight"],
          DOG_SIZE_FIELD: validated["dog_size"],
        }
        candidate[DOG_BREED_FIELD] = validated.get("dog_breed", "Mixed Breed")

        new_dogs_raw = [
          *self._dogs,
          cast(DogConfigData, dict(candidate)),
        ]
        typed_dogs = self._normalise_entry_dogs(new_dogs_raw)
        self._dogs = typed_dogs
        self._current_dog = typed_dogs[-1]

        new_data = {**self._entry.data, CONF_DOGS: typed_dogs}

        self.hass.config_entries.async_update_entry(
          self._entry,
          data=new_data,
        )
        self._invalidate_profile_caches()

        return await self.async_step_init()
      except FlowValidationError as err:
        errors.update(err.as_form_errors())
      except Exception as err:
        _LOGGER.error("Error adding new dog: %s", err)
        errors["base"] = "add_dog_failed"

    return self.async_show_form(
      step_id="add_new_dog",
      data_schema=self._get_add_dog_schema(),
      errors=errors,
    )

  def _get_add_dog_schema(self) -> vol.Schema:
    """Get schema for adding a new dog."""
    return vol.Schema(
      {
        vol.Required(CONF_DOG_ID): selector.TextSelector(
          selector.TextSelectorConfig(
            type=selector.TextSelectorType.TEXT,
            autocomplete="off",
          ),
        ),
        vol.Required(CONF_DOG_NAME): selector.TextSelector(
          selector.TextSelectorConfig(
            type=selector.TextSelectorType.TEXT,
            autocomplete="name",
          ),
        ),
        vol.Optional(CONF_DOG_BREED, default=""): selector.TextSelector(),
        vol.Optional(CONF_DOG_AGE, default=3): selector.NumberSelector(
          selector.NumberSelectorConfig(
            min=0,
            max=30,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
          ),
        ),
        vol.Optional(CONF_DOG_WEIGHT, default=20.0): selector.NumberSelector(
          selector.NumberSelectorConfig(
            min=0.5,
            max=200.0,
            step=0.1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="kg",
          ),
        ),
        vol.Optional(CONF_DOG_SIZE, default="medium"): selector.SelectSelector(
          selector.SelectSelectorConfig(
            options=["toy", "small", "medium", "large", "giant"],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="dog_size",
          ),
        ),
      },
    )

  def _get_remove_dog_schema(
    self,
    dogs: Sequence[Mapping[str, JSONValue]],
  ) -> vol.Schema:
    """Build the removal confirmation schema for the provided dog list."""

    dog_options: list[dict[str, str]] = []
    for dog in dogs:
      dog_id = dog.get(DOG_ID_FIELD)
      dog_name = dog.get(DOG_NAME_FIELD)
      if not isinstance(dog_id, str) or not dog_id:
        continue
      label_name = (
        dog_name
        if isinstance(
          dog_name,
          str,
        )
        and dog_name
        else dog_id
      )
      dog_options.append(
        {
          "value": dog_id,
          "label": f"{label_name} ({dog_id})",
        },
      )

    return vol.Schema(
      {
        vol.Required("dog_id"): selector.SelectSelector(
          selector.SelectSelectorConfig(
            options=dog_options,
            mode=selector.SelectSelectorMode.DROPDOWN,
          ),
        ),
        vol.Required(
          "confirm_remove",
          default=False,
        ): selector.BooleanSelector(),
      },
    )

  async def async_step_select_dog_to_edit(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select which dog to edit."""
    current_dogs_raw = self._entry.data.get(CONF_DOGS, [])
    current_dogs: list[DogConfigData] = []
    if isinstance(current_dogs_raw, Sequence):
      for dog in current_dogs_raw:
        if isinstance(dog, Mapping):
          normalised = ensure_dog_config_data(
            cast(Mapping[str, JSONValue], dog),
          )
          if normalised is not None:
            current_dogs.append(normalised)
    current_dogs = cast(list[DogConfigData], current_dogs)
    current_dogs = cast(list[DogConfigData], current_dogs)

    if not current_dogs:
      return await self.async_step_init()

    if user_input is not None:
      selected_dog_id = user_input.get("dog_id")
      self._current_dog = next(
        (dog for dog in current_dogs if dog.get(CONF_DOG_ID) == selected_dog_id),
        None,
      )
      if self._current_dog:
        return await self.async_step_edit_dog()
      return await self.async_step_init()

    # Create selection options
    dog_options = [
      {
        "value": dog.get(CONF_DOG_ID),
        "label": f"{dog.get(CONF_DOG_NAME)} ({dog.get(CONF_DOG_ID)})",
      }
      for dog in current_dogs
    ]

    return self.async_show_form(
      step_id="select_dog_to_edit",
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

  async def async_step_edit_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Edit the selected dog."""
    if not self._current_dog:
      return await self.async_step_init()

    if user_input is not None:
      try:
        target_id = self._current_dog[DOG_ID_FIELD]
        dog_index = next(
          (i for i, dog in enumerate(self._dogs) if dog[DOG_ID_FIELD] == target_id),
          -1,
        )

        if dog_index >= 0:
          existing_names = {
            str(dog.get(DOG_NAME_FIELD)).strip().lower()
            for dog in self._dogs
            if isinstance(dog.get(DOG_NAME_FIELD), str)
            and dog.get(DOG_ID_FIELD) != target_id
            and str(dog.get(DOG_NAME_FIELD)).strip()
          }
          candidate = validate_dog_update_input(
            cast(DogConfigData, dict(self._dogs[dog_index])),
            user_input,
            existing_names=existing_names,
          )
          normalised = ensure_dog_config_data(
            cast(Mapping[str, JSONValue], candidate),
          )
          if normalised is None:
            raise FlowValidationError(
              base_errors=["invalid_dog_config"],
            )

          self._dogs[dog_index] = normalised
          typed_dogs = self._normalise_entry_dogs(self._dogs)
          self._dogs = typed_dogs
          self._current_dog = normalised

          new_data = {**self._entry.data, CONF_DOGS: typed_dogs}

          self.hass.config_entries.async_update_entry(
            self._entry,
            data=new_data,
          )
          self._invalidate_profile_caches()

        return await self.async_step_init()
      except FlowValidationError as err:
        return self.async_show_form(
          step_id="edit_dog",
          data_schema=self._get_edit_dog_schema(),
          errors=err.as_form_errors(),
        )
      except Exception as err:
        _LOGGER.error("Error editing dog: %s", err)
        return self.async_show_form(
          step_id="edit_dog",
          data_schema=self._get_edit_dog_schema(),
          errors={"base": "edit_dog_failed"},
        )

    return self.async_show_form(
      step_id="edit_dog",
      data_schema=self._get_edit_dog_schema(),
    )

  def _get_edit_dog_schema(self) -> vol.Schema:
    """Get schema for editing a dog with current values pre-filled."""
    if not self._current_dog:
      return vol.Schema({})

    return vol.Schema(
      {
        vol.Optional(
          CONF_DOG_NAME,
          default=self._current_dog.get(
            CONF_DOG_NAME,
            "",
          ),
        ): selector.TextSelector(),
        vol.Optional(
          CONF_DOG_BREED,
          default=self._current_dog.get(CONF_DOG_BREED, ""),
        ): selector.TextSelector(),
        vol.Optional(
          CONF_DOG_AGE,
          default=self._current_dog.get(CONF_DOG_AGE, 3),
        ): selector.NumberSelector(
          selector.NumberSelectorConfig(
            min=0,
            max=30,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
          ),
        ),
        vol.Optional(
          CONF_DOG_WEIGHT,
          default=self._current_dog.get(CONF_DOG_WEIGHT, 20.0),
        ): selector.NumberSelector(
          selector.NumberSelectorConfig(
            min=0.5,
            max=200.0,
            step=0.1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="kg",
          ),
        ),
        vol.Optional(
          CONF_DOG_SIZE,
          default=self._current_dog.get(CONF_DOG_SIZE, "medium"),
        ): selector.SelectSelector(
          selector.SelectSelectorConfig(
            options=["toy", "small", "medium", "large", "giant"],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="dog_size",
          ),
        ),
      },
    )

  async def async_step_select_dog_to_remove(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select which dog to remove."""
    current_dogs = list(self._dogs)

    if not current_dogs:
      return await self.async_step_init()

    if user_input is not None:
      if user_input.get("confirm_remove"):
        selected_dog_id = user_input.get("dog_id")
        # Remove the selected dog
        updated_dogs = [
          dog for dog in current_dogs if dog.get(DOG_ID_FIELD) != selected_dog_id
        ]

        try:
          typed_dogs = self._normalise_entry_dogs(updated_dogs)
        except FlowValidationError as err:  # pragma: no cover - defensive guard
          _LOGGER.error(
            "Invalid dog configuration during removal: %s",
            err,
          )
          return self.async_show_form(
            step_id="select_dog_to_remove",
            data_schema=self._get_remove_dog_schema(
              cast(Sequence[Mapping[str, JSONValue]], current_dogs),
            ),
            errors={"base": "dog_remove_failed"},
          )

        # Update config entry
        new_data = {**self._entry.data, CONF_DOGS: typed_dogs}

        self.hass.config_entries.async_update_entry(
          self._entry,
          data=new_data,
        )
        self._dogs = typed_dogs
        if self._current_dog and (
          self._current_dog.get(DOG_ID_FIELD) == selected_dog_id
        ):
          self._current_dog = typed_dogs[0] if typed_dogs else None

        new_options = self._clone_options()
        dog_options = self._current_dog_options()
        if isinstance(selected_dog_id, str) and selected_dog_id in dog_options:
          dog_options.pop(selected_dog_id, None)
          new_options[DOG_OPTIONS_FIELD] = dog_options

        self._invalidate_profile_caches()

        typed_options = self._normalise_options_snapshot(new_options)

        return self.async_create_entry(title="", data=typed_options)

      return await self.async_step_init()

    # Create removal confirmation form
    return self.async_show_form(
      step_id="select_dog_to_remove",
      data_schema=self._get_remove_dog_schema(
        cast(Sequence[Mapping[str, JSONValue]], current_dogs),
      ),
      description_placeholders=dict(
        freeze_placeholders(
          {
            "warning": (
              "This will permanently remove the selected dog and all associated data!"
            ),
          },
        ),
      ),
    )

  # NEW: Weather Settings Configuration
