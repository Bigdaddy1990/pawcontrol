"""Config flow for PawControl integration.

Consolidated flow handling setup and initial dog configuration.
"""

from __future__ import annotations

from typing import Any, Final, Literal

import voluptuous as vol
from homeassistant.config_entries import (
  ConfigEntry,
  ConfigFlow,
  ConfigFlowResult,
  OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import (
  CONF_DOG_AGE,
  CONF_DOG_BREED,
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOG_SIZE,
  CONF_DOG_WEIGHT,
  CONF_DOGS,
  CONF_NAME,
  DOG_ID_PATTERN,
  DOMAIN,
  MAX_DOG_NAME_LENGTH,
  MIN_DOG_NAME_LENGTH,
)
from .entity_factory import EntityFactory
from .options_flow import PawControlOptionsFlow
from .types import VALID_DOG_SIZES, dog_modules_from_flow_input
from .validation import ValidationError, normalize_dog_id, validate_dog_name

DOG_SCHEMA = vol.Schema(
  {
    vol.Required(CONF_DOG_NAME): cv.string,
    vol.Required(CONF_DOG_ID): cv.string,
    vol.Optional(CONF_DOG_BREED): cv.string,
    vol.Optional(CONF_DOG_AGE): vol.Any(str, int, float),
    vol.Optional(CONF_DOG_WEIGHT): vol.Any(str, int, float),
    vol.Optional(CONF_DOG_SIZE): vol.In(sorted(VALID_DOG_SIZES)),
  },
)
INTEGRATION_NAME_SCHEMA = vol.Schema(
  {vol.Required(CONF_NAME): cv.string},
)


class PawControlConfigFlow(ConfigFlow, domain=DOMAIN):
  """Handle a config flow for PawControl."""

  VERSION = 1

  def __init__(self) -> None:
    """Initialize the config flow."""
    self._data: dict[str, Any] = {CONF_DOGS: []}
    self._entry_name: str | None = None
    self._pending_dog: dict[str, Any] | None = None
    self._entity_profile: str = "standard"
    self._reauth_entry: ConfigEntry | None = None
    self._reconfigure_entry: ConfigEntry | None = None

  @staticmethod
  @callback
  def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
    """Get the options flow for this handler."""
    return PawControlOptionsFlow(config_entry)

  @staticmethod
  @callback
  def async_supports_options_flow(config_entry: ConfigEntry) -> bool:
    """Return True because this integration supports options."""
    return True

  @staticmethod
  @callback
  def async_supports_reconfigure_flow(config_entry: ConfigEntry) -> bool:
    """Return True because this integration supports reconfigure."""
    return True

  def _existing_dog_ids(self) -> set[str]:
    return {
      dog[CONF_DOG_ID]
      for dog in self._data[CONF_DOGS]
      if isinstance(dog, dict) and dog.get(CONF_DOG_ID)
    }

  def _existing_dog_names(self) -> set[str]:
    return {
      dog[CONF_DOG_NAME].casefold()
      for dog in self._data[CONF_DOGS]
      if isinstance(dog, dict) and isinstance(dog.get(CONF_DOG_NAME), str)
    }

  def _validate_integration_name(self, name: str | None) -> str | None:
    if name is None:
      return None
    trimmed = name.strip()
    if not trimmed:
      return None
    if len(trimmed) < MIN_DOG_NAME_LENGTH:
      raise ValidationError(CONF_NAME, trimmed, "integration_name_too_short")
    if len(trimmed) > MAX_DOG_NAME_LENGTH:
      raise ValidationError(CONF_NAME, trimmed, "integration_name_too_long")
    return trimmed

  def _validate_dog_id(self, raw_id: str | None) -> str:
    if raw_id is None:
      raise ValidationError(CONF_DOG_ID, raw_id, "dog_id_required")
    normalised = normalize_dog_id(raw_id)
    if len(normalised) < MIN_DOG_NAME_LENGTH:
      raise ValidationError(CONF_DOG_ID, normalised, "dog_id_too_short")
    if len(normalised) > MAX_DOG_NAME_LENGTH:
      raise ValidationError(CONF_DOG_ID, normalised, "dog_id_too_long")
    if not DOG_ID_PATTERN.match(normalised):
      raise ValidationError(CONF_DOG_ID, normalised, "invalid_dog_id_format")
    if normalised in self._existing_dog_ids():
      raise ValidationError(CONF_DOG_ID, normalised, "dog_id_already_exists")
    return normalised

  def _validate_dog_breed(self, breed: str | None) -> str | None:
    if not breed:
      return None
    trimmed = breed.strip()
    if not trimmed:
      return None
    if len(trimmed) > 50:
      raise ValidationError(CONF_DOG_BREED, trimmed, "breed_name_too_long")
    if not all(char.isalpha() or char in {" ", "-", "'"} for char in trimmed):
      raise ValidationError(CONF_DOG_BREED, trimmed, "invalid_dog_breed")
    return trimmed

  def _validate_dog_age(self, age_value: Any) -> int | None:
    if age_value is None or age_value == "":
      return None
    try:
      age = float(age_value)
    except (TypeError, ValueError) as err:
      raise ValidationError(CONF_DOG_AGE, age_value, "invalid_age_format") from err
    if age < 0 or age > 30:
      raise ValidationError(CONF_DOG_AGE, age, "age_out_of_range")
    return int(age)

  def _validate_dog_weight(self, weight_value: Any) -> float | None:
    if weight_value is None or weight_value == "":
      return None
    try:
      weight = float(weight_value)
    except (TypeError, ValueError) as err:
      raise ValidationError(
        CONF_DOG_WEIGHT,
        weight_value,
        "invalid_weight_format",
      ) from err
    if weight < 0.5 or weight > 200:
      raise ValidationError(CONF_DOG_WEIGHT, weight, "weight_out_of_range")
    return weight

  def _validate_dog_payload(
    self,
    user_input: dict[str, Any],
  ) -> tuple[dict[str, Any] | None, dict[str, str]]:
    errors: dict[str, str] = {}
    validated: dict[str, Any] = {}

    try:
      name = validate_dog_name(user_input.get(CONF_DOG_NAME))
      if name is not None:
        if name.casefold() in self._existing_dog_names():
          raise ValidationError(CONF_DOG_NAME, name, "dog_name_already_exists")
        validated[CONF_DOG_NAME] = name
    except ValidationError as err:
      errors[CONF_DOG_NAME] = err.constraint or "invalid_config"

    try:
      dog_id = self._validate_dog_id(user_input.get(CONF_DOG_ID))
      validated[CONF_DOG_ID] = dog_id
    except ValidationError as err:
      errors[CONF_DOG_ID] = err.constraint or "invalid_config"

    try:
      breed = self._validate_dog_breed(user_input.get(CONF_DOG_BREED))
      if breed:
        validated[CONF_DOG_BREED] = breed
    except ValidationError as err:
      errors[CONF_DOG_BREED] = err.constraint or "invalid_config"

    try:
      age = self._validate_dog_age(user_input.get(CONF_DOG_AGE))
      if age is not None:
        validated[CONF_DOG_AGE] = age
    except ValidationError as err:
      errors[CONF_DOG_AGE] = err.constraint or "invalid_config"

    try:
      weight = self._validate_dog_weight(user_input.get(CONF_DOG_WEIGHT))
      if weight is not None:
        validated[CONF_DOG_WEIGHT] = weight
    except ValidationError as err:
      errors[CONF_DOG_WEIGHT] = err.constraint or "invalid_config"

    size = user_input.get(CONF_DOG_SIZE)
    if size:
      if size not in VALID_DOG_SIZES:
        errors[CONF_DOG_SIZE] = "invalid_dog_size"
      else:
        validated[CONF_DOG_SIZE] = size

    if errors:
      return None, errors
    return validated, {}

  def _build_profile_options(self) -> dict[str, str]:
    factory = EntityFactory(None, prewarm=False)
    options: dict[str, str] = {}
    for profile in factory.get_available_profiles():
      info = factory.get_profile_info(profile)
      options[profile] = info.name
    return options

  def _build_setup_summary(self) -> str:
    dogs = self._data[CONF_DOGS]
    dog_names = [dog.get(CONF_DOG_NAME, "?") for dog in dogs if isinstance(dog, dict)]
    return f"Dogs: {', '.join(dog_names)}"

  async def async_step_user(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle the initial step."""
    if user_input is not None:
      await self.async_set_unique_id(DOMAIN)
      self._abort_if_unique_id_configured()
      errors: dict[str, str] = {}
      try:
        validated_name = self._validate_integration_name(user_input.get(CONF_NAME))
      except ValidationError as err:
        validated_name = None
        errors[CONF_NAME] = err.constraint or "invalid_config"

      if not validated_name:
        errors[CONF_NAME] = errors.get(CONF_NAME, "integration_name_required")
      if errors:
        return self.async_show_form(
          step_id="user",
          data_schema=INTEGRATION_NAME_SCHEMA,
          errors=errors,
        )
      self._entry_name = validated_name
      return await self.async_step_add_dog()

    return self.async_show_form(step_id="user", data_schema=INTEGRATION_NAME_SCHEMA)

  async def async_step_add_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle dog configuration."""
    if user_input is not None:
      validated, errors = self._validate_dog_payload(user_input)
      if not errors and validated is not None:
        self._pending_dog = validated
        return await self.async_step_dog_modules()
      return self.async_show_form(
        step_id="add_dog",
        data_schema=DOG_SCHEMA,
        errors=errors,
        description_placeholders={"dog_count": str(len(self._data[CONF_DOGS]))},
      )

    return self.async_show_form(
      step_id="add_dog",
      data_schema=DOG_SCHEMA,
      description_placeholders={"dog_count": str(len(self._data[CONF_DOGS]))},
    )

  async def async_step_dog_modules(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure per-dog modules."""
    if self._pending_dog is None:
      return await self.async_step_add_dog()

    module_schema = vol.Schema(
      {
        vol.Optional("enable_feeding", default=True): bool,
        vol.Optional("enable_walk", default=True): bool,
        vol.Optional("enable_health", default=True): bool,
        vol.Optional("enable_gps", default=True): bool,
        vol.Optional("enable_garden", default=False): bool,
        vol.Optional("enable_notifications", default=True): bool,
        vol.Optional("enable_dashboard", default=True): bool,
        vol.Optional("enable_visitor", default=False): bool,
        vol.Optional("enable_grooming", default=False): bool,
        vol.Optional("enable_medication", default=False): bool,
        vol.Optional("enable_training", default=False): bool,
      },
    )

    if user_input is not None:
      modules = dog_modules_from_flow_input(user_input)
      dog_entry = dict(self._pending_dog)
      dog_entry["modules"] = modules
      self._data[CONF_DOGS].append(dog_entry)
      self._pending_dog = None
      return await self.async_step_add_another_dog()

    placeholders = {
      "dog_name": str(self._pending_dog.get(CONF_DOG_NAME, "")),
      "dog_size": str(self._pending_dog.get(CONF_DOG_SIZE, "")),
      "dog_age": str(self._pending_dog.get(CONF_DOG_AGE, "")),
    }
    return self.async_show_form(
      step_id="dog_modules",
      data_schema=module_schema,
      description_placeholders=placeholders,
    )

  async def async_step_add_another_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Ask if another dog should be added."""
    if user_input is not None:
      if user_input.get("add_another"):
        return await self.async_step_add_dog()
      return await self.async_step_entity_profile()

    dogs_list = ", ".join(
      dog.get(CONF_DOG_NAME, "")
      for dog in self._data[CONF_DOGS]
      if isinstance(dog, dict)
    )
    return self.async_show_form(
      step_id="add_another_dog",
      data_schema=vol.Schema({vol.Required("add_another", default=False): bool}),
      description_placeholders={
        "dog_count": str(len(self._data[CONF_DOGS])),
        "max_dogs": "10",
        "dogs_list": dogs_list,
        "remaining_spots": "0",
      },
    )

  async def async_step_entity_profile(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select entity profile for this entry."""
    profile_options = self._build_profile_options()

    if user_input is not None:
      self._entity_profile = user_input["entity_profile"]
      return await self.async_step_final_setup()

    schema = vol.Schema(
      {
        vol.Required(
          "entity_profile",
          default=self._entity_profile,
        ): vol.In(profile_options),
      },
    )
    return self.async_show_form(
      step_id="entity_profile",
      data_schema=schema,
      description_placeholders={
        "dogs_count": str(len(self._data[CONF_DOGS])),
        "profiles_info": ", ".join(profile_options.values()),
        "compatibility_info": "Ready",
        "reconfigure_valid_dogs": str(len(self._data[CONF_DOGS])),
        "reconfigure_invalid_dogs": "0",
        "last_reconfigure": "Never",
        "reconfigure_requested_profile": self._entity_profile,
        "reconfigure_previous_profile": self._entity_profile,
        "reconfigure_dogs": str(len(self._data[CONF_DOGS])),
        "reconfigure_entities": "0",
        "reconfigure_health": "OK",
        "reconfigure_warnings": "None",
        "reconfigure_merge_notes": "None",
      },
    )

  async def async_step_final_setup(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Finalize configuration."""
    if user_input is not None:
      data = {
        CONF_NAME: self._entry_name or "Paw Control",
        CONF_DOGS: self._data[CONF_DOGS],
        "entity_profile": self._entity_profile,
        "setup_timestamp": dt_util.utcnow().isoformat(),
      }
      return self.async_create_entry(
        title=self._entry_name or "Paw Control",
        data=data,
      )

    return self.async_show_form(
      step_id="final_setup",
      data_schema=vol.Schema({}),
      description_placeholders={
        "setup_summary": self._build_setup_summary(),
        "total_dogs": str(len(self._data[CONF_DOGS])),
      },
    )

  async def async_step_reauth(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle reauthentication."""
    entry_id = self.context.get("entry_id")
    if entry_id and self.hass:
      self._reauth_entry = self.hass.config_entries.async_get_entry(entry_id)
    return await self.async_step_reauth_confirm()

  async def async_step_reauth_confirm(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Confirm reauthentication."""
    if user_input is not None:
      if self._reauth_entry and self.hass:
        self.hass.config_entries.async_update_entry(
          self._reauth_entry,
          data={
            **self._reauth_entry.data,
            "reauth_timestamp": dt_util.utcnow().isoformat(),
          },
        )
      return self.async_abort(reason="reauth_successful")

    integration_name = self._reauth_entry.title if self._reauth_entry else "Paw Control"
    return self.async_show_form(
      step_id="reauth_confirm",
      data_schema=vol.Schema({vol.Required("confirm", default=True): bool}),
      description_placeholders={
        "integration_name": integration_name,
        "issues_detected": "Credentials refresh requested.",
      },
    )

  async def async_step_reconfigure(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle reconfigure flow."""
    entry_id = self.context.get("entry_id")
    if entry_id and self.hass:
      self._reconfigure_entry = self.hass.config_entries.async_get_entry(entry_id)
    profile_options = self._build_profile_options()
    current_profile = None
    if self._reconfigure_entry:
      current_profile = self._reconfigure_entry.options.get(
        "entity_profile",
        self._reconfigure_entry.data.get("entity_profile", "standard"),
      )

    if user_input is not None:
      if self._reconfigure_entry and self.hass:
        updated_options = dict(self._reconfigure_entry.options)
        updated_options["entity_profile"] = user_input["entity_profile"]
        updated_options["last_reconfigure"] = dt_util.utcnow().isoformat()
        self.hass.config_entries.async_update_entry(
          self._reconfigure_entry,
          data={
            **self._reconfigure_entry.data,
            "entity_profile": user_input["entity_profile"],
          },
          options=updated_options,
        )
      return self.async_abort(reason="reconfigure_successful")

    schema = vol.Schema(
      {
        vol.Required(
          "entity_profile",
          default=current_profile or self._entity_profile,
        ): vol.In(profile_options),
      },
    )
    return self.async_show_form(
      step_id="reconfigure",
      data_schema=schema,
      description_placeholders={
        "current_profile": current_profile or self._entity_profile,
        "profiles_info": ", ".join(profile_options.values()),
      },
    )


ConfigFlowAlias: Final[Literal["ConfigFlow"]] = "ConfigFlow"
ConfigFlow = PawControlConfigFlow

__all__: Final[tuple[Literal["ConfigFlow"], Literal["PawControlConfigFlow"]]] = (
  ConfigFlowAlias,
  "PawControlConfigFlow",
)
