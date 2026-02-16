"""External entity configuration steps for Paw Control configuration flow.

This module handles the configuration of external Home Assistant entities
that the integration depends on, including GPS sources, door sensors,
and notification services with comprehensive validation.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

import logging
from typing import TYPE_CHECKING, Final, Literal, Protocol, cast

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant
import voluptuous as vol

from .const import (
  CONF_DOOR_SENSOR,
  CONF_GPS_SOURCE,
  CONF_NOTIFY_FALLBACK,
  DOOR_SENSOR_DEVICE_CLASSES,
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
  ConfigFlowUserInput,
  DogConfigData,
  DogModulesConfig,
  ExternalEntityConfig,
  ExternalEntitySelectorOption,
  clone_placeholders,
  freeze_placeholders,
)
from .validation import (
  validate_gps_source,
  validate_notify_service,
  validate_sensor_entity_id,
)

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
  """Return immutable placeholders for the external entities step."""  # noqa: E111

  placeholder_payload = clone_placeholders(  # noqa: E111
    EXTERNAL_ENTITIES_PLACEHOLDERS_TEMPLATE,
  )
  placeholder_payload["gps_enabled"] = gps_enabled  # noqa: E111
  placeholder_payload["visitor_enabled"] = visitor_enabled  # noqa: E111
  placeholder_payload["dog_count"] = dog_count  # noqa: E111

  return freeze_placeholders(placeholder_payload)  # noqa: E111


if TYPE_CHECKING:

  class ExternalFlowHost(Protocol):  # noqa: E111
    """Type-checking protocol describing the config flow host."""

    _dogs: list[DogConfigData]
    _enabled_modules: DogModulesConfig
    _external_entities: ExternalEntityConfig
    hass: HomeAssistant

    async def async_step_final_setup(
      self,
      user_input: ConfigFlowUserInput | None = None,
    ) -> ConfigFlowResult:
      """Type-checking stub for the mixin's final step delegation."""  # noqa: E111
      ...  # noqa: E111

    def async_show_form(
      self,
      *,
      step_id: str,
      data_schema: vol.Schema,
      description_placeholders: ConfigFlowPlaceholders | None = None,
      errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
      """Type-checking stub for Home Assistant form rendering."""  # noqa: E111
      ...  # noqa: E111

    def _get_available_device_trackers(self) -> dict[str, str]:
      """Type-checking stub for available device trackers."""  # noqa: E111
      ...  # noqa: E111

    def _get_available_person_entities(self) -> dict[str, str]:
      """Type-checking stub for available person entities."""  # noqa: E111
      ...  # noqa: E111

    def _get_available_door_sensors(self) -> dict[str, str]:
      """Type-checking stub for available door sensors."""  # noqa: E111
      ...  # noqa: E111

    def _get_available_notify_services(self) -> dict[str, str]:
      """Type-checking stub for available notification services."""  # noqa: E111
      ...  # noqa: E111

else:  # pragma: no cover - used only for type checking
  ExternalFlowHost = object  # noqa: E111


class ExternalEntityConfigurationMixin:
  """Mixin for external entity configuration functionality.

  This mixin provides methods for configuring external Home Assistant
  entities that the integration depends on during setup. This is critical
  for Platinum quality scale compliance and ensures proper integration
  with the broader Home Assistant ecosystem.
  """  # noqa: E111

  if TYPE_CHECKING:  # noqa: E111
    hass: HomeAssistant
    _dogs: list[DogConfigData]
    _enabled_modules: DogModulesConfig
    _external_entities: ExternalEntityConfig

    def _get_available_device_trackers(self) -> dict[str, str]: ...

    def _get_available_person_entities(self) -> dict[str, str]: ...

    def _get_available_door_sensors(self) -> dict[str, str]: ...

    def _get_available_notify_services(self) -> dict[str, str]: ...

  async def async_step_configure_external_entities(  # noqa: E111
    self,
    user_input: ExternalEntityConfig | None = None,
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
      # Validate and store external entity selections  # noqa: E114
      try:  # noqa: E111
        validated_entities = await self._async_validate_external_entities(
          cast(ExternalEntityConfig, user_input),
        )
        self._merge_external_entity_config(
          flow._external_entities,
          validated_entities,
        )
        return await flow.async_step_final_setup()
      except FlowValidationError as err:  # noqa: E111
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

  def _get_external_entities_schema(self) -> vol.Schema:  # noqa: E111
    """Get schema for external entities configuration."""
    schema: dict[object, object] = {}

    if self._enabled_modules.get(MODULE_GPS, False):
      schema.update(self._build_gps_source_selector())  # noqa: E111

    if self._enabled_modules.get(MODULE_VISITOR, False):
      schema.update(self._build_door_sensor_selector())  # noqa: E111

    if self._enabled_modules.get(MODULE_NOTIFICATIONS, False):
      schema.update(self._build_notify_service_selector())  # noqa: E111

    return vol.Schema(schema)

  def _build_gps_source_selector(self) -> dict[object, object]:  # noqa: E111
    """Build selector schema for GPS source."""
    device_trackers = self._get_available_device_trackers()
    person_entities = self._get_available_person_entities()

    options: list[ExternalEntitySelectorOption] = []
    if device_trackers:
      options.extend(  # noqa: E111
        ExternalEntitySelectorOption(
          value=entity_id,
          label=f"📍 {name} (Device Tracker)",
        )
        for entity_id, name in device_trackers.items()
      )
    if person_entities:
      options.extend(  # noqa: E111
        ExternalEntitySelectorOption(
          value=entity_id,
          label=f"👤 {name} (Person)",
        )
        for entity_id, name in person_entities.items()
      )

    if options:
      selector_config = selector.SelectSelectorConfig(  # noqa: E111
        options=options,
        mode=selector.SelectSelectorMode.DROPDOWN,
      )
      return {  # noqa: E111
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

  def _build_door_sensor_selector(self) -> dict[object, object]:  # noqa: E111
    """Build selector schema for door sensor."""
    door_sensors = self._get_available_door_sensors()
    if not door_sensors:
      return {}  # noqa: E111

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

  def _build_notify_service_selector(self) -> dict[object, object]:  # noqa: E111
    """Build selector schema for notification fallback service."""
    notify_services = self._get_available_notify_services()
    if not notify_services:
      return {}  # noqa: E111

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

  def _merge_external_entity_config(  # noqa: E111
    self,
    target: ExternalEntityConfig,
    new_config: ExternalEntityConfig,
  ) -> None:
    """Merge external entity selections into the target mapping."""

    if GPS_SOURCE_KEY in new_config:
      target[GPS_SOURCE_KEY] = new_config[GPS_SOURCE_KEY]  # noqa: E111

    if DOOR_SENSOR_KEY in new_config:
      target[DOOR_SENSOR_KEY] = new_config[DOOR_SENSOR_KEY]  # noqa: E111

    if NOTIFY_FALLBACK_KEY in new_config:
      target[NOTIFY_FALLBACK_KEY] = new_config[NOTIFY_FALLBACK_KEY]  # noqa: E111

  async def _async_validate_external_entities(  # noqa: E111
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
      self._merge_external_entity_config(  # noqa: E111
        validated,
        self._validate_gps_source(gps_source),
      )
    except ValidationError as err:
      errors[CONF_GPS_SOURCE] = _map_external_error(err)  # noqa: E111

    try:
      self._merge_external_entity_config(  # noqa: E111
        validated,
        self._validate_door_sensor(door_sensor),
      )
    except ValidationError as err:
      errors[CONF_DOOR_SENSOR] = _map_external_error(err)  # noqa: E111

    try:
      self._merge_external_entity_config(  # noqa: E111
        validated,
        self._validate_notify_service(notify_service),
      )
    except ValidationError as err:
      if err.constraint == "notify_service_not_found":  # noqa: E111
        service_name = str(err.value) if err.value else "unknown"
        if isinstance(err.value, str) and "." in err.value:
          service_name = err.value.split(".", 1)[1]  # noqa: E111
        base_errors.append(f"Notification service {service_name} not found")
      else:  # noqa: E111
        errors[CONF_NOTIFY_FALLBACK] = _map_external_error(err)

    if errors or base_errors:
      raise FlowValidationError(field_errors=errors, base_errors=base_errors)  # noqa: E111

    return validated

  def _validate_gps_source(self, gps_source: str | None) -> ExternalEntityConfig:  # noqa: E111
    """Validate GPS source selection."""
    if not gps_source:
      return {}  # noqa: E111
    validated = validate_gps_source(
      self.hass,
      gps_source,
      field=CONF_GPS_SOURCE,
      allow_manual=True,
    )
    return {GPS_SOURCE_FIELD: validated}

  def _validate_door_sensor(self, door_sensor: str | None) -> ExternalEntityConfig:  # noqa: E111
    """Validate door sensor selection."""
    if not door_sensor:
      return {}  # noqa: E111
    validated = validate_sensor_entity_id(
      self.hass,
      door_sensor,
      field=CONF_DOOR_SENSOR,
      domain="binary_sensor",
      device_classes=set(DOOR_SENSOR_DEVICE_CLASSES),
      not_found_constraint="door_sensor_not_found",
    )
    if validated is None:
      return {}  # noqa: E111
    return {DOOR_SENSOR_FIELD: validated}

  def _validate_notify_service(  # noqa: E111
    self,
    notify_service: str | None,
  ) -> ExternalEntityConfig:
    """Validate notification service selection."""
    if not notify_service:
      return {}  # noqa: E111
    validated = validate_notify_service(
      self.hass,
      notify_service,
      field=CONF_NOTIFY_FALLBACK,
    )
    return {NOTIFY_FALLBACK_FIELD: validated}


def _map_external_error(error: ValidationError) -> str:
  if error.constraint == "gps_source_required":  # noqa: E111
    return "required"
  if error.constraint == "gps_source_not_found":  # noqa: E111
    return "gps_entity_not_found"
  if error.constraint == "gps_source_unavailable":  # noqa: E111
    return "gps_entity_unavailable"
  if error.constraint == "door_sensor_not_found":  # noqa: E111
    return "door_sensor_not_found"
  if error.constraint == "notify_service_invalid":  # noqa: E111
    return "invalid_notification_service"
  if error.constraint == "notify_service_not_found":  # noqa: E111
    return "notification_service_not_found"
  return "invalid_external_entity"  # noqa: E111
