"""Import/export steps for the PawControl options flow."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path  # noqa: F401
from typing import TYPE_CHECKING, Any, Protocol, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from .const import CONF_DOGS
from .exceptions import FlowValidationError
from .selector_shim import selector
from .types import (
  DogConfigData,
  JSONValue,
  ensure_dog_config_data,
  freeze_placeholders,
)

if TYPE_CHECKING:
  from .compat import ConfigEntry

_LOGGER = logging.getLogger(__name__)


if TYPE_CHECKING:

  class ImportExportOptionsHost(Protocol):
    _current_dog: DogConfigData | None
    _dogs: list[DogConfigData]

    @property
    def _entry(self) -> ConfigEntry: ...

    hass: Any

    def __getattr__(self, name: str) -> Any: ...

else:  # pragma: no cover
  ImportExportOptionsHost = object


class ImportExportOptionsMixin(ImportExportOptionsHost):
  _current_dog: DogConfigData | None
  _dogs: list[DogConfigData]

  async def async_step_import_export(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle selection for the import/export utilities."""

    if user_input is None:
      return self.async_show_form(
        step_id="import_export",
        data_schema=self._get_import_export_menu_schema(),
        description_placeholders=dict(
          freeze_placeholders(
            {
              "instructions": (
                "Create a JSON backup of the current PawControl "
                "options or restore a backup previously exported "
                "from this menu."
              ),
            },
          ),
        ),
      )

    action = user_input.get("action")
    if action == "export":
      return await self.async_step_import_export_export()
    if action == "import":
      return await self.async_step_import_export_import()

    return self.async_show_form(
      step_id="import_export",
      data_schema=self._get_import_export_menu_schema(),
      errors={"action": "invalid_action"},
    )

  async def async_step_import_export_export(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Surface a JSON export of the current configuration."""

    if user_input is not None:
      return await self.async_step_init()

    payload = self._build_export_payload()
    export_blob = json.dumps(payload, indent=2, sort_keys=True)

    return self.async_show_form(
      step_id="import_export_export",
      data_schema=vol.Schema(
        {
          vol.Optional(
            "export_blob",
            default=export_blob,
          ): selector.TextSelector(
            selector.TextSelectorConfig(
              type=selector.TextSelectorType.TEXT,
              multiline=True,
            ),
          ),
        },
      ),
      description_placeholders=dict(
        freeze_placeholders(
          {
            "export_blob": export_blob,
            "generated_at": payload["created_at"],
          },
        ),
      ),
    )

  async def async_step_import_export_import(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Import configuration from a JSON payload."""

    errors: dict[str, str] = {}
    payload_text = ""

    if user_input is not None:
      payload_text = str(user_input.get("payload", "")).strip()
      if not payload_text:
        errors["payload"] = "invalid_payload"
      else:
        try:
          parsed = json.loads(payload_text)
        except json.JSONDecodeError:
          errors["payload"] = "invalid_json"
        else:
          try:
            validated = self._validate_import_payload(parsed)
          except FlowValidationError as err:
            _LOGGER.debug(
              "Import payload validation failed: %s",
              err,
            )
            errors.update(err.as_form_errors())
          else:
            new_options = self._normalise_options_snapshot(
              validated["options"],
            )
            new_dogs: list[DogConfigData] = []
            for dog in validated.get("dogs", []):
              if not isinstance(dog, Mapping):
                continue
              normalised = ensure_dog_config_data(
                cast(Mapping[str, JSONValue], dog),
              )
              if normalised is not None:
                new_dogs.append(normalised)

            new_data = {**self._entry.data, CONF_DOGS: new_dogs}
            self.hass.config_entries.async_update_entry(
              self._entry,
              data=new_data,
            )
            self._dogs = new_dogs
            self._current_dog = None
            self._invalidate_profile_caches()

            return self.async_create_entry(title="", data=new_options)

    return self.async_show_form(
      step_id="import_export_import",
      data_schema=self._get_import_export_import_schema(payload_text),
      errors=errors,
    )

  def _get_import_export_menu_schema(self) -> vol.Schema:
    """Return the schema for selecting an import/export action."""

    return vol.Schema(
      {
        vol.Required("action", default="export"): selector.SelectSelector(
          selector.SelectSelectorConfig(
            options=["export", "import"],
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="import_export_action",
          ),
        ),
      },
    )

  def _get_import_export_import_schema(self, default_payload: str) -> vol.Schema:
    """Return the schema for the import form."""

    return vol.Schema(
      {
        vol.Required("payload", default=default_payload): selector.TextSelector(
          selector.TextSelectorConfig(
            type=selector.TextSelectorType.TEXT,
            multiline=True,
          ),
        ),
      },
    )
