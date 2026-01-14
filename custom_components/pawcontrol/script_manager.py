"""Automatic Home Assistant script management for PawControl.

This module keeps the promise from the public documentation that PawControl
automatically provisions helper scripts for every configured dog.  It creates
notification workflows, reset helpers, and setup automation scripts directly in
Home Assistant's ``script`` domain so that users can trigger the documented
automation flows without manual YAML editing.
"""
from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from collections.abc import Collection
from collections.abc import Iterable
from collections.abc import Mapping
from collections.abc import MutableMapping
from collections.abc import Sequence
from contextlib import suppress
from datetime import datetime
from typing import Any
from typing import cast
from typing import Final
from typing import Literal
from typing import Protocol

from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN
from homeassistant.components.script import ScriptEntity
from homeassistant.components.script.config import SCRIPT_ENTITY_SCHEMA
from homeassistant.components.script.const import CONF_FIELDS
from homeassistant.components.script.const import CONF_TRACE
from homeassistant.const import CONF_ALIAS
from homeassistant.const import CONF_DEFAULT
from homeassistant.const import CONF_DESCRIPTION
from homeassistant.const import CONF_NAME
from homeassistant.const import CONF_SEQUENCE
from homeassistant.core import callback
from homeassistant.core import CALLBACK_TYPE
from homeassistant.core import Event
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .compat import ConfigEntry
from .compat import HomeAssistantError
from .const import CACHE_TIMESTAMP_FUTURE_THRESHOLD
from .const import CACHE_TIMESTAMP_STALE_THRESHOLD
from .const import CONF_DOG_ID
from .const import CONF_DOG_NAME
from .const import DEFAULT_MANUAL_BREAKER_EVENT
from .const import DEFAULT_MANUAL_CHECK_EVENT
from .const import DEFAULT_MANUAL_GUARD_EVENT
from .const import DEFAULT_RESILIENCE_BREAKER_THRESHOLD
from .const import DEFAULT_RESILIENCE_SKIP_THRESHOLD
from .const import DOMAIN
from .const import MANUAL_EVENT_SOURCE_CANONICAL
from .const import MODULE_NOTIFICATIONS
from .const import RESILIENCE_BREAKER_THRESHOLD_MAX
from .const import RESILIENCE_BREAKER_THRESHOLD_MIN
from .const import RESILIENCE_SKIP_THRESHOLD_MAX
from .const import RESILIENCE_SKIP_THRESHOLD_MIN
from .coordinator_support import CacheMonitorRegistrar
from .types import CacheDiagnosticsMetadata
from .types import CacheDiagnosticsSnapshot
from .types import ConfigEntryOptionsPayload
from .types import DogConfigData
from .types import ensure_dog_modules_mapping
from .types import JSONMutableMapping
from .types import JSONValue
from .types import ManualResilienceAutomationEntry
from .types import ManualResilienceEventRecord
from .types import ManualResilienceEventSelection
from .types import ManualResilienceEventSnapshot
from .types import ManualResilienceEventSource
from .types import ManualResilienceEventsTelemetry
from .types import ManualResilienceListenerMetadata
from .types import ManualResilienceOptionsSnapshot
from .types import ManualResiliencePreferenceKey
from .types import ManualResilienceSystemSettingsSnapshot
from .types import ResilienceEscalationSnapshot
from .types import ResilienceEscalationThresholds
from .types import ScriptManagerDogScripts
from .types import ScriptManagerSnapshot
from .types import ScriptManagerStats

_LOGGER = logging.getLogger(__name__)


slugify = getattr(slugify, 'slugify', slugify)

_RESILIENCE_BLUEPRINT_IDENTIFIER: Final[str] = 'resilience_escalation_followup'
_RESILIENCE_BLUEPRINT_DOMAIN: Final[str] = 'pawcontrol'


def _normalise_entry_slug(entry: ConfigEntry) -> str:
    """Return the slug used for integration-managed scripts."""

    raw_slug = slugify(getattr(entry, 'title', '') or entry.entry_id or DOMAIN)
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
        return 'future', age_seconds
    if delta > CACHE_TIMESTAMP_STALE_THRESHOLD:
        return 'stale', age_seconds
    return None, age_seconds


MANUAL_EVENT_KEYS: tuple[ManualResiliencePreferenceKey, ...] = (
    'manual_check_event',
    'manual_guard_event',
    'manual_breaker_event',
)


class _FieldDefaultProvider(Protocol):
    """Protocol for script field objects exposing ``default`` attributes."""

    default: JSONValue


type ScriptFieldEntry = Mapping[str, JSONValue] | _FieldDefaultProvider
type ScriptFieldDefinitions = Mapping[str, ScriptFieldEntry]


def _coerce_optional_int(value: object) -> int | None:
    """Return an ``int`` when ``value`` can be losslessly coerced."""

    if isinstance(value, bool):
        # ``bool`` subclasses ``int`` but should not participate in resilience
        # thresholds to avoid confusing ``True``/``False`` inputs.
        return int(value) if value else None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return int(candidate)
        except ValueError:
            return None
    return None


def _coerce_manual_history_size(value: object) -> int | None:
    """Validate manual history length candidates from config mappings."""

    candidate = _coerce_optional_int(value)
    if candidate is None:
        return None
    if not (_MANUAL_EVENT_HISTORY_MIN <= candidate <= _MANUAL_EVENT_HISTORY_MAX):
        return None
    return candidate


def _parse_manual_resilience_system_settings(
    value: object,
) -> ManualResilienceSystemSettingsSnapshot | None:
    """Normalise system-settings mappings into typed resilience payloads."""

    if not isinstance(value, Mapping):
        return None

    settings: ManualResilienceSystemSettingsSnapshot = {}

    for key in MANUAL_EVENT_KEYS:
        manual_event = _normalise_manual_event(value.get(key))
        if manual_event is not None:
            settings[key] = manual_event

    skip_threshold = _coerce_optional_int(
        value.get('resilience_skip_threshold'),
    )
    if skip_threshold is not None:
        settings['resilience_skip_threshold'] = skip_threshold

    breaker_threshold = _coerce_optional_int(
        value.get('resilience_breaker_threshold'),
    )
    if breaker_threshold is not None:
        settings['resilience_breaker_threshold'] = breaker_threshold

    return settings or None


def _parse_manual_resilience_options(
    value: object,
) -> ManualResilienceOptionsSnapshot:
    """Normalise config-entry options related to manual resilience flows."""

    options: ManualResilienceOptionsSnapshot = {}

    if not isinstance(value, Mapping):
        return options

    for key in MANUAL_EVENT_KEYS:
        manual_event = _normalise_manual_event(value.get(key))
        if manual_event is not None:
            options[key] = manual_event

    skip_threshold = _coerce_optional_int(
        value.get('resilience_skip_threshold'),
    )
    if skip_threshold is not None:
        options['resilience_skip_threshold'] = skip_threshold

    breaker_threshold = _coerce_optional_int(
        value.get('resilience_breaker_threshold'),
    )
    if breaker_threshold is not None:
        options['resilience_breaker_threshold'] = breaker_threshold

    history_size = _coerce_manual_history_size(
        value.get('manual_event_history_size'),
    )
    if history_size is not None:
        options['manual_event_history_size'] = history_size

    system_settings = _parse_manual_resilience_system_settings(
        value.get('system_settings'),
    )
    if system_settings is not None:
        options['system_settings'] = system_settings

    return options


def _parse_event_selection(
    value: Mapping[str, object] | None,
) -> ManualResilienceEventSelection:
    """Normalise manual event selections used for automation updates."""

    selection: ManualResilienceEventSelection = {}
    if value is None:
        return selection

    for key in MANUAL_EVENT_KEYS:
        manual_event = _normalise_manual_event(value.get(key))
        if key in value:
            selection[key] = manual_event

    return selection


def _coerce_threshold(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Return a clamped integer threshold for resilience configuration."""

    candidate = _coerce_optional_int(value)
    if candidate is None:
        return default

    if candidate < minimum:
        return minimum
    if candidate > maximum:
        return maximum
    return candidate


def _extract_field_int(fields: ScriptFieldDefinitions | None, key: str) -> int | None:
    """Return the integer default stored under ``key`` in ``fields``."""

    if not isinstance(fields, Mapping):
        return None

    field = fields.get(key)
    candidate: JSONValue | None
    if isinstance(field, Mapping):
        candidate = field.get('default')
    else:
        candidate = getattr(field, 'default', None)

    if candidate is None:
        return None

    return _coerce_optional_int(candidate)


def resolve_resilience_script_thresholds(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> tuple[int | None, int | None]:
    """Return skip and breaker thresholds from the generated script entity."""

    states = getattr(hass, 'states', None)
    if states is None or not hasattr(states, 'get'):
        return None, None

    entity_id = _resolve_resilience_entity_id(entry)
    state = states.get(entity_id)
    if state is None:
        return None, None

    attributes = getattr(state, 'attributes', {})
    raw_fields = (
        attributes.get('fields')
        if isinstance(
            attributes,
            Mapping,
        )
        else None
    )
    fields: ScriptFieldDefinitions | None
    if isinstance(raw_fields, Mapping):
        fields = cast(ScriptFieldDefinitions, raw_fields)
    else:
        fields = None

    skip = _extract_field_int(fields, 'skip_threshold')
    breaker = _extract_field_int(fields, 'breaker_threshold')
    return skip, breaker


def _is_resilience_blueprint(use_blueprint: Mapping[str, object] | None) -> bool:
    """Return ``True`` when ``use_blueprint`` targets the resilience blueprint."""

    if not isinstance(use_blueprint, Mapping):
        return False

    identifier = str(
        use_blueprint.get('blueprint_id')
        or use_blueprint.get('path')
        or use_blueprint.get('id')
        or '',
    )
    if not identifier:
        return False

    normalized = identifier.replace('\\', '/').lower()
    expected_suffix = (
        f"{_RESILIENCE_BLUEPRINT_DOMAIN}/{_RESILIENCE_BLUEPRINT_IDENTIFIER}.yaml"
    )
    return normalized.endswith(expected_suffix)


def _normalise_manual_event(value: object) -> str | None:
    """Return a stripped event string when ``value`` contains text."""

    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate or None


def _serialise_event_data(data: Mapping[str, object]) -> JSONMutableMapping:
    """Return a JSON-friendly copy of ``data``."""

    serialised: JSONMutableMapping = {}
    for key, value in data.items():
        key_text = str(key)
        if isinstance(value, str | int | float | bool) or value is None:
            serialised[key_text] = value
            continue
        if isinstance(value, Mapping):
            serialised[key_text] = _serialise_event_data(value)
            continue
        if isinstance(value, Sequence) and not isinstance(
            value,
            str | bytes | bytearray,
        ):
            serialised[key_text] = [
                item
                if isinstance(item, str | int | float | bool) or item is None
                else repr(item)
                for item in value
            ]
            continue
        serialised[key_text] = repr(value)
    return serialised


class _ScriptManagerCacheMonitor:
    """Expose script manager state for diagnostics snapshots."""

    __slots__ = ('_manager',)

    def __init__(self, manager: PawControlScriptManager) -> None:
        self._manager = manager

    def _build_payload(
        self,
    ) -> tuple[ScriptManagerStats, ScriptManagerSnapshot, CacheDiagnosticsMetadata]:
        manager = self._manager
        created_entities = cast(
            Iterable[str],
            getattr(manager, '_created_entities', set()),
        )
        dog_scripts = cast(
            dict[str, Iterable[str]],
            getattr(manager, '_dog_scripts', {}),
        )
        entry_scripts = cast(
            Iterable[str],
            getattr(
                manager,
                '_entry_scripts',
                [],
            ),
        )
        last_generation = cast(
            datetime | None,
            getattr(manager, '_last_generation', None),
        )

        created_list = sorted(
            entity for entity in created_entities if isinstance(entity, str)
        )
        per_dog: dict[str, ScriptManagerDogScripts] = {}
        for dog_id, scripts in dog_scripts.items():
            if not isinstance(dog_id, str):
                continue
            script_list = [
                entity for entity in scripts if isinstance(entity, str)
            ]
            per_dog[dog_id] = {
                'count': len(script_list),
                'scripts': script_list,
            }
        entry_list = [
            entity for entity in entry_scripts if isinstance(entity, str)
        ]

        stats: ScriptManagerStats = {
            'scripts': len(created_list),
            'dogs': len(per_dog),
        }
        if entry_list:
            stats['entry_scripts'] = len(entry_list)

        timestamp_issue, age_seconds = _classify_timestamp(last_generation)
        if age_seconds is not None:
            stats['last_generated_age_seconds'] = age_seconds

        snapshot: ScriptManagerSnapshot = {
            'created_entities': created_list,
            'per_dog': per_dog,
            'last_generated': _serialize_datetime(last_generation),
        }
        if entry_list:
            snapshot['entry_scripts'] = entry_list

        per_dog_payload = cast(JSONMutableMapping, per_dog)
        diagnostics: CacheDiagnosticsMetadata = {
            'per_dog': per_dog_payload,
            'created_entities': created_list,
            'last_generated': _serialize_datetime(last_generation),
        }
        if entry_list:
            diagnostics['entry_scripts'] = entry_list

        if age_seconds is not None:
            diagnostics['manager_last_generated_age_seconds'] = age_seconds

        if timestamp_issue is not None:
            diagnostics['timestamp_anomalies'] = {'manager': timestamp_issue}

        return stats, snapshot, diagnostics

    def coordinator_snapshot(self) -> CacheDiagnosticsSnapshot:
        stats, snapshot, diagnostics = self._build_payload()
        return CacheDiagnosticsSnapshot(
            stats=cast(JSONMutableMapping, dict(stats)),
            snapshot=cast(JSONMutableMapping, dict(snapshot)),
            diagnostics=diagnostics,
        )

    def get_stats(self) -> JSONMutableMapping:
        stats, _snapshot, _diagnostics = self._build_payload()
        return cast(JSONMutableMapping, dict(stats))

    def get_diagnostics(self) -> CacheDiagnosticsMetadata:
        _stats, _snapshot, diagnostics = self._build_payload()
        return diagnostics


_SCRIPT_ENTITY_PREFIX: Final[str] = f"{SCRIPT_DOMAIN}."

_DEFAULT_MANUAL_EVENT_HISTORY_SIZE: Final[int] = 5
_MANUAL_EVENT_HISTORY_MIN: Final[int] = 1
_MANUAL_EVENT_HISTORY_MAX: Final[int] = 50


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
        self._resilience_escalation_definition: JSONMutableMapping | None = None
        self._manual_event_unsubs: dict[str, Callable[[], None]] = {}
        self._manual_event_reasons: dict[str, set[str]] = {}
        self._manual_event_sources: dict[str, ManualResilienceEventSource] = {}
        self._manual_event_counters: dict[str, int] = {}
        self._manual_event_unsubscribes: dict[str, CALLBACK_TYPE] = {}
        self._manual_history_maxlen = self._resolve_manual_history_size()
        self._manual_event_history: deque[ManualResilienceEventRecord] = deque(
            maxlen=self._manual_history_maxlen,
        )
        self._last_manual_event: ManualResilienceEventRecord | None = None
        self._entry_slug = _normalise_entry_slug(entry)
        title = getattr(entry, 'title', None)
        self._entry_title = (
            title.strip() if isinstance(title, str) and title.strip() else 'PawControl'
        )
        self._restore_manual_event_history_from_runtime()
        if self._manual_event_history:
            self._last_manual_event = cast(
                ManualResilienceEventRecord,
                dict(
                    self._manual_event_history[-1],
                ),
            )
        self._sync_manual_history_to_runtime()

    async def async_initialize(self) -> None:
        """Reset internal tracking structures prior to script generation."""

        self._created_entities.clear()
        self._dog_scripts.clear()
        self._entry_scripts.clear()
        self._update_manual_history_size()
        for unsub in list(self._manual_event_unsubs.values()):
            unsub()
        self._manual_event_unsubs.clear()
        self._manual_event_reasons.clear()
        self._manual_event_sources.clear()
        self._manual_event_counters.clear()
        if self._manual_event_history:
            self._last_manual_event = cast(
                ManualResilienceEventRecord,
                dict(
                    self._manual_event_history[-1],
                ),
            )
        else:
            self._last_manual_event = None
        self._refresh_manual_event_listeners()
        self._sync_manual_history_to_runtime()
        _LOGGER.debug(
            'Script manager initialised for entry %s',
            self._entry.entry_id,
        )

    def register_cache_monitors(
        self,
        registrar: CacheMonitorRegistrar,
        *,
        prefix: str = 'script_manager',
    ) -> None:
        """Expose script diagnostics through the shared cache monitor registry."""

        if registrar is None:
            raise ValueError('registrar is required')

        _LOGGER.debug(
            'Registering script manager cache monitor with prefix %s',
            prefix,
        )
        registrar.register_cache_monitor(
            f"{prefix}_cache",
            _ScriptManagerCacheMonitor(self),
        )

    def attach_runtime_manual_history(self, runtime: object) -> None:
        """Attach the current manual event history to ``runtime``."""

        if runtime is None:
            return

        manual_history = getattr(runtime, 'manual_event_history', None)
        if isinstance(manual_history, deque):
            manual_history.clear()
            manual_history.extend(self._manual_event_history)
            self._manual_event_history = manual_history
            self._update_manual_history_size()
        else:
            with suppress(AttributeError):
                runtime_any = cast(Any, runtime)
                runtime_any.manual_event_history = self._manual_event_history

    def sync_manual_event_history(self) -> None:
        """Persist the manual event history back to runtime storage."""

        self._sync_manual_history_to_runtime()

    def _resolve_manual_history_size(self) -> int:
        """Determine the configured manual event history length."""

        raw_options = getattr(self._entry, 'options', None)
        options = _parse_manual_resilience_options(raw_options)

        configured = options.get('manual_event_history_size')
        if configured is not None:
            return configured

        raw_system_settings = None
        if isinstance(raw_options, Mapping):
            raw_system_settings = raw_options.get('system_settings')

        raw_data = getattr(self._entry, 'data', None)

        for mapping in (raw_system_settings, raw_options, raw_data):
            if not isinstance(mapping, Mapping):
                continue
            candidate = _coerce_manual_history_size(
                mapping.get('manual_event_history_size'),
            )
            if candidate is not None:
                return candidate

        return _DEFAULT_MANUAL_EVENT_HISTORY_SIZE

    def _update_manual_history_size(self) -> None:
        """Resize the manual event history deque when configuration changes."""

        desired = self._resolve_manual_history_size()
        current = (
            self._manual_event_history.maxlen or _DEFAULT_MANUAL_EVENT_HISTORY_SIZE
        )
        if desired == current:
            self._manual_history_maxlen = desired
            return

        self._manual_event_history = deque(
            self._manual_event_history,
            maxlen=desired,
        )
        self._manual_history_maxlen = desired
        self._sync_manual_history_to_runtime()

    def export_manual_event_history(self) -> list[ManualResilienceEventRecord]:
        """Return a copy of the recorded manual event history."""

        return [
            cast(ManualResilienceEventRecord, dict(record))
            for record in self._manual_event_history
        ]

    def _resolve_resilience_thresholds(self) -> tuple[int, int]:
        """Return configured guard skip and breaker thresholds."""

        raw_options = getattr(self._entry, 'options', None)
        options = _parse_manual_resilience_options(raw_options)
        skip_threshold = DEFAULT_RESILIENCE_SKIP_THRESHOLD
        breaker_threshold = DEFAULT_RESILIENCE_BREAKER_THRESHOLD

        def _merge_candidate(
            candidate: int | None,
            *,
            default: int,
            minimum: int,
            maximum: int,
        ) -> int:
            if candidate is None:
                return default
            return _coerce_threshold(
                candidate,
                default=default,
                minimum=minimum,
                maximum=maximum,
            )

        system_settings = options.get('system_settings')
        if system_settings is not None:
            skip_threshold = _merge_candidate(
                system_settings.get('resilience_skip_threshold'),
                default=skip_threshold,
                minimum=RESILIENCE_SKIP_THRESHOLD_MIN,
                maximum=RESILIENCE_SKIP_THRESHOLD_MAX,
            )
            breaker_threshold = _merge_candidate(
                system_settings.get('resilience_breaker_threshold'),
                default=breaker_threshold,
                minimum=RESILIENCE_BREAKER_THRESHOLD_MIN,
                maximum=RESILIENCE_BREAKER_THRESHOLD_MAX,
            )

        skip_threshold = _merge_candidate(
            options.get('resilience_skip_threshold'),
            default=skip_threshold,
            minimum=RESILIENCE_SKIP_THRESHOLD_MIN,
            maximum=RESILIENCE_SKIP_THRESHOLD_MAX,
        )
        breaker_threshold = _merge_candidate(
            options.get('resilience_breaker_threshold'),
            default=breaker_threshold,
            minimum=RESILIENCE_BREAKER_THRESHOLD_MIN,
            maximum=RESILIENCE_BREAKER_THRESHOLD_MAX,
        )

        script_skip, script_breaker = resolve_resilience_script_thresholds(
            self._hass,
            self._entry,
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

    def ensure_resilience_threshold_options(
        self,
    ) -> ConfigEntryOptionsPayload | None:
        """Return updated options when legacy script defaults need migration."""

        raw_options = getattr(self._entry, 'options', None)
        options = _parse_manual_resilience_options(raw_options)
        system_settings = options.get('system_settings')
        script_skip, script_breaker = resolve_resilience_script_thresholds(
            self._hass,
            self._entry,
        )

        if not self._should_migrate_resilience_thresholds(
            script_skip,
            script_breaker,
            system_settings,
        ):
            return None

        migrated_system = self._build_resilience_system_settings(
            system_settings,
            script_skip=script_skip,
            script_breaker=script_breaker,
        )

        if migrated_system is None:
            return None

        options_mapping: Mapping[str, JSONValue] = (
            raw_options if isinstance(raw_options, Mapping) else {}
        )

        return self._apply_resilience_system_settings(options_mapping, migrated_system)

    @staticmethod
    def _should_migrate_resilience_thresholds(
        script_skip: int | None,
        script_breaker: int | None,
        system_settings: ManualResilienceSystemSettingsSnapshot | None,
    ) -> bool:
        """Return ``True`` when script defaults should populate options."""

        if script_skip is None and script_breaker is None:
            return False

        if system_settings is None:
            return True

        missing_skip = 'resilience_skip_threshold' not in system_settings
        missing_breaker = 'resilience_breaker_threshold' not in system_settings

        return missing_skip or missing_breaker

    @staticmethod
    def _build_resilience_system_settings(
        system_settings: ManualResilienceSystemSettingsSnapshot | None,
        *,
        script_skip: int | None,
        script_breaker: int | None,
    ) -> ManualResilienceSystemSettingsSnapshot | None:
        """Return a system settings payload with migrated thresholds."""

        original: ManualResilienceSystemSettingsSnapshot
        original = dict(system_settings) if system_settings is not None else {}
        updated: ManualResilienceSystemSettingsSnapshot = {}
        if system_settings is not None:
            if 'manual_check_event' in system_settings:
                updated['manual_check_event'] = system_settings['manual_check_event']
            if 'manual_guard_event' in system_settings:
                updated['manual_guard_event'] = system_settings['manual_guard_event']
            if 'manual_breaker_event' in system_settings:
                updated['manual_breaker_event'] = system_settings[
                    'manual_breaker_event'
                ]
            if 'resilience_skip_threshold' in system_settings:
                updated['resilience_skip_threshold'] = system_settings[
                    'resilience_skip_threshold'
                ]
            if 'resilience_breaker_threshold' in system_settings:
                updated['resilience_breaker_threshold'] = system_settings[
                    'resilience_breaker_threshold'
                ]

        if script_skip is not None and 'resilience_skip_threshold' not in updated:
            updated['resilience_skip_threshold'] = _coerce_threshold(
                script_skip,
                default=DEFAULT_RESILIENCE_SKIP_THRESHOLD,
                minimum=RESILIENCE_SKIP_THRESHOLD_MIN,
                maximum=RESILIENCE_SKIP_THRESHOLD_MAX,
            )

        if script_breaker is not None and 'resilience_breaker_threshold' not in updated:
            updated['resilience_breaker_threshold'] = _coerce_threshold(
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
        options: Mapping[str, JSONValue],
        system_settings: ManualResilienceSystemSettingsSnapshot,
    ) -> ConfigEntryOptionsPayload:
        """Return updated options including migrated system settings."""

        updated_options = cast(ConfigEntryOptionsPayload, dict(options))
        updated_options['system_settings'] = dict(system_settings)

        for key in ('resilience_skip_threshold', 'resilience_breaker_threshold'):
            if key not in updated_options and key in system_settings:
                updated_options[key] = system_settings[key]

        return updated_options

    def _resolve_manual_resilience_events(self) -> ManualResilienceEventsTelemetry:
        """Return configured manual escalation events from blueprint automations."""

        manager = getattr(self._hass, 'config_entries', None)
        entries_callable = getattr(manager, 'async_entries', None)
        if not callable(entries_callable):
            return {
                'available': False,
                'automations': [],
                'configured_guard_events': [],
                'configured_breaker_events': [],
                'configured_check_events': [],
                'system_guard_event': None,
                'system_breaker_event': None,
                'listener_events': {},
                'listener_sources': {},
                'listener_metadata': {},
                'event_history': [],
                'last_event': None,
                'last_trigger': None,
                'event_counters': {'total': 0, 'by_event': {}, 'by_reason': {}},
                'active_listeners': [],
            }

        raw_options = getattr(self._entry, 'options', None)
        options = _parse_manual_resilience_options(raw_options)
        system_guard = options.get('manual_guard_event')
        system_breaker = options.get('manual_breaker_event')

        system_settings = options.get('system_settings')
        if system_settings is not None:
            guard_override = system_settings.get('manual_guard_event')
            breaker_override = system_settings.get('manual_breaker_event')
            if guard_override is not None:
                system_guard = guard_override
            if breaker_override is not None:
                system_breaker = breaker_override

        automations: list[ManualResilienceAutomationEntry] = []
        guard_events: set[str] = set()
        breaker_events: set[str] = set()
        check_events: set[str] = set()
        listener_reasons: dict[str, set[str]] = {}
        listener_sources: dict[str, set[str]] = {}
        canonical_sources: dict[str, set[str]] = {}

        def _register_listener(event: str | None, reason: str, source: str) -> None:
            if not event:
                return
            listener_reasons.setdefault(event, set()).add(reason)
            listener_sources.setdefault(event, set()).add(source)
            canonical = MANUAL_EVENT_SOURCE_CANONICAL.get(source, source)
            canonical_sources.setdefault(event, set()).add(canonical)

        try:
            automation_entries = entries_callable('automation')
        except (AttributeError, TypeError, KeyError):
            automation_entries = []

        _register_listener(system_guard, 'guard', 'system_options')
        _register_listener(system_breaker, 'breaker', 'system_options')

        for entry in automation_entries or []:
            entry_data = getattr(entry, 'data', {})
            if not isinstance(entry_data, Mapping):
                continue

            use_blueprint = entry_data.get('use_blueprint')
            if not _is_resilience_blueprint(use_blueprint):
                continue

            blueprint = cast(Mapping[str, object], use_blueprint)

            inputs_key = 'input' if 'input' in blueprint else 'inputs'
            existing_inputs = blueprint.get(inputs_key)
            inputs_mapping = (
                existing_inputs
                if isinstance(
                    existing_inputs,
                    Mapping,
                )
                else None
            )
            inputs_selection = _parse_event_selection(inputs_mapping)
            manual_guard = inputs_selection.get('manual_guard_event')
            manual_breaker = inputs_selection.get('manual_breaker_event')
            manual_check = inputs_selection.get('manual_check_event')

            if manual_guard:
                guard_events.add(manual_guard)
                _register_listener(manual_guard, 'guard', 'blueprint')
            if manual_breaker:
                breaker_events.add(manual_breaker)
                _register_listener(manual_breaker, 'breaker', 'blueprint')
            if manual_check:
                check_events.add(manual_check)
                _register_listener(manual_check, 'check', 'blueprint')

            entry_id = getattr(entry, 'entry_id', None)
            config_entry_id = entry_id if isinstance(entry_id, str) else None
            title_value = getattr(entry, 'title', None)
            title = title_value if isinstance(title_value, str) else None

            automation_entry: ManualResilienceAutomationEntry = {
                'config_entry_id': config_entry_id,
                'title': title,
                'configured_guard': bool(manual_guard),
                'configured_breaker': bool(manual_breaker),
                'configured_check': bool(manual_check),
            }
            if manual_guard:
                automation_entry['manual_guard_event'] = manual_guard
            if manual_breaker:
                automation_entry['manual_breaker_event'] = manual_breaker
            if manual_check:
                automation_entry['manual_check_event'] = manual_check

            automations.append(automation_entry)

        available = bool(automations)
        if system_guard is not None or system_breaker is not None:
            available = True

        if isinstance(raw_options, Mapping):
            for key in (
                'manual_check_event',
                'manual_guard_event',
                'manual_breaker_event',
            ):
                option_value = _normalise_manual_event(raw_options.get(key))
                if option_value:
                    canonical_sources.setdefault(
                        option_value,
                        set(),
                    ).add('options')

            system_settings_map = raw_options.get('system_settings')
            if isinstance(system_settings_map, Mapping):
                for key in (
                    'manual_check_event',
                    'manual_guard_event',
                    'manual_breaker_event',
                ):
                    option_value = _normalise_manual_event(
                        system_settings_map.get(key),
                    )
                    if option_value:
                        canonical_sources.setdefault(option_value, set()).add(
                            'system_settings',
                        )

        entry_data = getattr(self._entry, 'data', {})
        if isinstance(entry_data, Mapping):
            for key in (
                'manual_check_event',
                'manual_guard_event',
                'manual_breaker_event',
            ):
                data_value = _normalise_manual_event(entry_data.get(key))
                if data_value:
                    canonical_sources.setdefault(
                        data_value,
                        set(),
                    ).add('config_entry')

        for default_value in (
            DEFAULT_MANUAL_CHECK_EVENT,
            DEFAULT_MANUAL_GUARD_EVENT,
            DEFAULT_MANUAL_BREAKER_EVENT,
        ):
            canonical_sources.setdefault(default_value, set()).add('default')

        def _primary_source(source_set: set[str]) -> str | None:
            for candidate in (
                'system_settings',
                'options',
                'config_entry',
                'blueprint',
                'default',
            ):
                if candidate in source_set:
                    return candidate
            if 'disabled' in source_set:
                return 'disabled'
            if source_set:
                return sorted(source_set)[0]
            return None

        return {
            'available': available,
            'automations': automations,
            'configured_guard_events': sorted(guard_events),
            'configured_breaker_events': sorted(breaker_events),
            'configured_check_events': sorted(check_events),
            'system_guard_event': system_guard,
            'system_breaker_event': system_breaker,
            'listener_events': {
                event: sorted(reasons) for event, reasons in listener_reasons.items()
            },
            'listener_sources': {
                event: sorted(sources) for event, sources in listener_sources.items()
            },
            'listener_metadata': {
                event: {
                    'sources': sorted(source_set),
                    'primary_source': _primary_source(source_set),
                }
                for event, source_set in canonical_sources.items()
            },
            'event_history': [],
            'last_event': None,
            'last_trigger': None,
            'event_counters': {'total': 0, 'by_event': {}, 'by_reason': {}},
            'active_listeners': [],
        }

    def _manual_event_preferences(
        self,
    ) -> dict[ManualResiliencePreferenceKey, str | None]:
        """Return manual event preferences derived from config entry options."""

        options = getattr(self._entry, 'options', {})
        preferences: dict[ManualResiliencePreferenceKey, str | None] = {
            'manual_check_event': DEFAULT_MANUAL_CHECK_EVENT,
            'manual_guard_event': DEFAULT_MANUAL_GUARD_EVENT,
            'manual_breaker_event': DEFAULT_MANUAL_BREAKER_EVENT,
        }

        if not isinstance(options, Mapping):
            return preferences

        system_settings = options.get('system_settings')
        if not isinstance(system_settings, Mapping):
            return preferences

        preference_keys: tuple[ManualResiliencePreferenceKey, ...] = (
            'manual_check_event',
            'manual_guard_event',
            'manual_breaker_event',
        )
        for key in preference_keys:
            if key not in system_settings:
                continue
            manual_value = _normalise_manual_event(system_settings.get(key))
            if manual_value is None:
                preferences[key] = None
            else:
                preferences[key] = manual_value

        return preferences

    def _manual_event_source_mapping(self) -> dict[str, ManualResilienceEventSource]:
        """Return metadata describing tracked manual resilience event types."""

        sources: dict[str, ManualResilienceEventSource] = {}
        preferences = self._manual_event_preferences()

        def _category_from_preference(
            key: ManualResiliencePreferenceKey,
        ) -> Literal['check', 'guard', 'breaker'] | None:
            if key == 'manual_check_event':
                return 'check'
            if key == 'manual_guard_event':
                return 'guard'
            if key == 'manual_breaker_event':
                return 'breaker'
            return None

        for preference_key, event_type in preferences.items():
            if not event_type:
                continue
            sources[event_type] = {
                'preference_key': preference_key,
            }
            category = _category_from_preference(preference_key)
            if category:
                sources[event_type]['configured_role'] = category

        manual_events = self._resolve_manual_resilience_events()
        listener_metadata = manual_events.get('listener_metadata')
        canonical_lookup: dict[str, ManualResilienceListenerMetadata] = {}
        if isinstance(listener_metadata, Mapping):
            for event, metadata in listener_metadata.items():
                if not isinstance(event, str) or not isinstance(metadata, Mapping):
                    continue
                raw_sources = metadata.get('sources')
                canonical_tags: list[str] = []
                if isinstance(raw_sources, Sequence) and not isinstance(
                    raw_sources,
                    str | bytes,
                ):
                    canonical_tags = [
                        str(source)
                        for source in raw_sources
                        if isinstance(source, str) and source
                    ]
                canonical_tags = list(dict.fromkeys(canonical_tags))
                primary_source = metadata.get('primary_source')
                if isinstance(primary_source, str) and primary_source:
                    canonical_tags = [
                        primary_source,
                        *[tag for tag in canonical_tags if tag != primary_source],
                    ]
                lookup_entry: ManualResilienceListenerMetadata = {}
                if canonical_tags:
                    lookup_entry['source_tags'] = canonical_tags
                if isinstance(primary_source, str) and primary_source:
                    lookup_entry['primary_source'] = primary_source
                canonical_lookup[event] = lookup_entry

        for role, key in (
            ('guard', 'configured_guard_events'),
            ('breaker', 'configured_breaker_events'),
            ('check', 'configured_check_events'),
        ):
            event_list = manual_events.get(key)
            if not isinstance(event_list, Sequence):
                continue
            for event_type in event_list:
                if not isinstance(event_type, str) or not event_type:
                    continue
                entry = sources.setdefault(event_type, {})
                entry.setdefault(
                    'configured_role',
                    cast(Literal['check', 'guard', 'breaker'], role),
                )
                metadata_entry = canonical_lookup.get(event_type)
                if metadata_entry:
                    tags = metadata_entry.get('source_tags')
                    if isinstance(tags, list):
                        entry['source_tags'] = list(dict.fromkeys(tags))
                    primary = metadata_entry.get('primary_source')
                    if isinstance(primary, str) and primary:
                        entry['primary_source'] = primary

        for event_type, metadata_entry in canonical_lookup.items():
            existing_entry = sources.get(event_type)
            if existing_entry is None:
                continue
            tags = metadata_entry.get('source_tags')
            if isinstance(tags, list):
                existing_entry['source_tags'] = list(dict.fromkeys(tags))
            primary = metadata_entry.get('primary_source')
            if isinstance(primary, str) and primary:
                existing_entry['primary_source'] = primary

        listener_sources = manual_events.get('listener_sources')
        if isinstance(listener_sources, Mapping):
            for event_type, raw_sources in listener_sources.items():
                if not isinstance(raw_sources, Sequence) or isinstance(
                    raw_sources,
                    str | bytes | bytearray,
                ):
                    continue
                normalised_sources = tuple(
                    str(source)
                    for source in raw_sources
                    if isinstance(source, str) and source
                )
                if normalised_sources:
                    entry = sources.setdefault(event_type, {})
                    entry['listener_sources'] = normalised_sources

        return sources

    def _refresh_manual_event_listeners(self) -> None:
        """Subscribe to configured manual escalation events."""

        hass = self._hass
        bus = getattr(hass, 'bus', None)
        async_listen = getattr(bus, 'async_listen', None)
        if not callable(async_listen):
            return

        sources = self._manual_event_source_mapping()
        desired_events = set(sources)

        current_events = set(self._manual_event_unsubscribes)
        for event_type in current_events - desired_events:
            unsub = self._manual_event_unsubscribes.pop(event_type, None)
            if unsub:
                unsub()
            self._manual_event_sources.pop(event_type, None)

        for event_type in desired_events:
            if event_type in self._manual_event_unsubscribes:
                self._manual_event_sources[event_type] = sources[event_type]
                continue

            unsubscribe = async_listen(event_type, self._handle_manual_event)
            if unsubscribe is None:
                continue
            self._manual_event_unsubscribes[event_type] = unsubscribe
            self._manual_event_sources[event_type] = sources[event_type]

    def _unsubscribe_manual_event_listeners(self) -> None:
        """Detach manual escalation event listeners."""

        while self._manual_event_unsubscribes:
            event_type, unsubscribe = self._manual_event_unsubscribes.popitem()
            try:
                unsubscribe()
            except Exception:  # pragma: no cover - defensive cleanup
                _LOGGER.debug(
                    'Error unsubscribing manual listener for %s',
                    event_type,
                )
        self._manual_event_sources.clear()

    def _coerce_manual_event_record(
        self,
        value: object,
    ) -> ManualResilienceEventRecord | None:
        """Normalise ``value`` into a manual event record when possible."""

        if not isinstance(value, Mapping):
            return None

        record: ManualResilienceEventRecord = {}

        event_type = value.get('event_type')
        if isinstance(event_type, str) and event_type:
            record['event_type'] = event_type

        preference_key = value.get(
            'preference_key',
        ) or value.get('matched_preference')
        if isinstance(preference_key, str) and preference_key in {
            'manual_check_event',
            'manual_guard_event',
            'manual_breaker_event',
        }:
            record['preference_key'] = cast(
                ManualResiliencePreferenceKey,
                preference_key,
            )

        configured_role = value.get('configured_role') or value.get('category')
        if isinstance(configured_role, str) and configured_role in {
            'check',
            'guard',
            'breaker',
        }:
            record['configured_role'] = cast(
                Literal['check', 'guard', 'breaker'],
                configured_role,
            )

        def _normalise_datetime(value: object) -> datetime | None:
            if isinstance(value, datetime):
                return dt_util.as_utc(value)
            if isinstance(value, str):
                parsed = dt_util.parse_datetime(value)
                if parsed is not None:
                    return dt_util.as_utc(parsed)
            return None

        fired_at = _normalise_datetime(value.get('time_fired'))
        if fired_at is not None:
            record['time_fired'] = fired_at

        received_at = _normalise_datetime(value.get('received_at'))
        if received_at is not None:
            record['received_at'] = received_at

        context_id = value.get('context_id')
        if isinstance(context_id, str) and context_id:
            record['context_id'] = context_id

        user_id = value.get('user_id')
        if isinstance(user_id, str) and user_id:
            record['user_id'] = user_id

        origin = value.get('origin')
        if isinstance(origin, str) and origin:
            record['origin'] = origin

        raw_data = value.get('data')
        if isinstance(raw_data, Mapping):
            record['data'] = _serialise_event_data(raw_data)
        elif raw_data is None or isinstance(raw_data, dict):
            record['data'] = cast(JSONMutableMapping | None, raw_data)

        raw_sources = value.get('sources')
        if isinstance(raw_sources, Sequence) and not isinstance(
            raw_sources,
            str | bytes | bytearray,
        ):
            sources = tuple(
                str(source)
                for source in raw_sources
                if isinstance(source, str) and source
            )
            if sources:
                record['sources'] = sources

        return record

    def _restore_manual_event_history_from_runtime(self) -> None:
        """Restore manual event history from ``ConfigEntry.runtime_data``."""

        runtime = getattr(self._entry, 'runtime_data', None)

        if isinstance(runtime, Mapping):
            candidates: object = runtime.get('manual_event_history')
        else:
            candidates = getattr(runtime, 'manual_event_history', None)

        if candidates is None:
            store = self._hass.data.get(DOMAIN)
            if isinstance(store, Mapping):
                payload = store.get(self._entry.entry_id)
                if isinstance(payload, Mapping):
                    candidates = payload.get('manual_event_history')
                    if candidates is not None and isinstance(store, MutableMapping):
                        if isinstance(payload, MutableMapping):
                            payload.pop('manual_event_history', None)
                            if not payload:
                                store.pop(self._entry.entry_id, None)
                        else:
                            store.pop(self._entry.entry_id, None)

        if not isinstance(candidates, Sequence):
            return

        for value in candidates:
            record = self._coerce_manual_event_record(value)
            if record is not None:
                self._manual_event_history.append(record)

    def _sync_manual_history_to_runtime(self) -> None:
        """Synchronise the manual event history back to runtime storage."""

        runtime = getattr(self._entry, 'runtime_data', None)
        if runtime is None:
            return

        if isinstance(runtime, MutableMapping):
            runtime['manual_event_history'] = self.export_manual_event_history()
            return

        manual_history = getattr(runtime, 'manual_event_history', None)
        if isinstance(manual_history, deque):
            if manual_history is not self._manual_event_history:
                manual_history.clear()
                manual_history.extend(self._manual_event_history)
                self._manual_event_history = manual_history
            return

        with suppress(AttributeError):
            runtime_any = cast(Any, runtime)
            runtime_any.manual_event_history = self._manual_event_history

    def _serialise_manual_event_record(
        self,
        record: ManualResilienceEventRecord | Mapping[str, object] | None,
        *,
        recorded_at: datetime | str | None = None,
    ) -> ManualResilienceEventSnapshot | None:
        """Serialise ``record`` into a diagnostics-friendly snapshot."""

        if not isinstance(record, Mapping):
            return None

        fired_at = record.get('time_fired')
        fired_dt = (
            dt_util.as_utc(fired_at)
            if isinstance(
                fired_at,
                datetime,
            )
            else None
        )
        fired_iso = _serialize_datetime(fired_dt)
        fired_age: int | None = None
        if fired_dt is not None:
            fired_age = int((dt_util.utcnow() - fired_dt).total_seconds())

        received_at = record.get('received_at')
        received_dt = (
            dt_util.as_utc(received_at)
            if isinstance(
                received_at,
                datetime,
            )
            else None
        )
        received_iso = _serialize_datetime(received_dt)
        received_age: int | None = None
        if received_dt is not None:
            received_age = int(
                (dt_util.utcnow() - received_dt).total_seconds(),
            )

        configured_role = record.get('configured_role')
        category: Literal['check', 'guard', 'breaker', 'unknown']
        if isinstance(configured_role, str) and configured_role in {
            'check',
            'guard',
            'breaker',
        }:
            category = cast(
                Literal['check', 'guard', 'breaker'],
                configured_role,
            )
        else:
            category = 'unknown'

        raw_sources = record.get('sources')
        if isinstance(raw_sources, Sequence) and not isinstance(
            raw_sources,
            str | bytes | bytearray,
        ):
            sources_iter = [
                str(source)
                for source in raw_sources
                if isinstance(source, str) and source
            ]
            sources_list: ManualEventSourceList | None = (
                ManualEventSourceList(sources_iter) if sources_iter else None
            )
        else:
            sources_list = None

        if recorded_at is not None:
            if isinstance(recorded_at, datetime):
                recorded_dt = dt_util.as_utc(recorded_at)
            elif isinstance(recorded_at, str):
                parsed_recorded = dt_util.parse_datetime(recorded_at)
                recorded_dt = (
                    dt_util.as_utc(
                        parsed_recorded,
                    )
                    if parsed_recorded
                    else None
                )
            else:
                recorded_dt = None
        else:
            raw_recorded = record.get('recorded_at')
            if isinstance(raw_recorded, datetime):
                recorded_dt = dt_util.as_utc(raw_recorded)
            elif isinstance(raw_recorded, str):
                parsed_recorded = dt_util.parse_datetime(raw_recorded)
                recorded_dt = (
                    dt_util.as_utc(
                        parsed_recorded,
                    )
                    if parsed_recorded
                    else None
                )
            else:
                recorded_dt = None

        recorded_age: int | None

        if recorded_dt is not None:
            recorded_iso = _serialize_datetime(recorded_dt)
            recorded_age = int(
                (dt_util.utcnow() - recorded_dt).total_seconds(),
            )
        else:
            recorded_iso = received_iso
            recorded_age = received_age

        event_type_value = record.get('event_type')
        event_type = (
            event_type_value
            if isinstance(
                event_type_value,
                str,
            )
            else None
        )

        snapshot: ManualResilienceEventSnapshot = {
            'event_type': event_type,
            'category': category,
            'matched_preference': cast(
                ManualResiliencePreferenceKey | None,
                record.get(
                    'preference_key',
                ),
            ),
            'time_fired': fired_iso,
            'time_fired_age_seconds': fired_age,
            'received_at': received_iso,
            'received_age_seconds': received_age,
            'origin': cast(str | None, record.get('origin')),
            'context_id': cast(str | None, record.get('context_id')),
            'user_id': cast(str | None, record.get('user_id')),
            'sources': sources_list,
        }
        snapshot['recorded_at'] = recorded_iso
        snapshot['recorded_age_seconds'] = recorded_age

        data_payload = record.get('data')
        if isinstance(data_payload, Mapping):
            snapshot['data'] = cast(JSONMutableMapping, dict(data_payload))
        reasons = record.get('reasons')
        if isinstance(reasons, Sequence) and not isinstance(
            reasons,
            str | bytes | bytearray,
        ):
            reasons_list = [
                str(reason) for reason in reasons if isinstance(reason, str) and reason
            ]
            if reasons_list:
                snapshot['reasons'] = reasons_list
        return snapshot

    def _serialise_manual_event_history(self) -> list[ManualResilienceEventSnapshot]:
        """Serialise the tracked manual event history."""

        snapshots: list[ManualResilienceEventSnapshot] = []
        for record in self._manual_event_history:
            snapshot = self._serialise_manual_event_record(record)
            if snapshot is not None:
                snapshots.append(snapshot)
        return snapshots

    def get_manual_event_history(self) -> list[ManualResilienceEventSnapshot]:
        """Return serialised manual event history for diagnostics."""

        return self._serialise_manual_event_history()

    def get_last_manual_event_snapshot(self) -> ManualResilienceEventSnapshot | None:
        """Return the most recent manual event snapshot when available."""

        if self._manual_event_history:
            return self._serialise_manual_event_record(self._manual_event_history[-1])
        return self._serialise_manual_event_record(self._last_manual_event)

    def _serialise_last_manual_event(self) -> ManualResilienceEventSnapshot | None:
        """Return the most recent manual event payload for diagnostics."""

        return self.get_last_manual_event_snapshot()

    @callback
    def _handle_manual_event(self, event: Event) -> None:
        """Capture metadata for manual resilience triggers."""

        event_type = getattr(event, 'event_type', None)
        if not isinstance(event_type, str):
            return

        source = self._manual_event_sources.get(event_type, {})
        preference_key = source.get('preference_key')
        configured_role = source.get('configured_role')
        raw_listener_sources = source.get('listener_sources')
        listener_sources: tuple[str, ...] | None = None
        if isinstance(raw_listener_sources, Sequence) and not isinstance(
            raw_listener_sources,
            str | bytes | bytearray,
        ):
            normalised_sources = tuple(
                str(source_label)
                for source_label in raw_listener_sources
                if isinstance(source_label, str) and source_label
            )
            if normalised_sources:
                listener_sources = normalised_sources

        fired_raw = getattr(event, 'time_fired', None)
        fired_at = (
            dt_util.as_utc(fired_raw)
            if isinstance(
                fired_raw,
                datetime,
            )
            else None
        )

        context = getattr(event, 'context', None)
        context_id = getattr(context, 'id', None)
        user_id = getattr(context, 'user_id', None)

        raw_data = getattr(event, 'data', None)
        if isinstance(raw_data, Mapping):
            data = _serialise_event_data(raw_data)
        else:
            data = None

        origin = getattr(event, 'origin', None)
        origin_text = str(origin) if origin is not None else None

        record: ManualResilienceEventRecord = {
            'event_type': event_type,
            'preference_key': preference_key,
            'time_fired': fired_at,
            'received_at': dt_util.utcnow(),
            'context_id': context_id,
            'user_id': user_id,
            'origin': origin_text,
            'data': data,
        }
        if configured_role is not None:
            record['configured_role'] = configured_role
        self._manual_event_history.append(record)
        self._last_manual_event = cast(
            ManualResilienceEventRecord,
            dict(record),
        )
        self._sync_manual_history_to_runtime()
        reasons: list[str] = []
        if isinstance(configured_role, str) and configured_role:
            reasons.append(
                cast(Literal['check', 'guard', 'breaker'], configured_role),
            )
        if reasons:
            record['reasons'] = reasons

        source_tags = source.get('source_tags')
        canonical_sources: list[str] = []
        if isinstance(source_tags, Sequence) and not isinstance(
            source_tags,
            str | bytes,
        ):
            canonical_sources = [
                str(tag) for tag in source_tags if isinstance(tag, str) and tag
            ]
        primary_source = source.get('primary_source')
        if (
            isinstance(primary_source, str)
            and primary_source
            and primary_source not in canonical_sources
        ):
            canonical_sources.insert(0, primary_source)

        aggregated_sources = list(listener_sources or ())
        if canonical_sources:
            aggregated_sources.extend(
                tag for tag in canonical_sources if tag not in aggregated_sources
            )

        if aggregated_sources:
            record['sources'] = ManualEventSourceList(aggregated_sources)

        if isinstance(event_type, str) and event_type:
            self._manual_event_counters[event_type] = (
                self._manual_event_counters.get(event_type, 0) + 1
            )

        self._last_manual_event = cast(
            ManualResilienceEventRecord,
            dict(record),
        )

    async def async_sync_manual_resilience_events(
        self,
        events: ManualResilienceEventSelection,
    ) -> None:
        """Update resilience blueprint automations with preferred manual events."""

        if not events:
            return

        manager = getattr(self._hass, 'config_entries', None)
        entries_callable = getattr(manager, 'async_entries', None)
        update_entry = getattr(manager, 'async_update_entry', None)

        if not callable(entries_callable) or not callable(update_entry):
            _LOGGER.debug(
                'Skipping manual resilience event sync; config entry API not available',
            )
            return

        automation_entries = entries_callable('automation') or []
        if not automation_entries:
            _LOGGER.debug(
                'Skipping manual resilience event sync; no automation entries discovered',
            )
            return

        desired_events: ManualResilienceEventSelection = {}
        for key in ('manual_check_event', 'manual_guard_event', 'manual_breaker_event'):
            if key not in events:
                continue
            desired_events[key] = _normalise_manual_event(events.get(key))

        if not desired_events:
            return

        updated_any = False

        for entry in automation_entries:
            entry_data = getattr(entry, 'data', None)
            if not isinstance(entry_data, Mapping):
                continue

            use_blueprint = entry_data.get('use_blueprint')
            if not _is_resilience_blueprint(use_blueprint):
                continue

            blueprint = cast(Mapping[str, object], use_blueprint)
            inputs_key = 'input' if 'input' in blueprint else 'inputs'
            existing_inputs = blueprint.get(inputs_key)
            if isinstance(existing_inputs, Mapping):
                inputs: dict[str, str | None] = dict(existing_inputs)
            else:
                inputs = {}
            changed = False
            for key, desired in desired_events.items():
                current_value = inputs.get(key)
                current_normalised = _normalise_manual_event(current_value)
                if desired == current_normalised:
                    continue

                if desired is None:
                    inputs[key] = ''
                else:
                    inputs[key] = desired
                changed = True

            if not changed:
                continue

            new_blueprint = dict(blueprint)
            new_blueprint[inputs_key] = inputs

            new_data = dict(entry_data)
            new_data['use_blueprint'] = new_blueprint

            try:
                update_entry(entry, data=new_data)
            except Exception as err:  # pragma: no cover - defensive guard
                _LOGGER.warning(
                    'Failed to update resilience blueprint %s: %s',
                    getattr(entry, 'entry_id', 'unknown'),
                    err,
                )
                continue

            updated_any = True

        if updated_any:
            _LOGGER.debug(
                'Synchronized manual resilience events with blueprint inputs',
            )

        self._refresh_manual_event_listeners()

    def _get_component(
        self,
        *,
        require_loaded: bool = True,
    ) -> EntityComponent[Any] | None:
        """Return the Home Assistant script entity component."""

        component: EntityComponent[Any] | None = self._hass.data.get(
            SCRIPT_DOMAIN,
        )
        if component is None:
            if require_loaded:
                raise HomeAssistantError(
                    'The Home Assistant script integration is not loaded. '
                    "Enable the built-in script integration to use PawControl's "
                    'auto-generated scripts.',
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
                    'Skipping script generation for invalid dog entry: %s',
                    dog,
                )
                continue

            processed_dogs.add(dog_id)
            raw_name = dog.get(CONF_DOG_NAME)
            dog_name = (
                raw_name
                if isinstance(
                    raw_name,
                    str,
                )
                and raw_name.strip()
                else dog_id
            )
            slug = slugify(dog_id)

            existing_for_dog = set(self._dog_scripts.get(dog_id, []))
            new_for_dog: list[str] = []

            dog_modules = ensure_dog_modules_mapping(dog)
            dog_notifications_enabled = dog_modules.get(
                MODULE_NOTIFICATIONS,
                global_notifications_enabled,
            )

            script_definitions = self._build_scripts_for_dog(
                slug,
                dog_id,
                dog_name,
                dog_notifications_enabled,
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
                        entity_id,
                        config_entry_id=self._entry.entry_id,
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
                    entity_id,
                    config_entry_id=self._entry.entry_id,
                )

        obsolete_entry_scripts = existing_entry_scripts - \
            set(new_entry_scripts)
        for entity_id in obsolete_entry_scripts:
            await self._async_remove_script_entity(entity_id)

        if new_entry_scripts:
            created['__entry__'] = list(new_entry_scripts)
            self._entry_scripts = list(new_entry_scripts)
        else:
            self._entry_scripts = []

        self._last_generation = dt_util.utcnow()
        self._refresh_manual_event_listeners()

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
        self._unsubscribe_manual_event_listeners()
        _LOGGER.debug(
            'Removed all PawControl managed scripts for entry %s',
            self._entry.entry_id,
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
            self._build_setup_script(
                slug,
                dog_id,
                dog_name,
                notifications_enabled,
            ),
        )

        if notifications_enabled:
            scripts.append(
                self._build_confirmation_script(
                    slug,
                    dog_id,
                    dog_name,
                ),
            )
            scripts.append(
                self._build_push_test_script(
                    slug,
                    dog_id,
                    dog_name,
                ),
            )

        return scripts

    def _build_entry_scripts(self) -> list[tuple[str, ConfigType]]:
        """Return global script definitions scoped to the config entry."""

        scripts: list[tuple[str, ConfigType]] = []
        scripts.append(self._build_resilience_escalation_script())
        return scripts

    def _build_resilience_escalation_script(self) -> tuple[str, ConfigType]:
        """Create the guard and breaker escalation script definition."""

        object_id = _resolve_resilience_object_id(self._entry)
        default_statistics_entity = 'sensor.pawcontrol_statistics'
        skip_threshold_default, breaker_threshold_default = (
            self._resolve_resilience_thresholds()
        )

        guard_default_title = f"{self._entry_title} guard escalation"
        guard_default_message = (
            'Guard skipped {{ skip_count }} call(s) while executing {{ executed_count }} '
            'request(s). Skip reasons: {{ guard_reason_text }}.'
        )
        guard_default_notification_id = (
            f"pawcontrol_{self._entry_slug}_guard_escalation"
        )

        breaker_default_title = f"{self._entry_title} breaker escalation"
        breaker_default_message = (
            'Circuit breakers report {{ breaker_count }} open and {{ half_open_count }} '
            'half-open guard(s). Open breakers: {{ open_breakers_text }}. '
            'Half-open breakers: {{ half_open_breakers_text }}.'
        )
        breaker_default_notification_id = (
            f"pawcontrol_{self._entry_slug}_breaker_escalation"
        )

        variables: ConfigType = {
            'statistics_entity': (
                f"{{{{ statistics_entity_id | default('{default_statistics_entity}') }}}}"
            ),
            'service_execution': (
                "{{ state_attr(statistics_entity, 'service_execution') or {} }}"
            ),
            'guard': (
                "{% set data = state_attr(statistics_entity, 'service_execution') or {} %}"
                "{% set metrics = data.get('guard_metrics') %}"
                '{% if metrics is mapping %}{{ metrics }}{% else %}{{ {} }}{% endif %}'
            ),
            'rejection': (
                "{% set data = state_attr(statistics_entity, 'service_execution') or {} %}"
                "{% set metrics = data.get('rejection_metrics') %}"
                '{% if metrics is mapping %}{{ metrics }}{% else %}{{ {} }}{% endif %}'
            ),
            'skip_count': "{{ guard.get('skipped', 0) | int(0) }}",
            'executed_count': "{{ guard.get('executed', 0) | int(0) }}",
            'breaker_count': "{{ rejection.get('open_breaker_count', 0) | int(0) }}",
            'half_open_count': (
                "{{ rejection.get('half_open_breaker_count', 0) | int(0) }}"
            ),
            'guard_reason_text': (
                "{% set items = guard.get('reasons', {}) | dictsort %}"
                '{% if items %}'
                '{% for reason, count in items %}'
                '{{ reason }} ({{ count }}){% if not loop.last %}, {% endif %}'
                '{% endfor %}'
                '{% else %}No guard skip reasons recorded{% endif %}'
            ),
            'open_breakers_text': (
                "{% set names = rejection.get('open_breakers', []) %}"
                "{% if names %}{{ names | join(', ') }}{% else %}None{% endif %}"
            ),
            'half_open_breakers_text': (
                "{% set names = rejection.get('half_open_breakers', []) %}"
                "{% if names %}{{ names | join(', ') }}{% else %}None{% endif %}"
            ),
        }

        guard_followup: ConfigType = {
            'choose': [
                {
                    'conditions': [
                        {
                            'condition': 'template',
                            'value_template': (
                                "{{ followup_script | default('') | trim != '' }}"
                            ),
                        },
                    ],
                    'sequence': [
                        {
                            'service': 'script.turn_on',
                            'target': {'entity_id': '{{ followup_script }}'},
                            'data': {
                                'variables': {
                                    'trigger_reason': 'guard',
                                    'skip_count': '{{ skip_count }}',
                                    'executed_count': '{{ executed_count }}',
                                    'guard_reasons': "{{ guard.get('reasons', {}) }}",
                                    'breaker_count': '{{ breaker_count }}',
                                    'half_open_count': '{{ half_open_count }}',
                                },
                            },
                        },
                    ],
                },
            ],
            'default': [],
        }

        breaker_followup: ConfigType = {
            'choose': [
                {
                    'conditions': [
                        {
                            'condition': 'template',
                            'value_template': (
                                "{{ followup_script | default('') | trim != '' }}"
                            ),
                        },
                    ],
                    'sequence': [
                        {
                            'service': 'script.turn_on',
                            'target': {'entity_id': '{{ followup_script }}'},
                            'data': {
                                'variables': {
                                    'trigger_reason': 'breaker',
                                    'breaker_count': '{{ breaker_count }}',
                                    'half_open_count': '{{ half_open_count }}',
                                    'open_breakers': "{{ rejection.get('open_breakers', []) }}",
                                    'half_open_breakers': "{{ rejection.get('half_open_breakers', []) }}",
                                    'skip_count': '{{ skip_count }}',
                                    'executed_count': '{{ executed_count }}',
                                },
                            },
                        },
                    ],
                },
            ],
            'default': [],
        }

        sequence: list[ConfigType] = [
            {'variables': variables},
            {
                'choose': [
                    {
                        'conditions': [
                            {
                                'condition': 'template',
                                'value_template': (
                                    '{{ (skip_threshold | int(0)) > 0 and '
                                    'skip_count >= (skip_threshold | int(0)) }}'
                                ),
                            },
                        ],
                        'sequence': [
                            {
                                'service': (
                                    "{{ escalation_service | default('persistent_notification.create') }}"
                                ),
                                'data': {
                                    'title': (
                                        f"{{{{ guard_title | default('{guard_default_title}') }}}}"
                                    ),
                                    'message': (
                                        f"{{{{ guard_message | default('{guard_default_message}') }}}}"
                                    ),
                                    'notification_id': (
                                        f"{{{{ guard_notification_id | default('{guard_default_notification_id}') }}}}"
                                    ),
                                },
                            },
                            guard_followup,
                        ],
                    },
                    {
                        'conditions': [
                            {
                                'condition': 'template',
                                'value_template': (
                                    '{{ (breaker_threshold | int(0)) > 0 and ('
                                    'breaker_count >= (breaker_threshold | int(0)) or '
                                    'half_open_count >= (breaker_threshold | int(0))) }}'
                                ),
                            },
                        ],
                        'sequence': [
                            {
                                'service': (
                                    "{{ escalation_service | default('persistent_notification.create') }}"
                                ),
                                'data': {
                                    'title': (
                                        f"{{{{ breaker_title | default('{breaker_default_title}') }}}}"
                                    ),
                                    'message': (
                                        f"{{{{ breaker_message | default('{breaker_default_message}') }}}}"
                                    ),
                                    'notification_id': (
                                        f"{{{{ breaker_notification_id | default('{breaker_default_notification_id}') }}}}"
                                    ),
                                },
                            },
                            breaker_followup,
                        ],
                    },
                ],
                'default': [],
            },
        ]

        fields: ConfigType = {
            'statistics_entity_id': {
                CONF_NAME: 'Statistics sensor',
                CONF_DESCRIPTION: (
                    'Entity that exposes PawControl runtime statistics including '
                    'service execution metrics.'
                ),
                CONF_DEFAULT: default_statistics_entity,
                'selector': {'entity': {'domain': 'sensor'}},
            },
            'skip_threshold': {
                CONF_NAME: 'Guard skip threshold',
                CONF_DESCRIPTION: (
                    'Escalate when skipped guard calls reach or exceed this value. '
                    'Set to 0 to disable guard escalations.'
                ),
                CONF_DEFAULT: skip_threshold_default,
                'selector': {'number': {'min': 0, 'max': 50, 'mode': 'box'}},
            },
            'breaker_threshold': {
                CONF_NAME: 'Breaker alert threshold',
                CONF_DESCRIPTION: (
                    'Escalate when open or half-open breaker counts reach this value. '
                    'Set to 0 to disable breaker escalations.'
                ),
                CONF_DEFAULT: breaker_threshold_default,
                'selector': {'number': {'min': 0, 'max': 10, 'mode': 'box'}},
            },
            'escalation_service': {
                CONF_NAME: 'Escalation service',
                CONF_DESCRIPTION: (
                    'Service called when an escalation fires. Uses persistent '
                    'notifications by default.'
                ),
                CONF_DEFAULT: 'persistent_notification.create',
                'selector': {'text': {}},
            },
            'guard_title': {
                CONF_NAME: 'Guard alert title',
                CONF_DESCRIPTION: 'Title used when guard skips trigger the escalation.',
                CONF_DEFAULT: guard_default_title,
                'selector': {'text': {}},
            },
            'guard_message': {
                CONF_NAME: 'Guard alert message',
                CONF_DESCRIPTION: (
                    'Message body for guard skip escalations. Jinja variables from the '
                    'script (e.g. {{ skip_count }}) are available.'
                ),
                CONF_DEFAULT: guard_default_message,
                'selector': {'text': {'multiline': True}},
            },
            'guard_notification_id': {
                CONF_NAME: 'Guard notification ID',
                CONF_DESCRIPTION: (
                    'Notification identifier so repeated alerts update the same '
                    'persistent notification.'
                ),
                CONF_DEFAULT: guard_default_notification_id,
                'selector': {'text': {}},
            },
            'breaker_title': {
                CONF_NAME: 'Breaker alert title',
                CONF_DESCRIPTION: 'Title used when breaker counts trigger the escalation.',
                CONF_DEFAULT: breaker_default_title,
                'selector': {'text': {}},
            },
            'breaker_message': {
                CONF_NAME: 'Breaker alert message',
                CONF_DESCRIPTION: (
                    'Message body for breaker escalations. Script variables such as '
                    '{{ breaker_count }} are available.'
                ),
                CONF_DEFAULT: breaker_default_message,
                'selector': {'text': {'multiline': True}},
            },
            'breaker_notification_id': {
                CONF_NAME: 'Breaker notification ID',
                CONF_DESCRIPTION: (
                    'Notification identifier for breaker alerts, keeping updates '
                    'idempotent.'
                ),
                CONF_DEFAULT: breaker_default_notification_id,
                'selector': {'text': {}},
            },
            'followup_script': {
                CONF_NAME: 'Follow-up script',
                CONF_DESCRIPTION: (
                    'Optional script triggered after escalations fire. Receives '
                    'context variables such as skip and breaker counts.'
                ),
                CONF_DEFAULT: '',
                'selector': {'entity': {'domain': 'script', 'multiple': False}},
            },
        }

        raw_config: ConfigType = {
            CONF_ALIAS: f"{self._entry_title} resilience escalation",
            CONF_DESCRIPTION: (
                "Escalates guard skips and breaker activations using PawControl's "
                'runtime service metrics and optional follow-up automations.'
            ),
            CONF_SEQUENCE: sequence,
            CONF_FIELDS: fields,
            CONF_TRACE: {},
        }

        field_defaults: JSONMutableMapping = {}
        for field_name, field_config in fields.items():
            if isinstance(field_config, Mapping):
                field_defaults[field_name] = field_config.get(CONF_DEFAULT)

        self._resilience_escalation_definition = {
            'object_id': object_id,
            'alias': raw_config[CONF_ALIAS],
            'description': raw_config[CONF_DESCRIPTION],
            'field_defaults': field_defaults,
        }

        return object_id, raw_config

    def get_resilience_escalation_snapshot(self) -> ResilienceEscalationSnapshot | None:
        """Return diagnostics metadata for the resilience escalation helper."""

        definition = self._resilience_escalation_definition
        if not isinstance(definition, dict):
            return None

        object_id = definition.get('object_id')
        entity_id: str | None = next(
            (
                entity
                for entity in self._entry_scripts
                if isinstance(entity, str) and entity.endswith('_resilience_escalation')
            ),
            None,
        )

        if entity_id is None and isinstance(object_id, str):
            entity_id = f"{SCRIPT_DOMAIN}.{object_id}"

        field_defaults = cast(
            JSONMutableMapping,
            definition.get('field_defaults', {}),
        )
        manual_events = self._resolve_manual_resilience_events()
        manual_preferences = self._manual_event_preferences()
        if not self._manual_event_sources:
            self._refresh_manual_event_listeners()
        source_mapping = self._manual_event_source_mapping()
        manual_payload: JSONMutableMapping = cast(
            JSONMutableMapping,
            dict(manual_events),
        )
        active_listeners = sorted(
            {*self._manual_event_sources, *source_mapping},
        )
        manual_payload['preferred_events'] = cast(
            JSONValue,
            dict(manual_preferences),
        )
        manual_payload['preferred_guard_event'] = cast(
            JSONValue,
            manual_preferences.get('manual_guard_event'),
        )
        manual_payload['preferred_breaker_event'] = cast(
            JSONValue,
            manual_preferences.get('manual_breaker_event'),
        )
        manual_payload['preferred_check_event'] = cast(
            JSONValue,
            manual_preferences.get('manual_check_event'),
        )
        manual_payload['active_listeners'] = cast(
            JSONValue,
            list(active_listeners),
        )
        manual_payload['last_event'] = cast(
            JSONValue,
            self.get_last_manual_event_snapshot(),
        )
        manual_payload['event_history'] = cast(
            JSONValue,
            self.get_manual_event_history(),
        )

        state = None
        if entity_id is not None:
            state = getattr(self._hass, 'states', None)
            state = state.get(entity_id) if state is not None else None

        state_available = state is not None
        last_triggered: datetime | None = None
        if state_available:
            last_value = getattr(state, 'attributes', {}).get('last_triggered')
            if isinstance(last_value, datetime):
                last_triggered = dt_util.as_utc(last_value)
            elif isinstance(last_value, str):
                parsed = dt_util.parse_datetime(last_value)
                if parsed is not None:
                    last_triggered = dt_util.as_utc(parsed)

        last_triggered_age: int | None = None
        if last_triggered is not None:
            last_triggered_age = int(
                (dt_util.utcnow() - dt_util.as_utc(last_triggered)).total_seconds(),
            )

        active_field_defaults: JSONMutableMapping = {}
        if state_available:
            fields_attr = getattr(state, 'attributes', {}).get('fields')
            if isinstance(fields_attr, Mapping):
                for field_name, field_config in fields_attr.items():
                    if isinstance(field_config, Mapping):
                        default_value = field_config.get('default')
                    else:
                        default_value = getattr(field_config, 'default', None)
                    if default_value is not None or field_name in field_defaults:
                        active_field_defaults[field_name] = default_value

        def _active_value(key: str) -> JSONValue | None:
            if key in active_field_defaults:
                return active_field_defaults[key]
            return field_defaults.get(key)

        thresholds: ResilienceEscalationThresholds = {
            'skip_threshold': {
                'default': field_defaults.get('skip_threshold'),
                'active': _active_value('skip_threshold'),
            },
            'breaker_threshold': {
                'default': field_defaults.get('breaker_threshold'),
                'active': _active_value('breaker_threshold'),
            },
        }

        followup_active = _active_value('followup_script')

        timestamp_issue, last_generated_age = _classify_timestamp(
            self._last_generation,
        )

        manual_last_trigger: ManualResilienceEventSnapshot | None = None
        candidate_record: ManualResilienceEventRecord | Mapping[str, object] | None = (
            None
        )
        if self._manual_event_history:
            candidate_record = self._manual_event_history[-1]
        elif isinstance(self._last_manual_event, Mapping):
            candidate_record = self._last_manual_event

        if candidate_record is not None:
            snapshot = self._serialise_manual_event_record(
                candidate_record,
                recorded_at=dt_util.utcnow(),
            )
            if snapshot is not None:
                manual_last_trigger = snapshot

        counters_by_event: dict[str, int] = {}
        candidate_events: set[str] = set()

        for key in (
            'configured_guard_events',
            'configured_breaker_events',
            'configured_check_events',
        ):
            values = manual_payload.get(key, [])
            if isinstance(values, Iterable):
                for value in values:
                    if isinstance(value, str) and value:
                        candidate_events.add(value)

        system_guard_event = manual_payload.get('system_guard_event')
        if isinstance(system_guard_event, str) and system_guard_event:
            candidate_events.add(system_guard_event)

        system_breaker_event = manual_payload.get('system_breaker_event')
        if isinstance(system_breaker_event, str) and system_breaker_event:
            candidate_events.add(system_breaker_event)

        listener_events = manual_payload.get('listener_events', {})
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
            counters_by_event[event] = int(
                self._manual_event_counters.get(event, 0),
            )

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

        manual_payload['last_trigger'] = cast(JSONValue, manual_last_trigger)
        manual_payload['event_counters'] = {
            'total': sum(counters_by_event.values()),
            'by_event': counters_by_event,
            'by_reason': dict(sorted(counters_by_reason.items())),
        }

        manual_payload_json = cast(JSONMutableMapping, dict(manual_payload))

        return cast(
            ResilienceEscalationSnapshot,
            {
                'available': entity_id is not None,
                'state_available': state_available,
                'entity_id': entity_id,
                'object_id': object_id,
                'alias': definition.get('alias'),
                'description': definition.get('description'),
                'last_generated': _serialize_datetime(self._last_generation),
                'last_generated_age_seconds': last_generated_age,
                'last_generated_status': timestamp_issue,
                'last_triggered': _serialize_datetime(last_triggered),
                'last_triggered_age_seconds': last_triggered_age,
                'thresholds': thresholds,
                'fields': {
                    key: {
                        'default': field_defaults.get(key),
                        'active': _active_value(key),
                    }
                    for key in field_defaults
                },
                'followup_script': {
                    'default': field_defaults.get('followup_script'),
                    'active': followup_active,
                    'configured': bool(followup_active),
                },
                'statistics_entity_id': {
                    'default': field_defaults.get('statistics_entity_id'),
                    'active': _active_value('statistics_entity_id'),
                },
                'escalation_service': {
                    'default': field_defaults.get('escalation_service'),
                    'active': _active_value('escalation_service'),
                },
                'manual_events': manual_payload_json,
            },
        )

    def _build_confirmation_script(
        self,
        slug: str,
        dog_id: str,
        dog_name: str,
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
                'Sends a push notification asking if the dog finished their outdoor '
                'break and optionally clears the reminder automatically.'
            ),
            CONF_SEQUENCE: [
                {
                    'service': "{{ notify_service | default('notify.notify') }}",
                    'data': {
                        'title': f"{{ title | default('{default_title}') }}",
                        'message': f"{{ message | default('{default_message}') }}",
                        'data': {
                            'notification_id': notification_id,
                            'actions': [
                                {
                                    'action': "{{ confirm_action | default('PAWCONTROL_CONFIRM') }}",
                                    'title': "{{ confirm_title | default('✅ All good') }}",
                                },
                                {
                                    'action': "{{ remind_action | default('PAWCONTROL_REMIND') }}",
                                    'title': "{{ remind_title | default('🔁 Remind me later') }}",
                                },
                            ],
                        },
                    },
                },
                {
                    'choose': [
                        {
                            'conditions': [
                                {
                                    'condition': 'template',
                                    'value_template': '{{ auto_acknowledge | default(false) }}',
                                },
                            ],
                            'sequence': [
                                {
                                    'service': 'pawcontrol.acknowledge_notification',
                                    'data': {'notification_id': notification_id},
                                },
                            ],
                        },
                    ],
                    'default': [],
                },
            ],
            CONF_FIELDS: {
                'notify_service': {
                    CONF_NAME: 'Notification service',
                    CONF_DESCRIPTION: 'Service used to deliver the confirmation question.',
                    CONF_DEFAULT: 'notify.notify',
                    'selector': {'text': {}},
                },
                'title': {
                    CONF_NAME: 'Title',
                    CONF_DESCRIPTION: 'Title shown in the push notification.',
                    CONF_DEFAULT: default_title,
                    'selector': {'text': {}},
                },
                'message': {
                    CONF_NAME: 'Message',
                    CONF_DESCRIPTION: 'Body text shown in the push notification.',
                    CONF_DEFAULT: default_message,
                    'selector': {'text': {'multiline': True}},
                },
                'auto_acknowledge': {
                    CONF_NAME: 'Auto acknowledge',
                    CONF_DESCRIPTION: (
                        'Automatically clear the notification after sending the '
                        'question.'
                    ),
                    CONF_DEFAULT: False,
                    'selector': {'boolean': {}},
                },
            },
            CONF_TRACE: {},
        }

        return object_id, raw_config

    def _build_reset_script(
        self,
        slug: str,
        dog_id: str,
        dog_name: str,
    ) -> tuple[str, ConfigType]:
        """Create the daily reset helper script definition."""

        object_id = f"pawcontrol_{slug}_daily_reset"
        raw_config: ConfigType = {
            CONF_ALIAS: f"{dog_name} reset daily counters",
            CONF_DESCRIPTION: (
                "Resets PawControl's counters for the dog and optionally records a "
                'summary in the logbook.'
            ),
            CONF_SEQUENCE: [
                {
                    'service': 'pawcontrol.reset_daily_stats',
                    'data': {
                        'dog_id': dog_id,
                        'confirm': '{{ confirm | default(true) }}',
                    },
                },
                {
                    'choose': [
                        {
                            'conditions': [
                                {
                                    'condition': 'template',
                                    'value_template': "{{ summary | default('') != '' }}",
                                },
                            ],
                            'sequence': [
                                {
                                    'service': 'logbook.log',
                                    'data': {
                                        'name': 'PawControl',
                                        'message': '{{ summary }}',
                                    },
                                },
                            ],
                        },
                    ],
                    'default': [],
                },
            ],
            CONF_FIELDS: {
                'confirm': {
                    CONF_NAME: 'Require confirmation',
                    CONF_DESCRIPTION: 'Require an additional confirmation before resetting counters.',
                    CONF_DEFAULT: True,
                    'selector': {'boolean': {}},
                },
                'summary': {
                    CONF_NAME: 'Log summary',
                    CONF_DESCRIPTION: (
                        'Optional summary that will be written to the logbook after the reset.'
                    ),
                    CONF_DEFAULT: '',
                    'selector': {'text': {'multiline': True}},
                },
            },
            CONF_TRACE: {},
        }

        return object_id, raw_config

    def _build_push_test_script(
        self,
        slug: str,
        dog_id: str,
        dog_name: str,
    ) -> tuple[str, ConfigType]:
        """Create the push notification test script definition."""

        object_id = f"pawcontrol_{slug}_notification_test"
        default_message = f"Test notification for {dog_name} from PawControl"

        raw_config: ConfigType = {
            CONF_ALIAS: f"{dog_name} notification test",
            CONF_DESCRIPTION: (
                'Sends the PawControl test notification so that you can verify '
                'push delivery for this dog.'
            ),
            CONF_SEQUENCE: [
                {
                    'service': 'pawcontrol.notify_test',
                    'data': {
                        'dog_id': dog_id,
                        'message': f"{{ message | default('{default_message}') }}",
                        'priority': "{{ priority | default('normal') }}",
                    },
                },
            ],
            CONF_FIELDS: {
                'message': {
                    CONF_NAME: 'Message',
                    CONF_DESCRIPTION: 'Notification message body.',
                    CONF_DEFAULT: default_message,
                    'selector': {'text': {'multiline': True}},
                },
                'priority': {
                    CONF_NAME: 'Priority',
                    CONF_DESCRIPTION: 'Notification priority used for the test message.',
                    CONF_DEFAULT: 'normal',
                    'selector': {
                        'select': {
                            'options': ['low', 'normal', 'high', 'urgent'],
                        },
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
                'service': 'pawcontrol.reset_daily_stats',
                'data': {'dog_id': dog_id, 'confirm': False},
            },
        ]

        fields: dict[str, ConfigType] = {}

        if notifications_enabled:
            sequence.append(
                {
                    'choose': [
                        {
                            'conditions': [
                                {
                                    'condition': 'template',
                                    'value_template': '{{ send_notification | default(true) }}',
                                },
                            ],
                            'sequence': [
                                {
                                    'service': 'pawcontrol.notify_test',
                                    'data': {
                                        'dog_id': dog_id,
                                        'message': f"{{ message | default('{default_message}') }}",
                                        'priority': "{{ priority | default('normal') }}",
                                    },
                                },
                            ],
                        },
                    ],
                    'default': [],
                },
            )

            fields['send_notification'] = {
                CONF_NAME: 'Send verification',
                CONF_DESCRIPTION: 'Send a PawControl notification after resetting counters.',
                CONF_DEFAULT: True,
                'selector': {'boolean': {}},
            }
            fields['message'] = {
                CONF_NAME: 'Verification message',
                CONF_DESCRIPTION: 'Message used when the verification notification is sent.',
                CONF_DEFAULT: default_message,
                'selector': {'text': {'multiline': True}},
            }
            fields['priority'] = {
                CONF_NAME: 'Verification priority',
                CONF_DESCRIPTION: 'Priority level for the verification notification.',
                CONF_DEFAULT: 'normal',
                'selector': {
                    'select': {
                        'options': ['low', 'normal', 'high', 'urgent'],
                    },
                },
            }

        raw_config: ConfigType = {
            CONF_ALIAS: f"{dog_name} daily setup",
            CONF_DESCRIPTION: (
                'Runs the documented PawControl setup flow by resetting counters '
                'and optionally sending a verification notification.'
            ),
            CONF_SEQUENCE: sequence,
            CONF_FIELDS: fields,
            CONF_TRACE: {},
        }

        return object_id, raw_config


class ManualEventSourceList(list[str]):
    """List-like container that compares equal to listener and canonical sources."""

    def __eq__(
        self,
        other: object,
    ) -> bool:  # pragma: no cover - behaviour validated via tests
        """Normalise ``system_options`` placeholder values during comparisons.

        Manual resilience listeners historically recorded ``"system_options"`` as
        a placeholder whenever the event originated from config entry options.
        Older persistence layers therefore store the placeholder as a standalone
        list entry, while newer telemetry emits the canonical listener list and
        appends the placeholder for provenance.  The custom equality keeps both
        representations equivalent so downstream code that still compares raw
        lists continues to work while the new telemetry retains its richer
        metadata.
        """
        if isinstance(other, list):
            if other == ['system_options']:
                return 'system_options' in self
            cleaned = [item for item in self if item != 'system_options']
            return cleaned == other
        return super().__eq__(other)
