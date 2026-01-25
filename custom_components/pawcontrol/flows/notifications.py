"""Notification configuration steps for Paw Control options flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from ..const import CONF_NOTIFICATIONS, DEFAULT_REMINDER_REPEAT_MIN
from ..exceptions import FlowValidationError
from ..selector_shim import selector
from ..types import (
  DEFAULT_NOTIFICATION_OPTIONS,
  DOG_ID_FIELD,
  DOG_OPTIONS_FIELD,
  NOTIFICATION_MOBILE_FIELD,
  NOTIFICATION_PRIORITY_FIELD,
  NOTIFICATION_QUIET_END_FIELD,
  NOTIFICATION_QUIET_HOURS_FIELD,
  NOTIFICATION_QUIET_START_FIELD,
  NOTIFICATION_REMINDER_REPEAT_FIELD,
  DogConfigData,
  DogOptionsMap,
  JSONLikeMapping,
  JSONMutableMapping,
  JSONValue,
  NotificationOptions,
  NotificationOptionsInput,
  NotificationSettingsInput,
  ensure_dog_options_entry,
  ensure_notification_options,
)

if TYPE_CHECKING:

  class NotificationOptionsHost:
    _current_dog: DogConfigData | None
    _dogs: list[DogConfigData]

    def _clone_options(self) -> dict[str, JSONValue]: ...

    def _current_dog_options(self) -> DogOptionsMap: ...

    def _current_options(self) -> Mapping[str, JSONValue]: ...

    def _normalise_options_snapshot(
      self,
      options: Mapping[str, JSONValue],
    ) -> Mapping[str, JSONValue]: ...

    def _build_dog_selector_schema(self) -> vol.Schema: ...

    def _require_current_dog(self) -> DogConfigData | None: ...

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool: ...

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int: ...

    @staticmethod
    def _coerce_time_string(value: Any, default: str) -> str: ...

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
      description_placeholders: Mapping[str, str] | None = None,
    ) -> ConfigFlowResult: ...

    def async_create_entry(
      self,
      *,
      title: str,
      data: Mapping[str, JSONValue],
    ) -> ConfigFlowResult: ...

    async def async_step_init(self) -> ConfigFlowResult: ...

else:  # pragma: no cover
  NotificationOptionsHost = object


class NotificationOptionsMixin(NotificationOptionsHost):
  """Handle per-dog notification options."""

  def _current_notification_options(
    self,
    dog_id: str | None = None,
  ) -> NotificationOptions:
    """Fetch per-dog notification configuration with legacy fallbacks."""

    raw = None
    if dog_id is not None:
      dog_options = self._current_dog_options()
      entry = dog_options.get(dog_id, {})
      raw = entry.get(CONF_NOTIFICATIONS)
    payload: Mapping[str, JSONValue]
    if isinstance(raw, Mapping):
      payload = raw
    else:
      legacy = self._current_options().get(CONF_NOTIFICATIONS, {})
      payload = legacy if isinstance(legacy, Mapping) else {}

    return ensure_notification_options(
      cast(JSONLikeMapping, dict(payload)),
      defaults=cast(
        NotificationOptionsInput,
        dict(
          DEFAULT_NOTIFICATION_OPTIONS,
        ),
      ),
    )


class NotificationOptionsNormalizerHost(Protocol):
  """Protocol describing the options flow host requirements."""


class NotificationOptionsNormalizerMixin(NotificationOptionsNormalizerHost):
  """Mixin providing notification normalization for options payloads."""

  def _normalise_notification_options(
    self,
    mutable: JSONMutableMapping,
  ) -> NotificationOptions | None:
    """Normalise notification payloads in the options snapshot."""

    if CONF_NOTIFICATIONS not in mutable:
      return None

    raw_notifications = mutable.get(CONF_NOTIFICATIONS)
    notifications_source = (
      cast(Mapping[str, JSONValue], raw_notifications)
      if isinstance(raw_notifications, Mapping)
      else {}
    )
    normalised_notifications = ensure_notification_options(
      cast(NotificationOptionsInput, dict(notifications_source)),
      defaults=DEFAULT_NOTIFICATION_OPTIONS,
    )

    raw_dog_options = mutable.get(DOG_OPTIONS_FIELD, {})
    dog_options: DogOptionsMap = {}
    if isinstance(raw_dog_options, Mapping):
      for raw_id, entry_source in raw_dog_options.items():
        dog_id = str(raw_id)
        entry_payload = (
          cast(Mapping[str, JSONValue], entry_source)
          if isinstance(entry_source, Mapping)
          else {}
        )
        entry = ensure_dog_options_entry(
          cast(JSONLikeMapping, dict(entry_payload)),
          dog_id=dog_id,
        )
        if "notifications" not in entry:
          entry["notifications"] = normalised_notifications
        dog_options[dog_id] = entry
    if dog_options:
      mutable[DOG_OPTIONS_FIELD] = cast(JSONValue, dog_options)

    mutable["notifications"] = cast(
      JSONValue,
      normalised_notifications,
    )
    return normalised_notifications

  @classmethod
  def _build_notification_settings_payload(
    cls,
    user_input: NotificationSettingsInput,
    current: NotificationOptions,
  ) -> NotificationOptions:
    """Create a typed notification payload from submitted form data."""

    notifications = {
      NOTIFICATION_QUIET_HOURS_FIELD: cls._coerce_bool(
        user_input.get(NOTIFICATION_QUIET_HOURS_FIELD),
        bool(current.get(NOTIFICATION_QUIET_HOURS_FIELD, True)),
      ),
      NOTIFICATION_QUIET_START_FIELD: cls._coerce_time_string(
        user_input.get(NOTIFICATION_QUIET_START_FIELD),
        str(current.get(NOTIFICATION_QUIET_START_FIELD, "22:00:00")),
      ),
      NOTIFICATION_QUIET_END_FIELD: cls._coerce_time_string(
        user_input.get(NOTIFICATION_QUIET_END_FIELD),
        str(current.get(NOTIFICATION_QUIET_END_FIELD, "07:00:00")),
      ),
      NOTIFICATION_REMINDER_REPEAT_FIELD: cls._coerce_int(
        user_input.get(NOTIFICATION_REMINDER_REPEAT_FIELD),
        int(
          current.get(
            NOTIFICATION_REMINDER_REPEAT_FIELD,
            DEFAULT_REMINDER_REPEAT_MIN,
          ),
        ),
      ),
      NOTIFICATION_PRIORITY_FIELD: cls._coerce_bool(
        user_input.get(NOTIFICATION_PRIORITY_FIELD),
        bool(current.get(NOTIFICATION_PRIORITY_FIELD, True)),
      ),
      NOTIFICATION_MOBILE_FIELD: cls._coerce_bool(
        user_input.get(NOTIFICATION_MOBILE_FIELD),
        bool(current.get(NOTIFICATION_MOBILE_FIELD, True)),
      ),
    }

    return cast(NotificationOptions, notifications)

  def _build_notification_settings(
    self,
    user_input: NotificationSettingsInput,
    current: NotificationOptions,
  ) -> NotificationOptions:
    """Create a typed notification payload from submitted form data."""

    return self._build_notification_settings_payload(user_input, current)

  async def async_step_select_dog_for_notifications(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select which dog to configure notifications for."""

    if not self._dogs:
      return await self.async_step_init()

    if user_input is not None:
      selected_dog_id = user_input.get("dog_id")
      self._select_dog_by_id(
        selected_dog_id if isinstance(selected_dog_id, str) else None,
      )
      if self._current_dog:
        return await self.async_step_notifications()
      return await self.async_step_init()

    return self.async_show_form(
      step_id="select_dog_for_notifications",
      data_schema=self._build_dog_selector_schema(),
    )

  async def async_step_notifications(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure notification settings."""

    current_dog = self._require_current_dog()
    if current_dog is None:
      return await self.async_step_select_dog_for_notifications()

    dog_id = current_dog.get(DOG_ID_FIELD)
    if not isinstance(dog_id, str):
      return await self.async_step_select_dog_for_notifications()

    if user_input is not None:
      try:
        current_notifications = self._current_notification_options(
          dog_id,
        )
        notification_settings = self._build_notification_settings(
          cast(NotificationSettingsInput, user_input),
          current_notifications,
        )

        new_options = self._clone_options()
        dog_options = self._current_dog_options()
        entry = ensure_dog_options_entry(
          cast(JSONLikeMapping, dict(dog_options.get(dog_id, {}))),
          dog_id=dog_id,
        )
        entry["notifications"] = notification_settings
        if dog_id in dog_options or not dog_options:
          dog_options[dog_id] = entry
          new_options[DOG_OPTIONS_FIELD] = cast(JSONValue, dog_options)
        new_options["notifications"] = cast(JSONValue, notification_settings)

        typed_options = self._normalise_options_snapshot(new_options)
        return self.async_create_entry(title="", data=typed_options)

      except FlowValidationError as err:
        return self.async_show_form(
          step_id="notifications",
          data_schema=self._get_notifications_schema(
            dog_id,
            user_input,
          ),
          errors=err.as_form_errors(),
        )
      except Exception:
        return self.async_show_form(
          step_id="notifications",
          data_schema=self._get_notifications_schema(
            dog_id,
            user_input,
          ),
          errors={"base": "update_failed"},
        )

    return self.async_show_form(
      step_id="notifications",
      data_schema=self._get_notifications_schema(dog_id),
    )

  def _get_notifications_schema(
    self,
    dog_id: str,
    user_input: dict[str, Any] | None = None,
  ) -> vol.Schema:
    """Get notifications schema."""

    current_notifications = self._current_notification_options(dog_id)
    current_values = user_input or {}

    return vol.Schema(
      {
        vol.Optional(
          NOTIFICATION_QUIET_HOURS_FIELD,
          default=current_values.get(
            NOTIFICATION_QUIET_HOURS_FIELD,
            current_notifications.get(
              NOTIFICATION_QUIET_HOURS_FIELD,
              True,
            ),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          NOTIFICATION_QUIET_START_FIELD,
          default=current_values.get(
            NOTIFICATION_QUIET_START_FIELD,
            current_notifications.get(
              NOTIFICATION_QUIET_START_FIELD,
              "22:00:00",
            ),
          ),
        ): selector.TimeSelector(),
        vol.Optional(
          NOTIFICATION_QUIET_END_FIELD,
          default=current_values.get(
            NOTIFICATION_QUIET_END_FIELD,
            current_notifications.get(
              NOTIFICATION_QUIET_END_FIELD,
              "07:00:00",
            ),
          ),
        ): selector.TimeSelector(),
        vol.Optional(
          NOTIFICATION_REMINDER_REPEAT_FIELD,
          default=current_values.get(
            NOTIFICATION_REMINDER_REPEAT_FIELD,
            current_notifications.get(
              NOTIFICATION_REMINDER_REPEAT_FIELD,
              DEFAULT_REMINDER_REPEAT_MIN,
            ),
          ),
        ): selector.NumberSelector(
          selector.NumberSelectorConfig(
            min=5,
            max=240,
            step=5,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="minutes",
          ),
        ),
        vol.Optional(
          NOTIFICATION_PRIORITY_FIELD,
          default=current_values.get(
            NOTIFICATION_PRIORITY_FIELD,
            current_notifications.get(
              NOTIFICATION_PRIORITY_FIELD,
              True,
            ),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          NOTIFICATION_MOBILE_FIELD,
          default=current_values.get(
            NOTIFICATION_MOBILE_FIELD,
            current_notifications.get(
              NOTIFICATION_MOBILE_FIELD,
              True,
            ),
          ),
        ): selector.BooleanSelector(),
      },
    )
