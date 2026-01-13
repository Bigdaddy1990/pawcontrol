"""Import/export steps for the PawControl options flow."""

from __future__ import annotations

import json
import logging
from pathlib import Path  # noqa: F401
from typing import cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from .types import OptionsExportDisplayInput
from .types import OptionsImportExportInput
from .types import OptionsImportPayloadInput

_LOGGER = logging.getLogger(__name__)


class ImportExportOptionsMixin:
    async def async_step_import_export(
        self, user_input: OptionsImportExportInput | None = None
    ) -> ConfigFlowResult:
        """Handle selection for the import/export utilities."""

        if user_input is None:
            return self.async_show_form(
                step_id='import_export',
                data_schema=self._get_import_export_menu_schema(),
                description_placeholders=dict(
                    freeze_placeholders(  # noqa: F821
                        {
                            'instructions': (
                                'Create a JSON backup of the current PawControl '
                                'options or restore a backup previously exported '
                                'from this menu.'
                            )
                        }
                    )
                ),
            )

        action = user_input.get('action')
        if action == 'export':
            return await self.async_step_import_export_export()
        if action == 'import':
            return await self.async_step_import_export_import()

        return self.async_show_form(
            step_id='import_export',
            data_schema=self._get_import_export_menu_schema(),
            errors={'action': 'invalid_action'},
        )

    async def async_step_import_export_export(
        self, user_input: OptionsExportDisplayInput | None = None
    ) -> ConfigFlowResult:
        """Surface a JSON export of the current configuration."""

        if user_input is not None:
            return await self.async_step_init()

        payload = self._build_export_payload()
        export_blob = json.dumps(payload, indent=2, sort_keys=True)

        return self.async_show_form(
            step_id='import_export_export',
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        'export_blob',
                        default=export_blob,
                    ): selector.TextSelector(  # noqa: F821
                        selector.TextSelectorConfig(  # noqa: F821
                            type=selector.TextSelectorType.TEXT,  # noqa: F821
                            multiline=True,
                        )
                    )
                }
            ),
            description_placeholders=dict(
                freeze_placeholders(  # noqa: F821
                    {
                        'export_blob': export_blob,
                        'generated_at': payload['created_at'],
                    }
                )
            ),
        )

    async def async_step_import_export_import(
        self, user_input: OptionsImportPayloadInput | None = None
    ) -> ConfigFlowResult:
        """Import configuration from a JSON payload."""

        errors: dict[str, str] = {}
        payload_text = ''

        if user_input is not None:
            payload_text = str(user_input.get('payload', '')).strip()
            if not payload_text:
                errors['payload'] = 'invalid_payload'
            else:
                try:
                    parsed = json.loads(payload_text)
                except json.JSONDecodeError:
                    errors['payload'] = 'invalid_json'
                else:
                    try:
                        validated = self._validate_import_payload(parsed)
                    except FlowValidationError as err:  # noqa: F821
                        _LOGGER.debug('Import payload validation failed: %s', err)
                        errors.update(err.as_form_errors())
                    else:
                        new_options = self._normalise_options_snapshot(
                            validated['options']
                        )
                        new_dogs: list[DogConfigData] = []  # noqa: F821
                        for dog in validated.get('dogs', []):
                            if not isinstance(dog, Mapping):  # noqa: F821
                                continue
                            normalised = ensure_dog_config_data(  # noqa: F821
                                cast(Mapping[str, JSONValue], dog)  # noqa: F821
                            )
                            if normalised is not None:
                                new_dogs.append(normalised)

                        new_data = {**self._entry.data, CONF_DOGS: new_dogs}  # noqa: F821
                        self.hass.config_entries.async_update_entry(
                            self._entry, data=new_data
                        )
                        self._dogs = new_dogs
                        self._current_dog = None
                        self._invalidate_profile_caches()

                        return self.async_create_entry(title='', data=new_options)

        return self.async_show_form(
            step_id='import_export_import',
            data_schema=self._get_import_export_import_schema(payload_text),
            errors=errors,
        )

    def _get_import_export_menu_schema(self) -> vol.Schema:
        """Return the schema for selecting an import/export action."""

        return vol.Schema(
            {
                vol.Required('action', default='export'): selector.SelectSelector(  # noqa: F821
                    selector.SelectSelectorConfig(  # noqa: F821
                        options=['export', 'import'],
                        mode=selector.SelectSelectorMode.DROPDOWN,  # noqa: F821
                        translation_key='import_export_action',
                    )
                )
            }
        )

    def _get_import_export_import_schema(self, default_payload: str) -> vol.Schema:
        """Return the schema for the import form."""

        return vol.Schema(
            {
                vol.Required('payload', default=default_payload): selector.TextSelector(  # noqa: F821
                    selector.TextSelectorConfig(  # noqa: F821
                        type=selector.TextSelectorType.TEXT,  # noqa: F821
                        multiline=True,
                    )
                )
            }
        )
