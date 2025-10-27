"""Automatic Home Assistant script management for PawControl.

This module keeps the promise from the public documentation that PawControl
automatically provisions helper scripts for every configured dog.  It creates
notification workflows, reset helpers, and setup automation scripts directly in
Home Assistant's ``script`` domain so that users can trigger the documented
automation flows without manual YAML editing.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
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
from homeassistant.core import Event, HomeAssistant
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
    DEFAULT_RESILIENCE_BREAKER_THRESHOLD,
    DEFAULT_RESILIENCE_SKIP_THRESHOLD,
    DOMAIN,
    MODULE_NOTIFICATIONS,
    RESILIENCE_BREAKER_THRESHOLD_MAX,
    RESILIENCE_BREAKER_THRESHOLD_MIN,
    RESILIENCE_SKIP_THRESHOLD_MAX,
    RESILIENCE_SKIP_THRESHOLD_MIN,
)
from .coordinator_support import CacheMonitorRegistrar
from .types import (
    CacheDiagnosticsMetadata,
    CacheDiagnosticsSnapshot,
    DogConfigData,
    ensure_dog_modules_mapping,
)

_LOGGER = logging.getLogger(__name__)


slugify = getattr(slugify, "slugify", slugify)

_RESILIENCE_BLUEPRINT_IDENTIFIER: Final[str] = "resilience_escalation_followup"
_RESILIENCE_BLUEPRINT_DOMAIN: Final[str] = "pawcontrol"


def _normalise_entry_slug(entry: ConfigEntry) -> str:
    """Return the slug used for integration-managed scripts."""

    raw_slug = slugify(getattr(entry, "title", "") or entry.entry_id or DOMAIN)
    return raw_slug or DOMAIN


def _resolve_resilience_object_id(entry: ConfigEntry) -> str:
    """Return the script object id for the resilience escalation helper."""

    return f"pawcontrol_{_normalise_entry_slug(entry)}_resilience_escalation"


def _resolve_resilience_entity_id(entry: ConfigEntry) -> str:
    """Return the script entity id for the resilience escalation helper."""

    return f"{SCRIPT_DOMAIN}.{_resolve_resilience_object_id(entry)}"


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


def _coerce_threshold(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    """Return a clamped integer threshold for resilience configuration."""

    try:
        candidate = int(value)
    except (TypeError, ValueError):
        return default

    if candidate < minimum:
        return minimum
    if candidate > maximum:
        return maximum
    return candidate


def _extract_field_int(fields: Mapping[str, Any] | None, key: str) -> int | None:
    """Return the integer default stored under ``key`` in ``fields``."""

    if not isinstance(fields, Mapping):
        return None

    field = fields.get(key)
    if isinstance(field, Mapping):
        candidate = field.get("default")
    else:
        candidate = getattr(field, "default", None)

    if candidate is None:
        return None

    try:
        return int(candidate)
    except (TypeError, ValueError):
        return None


def resolve_resilience_script_thresholds(
    hass: HomeAssistant, entry: ConfigEntry
) -> tuple[int | None, int | None]:
    """Return skip and breaker thresholds from the generated script entity."""

    states = getattr(hass, "states", None)
    if states is None or not hasattr(states, "get"):
        return None, None

    entity_id = _resolve_resilience_entity_id(entry)
    state = states.get(entity_id)
    if state is None:
        return None, None

    attributes = getattr(state, "attributes", {})
    fields = attributes.get("fields") if isinstance(attributes, Mapping) else None

    skip = _extract_field_int(fields, "skip_threshold")
    breaker = _extract_field_int(fields, "breaker_threshold")
    return skip, breaker


def _is_resilience_blueprint(use_blueprint: Mapping[str, Any] | None) -> bool:
    """Return ``True`` when ``use_blueprint`` targets the resilience blueprint."""

    if not isinstance(use_blueprint, Mapping):
        return False

    identifier = str(
        use_blueprint.get("blueprint_id")
        or use_blueprint.get("path")
        or use_blueprint.get("id")
        or ""
    )
    if not identifier:
        return False

    normalized = identifier.replace("\\", "/").lower()
    expected_suffix = (
        f"{_RESILIENCE_BLUEPRINT_DOMAIN}/{_RESILIENCE_BLUEPRINT_IDENTIFIER}.yaml"
    )
    return normalized.endswith(expected_suffix)


def _normalise_manual_event(value: Any) -> str | None:
    """Return a stripped event string when ``value`` contains text."""

    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate or None


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
        entry_scripts = cast(Iterable[str], getattr(manager, "_entry_scripts", []))
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
        entry_list = [entity for entity in entry_scripts if isinstance(entity, str)]

        stats: dict[str, Any] = {
            "scripts": len(created_list),
            "dogs": len(per_dog),
        }
        if entry_list:
            stats["entry_scripts"] = len(entry_list)

        timestamp_issue, age_seconds = _classify_timestamp(last_generation)
        if age_seconds is not None:
            stats["last_generated_age_seconds"] = age_seconds

        snapshot: dict[str, Any] = {
            "created_entities": created_list,
            "per_dog": per_dog,
            "last_generated": _serialize_datetime(last_generation),
        }
        if entry_list:
            snapshot["entry_scripts"] = entry_list

        diagnostics: CacheDiagnosticsMetadata = {
            "per_dog": per_dog,
            "created_entities": created_list,
            "last_generated": _serialize_datetime(last_generation),
        }
        if entry_list:
            diagnostics["entry_scripts"] = entry_list

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
        self._entry_scripts: list[str] = []
        self._last_generation: datetime | None = None
        self._resilience_escalation_definition: dict[str, Any] | None = None
        self._manual_event_unsubs: dict[str, Callable[[], None]] = {}
        self._manual_event_reasons: dict[str, set[str]] = {}
        self._manual_event_sources: dict[str, set[str]] = {}
        self._manual_event_counters: dict[str, int] = {}
        self._last_manual_event: dict[str, Any] | None = None
        self._entry_slug = _normalise_entry_slug(entry)
        title = getattr(entry, "title", None)
        self._entry_title = (
            title.strip() if isinstance(title, str) and title.strip() else "PawControl"
        )

    async def async_initialize(self) -> None:
        """Reset internal tracking structures prior to script generation."""

        self._created_entities.clear()
        self._dog_scripts.clear()
        self._entry_scripts.clear()
        for unsub in list(self._manual_event_unsubs.values()):
            unsub()
        self._manual_event_unsubs.clear()
        self._manual_event_reasons.clear()
        self._manual_event_sources.clear()
        self._manual_event_counters.clear()
        self._last_manual_event = None
        self._refresh_manual_event_listeners()
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

    def _resolve_resilience_thresholds(self) -> tuple[int, int]:
        """Return configured guard skip and breaker thresholds."""

        options = getattr(self._entry, "options", {})
        skip_threshold = DEFAULT_RESILIENCE_SKIP_THRESHOLD
        breaker_threshold = DEFAULT_RESILIENCE_BREAKER_THRESHOLD

        def _merge_threshold(
            source: Mapping[str, Any] | None,
            *,
            key: str,
            default: int,
            minimum: int,
            maximum: int,
        ) -> int:
            if not isinstance(source, Mapping):
                return default
            return _coerce_threshold(
                source.get(key),
                default=default,
                minimum=minimum,
                maximum=maximum,
            )

        if isinstance(options, Mapping):
            system_settings = options.get("system_settings")
            if isinstance(system_settings, Mapping):
                skip_threshold = _merge_threshold(
                    system_settings,
                    key="resilience_skip_threshold",
                    default=skip_threshold,
                    minimum=RESILIENCE_SKIP_THRESHOLD_MIN,
                    maximum=RESILIENCE_SKIP_THRESHOLD_MAX,
                )
                breaker_threshold = _merge_threshold(
                    system_settings,
                    key="resilience_breaker_threshold",
                    default=breaker_threshold,
                    minimum=RESILIENCE_BREAKER_THRESHOLD_MIN,
                    maximum=RESILIENCE_BREAKER_THRESHOLD_MAX,
                )

            skip_threshold = _merge_threshold(
                options,
                key="resilience_skip_threshold",
                default=skip_threshold,
                minimum=RESILIENCE_SKIP_THRESHOLD_MIN,
                maximum=RESILIENCE_SKIP_THRESHOLD_MAX,
            )
            breaker_threshold = _merge_threshold(
                options,
                key="resilience_breaker_threshold",
                default=breaker_threshold,
                minimum=RESILIENCE_BREAKER_THRESHOLD_MIN,
                maximum=RESILIENCE_BREAKER_THRESHOLD_MAX,
            )

        script_skip, script_breaker = resolve_resilience_script_thresholds(
            self._hass, self._entry
        )
        if script_skip is not None:
            skip_threshold = _coerce_threshold(
                script_skip,
                default=skip_threshold,
                minimum=RESILIENCE_SKIP_THRESHOLD_MIN,
                maximum=RESILIENCE_SKIP_THRESHOLD_MAX,
            )
        if script_breaker is not None:
            breaker_threshold = _coerce_threshold(
                script_breaker,
                default=breaker_threshold,
                minimum=RESILIENCE_BREAKER_THRESHOLD_MIN,
                maximum=RESILIENCE_BREAKER_THRESHOLD_MAX,
            )

        return skip_threshold, breaker_threshold

    def ensure_resilience_threshold_options(self) -> dict[str, Any] | None:
        """Return updated options when legacy script defaults need migration."""

        options = getattr(self._entry, "options", {})
        system_settings = (
            options.get("system_settings") if isinstance(options, Mapping) else None
        )
        script_skip, script_breaker = resolve_resilience_script_thresholds(
            self._hass, self._entry
        )

        if not self._should_migrate_resilience_thresholds(
            script_skip, script_breaker, system_settings
        ):
            return None

        migrated_system = self._build_resilience_system_settings(
            system_settings,
            script_skip=script_skip,
            script_breaker=script_breaker,
        )

        if migrated_system is None:
            return None

        return self._apply_resilience_system_settings(options, migrated_system)

    @staticmethod
    def _should_migrate_resilience_thresholds(
        script_skip: int | None,
        script_breaker: int | None,
        system_settings: Mapping[str, Any] | None,
    ) -> bool:
        """Return ``True`` when script defaults should populate options."""

        if script_skip is None and script_breaker is None:
            return False

        if not isinstance(system_settings, Mapping):
            return True

        missing_skip = "resilience_skip_threshold" not in system_settings
        missing_breaker = "resilience_breaker_threshold" not in system_settings

        return missing_skip or missing_breaker

    @staticmethod
    def _build_resilience_system_settings(
        system_settings: Mapping[str, Any] | None,
        *,
        script_skip: int | None,
        script_breaker: int | None,
    ) -> dict[str, Any] | None:
        """Return a system settings payload with migrated thresholds."""

        original = dict(system_settings) if isinstance(system_settings, Mapping) else {}
        updated = dict(original)

        if script_skip is not None and "resilience_skip_threshold" not in updated:
            updated["resilience_skip_threshold"] = _coerce_threshold(
                script_skip,
                default=DEFAULT_RESILIENCE_SKIP_THRESHOLD,
                minimum=RESILIENCE_SKIP_THRESHOLD_MIN,
                maximum=RESILIENCE_SKIP_THRESHOLD_MAX,
            )

        if script_breaker is not None and "resilience_breaker_threshold" not in updated:
            updated["resilience_breaker_threshold"] = _coerce_threshold(
                script_breaker,
                default=DEFAULT_RESILIENCE_BREAKER_THRESHOLD,
                minimum=RESILIENCE_BREAKER_THRESHOLD_MIN,
                maximum=RESILIENCE_BREAKER_THRESHOLD_MAX,
            )

        if updated == original:
            return None

        return updated

    @staticmethod
    def _apply_resilience_system_settings(
        options: Mapping[str, Any],
        system_settings: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return updated options including migrated system settings."""

        updated_options = dict(options)
        updated_options["system_settings"] = dict(system_settings)

        for key in ("resilience_skip_threshold", "resilience_breaker_threshold"):
            if key not in updated_options and key in system_settings:
                updated_options[key] = system_settings[key]

        return updated_options

    def _resolve_manual_resilience_events(self) -> dict[str, Any]:
        """Return configured manual escalation events from blueprint automations."""

        manager = getattr(self._hass, "config_entries", None)
        entries_callable = getattr(manager, "async_entries", None)
        if not callable(entries_callable):
            return {
                "available": False,
                "automations": [],
                "configured_guard_events": [],
                "configured_breaker_events": [],
                "configured_check_events": [],
                "system_guard_event": None,
                "system_breaker_event": None,
                "listener_events": {},
                "listener_sources": {},
            }

        options = getattr(self._entry, "options", {})
        system_guard: str | None = None
        system_breaker: str | None = None
        if isinstance(options, Mapping):
            system_guard = _normalise_manual_event(options.get("manual_guard_event"))
            system_breaker = _normalise_manual_event(
                options.get("manual_breaker_event")
            )
            system_settings = options.get("system_settings")
            if isinstance(system_settings, Mapping):
                guard_override = _normalise_manual_event(
                    system_settings.get("manual_guard_event")
                )
                breaker_override = _normalise_manual_event(
                    system_settings.get("manual_breaker_event")
                )
                if guard_override is not None:
                    system_guard = guard_override
                if breaker_override is not None:
                    system_breaker = breaker_override

        automations = []
        guard_events: set[str] = set()
        breaker_events: set[str] = set()
        check_events: set[str] = set()
        listener_reasons: dict[str, set[str]] = {}
        listener_sources: dict[str, set[str]] = {}

        def _register_listener(event: str | None, reason: str, source: str) -> None:
            if not event:
                return
            listener_reasons.setdefault(event, set()).add(reason)
            listener_sources.setdefault(event, set()).add(source)

        try:
            automation_entries = entries_callable("automation")
        except (AttributeError, TypeError, KeyError):
            automation_entries = []

        _register_listener(system_guard, "guard", "system_options")
        _register_listener(system_breaker, "breaker", "system_options")

        for entry in automation_entries or []:
            entry_data = getattr(entry, "data", {})
            if not isinstance(entry_data, Mapping):
                continue

            use_blueprint = entry_data.get("use_blueprint")
            if not _is_resilience_blueprint(use_blueprint):
                continue

            blueprint = cast(Mapping[str, Any], use_blueprint)

            inputs = blueprint.get("input") or blueprint.get("inputs")
            if not isinstance(inputs, Mapping):
                inputs = {}

            manual_guard = _normalise_manual_event(inputs.get("manual_guard_event"))
            manual_breaker = _normalise_manual_event(inputs.get("manual_breaker_event"))
            manual_check = _normalise_manual_event(inputs.get("manual_check_event"))

            if manual_guard:
                guard_events.add(manual_guard)
                _register_listener(manual_guard, "guard", "blueprint")
            if manual_breaker:
                breaker_events.add(manual_breaker)
                _register_listener(manual_breaker, "breaker", "blueprint")
            if manual_check:
                check_events.add(manual_check)
                _register_listener(manual_check, "check", "blueprint")

            automations.append(
                {
                    "config_entry_id": getattr(entry, "entry_id", None),
                    "title": getattr(entry, "title", None),
                    "manual_guard_event": manual_guard,
                    "manual_breaker_event": manual_breaker,
                    "manual_check_event": manual_check,
                    "configured_guard": bool(manual_guard),
                    "configured_breaker": bool(manual_breaker),
                    "configured_check": bool(manual_check),
                }
            )

        available = bool(automations)
        if system_guard is not None or system_breaker is not None:
            available = True

        return {
            "available": available,
            "automations": automations,
            "configured_guard_events": sorted(guard_events),
            "configured_breaker_events": sorted(breaker_events),
            "configured_check_events": sorted(check_events),
            "system_guard_event": system_guard,
            "system_breaker_event": system_breaker,
            "listener_events": {
                event: sorted(reasons) for event, reasons in listener_reasons.items()
            },
            "listener_sources": {
                event: sorted(sources) for event, sources in listener_sources.items()
            },
        }

    def _refresh_manual_event_listeners(self) -> dict[str, Any]:
        """Synchronise manual event listeners with configured inputs."""

        manual_data = self._resolve_manual_resilience_events()
        listener_events = manual_data.get("listener_events", {})
        listener_sources = manual_data.get("listener_sources", {})

        desired_reasons: dict[str, set[str]] = {}
        for event, reasons in listener_events.items():
            if not isinstance(event, str):
                continue
            if isinstance(reasons, str):
                reason_iterable = [reasons]
            elif isinstance(reasons, Iterable):
                reason_iterable = [
                    reason for reason in reasons if isinstance(reason, str)
                ]
            else:
                reason_iterable = []
            desired_reasons[event] = set(reason_iterable)

        desired_sources: dict[str, set[str]] = {}
        for event in desired_reasons:
            sources_iterable = listener_sources.get(event, [])
            if isinstance(sources_iterable, str):
                sources = {sources_iterable}
            elif isinstance(sources_iterable, Iterable):
                sources = {
                    source for source in sources_iterable if isinstance(source, str)
                }
            else:
                sources = set()
            desired_sources[event] = sources

        bus = getattr(self._hass, "bus", None)
        async_listen = getattr(bus, "async_listen", None)

        for event, unsub in list(self._manual_event_unsubs.items()):
            if event not in desired_reasons:
                unsub()
                self._manual_event_unsubs.pop(event, None)
                self._manual_event_reasons.pop(event, None)
                self._manual_event_sources.pop(event, None)

        self._manual_event_reasons = desired_reasons
        self._manual_event_sources = desired_sources

        if not callable(async_listen):
            return manual_data

        for event in desired_reasons:
            if event not in self._manual_event_unsubs:
                self._manual_event_unsubs[event] = async_listen(
                    event, self._handle_manual_event
                )

        return manual_data

    def _handle_manual_event(self, event: Event) -> None:
        """Record metadata for the most recent manual resilience trigger."""

        event_type = event.event_type
        reasons = sorted(self._manual_event_reasons.get(event_type, set()))
        sources = sorted(self._manual_event_sources.get(event_type, set()))
        recorded_at = dt_util.utcnow()
        self._last_manual_event = {
            "event_type": event_type,
            "reasons": reasons,
            "sources": sources,
            "recorded_at": recorded_at,
        }
        if isinstance(event_type, str) and event_type:
            self._manual_event_counters[event_type] = (
                self._manual_event_counters.get(event_type, 0) + 1
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

        entry_script_definitions = self._build_entry_scripts()
        existing_entry_scripts = set(self._entry_scripts)
        new_entry_scripts: list[str] = []

        for object_id, raw_config in entry_script_definitions:
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
            new_entry_scripts.append(entity_id)

            if (entry := registry.async_get(entity_id)) and (
                entry.config_entry_id != self._entry.entry_id
            ):
                registry.async_update_entity(
                    entity_id, config_entry_id=self._entry.entry_id
                )

        obsolete_entry_scripts = existing_entry_scripts - set(new_entry_scripts)
        for entity_id in obsolete_entry_scripts:
            await self._async_remove_script_entity(entity_id)

        if new_entry_scripts:
            created["__entry__"] = list(new_entry_scripts)
            self._entry_scripts = list(new_entry_scripts)
        else:
            self._entry_scripts = []

        self._last_generation = dt_util.utcnow()

        self._refresh_manual_event_listeners()

        return created

    async def async_cleanup(self) -> None:
        """Remove all scripts created by the integration."""

        component = self._get_component(require_loaded=False)
        registry = er.async_get(self._hass)

        for unsub in list(self._manual_event_unsubs.values()):
            unsub()
        self._manual_event_unsubs.clear()
        self._manual_event_reasons.clear()
        self._manual_event_sources.clear()
        self._manual_event_counters.clear()
        self._last_manual_event = None

        for entity_id in list(self._created_entities):
            if component is not None and (entity := component.get_entity(entity_id)):
                await entity.async_remove()

            if registry.async_get(entity_id):
                await registry.async_remove(entity_id)

            self._created_entities.discard(entity_id)

        self._dog_scripts.clear()
        self._entry_scripts.clear()
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

    def _build_entry_scripts(self) -> list[tuple[str, ConfigType]]:
        """Return global script definitions scoped to the config entry."""

        scripts: list[tuple[str, ConfigType]] = []
        scripts.append(self._build_resilience_escalation_script())
        return scripts

    def _build_resilience_escalation_script(self) -> tuple[str, ConfigType]:
        """Create the guard and breaker escalation script definition."""

        object_id = _resolve_resilience_object_id(self._entry)
        default_statistics_entity = "sensor.pawcontrol_statistics"
        skip_threshold_default, breaker_threshold_default = (
            self._resolve_resilience_thresholds()
        )

        guard_default_title = f"{self._entry_title} guard escalation"
        guard_default_message = (
            "Guard skipped {{ skip_count }} call(s) while executing {{ executed_count }} "
            "request(s). Skip reasons: {{ guard_reason_text }}."
        )
        guard_default_notification_id = (
            f"pawcontrol_{self._entry_slug}_guard_escalation"
        )

        breaker_default_title = f"{self._entry_title} breaker escalation"
        breaker_default_message = (
            "Circuit breakers report {{ breaker_count }} open and {{ half_open_count }} "
            "half-open guard(s). Open breakers: {{ open_breakers_text }}. "
            "Half-open breakers: {{ half_open_breakers_text }}."
        )
        breaker_default_notification_id = (
            f"pawcontrol_{self._entry_slug}_breaker_escalation"
        )

        variables: ConfigType = {
            "statistics_entity": (
                f"{{{{ statistics_entity_id | default('{default_statistics_entity}') }}}}"
            ),
            "service_execution": (
                "{{ state_attr(statistics_entity, 'service_execution') or {} }}"
            ),
            "guard": (
                "{% set data = state_attr(statistics_entity, 'service_execution') or {} %}"
                "{% set metrics = data.get('guard_metrics') %}"
                "{% if metrics is mapping %}{{ metrics }}{% else %}{{ {} }}{% endif %}"
            ),
            "rejection": (
                "{% set data = state_attr(statistics_entity, 'service_execution') or {} %}"
                "{% set metrics = data.get('rejection_metrics') %}"
                "{% if metrics is mapping %}{{ metrics }}{% else %}{{ {} }}{% endif %}"
            ),
            "skip_count": "{{ guard.get('skipped', 0) | int(0) }}",
            "executed_count": "{{ guard.get('executed', 0) | int(0) }}",
            "breaker_count": "{{ rejection.get('open_breaker_count', 0) | int(0) }}",
            "half_open_count": (
                "{{ rejection.get('half_open_breaker_count', 0) | int(0) }}"
            ),
            "guard_reason_text": (
                "{% set items = guard.get('reasons', {}) | dictsort %}"
                "{% if items %}"
                "{% for reason, count in items %}"
                "{{ reason }} ({{ count }}){% if not loop.last %}, {% endif %}"
                "{% endfor %}"
                "{% else %}No guard skip reasons recorded{% endif %}"
            ),
            "open_breakers_text": (
                "{% set names = rejection.get('open_breakers', []) %}"
                "{% if names %}{{ names | join(', ') }}{% else %}None{% endif %}"
            ),
            "half_open_breakers_text": (
                "{% set names = rejection.get('half_open_breakers', []) %}"
                "{% if names %}{{ names | join(', ') }}{% else %}None{% endif %}"
            ),
        }

        guard_followup: ConfigType = {
            "choose": [
                {
                    "conditions": [
                        {
                            "condition": "template",
                            "value_template": (
                                "{{ followup_script | default('') | trim != '' }}"
                            ),
                        }
                    ],
                    "sequence": [
                        {
                            "service": "script.turn_on",
                            "target": {"entity_id": "{{ followup_script }}"},
                            "data": {
                                "variables": {
                                    "trigger_reason": "guard",
                                    "skip_count": "{{ skip_count }}",
                                    "executed_count": "{{ executed_count }}",
                                    "guard_reasons": "{{ guard.get('reasons', {}) }}",
                                    "breaker_count": "{{ breaker_count }}",
                                    "half_open_count": "{{ half_open_count }}",
                                }
                            },
                        }
                    ],
                }
            ],
            "default": [],
        }

        breaker_followup: ConfigType = {
            "choose": [
                {
                    "conditions": [
                        {
                            "condition": "template",
                            "value_template": (
                                "{{ followup_script | default('') | trim != '' }}"
                            ),
                        }
                    ],
                    "sequence": [
                        {
                            "service": "script.turn_on",
                            "target": {"entity_id": "{{ followup_script }}"},
                            "data": {
                                "variables": {
                                    "trigger_reason": "breaker",
                                    "breaker_count": "{{ breaker_count }}",
                                    "half_open_count": "{{ half_open_count }}",
                                    "open_breakers": "{{ rejection.get('open_breakers', []) }}",
                                    "half_open_breakers": "{{ rejection.get('half_open_breakers', []) }}",
                                    "skip_count": "{{ skip_count }}",
                                    "executed_count": "{{ executed_count }}",
                                }
                            },
                        }
                    ],
                }
            ],
            "default": [],
        }

        sequence: list[ConfigType] = [
            {"variables": variables},
            {
                "choose": [
                    {
                        "conditions": [
                            {
                                "condition": "template",
                                "value_template": (
                                    "{{ (skip_threshold | int(0)) > 0 and "
                                    "skip_count >= (skip_threshold | int(0)) }}"
                                ),
                            }
                        ],
                        "sequence": [
                            {
                                "service": (
                                    "{{ escalation_service | default('persistent_notification.create') }}"
                                ),
                                "data": {
                                    "title": (
                                        f"{{{{ guard_title | default('{guard_default_title}') }}}}"
                                    ),
                                    "message": (
                                        f"{{{{ guard_message | default('{guard_default_message}') }}}}"
                                    ),
                                    "notification_id": (
                                        f"{{{{ guard_notification_id | default('{guard_default_notification_id}') }}}}"
                                    ),
                                },
                            },
                            guard_followup,
                        ],
                    },
                    {
                        "conditions": [
                            {
                                "condition": "template",
                                "value_template": (
                                    "{{ (breaker_threshold | int(0)) > 0 and ("
                                    "breaker_count >= (breaker_threshold | int(0)) or "
                                    "half_open_count >= (breaker_threshold | int(0))) }}"
                                ),
                            }
                        ],
                        "sequence": [
                            {
                                "service": (
                                    "{{ escalation_service | default('persistent_notification.create') }}"
                                ),
                                "data": {
                                    "title": (
                                        f"{{{{ breaker_title | default('{breaker_default_title}') }}}}"
                                    ),
                                    "message": (
                                        f"{{{{ breaker_message | default('{breaker_default_message}') }}}}"
                                    ),
                                    "notification_id": (
                                        f"{{{{ breaker_notification_id | default('{breaker_default_notification_id}') }}}}"
                                    ),
                                },
                            },
                            breaker_followup,
                        ],
                    },
                ],
                "default": [],
            },
        ]

        fields: ConfigType = {
            "statistics_entity_id": {
                CONF_NAME: "Statistics sensor",
                CONF_DESCRIPTION: (
                    "Entity that exposes PawControl runtime statistics including "
                    "service execution metrics."
                ),
                CONF_DEFAULT: default_statistics_entity,
                "selector": {"entity": {"domain": "sensor"}},
            },
            "skip_threshold": {
                CONF_NAME: "Guard skip threshold",
                CONF_DESCRIPTION: (
                    "Escalate when skipped guard calls reach or exceed this value. "
                    "Set to 0 to disable guard escalations."
                ),
                CONF_DEFAULT: skip_threshold_default,
                "selector": {"number": {"min": 0, "max": 50, "mode": "box"}},
            },
            "breaker_threshold": {
                CONF_NAME: "Breaker alert threshold",
                CONF_DESCRIPTION: (
                    "Escalate when open or half-open breaker counts reach this value. "
                    "Set to 0 to disable breaker escalations."
                ),
                CONF_DEFAULT: breaker_threshold_default,
                "selector": {"number": {"min": 0, "max": 10, "mode": "box"}},
            },
            "escalation_service": {
                CONF_NAME: "Escalation service",
                CONF_DESCRIPTION: (
                    "Service called when an escalation fires. Uses persistent "
                    "notifications by default."
                ),
                CONF_DEFAULT: "persistent_notification.create",
                "selector": {"text": {}},
            },
            "guard_title": {
                CONF_NAME: "Guard alert title",
                CONF_DESCRIPTION: "Title used when guard skips trigger the escalation.",
                CONF_DEFAULT: guard_default_title,
                "selector": {"text": {}},
            },
            "guard_message": {
                CONF_NAME: "Guard alert message",
                CONF_DESCRIPTION: (
                    "Message body for guard skip escalations. Jinja variables from the "
                    "script (e.g. {{ skip_count }}) are available."
                ),
                CONF_DEFAULT: guard_default_message,
                "selector": {"text": {"multiline": True}},
            },
            "guard_notification_id": {
                CONF_NAME: "Guard notification ID",
                CONF_DESCRIPTION: (
                    "Notification identifier so repeated alerts update the same "
                    "persistent notification."
                ),
                CONF_DEFAULT: guard_default_notification_id,
                "selector": {"text": {}},
            },
            "breaker_title": {
                CONF_NAME: "Breaker alert title",
                CONF_DESCRIPTION: "Title used when breaker counts trigger the escalation.",
                CONF_DEFAULT: breaker_default_title,
                "selector": {"text": {}},
            },
            "breaker_message": {
                CONF_NAME: "Breaker alert message",
                CONF_DESCRIPTION: (
                    "Message body for breaker escalations. Script variables such as "
                    "{{ breaker_count }} are available."
                ),
                CONF_DEFAULT: breaker_default_message,
                "selector": {"text": {"multiline": True}},
            },
            "breaker_notification_id": {
                CONF_NAME: "Breaker notification ID",
                CONF_DESCRIPTION: (
                    "Notification identifier for breaker alerts, keeping updates "
                    "idempotent."
                ),
                CONF_DEFAULT: breaker_default_notification_id,
                "selector": {"text": {}},
            },
            "followup_script": {
                CONF_NAME: "Follow-up script",
                CONF_DESCRIPTION: (
                    "Optional script triggered after escalations fire. Receives "
                    "context variables such as skip and breaker counts."
                ),
                CONF_DEFAULT: "",
                "selector": {"entity": {"domain": "script", "multiple": False}},
            },
        }

        raw_config: ConfigType = {
            CONF_ALIAS: f"{self._entry_title} resilience escalation",
            CONF_DESCRIPTION: (
                "Escalates guard skips and breaker activations using PawControl's "
                "runtime service metrics and optional follow-up automations."
            ),
            CONF_SEQUENCE: sequence,
            CONF_FIELDS: fields,
            CONF_TRACE: {},
        }

        field_defaults: dict[str, Any] = {}
        for field_name, field_config in fields.items():
            if isinstance(field_config, Mapping):
                field_defaults[field_name] = field_config.get(CONF_DEFAULT)

        self._resilience_escalation_definition = {
            "object_id": object_id,
            "alias": raw_config[CONF_ALIAS],
            "description": raw_config[CONF_DESCRIPTION],
            "field_defaults": field_defaults,
        }

        return object_id, raw_config

    def get_resilience_escalation_snapshot(self) -> dict[str, Any] | None:
        """Return diagnostics metadata for the resilience escalation helper."""

        definition = self._resilience_escalation_definition
        if not isinstance(definition, dict):
            return None

        object_id = definition.get("object_id")
        entity_id: str | None = next(
            (
                entity
                for entity in self._entry_scripts
                if isinstance(entity, str) and entity.endswith("_resilience_escalation")
            ),
            None,
        )

        if entity_id is None and isinstance(object_id, str):
            entity_id = f"{SCRIPT_DOMAIN}.{object_id}"

        field_defaults = cast(dict[str, Any], definition.get("field_defaults", {}))
        manual_events = self._refresh_manual_event_listeners()

        state = None
        if entity_id is not None:
            state = getattr(self._hass, "states", None)
            state = state.get(entity_id) if state is not None else None

        state_available = state is not None
        last_triggered: datetime | None = None
        if state_available:
            last_value = getattr(state, "attributes", {}).get("last_triggered")
            if isinstance(last_value, datetime):
                last_triggered = dt_util.as_utc(last_value)
            elif isinstance(last_value, str):
                parsed = dt_util.parse_datetime(last_value)
                if parsed is not None:
                    last_triggered = dt_util.as_utc(parsed)

        last_triggered_age: int | None = None
        if last_triggered is not None:
            last_triggered_age = int(
                (dt_util.utcnow() - dt_util.as_utc(last_triggered)).total_seconds()
            )

        active_field_defaults: dict[str, Any] = {}
        if state_available:
            fields_attr = getattr(state, "attributes", {}).get("fields")
            if isinstance(fields_attr, Mapping):
                for field_name, field_config in fields_attr.items():
                    if isinstance(field_config, Mapping):
                        default_value = field_config.get("default")
                    else:
                        default_value = getattr(field_config, "default", None)
                    if default_value is not None or field_name in field_defaults:
                        active_field_defaults[field_name] = default_value

        def _active_value(key: str) -> Any:
            if key in active_field_defaults:
                return active_field_defaults[key]
            return field_defaults.get(key)

        thresholds = {
            "skip_threshold": {
                "default": field_defaults.get("skip_threshold"),
                "active": _active_value("skip_threshold"),
            },
            "breaker_threshold": {
                "default": field_defaults.get("breaker_threshold"),
                "active": _active_value("breaker_threshold"),
            },
        }

        followup_active = _active_value("followup_script")

        timestamp_issue, last_generated_age = _classify_timestamp(self._last_generation)

        manual_last_trigger: dict[str, Any] | None = None
        if isinstance(self._last_manual_event, Mapping):
            recorded_at = self._last_manual_event.get("recorded_at")
            recorded_dt = recorded_at if isinstance(recorded_at, datetime) else None
            recorded_age: int | None = None
            if recorded_dt is not None:
                recorded_age = int(
                    (dt_util.utcnow() - dt_util.as_utc(recorded_dt)).total_seconds()
                )
            manual_last_trigger = {
                "event_type": self._last_manual_event.get("event_type"),
                "reasons": list(self._last_manual_event.get("reasons", [])),
                "sources": list(self._last_manual_event.get("sources", [])),
                "recorded_at": _serialize_datetime(recorded_dt),
                "recorded_age_seconds": recorded_age,
            }

        manual_events_payload = dict(manual_events)
        manual_events_payload["last_trigger"] = manual_last_trigger

        counters_by_event: dict[str, int] = {}
        candidate_events: set[str] = set()

        for key in (
            "configured_guard_events",
            "configured_breaker_events",
            "configured_check_events",
        ):
            values = manual_events_payload.get(key, [])
            if isinstance(values, Iterable):
                for value in values:
                    if isinstance(value, str) and value:
                        candidate_events.add(value)

        system_guard_event = manual_events_payload.get("system_guard_event")
        if isinstance(system_guard_event, str) and system_guard_event:
            candidate_events.add(system_guard_event)

        system_breaker_event = manual_events_payload.get("system_breaker_event")
        if isinstance(system_breaker_event, str) and system_breaker_event:
            candidate_events.add(system_breaker_event)

        listener_events = manual_events_payload.get("listener_events", {})
        if isinstance(listener_events, Mapping):
            candidate_events.update(
                event for event in listener_events if isinstance(event, str)
            )

        candidate_events.update(
            event
            for event in self._manual_event_counters
            if isinstance(event, str) and event
        )

        for event in sorted(candidate_events):
            counters_by_event[event] = int(self._manual_event_counters.get(event, 0))

        counters_by_reason: dict[str, int] = {}
        if isinstance(listener_events, Mapping):
            for event, reasons in listener_events.items():
                if not isinstance(event, str):
                    continue
                event_count = counters_by_event.get(event, 0)
                if not event_count:
                    continue
                if isinstance(reasons, str):
                    reasons_iterable: Iterable[str] = [reasons]
                elif isinstance(reasons, Iterable):
                    reasons_iterable = (
                        reason for reason in reasons if isinstance(reason, str)
                    )
                else:
                    reasons_iterable = []
                for reason in reasons_iterable:
                    counters_by_reason[reason] = (
                        counters_by_reason.get(reason, 0) + event_count
                    )

        manual_events_payload["event_counters"] = {
            "total": sum(counters_by_event.values()),
            "by_event": counters_by_event,
            "by_reason": dict(sorted(counters_by_reason.items())),
        }

        return {
            "available": entity_id is not None,
            "state_available": state_available,
            "entity_id": entity_id,
            "object_id": object_id,
            "alias": definition.get("alias"),
            "description": definition.get("description"),
            "last_generated": _serialize_datetime(self._last_generation),
            "last_generated_age_seconds": last_generated_age,
            "last_generated_status": timestamp_issue,
            "last_triggered": _serialize_datetime(last_triggered),
            "last_triggered_age_seconds": last_triggered_age,
            "thresholds": thresholds,
            "fields": {
                key: {
                    "default": field_defaults.get(key),
                    "active": _active_value(key),
                }
                for key in field_defaults
            },
            "followup_script": {
                "default": field_defaults.get("followup_script"),
                "active": followup_active,
                "configured": bool(followup_active),
            },
            "statistics_entity_id": {
                "default": field_defaults.get("statistics_entity_id"),
                "active": _active_value("statistics_entity_id"),
            },
            "escalation_service": {
                "default": field_defaults.get("escalation_service"),
                "active": _active_value("escalation_service"),
            },
            "manual_events": manual_events_payload,
        }

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
