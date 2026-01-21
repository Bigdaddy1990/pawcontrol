"""External entity configuration steps for Paw Control configuration flow.

This module handles the configuration of external Home Assistant entities
that the integration depends on, including GPS sources, door sensors,
and notification services with comprehensive validation.

Quality Scale: Platinum target
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant

from .const import (
  CONF_DOOR_SENSOR,
  CONF_GPS_SOURCE,
  CONF_NOTIFY_FALLBACK,
  MODULE_GPS,
  MODULE_NOTIFICATIONS,
  MODULE_VISITOR,
)
from .exceptions import FlowValidationError, ValidationError
from .selector_shim import selector
from .types import (
  DOOR_SENSOR_FIELD,
  EXTERNAL_ENTITIES_PLACEHOLDERS_TEMPLATE,
  GPS_SOURCE_FIELD,
  NOTIFY_FALLBACK_FIELD,
  ConfigFlowPlaceholders,
  DogConfigData,
  DogModulesConfig,
  ExternalEntityConfig,
  ExternalEntitySelectorOption,
  clone_placeholders,
  freeze_placeholders,
)
from .validators import validate_gps_source

GPS_SOURCE_KEY: Final[Literal["gps_source"]] = cast(
  Literal["gps_source"],
  CONF_GPS_SOURCE,
)
DOOR_SENSOR_KEY: Final[Literal["door_sensor"]] = cast(
  Literal["door_sensor"],
  CONF_DOOR_SENSOR,
)
NOTIFY_FALLBACK_KEY: Final[Literal["notify_fallback"]] = cast(
  Literal["notify_fallback"],
  CONF_NOTIFY_FALLBACK,
)

_LOGGER = logging.getLogger(__name__)


def _build_external_entities_placeholders(
  *,
  gps_enabled: bool,
  visitor_enabled: bool,
  dog_count: int,
) -> ConfigFlowPlaceholders:
  """Return immutable placeholders for the external entities step."""

  placeholder_payload = clone_placeholders(
    EXTERNAL_ENTITIES_PLACEHOLDERS_TEMPLATE,
  )
  placeholder_payload["gps_enabled"] = gps_enabled
  placeholder_payload["visitor_enabled"] = visitor_enabled
  placeholder_payload["dog_count"] = dog_count

  return freeze_placeholders(placeholder_payload)


if TYPE_CHECKING:

  class ExternalFlowHost(Protocol):
    """Type-checking protocol describing the config flow host."""

    _dogs: list[DogConfigData]
    _enabled_modules: DogModulesConfig
    _external_entities: ExternalEntityConfig
    hass: HomeAssistant

    async def async_step_final_setup(
      self,
      user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
      """Type-checking stub for the mixin's final step delegation."""
      ...

    def async_show_form(
      self,
      *,
      step_id: str,
      data_schema: vol.Schema,
      description_placeholders: ConfigFlowPlaceholders | None = None,
      errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
      """Type-checking stub for Home Assistant form rendering."""
      ...

    def _get_available_device_trackers(self) -> dict[str, str]:
      """Type-checking stub for available device trackers."""
      ...

    def _get_available_person_entities(self) -> dict[str, str]:
      """Type-checking stub for available person entities."""
      ...

    def _get_available_door_sensors(self) -> dict[str, str]:
      """Type-checking stub for available door sensors."""
      ...

    def _get_available_notify_services(self) -> dict[str, str]:
      """Type-checking stub for available notification services."""
      ...

else:  # pragma: no cover - used only for type checking
  ExternalFlowHost = object


class ExternalEntityConfigurationMixin:
  """Mixin for external entity configuration functionality.

  This mixin provides methods for configuring external Home Assistant
  entities that the integration depends on during setup. This is critical
  for Platinum quality scale compliance and ensures proper integration
  with the broader Home Assistant ecosystem.
  """

  if TYPE_CHECKING:
    hass: HomeAssistant
    _dogs: list[DogConfigData]
    _enabled_modules: DogModulesConfig
    _external_entities: ExternalEntityConfig

    def _get_available_device_trackers(self) -> dict[str, str]: ...

    def _get_available_person_entities(self) -> dict[str, str]: ...

    def _get_available_door_sensors(self) -> dict[str, str]: ...

    def _get_available_notify_services(self) -> dict[str, str]: ...

  async def async_step_configure_external_entities(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure external entities required for enabled modules.

    This critical step configures external Home Assistant entities that
    the integration depends on. Required for Platinum quality scale compliance.

    Args:
        user_input: External entity configuration

    Returns:
        Configuration flow result for final setup
    """
    flow = cast(ExternalFlowHost, self)

    if user_input is not None:
      # Validate and store external entity selections
      try:
        validated_entities = await self._async_validate_external_entities(
          user_input,
        )
        self._merge_external_entity_config(
          flow._external_entities,
          validated_entities,
        )
        return await flow.async_step_final_setup()
      except FlowValidationError as err:
        return flow.async_show_form(
          step_id="configure_external_entities",
          data_schema=self._get_external_entities_schema(),
          errors=err.as_form_errors(),
        )

    return flow.async_show_form(
      step_id="configure_external_entities",
      data_schema=self._get_external_entities_schema(),
      description_placeholders=_build_external_entities_placeholders(
        gps_enabled=bool(
          flow._enabled_modules.get(MODULE_GPS, False),
        ),
        visitor_enabled=bool(
          flow._enabled_modules.get(MODULE_VISITOR, False),
        ),
        dog_count=len(flow._dogs),
      ),
    )

  def _get_external_entities_schema(self) -> vol.Schema:
    """Get schema for external entities configuration."""
    schema: dict[object, object] = {}

    if self._enabled_modules.get(MODULE_GPS, False):
      schema.update(self._build_gps_source_selector())

    if self._enabled_modules.get(MODULE_VISITOR, False):
      schema.update(self._build_door_sensor_selector())

    if self._enabled_modules.get(MODULE_NOTIFICATIONS, False):
      schema.update(self._build_notify_service_selector())

    return vol.Schema(schema)

  def _build_gps_source_selector(self) -> dict[object, object]:
    """Build selector schema for GPS source."""
    device_trackers = self._get_available_device_trackers()
    person_entities = self._get_available_person_entities()

    options: list[ExternalEntitySelectorOption] = []
    if device_trackers:
      options.extend(
        ExternalEntitySelectorOption(
          value=entity_id,
          label=f"📍 {name} (Device Tracker)",
        )
        for entity_id, name in device_trackers.items()
      )
    if person_entities:
      options.extend(
        ExternalEntitySelectorOption(
          value=entity_id,
          label=f"👤 {name} (Person)",
        )
        for entity_id, name in person_entities.items()
      )

    if options:
      selector_config = selector.SelectSelectorConfig(
        options=options,
        mode=selector.SelectSelectorMode.DROPDOWN,
      )
      return {
        vol.Required(CONF_GPS_SOURCE): selector.SelectSelector(selector_config),
      }

    selector_config = selector.SelectSelectorConfig(
      options=[
        ExternalEntitySelectorOption(
          value="manual",
          label="📝 Manual GPS (configure later)",
        ),
      ],
      mode=selector.SelectSelectorMode.DROPDOWN,
    )
    return {
      vol.Required(CONF_GPS_SOURCE, default="manual"): selector.SelectSelector(
        selector_config,
      ),
    }

  def _build_door_sensor_selector(self) -> dict[object, object]:
    """Build selector schema for door sensor."""
    door_sensors = self._get_available_door_sensors()
    if not door_sensors:
      return {}

    options: list[ExternalEntitySelectorOption] = [
      ExternalEntitySelectorOption(value="", label="None (optional)"),
    ]
    options.extend(
      ExternalEntitySelectorOption(value=entity_id, label=f"🚪 {name}")
      for entity_id, name in door_sensors.items()
    )

    selector_config = selector.SelectSelectorConfig(
      options=options,
      mode=selector.SelectSelectorMode.DROPDOWN,
    )
    return {
      vol.Optional(CONF_DOOR_SENSOR, default=""): selector.SelectSelector(
        selector_config,
      ),
    }

  def _build_notify_service_selector(self) -> dict[object, object]:
    """Build selector schema for notification fallback service."""
    notify_services = self._get_available_notify_services()
    if not notify_services:
      return {}

    options: list[ExternalEntitySelectorOption] = [
      ExternalEntitySelectorOption(
        value="",
        label="Default (persistent_notification)",
      ),
    ]
    options.extend(
      ExternalEntitySelectorOption(value=service_id, label=f"🔔 {name}")
      for service_id, name in notify_services.items()
    )

    selector_config = selector.SelectSelectorConfig(
      options=options,
      mode=selector.SelectSelectorMode.DROPDOWN,
    )
    return {
      vol.Optional(CONF_NOTIFY_FALLBACK, default=""): selector.SelectSelector(
        selector_config,
      ),
    }

  def _merge_external_entity_config(
    self,
    target: ExternalEntityConfig,
    new_config: ExternalEntityConfig,
  ) -> None:
    """Merge external entity selections into the target mapping."""

    if GPS_SOURCE_KEY in new_config:
      target[GPS_SOURCE_KEY] = new_config[GPS_SOURCE_KEY]

    if DOOR_SENSOR_KEY in new_config:
      target[DOOR_SENSOR_KEY] = new_config[DOOR_SENSOR_KEY]

    if NOTIFY_FALLBACK_KEY in new_config:
      target[NOTIFY_FALLBACK_KEY] = new_config[NOTIFY_FALLBACK_KEY]

  async def _async_validate_external_entities(
    self,
    user_input: ExternalEntityConfig,
  ) -> ExternalEntityConfig:
    """Validate external entity selections.

    Args:
        user_input: User selections to validate

    Returns:
        Validated entity configuration

    Raises:
        FlowValidationError: If validation fails
    """
    validated: ExternalEntityConfig = {}
    errors: dict[str, str] = {}
    base_errors: list[str] = []

    gps_source = cast(str | None, user_input.get(CONF_GPS_SOURCE))
    door_sensor = cast(str | None, user_input.get(CONF_DOOR_SENSOR))
    notify_service = cast(str | None, user_input.get(CONF_NOTIFY_FALLBACK))

    try:
      self._merge_external_entity_config(
        validated,
        self._validate_gps_source(gps_source),
      )
    except ValidationError as err:
      errors[CONF_GPS_SOURCE] = _map_external_error(err)

    try:
      self._merge_external_entity_config(
        validated,
        self._validate_door_sensor(door_sensor),
      )
    except ValidationError as err:
      errors[CONF_DOOR_SENSOR] = _map_external_error(err)

    try:
      self._merge_external_entity_config(
        validated,
        self._validate_notify_service(notify_service),
      )
    except ValidationError as err:
      if err.constraint == "notify_service_not_found":
        service_name = str(err.value) if err.value else "unknown"
        if isinstance(err.value, str) and "." in err.value:
          service_name = err.value.split(".", 1)[1]
        base_errors.append(f"Notification service {service_name} not found")
      else:
        errors[CONF_NOTIFY_FALLBACK] = _map_external_error(err)

    if errors or base_errors:
      raise FlowValidationError(field_errors=errors, base_errors=base_errors)

    return validated

  def _validate_gps_source(self, gps_source: str | None) -> ExternalEntityConfig:
    """Validate GPS source selection."""
    if not gps_source:
      return {}
    validated = validate_gps_source(
      self.hass,
      gps_source,
      field=CONF_GPS_SOURCE,
      allow_manual=True,
    )
    return {GPS_SOURCE_FIELD: validated}

  def _validate_door_sensor(self, door_sensor: str | None) -> ExternalEntityConfig:
    """Validate door sensor selection."""
    if not door_sensor:
      return {}
    state = self.hass.states.get(door_sensor)
    if not state:
      raise ValidationError(
        CONF_DOOR_SENSOR,
        door_sensor,
        "door_sensor_not_found",
      )
    return {DOOR_SENSOR_FIELD: door_sensor}

  def _validate_notify_service(
    self,
    notify_service: str | None,
  ) -> ExternalEntityConfig:
    """Validate notification service selection."""
    if not notify_service:
      return {}
    service_parts = notify_service.split(".", 1)
    if len(service_parts) != 2 or service_parts[0] != "notify":
      raise ValidationError(
        CONF_NOTIFY_FALLBACK,
        notify_service,
        "notify_service_invalid",
      )

    services = self.hass.services.async_services().get("notify", {})
    if service_parts[1] not in services:
      raise ValidationError(
        CONF_NOTIFY_FALLBACK,
        notify_service,
        "notify_service_not_found",
      )

    return {NOTIFY_FALLBACK_FIELD: notify_service}


def _map_external_error(error: ValidationError) -> str:
  if error.constraint == "gps_source_required":
    return "required"
  if error.constraint == "gps_source_not_found":
    return "gps_entity_not_found"
  if error.constraint == "gps_source_unavailable":
    return "gps_entity_unavailable"
  if error.constraint == "door_sensor_not_found":
    return "door_sensor_not_found"
  if error.constraint == "notify_service_invalid":
    return "invalid_notification_service"
  if error.constraint == "notify_service_not_found":
    return "notification_service_not_found"
  return "invalid_external_entity"
