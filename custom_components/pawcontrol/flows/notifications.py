"""Notification configuration steps for Paw Control options flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from ..const import CONF_NOTIFICATIONS
from ..exceptions import FlowValidationError
from ..types import (
  DEFAULT_NOTIFICATION_OPTIONS,
  DOG_ID_FIELD,
  DOG_OPTIONS_FIELD,
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
from .notifications_helpers import build_notification_settings_payload
from .notifications_schemas import build_notifications_schema

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

  class NotificationOptionsNormalizerHost(Protocol):
    """Protocol describing the options flow host requirements."""

    _current_dog: DogConfigData | None
    _dogs: list[DogConfigData]

    def _current_notification_options(
      self,
      dog_id: str | None = None,
    ) -> NotificationOptions: ...

    def _clone_options(self) -> dict[str, JSONValue]: ...

    def _current_dog_options(self) -> DogOptionsMap: ...

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
  NotificationOptionsNormalizerHost = object


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

    return build_notification_settings_payload(
      user_input,
      current,
      coerce_bool=cls._coerce_bool,
      coerce_int=cls._coerce_int,
      coerce_time_string=cls._coerce_time_string,
    )

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
    return build_notifications_schema(current_notifications, user_input)
