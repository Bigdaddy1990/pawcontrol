"""Automatic Home Assistant script management for PawControl.

This module keeps the promise from the public documentation that PawControl
automatically provisions helper scripts for every configured dog.  It creates
notification workflows, reset helpers, and setup automation scripts directly in
Home Assistant's ``script`` domain so that users can trigger the documented
automation flows without manual YAML editing.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Iterable, Sequence
from datetime import datetime
from typing import Any, Final, cast

from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN
from homeassistant.components.script import ScriptEntity
from homeassistant.components.script.config import SCRIPT_ENTITY_SCHEMA
from homeassistant.components.script.const import CONF_FIELDS, CONF_TRACE
from homeassistant.const import (
    CONF_ALIAS,
    CONF_DEFAULT,
    CONF_DESCRIPTION,
    CONF_NAME,
    CONF_SEQUENCE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .compat import ConfigEntry, HomeAssistantError
from .const import (
    CACHE_TIMESTAMP_FUTURE_THRESHOLD,
    CACHE_TIMESTAMP_STALE_THRESHOLD,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    MODULE_NOTIFICATIONS,
)
from .coordinator_support import CacheMonitorRegistrar
from .types import (
    CacheDiagnosticsMetadata,
    CacheDiagnosticsSnapshot,
    DogConfigData,
    ensure_dog_modules_mapping,
)

_LOGGER = logging.getLogger(__name__)


def _serialize_datetime(value: datetime | None) -> str | None:
    """Return an ISO formatted timestamp for diagnostics payloads."""

    if value is None:
        return None
    return dt_util.as_utc(value).isoformat()


def _classify_timestamp(value: datetime | None) -> tuple[str | None, int | None]:
    """Classify ``value`` against the cache timestamp thresholds."""

    if value is None:
        return None, None

    delta = dt_util.utcnow() - dt_util.as_utc(value)
    age_seconds = int(delta.total_seconds())

    if delta < -CACHE_TIMESTAMP_FUTURE_THRESHOLD:
        return "future", age_seconds
    if delta > CACHE_TIMESTAMP_STALE_THRESHOLD:
        return "stale", age_seconds
    return None, age_seconds


class _ScriptManagerCacheMonitor:
    """Expose script manager state for diagnostics snapshots."""

    __slots__ = ("_manager",)

    def __init__(self, manager: PawControlScriptManager) -> None:
        self._manager = manager

    def _build_payload(
        self,
    ) -> tuple[dict[str, Any], dict[str, Any], CacheDiagnosticsMetadata]:
        manager = self._manager
        created_entities = cast(
            Iterable[str], getattr(manager, "_created_entities", set())
        )
        dog_scripts = cast(
            dict[str, Iterable[str]], getattr(manager, "_dog_scripts", {})
        )
        last_generation = cast(
            datetime | None, getattr(manager, "_last_generation", None)
        )

        created_list = sorted(
            entity for entity in created_entities if isinstance(entity, str)
        )
        per_dog: dict[str, dict[str, Any]] = {}
        for dog_id, scripts in dog_scripts.items():
            if not isinstance(dog_id, str):
                continue
            script_list = [entity for entity in scripts if isinstance(entity, str)]
            per_dog[dog_id] = {
                "count": len(script_list),
                "scripts": script_list,
            }

        stats: dict[str, Any] = {
            "scripts": len(created_list),
            "dogs": len(per_dog),
        }

        timestamp_issue, age_seconds = _classify_timestamp(last_generation)
        if age_seconds is not None:
            stats["last_generated_age_seconds"] = age_seconds

        snapshot: dict[str, Any] = {
            "created_entities": created_list,
            "per_dog": per_dog,
            "last_generated": _serialize_datetime(last_generation),
        }

        diagnostics: CacheDiagnosticsMetadata = {
            "per_dog": per_dog,
            "created_entities": created_list,
            "last_generated": _serialize_datetime(last_generation),
        }

        if age_seconds is not None:
            diagnostics["manager_last_generated_age_seconds"] = age_seconds

        if timestamp_issue is not None:
            diagnostics["timestamp_anomalies"] = {"manager": timestamp_issue}

        return stats, snapshot, diagnostics

    def coordinator_snapshot(self) -> CacheDiagnosticsSnapshot:
        stats, snapshot, diagnostics = self._build_payload()
        return CacheDiagnosticsSnapshot(
            stats=stats,
            snapshot=snapshot,
            diagnostics=diagnostics,
        )

    def get_stats(self) -> dict[str, Any]:
        stats, _snapshot, _diagnostics = self._build_payload()
        return stats

    def get_diagnostics(self) -> CacheDiagnosticsMetadata:
        _stats, _snapshot, diagnostics = self._build_payload()
        return diagnostics


_SCRIPT_ENTITY_PREFIX: Final[str] = f"{SCRIPT_DOMAIN}."


class PawControlScriptManager:
    """Create and maintain Home Assistant scripts for PawControl dogs."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the script manager."""

        self._hass = hass
        self._entry = entry
        self._created_entities: set[str] = set()
        self._dog_scripts: dict[str, list[str]] = {}
        self._last_generation: datetime | None = None

    async def async_initialize(self) -> None:
        """Reset internal tracking structures prior to script generation."""

        self._created_entities.clear()
        self._dog_scripts.clear()
        _LOGGER.debug("Script manager initialised for entry %s", self._entry.entry_id)

    def register_cache_monitors(
        self, registrar: CacheMonitorRegistrar, *, prefix: str = "script_manager"
    ) -> None:
        """Expose script diagnostics through the shared cache monitor registry."""

        if registrar is None:
            raise ValueError("registrar is required")

        _LOGGER.debug("Registering script manager cache monitor with prefix %s", prefix)
        registrar.register_cache_monitor(
            f"{prefix}_cache", _ScriptManagerCacheMonitor(self)
        )

    def _get_component(
        self, *, require_loaded: bool = True
    ) -> EntityComponent[Any] | None:
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
        if component is None:
            # ``_get_component`` raises when the script integration is missing, but keep
            # the guard so the type checker understands ``component`` is non-null.
            return {}
        registry = er.async_get(self._hass)
        created: dict[str, list[str]] = {}
        processed_dogs: set[str] = set()

        global_notifications_enabled = MODULE_NOTIFICATIONS in enabled_modules

        for dog in dogs:
            dog_id = dog.get(CONF_DOG_ID)
            if not isinstance(dog_id, str) or not dog_id:
                _LOGGER.debug(
                    "Skipping script generation for invalid dog entry: %s", dog
                )
                continue

            processed_dogs.add(dog_id)
            raw_name = dog.get(CONF_DOG_NAME)
            dog_name = (
                raw_name if isinstance(raw_name, str) and raw_name.strip() else dog_id
            )
            slug = slugify(dog_id)

            existing_for_dog = set(self._dog_scripts.get(dog_id, []))
            new_for_dog: list[str] = []

            dog_modules = ensure_dog_modules_mapping(dog)
            dog_notifications_enabled = dog_modules.get(
                MODULE_NOTIFICATIONS, global_notifications_enabled
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

        self._last_generation = dt_util.utcnow()

        return created

    async def async_cleanup(self) -> None:
        """Remove all scripts created by the integration."""

        component = self._get_component(require_loaded=False)
        registry = er.async_get(self._hass)

        for entity_id in list(self._created_entities):
            if component is not None and (entity := component.get_entity(entity_id)):
                await entity.async_remove()

            if registry.async_get(entity_id):
                await registry.async_remove(entity_id)

            self._created_entities.discard(entity_id)

        self._dog_scripts.clear()
        _LOGGER.debug(
            "Removed all PawControl managed scripts for entry %s", self._entry.entry_id
        )

    async def _async_remove_script_entity(self, entity_id: str) -> None:
        """Remove a specific script entity and its registry entry."""

        component = self._get_component(require_loaded=False)
        registry = er.async_get(self._hass)

        if component is not None and (entity := component.get_entity(entity_id)):
            await entity.async_remove()

        if registry.async_get(entity_id):
            await registry.async_remove(entity_id)

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
            scripts.append(self._build_confirmation_script(slug, dog_id, dog_name))
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
