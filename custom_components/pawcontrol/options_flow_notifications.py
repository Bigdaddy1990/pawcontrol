"""Notification options normalization helpers for the options flow."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

from .const import CONF_NOTIFICATIONS
from .options_flow_shared import DOG_OPTIONS_FIELD
from .types import (
  DEFAULT_NOTIFICATION_OPTIONS,
  JSONLikeMapping,
  JSONMutableMapping,
  JSONValue,
  NotificationOptions,
  NotificationOptionsInput,
  DogOptionsMap,
  ensure_dog_options_entry,
  ensure_notification_options,
)


class NotificationOptionsHost(Protocol):
  """Protocol describing the options flow host requirements."""


class NotificationOptionsNormalizerMixin(NotificationOptionsHost):
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
