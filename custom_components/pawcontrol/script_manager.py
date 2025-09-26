"""Automatic Home Assistant script management for PawControl.

This module keeps the promise from the public documentation that PawControl
automatically provisions helper scripts for every configured dog.  It creates
notification workflows, reset helpers, and setup automation scripts directly in
Home Assistant's ``script`` domain so that users can trigger the documented
automation flows without manual YAML editing.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping, Sequence
from typing import Any, Final

from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN, ScriptEntity
from homeassistant.components.script.config import SCRIPT_ENTITY_SCHEMA
from homeassistant.components.script.const import (CONF_FIELDS, CONF_TRACE)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ALIAS,
    CONF_DEFAULT,
    CONF_DESCRIPTION,
    CONF_NAME,
    CONF_SEQUENCE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

from .const import CONF_DOG_ID, CONF_DOG_NAME, CONF_MODULES, MODULE_NOTIFICATIONS
from .types import DogConfigData

_LOGGER = logging.getLogger(__name__)

_SCRIPT_ENTITY_PREFIX: Final[str] = f"{SCRIPT_DOMAIN}."


class PawControlScriptManager:
    """Create and maintain Home Assistant scripts for PawControl dogs."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the script manager."""

        self._hass = hass
        self._entry = entry
        self._created_entities: set[str] = set()
        self._dog_scripts: dict[str, list[str]] = {}

    async def async_initialize(self) -> None:
        """Reset internal tracking structures prior to script generation."""

        self._created_entities.clear()
        self._dog_scripts.clear()
        _LOGGER.debug("Script manager initialised for entry %s", self._entry.entry_id)

    def _get_component(self, *, require_loaded: bool = True) -> EntityComponent[Any] | None:
        """Return the Home Assistant script entity component."""

        component: EntityComponent[Any] | None = self._hass.data.get(SCRIPT_DOMAIN)
        if component is None:
            if require_loaded:
                raise HomeAssistantError(
                    "The Home Assistant script integration is not loaded. "
                    "Enable the built-in script integration to use PawControl's "
                    "auto-generated scripts."
                )
            return None

        return component

    async def async_generate_scripts_for_dogs(
        self,
        dogs: Sequence[DogConfigData],
        enabled_modules: Collection[str],
    ) -> dict[str, list[str]]:
        """Create or update scripts for every configured dog."""

        if not dogs:
            return {}

        component = self._get_component()
        registry = er.async_get(self._hass)
        created: dict[str, list[str]] = {}
        processed_dogs: set[str] = set()

        global_notifications_enabled = MODULE_NOTIFICATIONS in enabled_modules

        for dog in dogs:
            dog_id = dog.get(CONF_DOG_ID)
            if not isinstance(dog_id, str) or not dog_id:
                _LOGGER.debug("Skipping script generation for invalid dog entry: %s", dog)
                continue

            processed_dogs.add(dog_id)
            dog_name = dog.get(CONF_DOG_NAME) or dog_id
            slug = slugify(dog_id)

            existing_for_dog = set(self._dog_scripts.get(dog_id, []))
            new_for_dog: list[str] = []

            dog_modules = dog.get(CONF_MODULES, {})
            dog_notifications_enabled = global_notifications_enabled
            if isinstance(dog_modules, Mapping):
                if MODULE_NOTIFICATIONS in dog_modules:
                    dog_notifications_enabled = bool(
                        dog_modules.get(MODULE_NOTIFICATIONS)
                    )
            elif isinstance(dog_modules, Collection) and not isinstance(
                dog_modules, (str, bytes)
            ):
                dog_notifications_enabled = (
                    global_notifications_enabled
                    and MODULE_NOTIFICATIONS in {
                        str(module) for module in dog_modules
                    }
                )

            script_definitions = self._build_scripts_for_dog(
                slug, dog_id, dog_name, dog_notifications_enabled
            )

            for object_id, raw_config in script_definitions:
                entity_id = f"{_SCRIPT_ENTITY_PREFIX}{object_id}"
                existing_entity = component.get_entity(entity_id)
                if existing_entity is not None:
                    await existing_entity.async_remove()

                validated_config = SCRIPT_ENTITY_SCHEMA(dict(raw_config))
                entity = ScriptEntity(
                    self._hass,
                    object_id,
                    validated_config,
                    raw_config,
                    None,
                )
                await component.async_add_entities([entity])

                self._created_entities.add(entity_id)
                new_for_dog.append(entity_id)

                # Preserve user customisations by keeping the registry entry but ensure
                # it is linked to the PawControl config entry for diagnostics.
                if (entry := registry.async_get(entity_id)) and (
                    entry.config_entry_id != self._entry.entry_id
                ):
                    registry.async_update_entity(
                        entity_id, config_entry_id=self._entry.entry_id
                    )

            # Remove scripts that are no longer needed for this dog (e.g. module disabled)
            obsolete = existing_for_dog - set(new_for_dog)
            for entity_id in obsolete:
                await self._async_remove_script_entity(entity_id)

            if new_for_dog:
                created[dog_id] = list(new_for_dog)
                self._dog_scripts[dog_id] = list(new_for_dog)

        # Remove scripts for dogs that were removed from the configuration
        removed_dogs = set(self._dog_scripts) - processed_dogs
        for removed_dog in removed_dogs:
            for entity_id in self._dog_scripts.pop(removed_dog, []):
                await self._async_remove_script_entity(entity_id)

        return created

    async def async_cleanup(self) -> None:
        """Remove all scripts created by the integration."""

        component = self._get_component(require_loaded=False)
        registry = er.async_get(self._hass)

        for entity_id in list(self._created_entities):
            if component is not None and (entity := component.get_entity(entity_id)):
                await entity.async_remove()

            if registry.async_get(entity_id):
                registry.async_remove(entity_id)

            self._created_entities.discard(entity_id)

        self._dog_scripts.clear()
        _LOGGER.debug("Removed all PawControl managed scripts for entry %s", self._entry.entry_id)

    async def _async_remove_script_entity(self, entity_id: str) -> None:
        """Remove a specific script entity and its registry entry."""

        component = self._get_component(require_loaded=False)
        registry = er.async_get(self._hass)

        if component is not None and (entity := component.get_entity(entity_id)):
            await entity.async_remove()

        if registry.async_get(entity_id):
            registry.async_remove(entity_id)

        self._created_entities.discard(entity_id)

    def _build_scripts_for_dog(
        self,
        slug: str,
        dog_id: str,
        dog_name: str,
        notifications_enabled: bool,
    ) -> list[tuple[str, ConfigType]]:
        """Return raw script configurations for a dog."""

        scripts: list[tuple[str, ConfigType]] = []

        scripts.append(self._build_reset_script(slug, dog_id, dog_name))
        scripts.append(
            self._build_setup_script(slug, dog_id, dog_name, notifications_enabled)
        )

        if notifications_enabled:
            scripts.append(
                self._build_confirmation_script(slug, dog_id, dog_name)
            )
            scripts.append(self._build_push_test_script(slug, dog_id, dog_name))

        return scripts

    def _build_confirmation_script(
        self, slug: str, dog_id: str, dog_name: str
    ) -> tuple[str, ConfigType]:
        """Create the confirmation notification script definition."""

        object_id = f"pawcontrol_{slug}_outdoor_check"
        notification_id = f"pawcontrol_{slug}_outdoor_check"
        default_title = f"{dog_name} outdoor check"
        default_message = (
            f"{dog_name} just came back inside. Did everything go well outside?"
        )

        raw_config: ConfigType = {
            CONF_ALIAS: f"{dog_name} outdoor confirmation",
            CONF_DESCRIPTION: (
                "Sends a push notification asking if the dog finished their outdoor "
                "break and optionally clears the reminder automatically."
            ),
            CONF_SEQUENCE: [
                {
                    "service": "{{ notify_service | default('notify.notify') }}",
                    "data": {
                        "title": f"{{ title | default('{default_title}') }}",
                        "message": f"{{ message | default('{default_message}') }}",
                        "data": {
                            "notification_id": notification_id,
                            "actions": [
                                {
                                    "action": "{{ confirm_action | default('PAWCONTROL_CONFIRM') }}",
                                    "title": "{{ confirm_title | default('✅ All good') }}",
                                },
                                {
                                    "action": "{{ remind_action | default('PAWCONTROL_REMIND') }}",
                                    "title": "{{ remind_title | default('🔁 Remind me later') }}",
                                },
                            ],
                        },
                    },
                },
                {
                    "choose": [
                        {
                            "conditions": [
                                {
                                    "condition": "template",
                                    "value_template": "{{ auto_acknowledge | default(false) }}",
                                }
                            ],
                            "sequence": [
                                {
                                    "service": "pawcontrol.acknowledge_notification",
                                    "data": {"notification_id": notification_id},
                                }
                            ],
                        }
                    ],
                    "default": [],
                },
            ],
            CONF_FIELDS: {
                "notify_service": {
                    CONF_NAME: "Notification service",
                    CONF_DESCRIPTION: "Service used to deliver the confirmation question.",
                    CONF_DEFAULT: "notify.notify",
                    "selector": {"text": {}},
                },
                "title": {
                    CONF_NAME: "Title",
                    CONF_DESCRIPTION: "Title shown in the push notification.",
                    CONF_DEFAULT: default_title,
                    "selector": {"text": {}},
                },
                "message": {
                    CONF_NAME: "Message",
                    CONF_DESCRIPTION: "Body text shown in the push notification.",
                    CONF_DEFAULT: default_message,
                    "selector": {"text": {"multiline": True}},
                },
                "auto_acknowledge": {
                    CONF_NAME: "Auto acknowledge",
                    CONF_DESCRIPTION: (
                        "Automatically clear the notification after sending the "
                        "question."
                    ),
                    CONF_DEFAULT: False,
                    "selector": {"boolean": {}},
                },
            },
            CONF_TRACE: {},
        }

        return object_id, raw_config

    def _build_reset_script(
        self, slug: str, dog_id: str, dog_name: str
    ) -> tuple[str, ConfigType]:
        """Create the daily reset helper script definition."""

        object_id = f"pawcontrol_{slug}_daily_reset"
        raw_config: ConfigType = {
            CONF_ALIAS: f"{dog_name} reset daily counters",
            CONF_DESCRIPTION: (
                "Resets PawControl's counters for the dog and optionally records a "
                "summary in the logbook."
            ),
            CONF_SEQUENCE: [
                {
                    "service": "pawcontrol.reset_daily_stats",
                    "data": {
                        "dog_id": dog_id,
                        "confirm": "{{ confirm | default(true) }}",
                    },
                },
                {
                    "choose": [
                        {
                            "conditions": [
                                {
                                    "condition": "template",
                                    "value_template": "{{ summary | default('') != '' }}",
                                }
                            ],
                            "sequence": [
                                {
                                    "service": "logbook.log",
                                    "data": {
                                        "name": "PawControl",
                                        "message": "{{ summary }}",
                                    },
                                }
                            ],
                        }
                    ],
                    "default": [],
                },
            ],
            CONF_FIELDS: {
                "confirm": {
                    CONF_NAME: "Require confirmation",
                    CONF_DESCRIPTION: "Require an additional confirmation before resetting counters.",
                    CONF_DEFAULT: True,
                    "selector": {"boolean": {}},
                },
                "summary": {
                    CONF_NAME: "Log summary",
                    CONF_DESCRIPTION: (
                        "Optional summary that will be written to the logbook after the reset."
                    ),
                    CONF_DEFAULT: "",
                    "selector": {"text": {"multiline": True}},
                },
            },
            CONF_TRACE: {},
        }

        return object_id, raw_config

    def _build_push_test_script(
        self, slug: str, dog_id: str, dog_name: str
    ) -> tuple[str, ConfigType]:
        """Create the push notification test script definition."""

        object_id = f"pawcontrol_{slug}_notification_test"
        default_message = f"Test notification for {dog_name} from PawControl"

        raw_config: ConfigType = {
            CONF_ALIAS: f"{dog_name} notification test",
            CONF_DESCRIPTION: (
                "Sends the PawControl test notification so that you can verify "
                "push delivery for this dog."
            ),
            CONF_SEQUENCE: [
                {
                    "service": "pawcontrol.notify_test",
                    "data": {
                        "dog_id": dog_id,
                        "message": f"{{ message | default('{default_message}') }}",
                        "priority": "{{ priority | default('normal') }}",
                    },
                }
            ],
            CONF_FIELDS: {
                "message": {
                    CONF_NAME: "Message",
                    CONF_DESCRIPTION: "Notification message body.",
                    CONF_DEFAULT: default_message,
                    "selector": {"text": {"multiline": True}},
                },
                "priority": {
                    CONF_NAME: "Priority",
                    CONF_DESCRIPTION: "Notification priority used for the test message.",
                    CONF_DEFAULT: "normal",
                    "selector": {
                        "select": {
                            "options": ["low", "normal", "high", "urgent"],
                        }
                    },
                },
            },
            CONF_TRACE: {},
        }

        return object_id, raw_config

    def _build_setup_script(
        self,
        slug: str,
        dog_id: str,
        dog_name: str,
        notifications_enabled: bool,
    ) -> tuple[str, ConfigType]:
        """Create the daily setup orchestration script definition."""

        object_id = f"pawcontrol_{slug}_daily_setup"
        default_message = f"Daily PawControl setup completed for {dog_name}."

        sequence: list[ConfigType] = [
            {
                "service": "pawcontrol.reset_daily_stats",
                "data": {"dog_id": dog_id, "confirm": False},
            }
        ]

        fields: dict[str, ConfigType] = {}

        if notifications_enabled:
            sequence.append(
                {
                    "choose": [
                        {
                            "conditions": [
                                {
                                    "condition": "template",
                                    "value_template": "{{ send_notification | default(true) }}",
                                }
                            ],
                            "sequence": [
                                {
                                    "service": "pawcontrol.notify_test",
                                    "data": {
                                        "dog_id": dog_id,
                                        "message": f"{{ message | default('{default_message}') }}",
                                        "priority": "{{ priority | default('normal') }}",
                                    },
                                }
                            ],
                        }
                    ],
                    "default": [],
                }
            )

            fields["send_notification"] = {
                CONF_NAME: "Send verification",
                CONF_DESCRIPTION: "Send a PawControl notification after resetting counters.",
                CONF_DEFAULT: True,
                "selector": {"boolean": {}},
            }
            fields["message"] = {
                CONF_NAME: "Verification message",
                CONF_DESCRIPTION: "Message used when the verification notification is sent.",
                CONF_DEFAULT: default_message,
                "selector": {"text": {"multiline": True}},
            }
            fields["priority"] = {
                CONF_NAME: "Verification priority",
                CONF_DESCRIPTION: "Priority level for the verification notification.",
                CONF_DEFAULT: "normal",
                "selector": {
                    "select": {
                        "options": ["low", "normal", "high", "urgent"],
                    }
                },
            }

        raw_config: ConfigType = {
            CONF_ALIAS: f"{dog_name} daily setup",
            CONF_DESCRIPTION: (
                "Runs the documented PawControl setup flow by resetting counters "
                "and optionally sending a verification notification."
            ),
            CONF_SEQUENCE: sequence,
            CONF_FIELDS: fields,
            CONF_TRACE: {},
        }

        return object_id, raw_config
