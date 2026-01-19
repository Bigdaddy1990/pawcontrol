"""Health configuration steps for Paw Control options flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from .exceptions import FlowValidationError
from .selector_shim import selector
from .types import (
  DOG_ID_FIELD,
  DOG_OPTIONS_FIELD,
  DogConfigData,
  DogOptionsMap,
  HealthOptions,
  JSONLikeMapping,
  JSONValue,
  OptionsHealthSettingsInput,
  ensure_dog_options_entry,
)

if TYPE_CHECKING:

  class HealthOptionsHost:
    _current_dog: DogConfigData | None
    _dogs: list[DogConfigData]

    def _clone_options(self) -> dict[str, JSONValue]: ...

    def _current_dog_options(self) -> DogOptionsMap: ...

    def _current_options(self) -> Mapping[str, JSONValue]: ...

    def _coerce_bool(self, value: Any, default: bool) -> bool: ...

    def _normalise_options_snapshot(
      self,
      options: Mapping[str, JSONValue],
    ) -> Mapping[str, JSONValue]: ...

    def _build_dog_selector_schema(self) -> vol.Schema: ...

    def _require_current_dog(self) -> DogConfigData | None: ...

    def _select_dog_by_id(
      self,
      dog_id: str | None,
    ) -> DogConfigData | None: ...

    def async_show_form(
      self,
      *,
      step_id: str,
      data_schema: vol.Schema,
      errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult: ...

    def async_create_entry(
      self,
      *,
      title: str,
      data: Mapping[str, JSONValue],
    ) -> ConfigFlowResult: ...

    async def async_step_init(self) -> ConfigFlowResult: ...

else:  # pragma: no cover
  HealthOptionsHost = object


class HealthOptionsMixin(HealthOptionsHost):
  """Handle per-dog health options."""

  def _current_health_options(self, dog_id: str) -> HealthOptions:
    """Return the stored health configuration as a typed mapping."""

    dog_options = self._current_dog_options()
    entry = dog_options.get(dog_id, {})
    raw = entry.get("health_settings")
    if isinstance(raw, Mapping):
      return cast(HealthOptions, dict(raw))

    legacy = self._current_options().get("health_settings", {})
    if isinstance(legacy, Mapping):
      return cast(HealthOptions, dict(legacy))

    return cast(HealthOptions, {})

  async def async_step_select_dog_for_health_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select which dog to configure health settings for."""

    if not self._dogs:
      return await self.async_step_init()

    if user_input is not None:
      selected_dog_id = user_input.get("dog_id")
      self._select_dog_by_id(
        selected_dog_id if isinstance(selected_dog_id, str) else None,
      )
      if self._current_dog:
        return await self.async_step_health_settings()
      return await self.async_step_init()

    return self.async_show_form(
      step_id="select_dog_for_health_settings",
      data_schema=self._build_dog_selector_schema(),
    )

  async def async_step_health_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure health monitoring settings."""

    current_dog = self._require_current_dog()
    if current_dog is None:
      return await self.async_step_select_dog_for_health_settings()

    dog_id = current_dog.get(DOG_ID_FIELD)
    if not isinstance(dog_id, str):
      return await self.async_step_select_dog_for_health_settings()

    if user_input is not None:
      try:
        current_health = self._current_health_options(dog_id)
        new_options = self._clone_options()
        dog_options = self._current_dog_options()
        entry = ensure_dog_options_entry(
          cast(JSONLikeMapping, dict(dog_options.get(dog_id, {}))),
          dog_id=dog_id,
        )
        entry["health_settings"] = self._build_health_settings(
          user_input,
          current_health,
        )
        if dog_id in dog_options or not dog_options:
          dog_options[dog_id] = entry
          new_options[DOG_OPTIONS_FIELD] = dog_options
        new_options["health_settings"] = entry["health_settings"]

        typed_options = self._normalise_options_snapshot(new_options)
        return self.async_create_entry(title="", data=typed_options)
      except FlowValidationError as err:
        return self.async_show_form(
          step_id="health_settings",
          data_schema=self._get_health_settings_schema(
            dog_id,
            user_input,
          ),
          errors=err.as_form_errors(),
        )
      except Exception:
        return self.async_show_form(
          step_id="health_settings",
          data_schema=self._get_health_settings_schema(
            dog_id,
            user_input,
          ),
          errors={"base": "update_failed"},
        )

    return self.async_show_form(
      step_id="health_settings",
      data_schema=self._get_health_settings_schema(dog_id),
    )

  def _get_health_settings_schema(
    self,
    dog_id: str,
    user_input: dict[str, Any] | None = None,
  ) -> vol.Schema:
    """Get health settings schema."""

    current_health = self._current_health_options(dog_id)
    current_values = user_input or {}

    return vol.Schema(
      {
        vol.Optional(
          "weight_tracking",
          default=current_values.get(
            "weight_tracking",
            current_health.get("weight_tracking", True),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          "medication_reminders",
          default=current_values.get(
            "medication_reminders",
            current_health.get("medication_reminders", True),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          "vet_reminders",
          default=current_values.get(
            "vet_reminders",
            current_health.get("vet_reminders", True),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          "grooming_reminders",
          default=current_values.get(
            "grooming_reminders",
            current_health.get("grooming_reminders", True),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          "health_alerts",
          default=current_values.get(
            "health_alerts",
            current_health.get("health_alerts", True),
          ),
        ): selector.BooleanSelector(),
      },
    )

  def _build_health_settings(
    self,
    user_input: OptionsHealthSettingsInput,
    current: HealthOptions,
  ) -> HealthOptions:
    """Create a typed health payload from the submitted form data."""

    return cast(
      HealthOptions,
      {
        "weight_tracking": self._coerce_bool(
          user_input.get("weight_tracking"),
          current.get("weight_tracking", True),
        ),
        "medication_reminders": self._coerce_bool(
          user_input.get("medication_reminders"),
          current.get("medication_reminders", True),
        ),
        "vet_reminders": self._coerce_bool(
          user_input.get("vet_reminders"),
          current.get("vet_reminders", True),
        ),
        "grooming_reminders": self._coerce_bool(
          user_input.get("grooming_reminders"),
          current.get("grooming_reminders", True),
        ),
        "health_alerts": self._coerce_bool(
          user_input.get("health_alerts"),
          current.get("health_alerts", True),
        ),
      },
    )
