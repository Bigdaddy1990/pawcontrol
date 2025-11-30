"""Home Assistant compatibility shims for PawControl's test suite."""

from __future__ import annotations

import re
import sys
import types
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

__all__ = [
    "ConfigEntry",
    "ConfigEntryAuthFailed",
    "ConfigEntryNotReady",
    "ConfigEntryState",
    "ConfigSubentry",
    "HomeAssistantError",
    "IssueSeverity",
    "Platform",
    "install_homeassistant_stubs",
    "support_entry_unload",
    "support_remove_from_device",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENT_ROOT = REPO_ROOT / "custom_components"
PAWCONTROL_ROOT = COMPONENT_ROOT / "pawcontrol"

_DEVICE_REGISTRY: DeviceRegistry | None = None
_ENTITY_REGISTRY: EntityRegistry | None = None
_ISSUE_REGISTRY: IssueRegistry | None = None
HOME_ASSISTANT_VERSION = "2025.1.0"


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class Platform(StrEnum):
    """StrEnum stub that mirrors ``homeassistant.const.Platform``."""

    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    SWITCH = "switch"
    NUMBER = "number"
    SELECT = "select"
    TEXT = "text"
    DEVICE_TRACKER = "device_tracker"
    DATE = "date"
    DATETIME = "datetime"


class ConfigEntryState(Enum):
    """Enum mirroring Home Assistant's config entry states."""

    LOADED = ("loaded", True)
    SETUP_ERROR = ("setup_error", True)
    MIGRATION_ERROR = ("migration_error", False)
    SETUP_RETRY = ("setup_retry", True)
    NOT_LOADED = ("not_loaded", True)
    FAILED_UNLOAD = ("failed_unload", False)
    SETUP_IN_PROGRESS = ("setup_in_progress", False)
    UNLOAD_IN_PROGRESS = ("unload_in_progress", False)

    def __new__(cls, value: str, recoverable: bool) -> ConfigEntryState:
        """Store the string value and recoverability flag."""

        obj = object.__new__(cls)
        obj._value_ = value
        obj._recoverable = recoverable
        return obj

    @property
    def recoverable(self) -> bool:
        """Return whether the state can be auto-recovered."""

        return self._recoverable

    @classmethod
    def from_value(cls, value: str | ConfigEntryState) -> ConfigEntryState:
        """Return the enum member matching ``value`` regardless of casing."""

        if isinstance(value, cls):
            return value

        for member in cls:
            if member.value == value:
                return member
            if isinstance(value, str) and member.name == value.upper():
                return member
        raise ValueError(value)


class IssueSeverity(StrEnum):
    """Home Assistant issue severity mirror."""

    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @classmethod
    def from_value(cls, value: str | IssueSeverity | None) -> IssueSeverity:
        """Return the severity matching ``value`` with graceful fallback."""

        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value.lower())
            except ValueError:
                return cls.WARNING
        return cls.WARNING


class _ConfigEntryError(Exception):
    """Base class for stub config entry exceptions."""


class ConfigEntryAuthFailed(_ConfigEntryError):  # noqa: N818
    """Replacement for :class:`homeassistant.exceptions.ConfigEntryAuthFailed`."""


class ConfigEntryNotReady(_ConfigEntryError):  # noqa: N818
    """Replacement for :class:`homeassistant.exceptions.ConfigEntryNotReady`."""


class HomeAssistantError(Exception):
    """Replacement for :class:`homeassistant.exceptions.HomeAssistantError`."""


class HomeAssistant:
    """Minimal stand-in for :class:`homeassistant.core.HomeAssistant`."""

    def __init__(self) -> None:
        self.data: dict[str, object] = {}


class Event:
    """Simplified version of ``homeassistant.core.Event`` used by tests."""

    def __init__(self, event_type: str, data: dict[str, object] | None = None) -> None:
        self.event_type = event_type
        self.data = data or {}


class State:
    """Simplified version of ``homeassistant.core.State``."""

    def __init__(
        self,
        entity_id: str,
        state: str,
        attributes: dict[str, object] | None = None,
    ) -> None:
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes or {}


class Context:
    """Lightweight ``homeassistant.core.Context`` replacement."""

    def __init__(self, user_id: str | None = None) -> None:
        self.user_id = user_id


def _callback(func: Callable[..., None]) -> Callable[..., None]:
    return func


# Minimal registry matching Home Assistant's ConfigEntry handler mapping.
HANDLERS: dict[str, object] = {}


async def support_entry_unload(hass: object, domain: str) -> bool:
    """Return ``True`` if the handler exposes an unload hook."""

    handler = HANDLERS.get(domain)
    return bool(handler and hasattr(handler, "async_unload_entry"))


async def support_remove_from_device(hass: object, domain: str) -> bool:
    """Return ``True`` if the handler exposes a remove-device hook."""

    handler = HANDLERS.get(domain)
    return bool(handler and hasattr(handler, "async_remove_config_entry_device"))


class ConfigSubentry:
    """Minimal representation of a Home Assistant configuration subentry."""

    def __init__(
        self,
        *,
        subentry_id: str,
        data: dict[str, Any] | None = None,
        subentry_type: str,
        title: str,
        unique_id: str | None = None,
    ) -> None:
        self.subentry_id = subentry_id
        self.data = dict(data or {})
        self.subentry_type = subentry_type
        self.title = title
        self.unique_id = unique_id


def _build_subentries(
    subentries_data: Iterable[dict[str, Any]] | None,
) -> dict[str, ConfigSubentry]:
    """Construct deterministic subentries from the provided data."""

    subentries: dict[str, ConfigSubentry] = {}
    for index, subentry_data in enumerate(subentries_data or (), start=1):
        subentry_id = (
            str(subentry_data.get("subentry_id"))
            if "subentry_id" in subentry_data
            else f"subentry_{index}"
        )
        subentries[subentry_id] = ConfigSubentry(
            subentry_id=subentry_id,
            data=dict(subentry_data.get("data", {})),
            subentry_type=str(subentry_data.get("subentry_type", "subentry")),
            title=str(subentry_data.get("title", subentry_id)),
            unique_id=subentry_data.get("unique_id"),
        )

    return subentries


class ConfigEntry:
    """Minimal representation of Home Assistant config entries."""

    def __init__(
        self,
        entry_id: str | None = None,
        *,
        created_at: datetime | None = None,
        domain: str | None = None,
        data: dict[str, object] | None = None,
        options: dict[str, object] | None = None,
        discovery_keys: dict[str, tuple[object, ...]] | None = None,
        subentries_data: Iterable[dict[str, Any]] | None = None,
        title: str | None = None,
        source: str = "user",
        version: int = 1,
        minor_version: int = 0,
        unique_id: str | None = None,
        pref_disable_new_entities: bool = False,
        pref_disable_polling: bool = False,
        pref_disable_discovery: bool = False,
        disabled_by: str | None = None,
        state: ConfigEntryState | str = ConfigEntryState.NOT_LOADED,
        supports_unload: bool | None = None,
        supports_remove_device: bool | None = None,
        supports_options: bool | None = None,
        supports_reconfigure: bool | None = None,
        supported_subentry_types: dict[str, dict[str, bool]] | None = None,
        reason: str | None = None,
        error_reason_translation_key: str | None = None,
        error_reason_translation_placeholders: dict[str, object] | None = None,
        modified_at: datetime | None = None,
    ) -> None:
        self.entry_id = entry_id or "stub-entry"
        self.domain = domain or "unknown"
        self.data = dict(data or {})
        self.options = dict(options or {})
        self.title = title or self.domain
        self.source = source
        self.version = version
        self.minor_version = minor_version
        self.unique_id = unique_id
        self.pref_disable_new_entities = pref_disable_new_entities
        self.pref_disable_polling = pref_disable_polling
        self.pref_disable_discovery = pref_disable_discovery
        self.disabled_by = disabled_by
        self.state = ConfigEntryState.from_value(state)
        self.discovery_keys = dict(discovery_keys or {})
        self.subentries = _build_subentries(subentries_data)
        self._supports_unload = supports_unload
        self._supports_remove_device = supports_remove_device
        self._supports_options = supports_options
        self._supports_reconfigure = supports_reconfigure
        self._supported_subentry_types = (
            dict(supported_subentry_types) if supported_subentry_types else None
        )
        self.runtime_data: object | None = None
        self.reason = reason
        self.error_reason_translation_key = error_reason_translation_key
        self.error_reason_translation_placeholders = dict(
            error_reason_translation_placeholders or {}
        )
        self.update_listeners: list[Callable[..., object]] = []
        self.created_at: datetime = created_at or _utcnow()
        self.modified_at: datetime = modified_at or self.created_at

    @property
    def supports_options(self) -> bool:
        """Return whether the entry exposes an options flow."""

        if self._supports_options is None:
            handler = HANDLERS.get(self.domain)
            if handler and hasattr(handler, "async_supports_options_flow"):
                self._supports_options = bool(handler.async_supports_options_flow(self))

        return bool(self._supports_options)

    @property
    def supports_unload(self) -> bool:
        """Return whether the entry exposes an unload hook."""

        if self._supports_unload is None:
            handler = HANDLERS.get(self.domain)
            if handler and hasattr(handler, "async_unload_entry"):
                self._supports_unload = True

        return bool(self._supports_unload)

    @property
    def supports_remove_device(self) -> bool:
        """Return whether the entry exposes a remove-device hook."""

        if self._supports_remove_device is None:
            handler = HANDLERS.get(self.domain)
            if handler and hasattr(handler, "async_remove_config_entry_device"):
                self._supports_remove_device = True

        return bool(self._supports_remove_device)

    @property
    def supports_reconfigure(self) -> bool:
        """Return whether the entry exposes a reconfigure flow."""

        if self._supports_reconfigure is None:
            handler = HANDLERS.get(self.domain)
            if handler and hasattr(handler, "async_supports_reconfigure_flow"):
                self._supports_reconfigure = bool(
                    handler.async_supports_reconfigure_flow(self)
                )

        return bool(self._supports_reconfigure)

    @property
    def supported_subentry_types(self) -> dict[str, dict[str, bool]]:
        """Return the supported subentry types mapping."""

        if self._supported_subentry_types is None:
            handler = HANDLERS.get(self.domain)
            if handler and hasattr(handler, "async_get_supported_subentry_types"):
                supported_flows = handler.async_get_supported_subentry_types(self)
                self._supported_subentry_types = {
                    subentry_type: {
                        "supports_reconfigure": hasattr(
                            subentry_handler, "async_step_reconfigure"
                        )
                    }
                    for subentry_type, subentry_handler in supported_flows.items()
                }

        return self._supported_subentry_types or {}


class _FlowBase:
    """Common helpers shared by flow handler stubs."""

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: dict[str, object] | None = None,
        description_placeholders: dict[str, object] | None = None,
        errors: dict[str, object] | None = None,
    ) -> FlowResult:
        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "description_placeholders": dict(description_placeholders or {}),
            "errors": dict(errors or {}),
        }

    def async_external_step(self, *, step_id: str, url: str) -> FlowResult:
        return {"type": "external", "step_id": step_id, "url": url}

    def async_create_entry(
        self,
        *,
        title: str | None = None,
        data: dict[str, object] | None = None,
    ) -> FlowResult:
        return {
            "type": "create_entry",
            **({"title": title} if title is not None else {}),
            "data": dict(data or {}),
        }

    def async_abort(self, *, reason: str) -> FlowResult:
        return {"type": "abort", "reason": reason}

    def async_show_menu(
        self,
        *,
        step_id: str,
        menu_options: Iterable[str],
        description_placeholders: dict[str, object] | None = None,
    ) -> FlowResult:
        return {
            "type": "menu",
            "step_id": step_id,
            "menu_options": list(menu_options),
            "description_placeholders": dict(description_placeholders or {}),
        }

    def async_show_progress(
        self,
        *,
        step_id: str,
        progress_action: str,
        description_placeholders: dict[str, object] | None = None,
    ) -> FlowResult:
        return {
            "type": "progress",
            "step_id": step_id,
            "progress_action": progress_action,
            "description_placeholders": dict(description_placeholders or {}),
        }

    def async_show_progress_done(
        self,
        *,
        next_step_id: str,
        description_placeholders: dict[str, object] | None = None,
    ) -> FlowResult:
        return {
            "type": "progress_done",
            "next_step_id": next_step_id,
            "description_placeholders": dict(description_placeholders or {}),
        }

    def async_external_step_done(self, *, next_step_id: str) -> FlowResult:
        return {"type": "external_done", "next_step_id": next_step_id}


class OptionsFlow(_FlowBase):
    """Options flow stub used by coordinator tests."""

    async def async_step_init(self, user_input: dict[str, object] | None = None):
        return self.async_create_entry(data=user_input or {})


class ConfigFlowResult(dict):
    """Dictionary wrapper to mimic Home Assistant flow results."""


class DeviceInfo(dict):
    """Match Home Assistant's mapping-style device info container."""


FlowResult = dict[str, object]


class DeviceEntry:
    """Simple device registry entry stub."""

    def __init__(self, **kwargs: object) -> None:
        self.id = kwargs.get("id", "device")
        self.name = kwargs.get("name")
        self.manufacturer = kwargs.get("manufacturer")
        self.model = kwargs.get("model")
        self.model_id = kwargs.get("model_id")
        self.sw_version = kwargs.get("sw_version")
        self.via_device_id = kwargs.get("via_device_id")
        self.configuration_url = kwargs.get("configuration_url")
        self.area_id = kwargs.get("area_id")
        self.suggested_area = kwargs.get("suggested_area")
        self.disabled_by = kwargs.get("disabled_by")
        self.primary_config_entry = kwargs.get("primary_config_entry")
        self.hw_version = kwargs.get("hw_version")
        self.serial_number = kwargs.get("serial_number")
        self.name_by_user = kwargs.get("name_by_user")
        self.entry_type = kwargs.get("entry_type")
        self.identifiers = set(kwargs.get("identifiers", set()))
        self.connections = set(kwargs.get("connections", set()))
        self.created_at: datetime = kwargs.get("created_at") or _utcnow()
        self.modified_at: datetime = kwargs.get("modified_at") or self.created_at
        self.config_entries: set[str] = set()
        config_entry_id = kwargs.get("config_entry_id")
        if isinstance(config_entry_id, str):
            self.config_entries.add(config_entry_id)
        self.config_entries.update(
            entry
            for entry in kwargs.get("config_entries", set())
            if isinstance(entry, str)
        )
        for key, value in kwargs.items():
            if not hasattr(self, key):
                setattr(self, key, value)


class DeviceRegistry:
    """In-memory registry used by device tests."""

    def __init__(self) -> None:
        self.devices: dict[str, DeviceEntry] = {}
        self._id_sequence = 0

    def async_get_or_create(self, **kwargs: object) -> DeviceEntry:
        creation_kwargs = dict(kwargs)
        identifiers = set(creation_kwargs.get("identifiers", set()))
        connections = set(creation_kwargs.get("connections", set()))

        entry_id = creation_kwargs.pop("id", None)
        stored = self.devices.get(entry_id) if isinstance(entry_id, str) else None

        if stored is None and (identifiers or connections):
            stored = self.async_get_device(
                identifiers=identifiers or None, connections=connections or None
            )

        if stored is None:
            stored = DeviceEntry(
                id=entry_id if isinstance(entry_id, str) else self._next_device_id(),
                **creation_kwargs,
            )
            self.devices.setdefault(stored.id, stored)

        self._track_device_id(stored.id)
        self._update_device(stored, **creation_kwargs)
        return stored

    def async_update_device(self, device_id: str, **kwargs: object) -> DeviceEntry:
        entry = self.devices.setdefault(device_id, DeviceEntry(id=device_id))
        self._update_device(entry, **kwargs)
        return entry

    def async_remove_device(self, device_id: str) -> bool:
        """Remove a device by ID, mirroring Home Assistant's registry helper."""

        return self.devices.pop(device_id, None) is not None

    def async_get(self, device_id: str) -> DeviceEntry | None:
        return self.devices.get(device_id)

    def async_get_device(
        self,
        *,
        identifiers: set[tuple[str, str]] | None = None,
        connections: set[tuple[str, str]] | None = None,
        device_id: str | None = None,
    ) -> DeviceEntry | None:
        if isinstance(device_id, str) and device_id in self.devices:
            return self.devices[device_id]

        identifier_matches = identifiers or set()
        connection_matches = connections or set()
        if not identifier_matches and not connection_matches:
            return None

        for device in self.devices.values():
            if (device.identifiers & identifier_matches) or (
                device.connections & connection_matches
            ):
                return device

        return None

    def async_entries_for_config_entry(self, entry_id: str) -> list[DeviceEntry]:
        return [
            device
            for device in self.devices.values()
            if entry_id in device.config_entries
        ]

    def async_listen(self, callback):  # type: ignore[no-untyped-def]
        return None

    def _update_device(self, entry: DeviceEntry, **kwargs: object) -> None:
        if isinstance(kwargs.get("config_entry_id"), str):
            entry.config_entries.add(kwargs["config_entry_id"])
        if "config_entries" in kwargs:
            entry.config_entries.update(
                entry_id
                for entry_id in kwargs["config_entries"]
                if isinstance(entry_id, str)
            )
        if "name" in kwargs:
            entry.name = kwargs["name"]
        if "manufacturer" in kwargs:
            entry.manufacturer = kwargs["manufacturer"]
        if "model" in kwargs:
            entry.model = kwargs["model"]
        if "model_id" in kwargs:
            entry.model_id = kwargs["model_id"]
        if "sw_version" in kwargs:
            entry.sw_version = kwargs["sw_version"]
        if "via_device_id" in kwargs:
            entry.via_device_id = kwargs["via_device_id"]
        if "configuration_url" in kwargs:
            entry.configuration_url = kwargs["configuration_url"]
        if "area_id" in kwargs:
            entry.area_id = kwargs["area_id"]
        if "suggested_area" in kwargs:
            entry.suggested_area = kwargs["suggested_area"]
        if "disabled_by" in kwargs:
            entry.disabled_by = kwargs["disabled_by"]
        if "primary_config_entry" in kwargs:
            entry.primary_config_entry = kwargs["primary_config_entry"]
        if "hw_version" in kwargs:
            entry.hw_version = kwargs["hw_version"]
        if "serial_number" in kwargs:
            entry.serial_number = kwargs["serial_number"]
        if "identifiers" in kwargs:
            entry.identifiers.update(set(kwargs["identifiers"]))
        if "connections" in kwargs:
            entry.connections.update(set(kwargs["connections"]))
        if "name_by_user" in kwargs:
            entry.name_by_user = kwargs["name_by_user"]
        if "entry_type" in kwargs:
            entry.entry_type = kwargs["entry_type"]
        if "preferred_area_id" in kwargs:
            entry.preferred_area_id = kwargs["preferred_area_id"]
        if "created_at" in kwargs:
            entry.created_at = kwargs["created_at"]
        if "modified_at" in kwargs:
            entry.modified_at = kwargs["modified_at"]
        elif kwargs:
            entry.modified_at = _utcnow()
        for key, value in kwargs.items():
            if not hasattr(entry, key):
                setattr(entry, key, value)

    def _track_device_id(self, device_id: str) -> None:
        match = re.fullmatch(r"device-(\d+)", device_id)
        if match:
            self._id_sequence = max(self._id_sequence, int(match.group(1)))

    def _next_device_id(self) -> str:
        self._id_sequence += 1
        return f"device-{self._id_sequence}"


def _async_get_device_registry(*args: object, **kwargs: object) -> DeviceRegistry:
    global _DEVICE_REGISTRY

    if _DEVICE_REGISTRY is None:
        _DEVICE_REGISTRY = DeviceRegistry()

    return _DEVICE_REGISTRY


def _async_get_device_by_hints(
    registry: DeviceRegistry,
    *,
    identifiers: Iterable[tuple[str, str]] | None = None,
    connections: Iterable[tuple[str, str]] | None = None,
    device_id: str | None = None,
) -> DeviceEntry | None:
    return registry.async_get_device(
        identifiers=set(identifiers or set()),
        connections=set(connections or set()),
        device_id=device_id,
    )


def _async_entries_for_device_config(
    registry: DeviceRegistry, entry_id: str
) -> list[DeviceEntry]:
    return registry.async_entries_for_config_entry(entry_id)


def _async_remove_device_entry(registry: DeviceRegistry, device_id: str) -> bool:
    return registry.async_remove_device(device_id)


def _async_get_issue_registry(*args: object, **kwargs: object) -> IssueRegistry:
    global _ISSUE_REGISTRY

    if _ISSUE_REGISTRY is None:
        _ISSUE_REGISTRY = IssueRegistry()

    return _ISSUE_REGISTRY


def _async_create_issue(
    hass: object,
    domain: str,
    issue_id: str,
    *,
    active: bool | None = None,
    is_persistent: bool | None = None,
    issue_domain: str | None = None,
    translation_domain: str | None = None,
    translation_key: str | None = None,
    translation_placeholders: dict[str, object] | None = None,
    severity: str | None = None,
    is_fixable: bool | None = None,
    breaks_in_ha_version: str | None = None,
    learn_more_url: str | None = None,
    data: dict[str, object] | None = None,
    dismissed_version: str | None = None,
) -> dict[str, object]:
    registry = _async_get_issue_registry(hass)
    return registry.async_create_issue(
        domain,
        issue_id,
        active=active,
        is_persistent=is_persistent,
        issue_domain=issue_domain,
        translation_domain=translation_domain,
        translation_key=translation_key,
        translation_placeholders=translation_placeholders,
        severity=severity,
        is_fixable=is_fixable,
        breaks_in_ha_version=breaks_in_ha_version,
        learn_more_url=learn_more_url,
        data=data,
        dismissed_version=dismissed_version,
    )


def _async_delete_issue(hass: object, domain: str, issue_id: str) -> bool:
    registry = _async_get_issue_registry(hass)
    return registry.async_delete_issue(domain, issue_id)


def _async_get_issue(
    hass: object, domain: str, issue_id: str
) -> dict[str, object] | None:
    registry = _async_get_issue_registry(hass)
    return registry.async_get_issue(domain, issue_id)


def _async_ignore_issue(
    hass: object, domain: str, issue_id: str, ignore: bool
) -> dict[str, object]:
    registry = _async_get_issue_registry(hass)
    return registry.async_ignore_issue(domain, issue_id, ignore)


class IssueRegistry:
    """Minimal Home Assistant issue registry stub."""

    def __init__(self) -> None:
        self.issues: dict[tuple[str, str], dict[str, object]] = {}

    def async_create_issue(
        self,
        domain: str,
        issue_id: str,
        *,
        active: bool | None = None,
        is_persistent: bool | None = None,
        issue_domain: str | None = None,
        translation_domain: str | None = None,
        translation_key: str | None = None,
        translation_placeholders: dict[str, object] | None = None,
        severity: str | None = None,
        is_fixable: bool | None = None,
        breaks_in_ha_version: str | None = None,
        learn_more_url: str | None = None,
        data: dict[str, object] | None = None,
        dismissed_version: str | None = None,
    ) -> dict[str, object]:
        key = (domain, issue_id)
        existing = self.issues.get(key, {})
        severity_value = IssueSeverity.from_value(
            severity if severity is not None else existing.get("severity")
        )
        is_fixable_value = (
            is_fixable if is_fixable is not None else existing.get("is_fixable", False)
        )
        translation_key_value = (
            translation_key
            if translation_key is not None
            else existing.get("translation_key") or issue_id
        )
        data_value: dict[str, object] | None
        if data is not None:
            data_value = dict(data)
        else:
            data_value = (
                dict(existing_data)
                if (existing_data := existing.get("data")) is not None
                else None
            )
        translation_placeholders_value: dict[str, object] | None
        if translation_placeholders is not None:
            translation_placeholders_value = dict(translation_placeholders)
        else:
            translation_placeholders_value = (
                dict(existing_placeholders)
                if (existing_placeholders := existing.get("translation_placeholders"))
                is not None
                else None
            )
        dismissed_version_value = (
            dismissed_version
            if dismissed_version is not None
            else existing.get("dismissed_version")
        )
        dismissed_at = existing.get("dismissed")
        if dismissed_version is not None:
            dismissed_at = dismissed_at or _utcnow()
        if dismissed_version is None and dismissed_version_value is None:
            dismissed_at = None
        details = {
            **existing,
            "active": active if active is not None else existing.get("active", True),
            "created": existing.get("created", _utcnow()),
            "domain": domain,
            "issue_domain": issue_domain
            if issue_domain is not None
            else existing.get("issue_domain") or domain,
            "issue_id": issue_id,
            "translation_domain": translation_domain
            if translation_domain is not None
            else existing.get("translation_domain", domain),
            "translation_key": translation_key_value,
            "translation_placeholders": translation_placeholders_value,
            "severity": severity_value,
            "is_fixable": is_fixable_value,
            "breaks_in_ha_version": (
                breaks_in_ha_version
                if breaks_in_ha_version is not None
                else existing.get("breaks_in_ha_version")
            ),
            "learn_more_url": (
                learn_more_url
                if learn_more_url is not None
                else existing.get("learn_more_url")
            ),
            "is_persistent": (
                is_persistent
                if is_persistent is not None
                else existing.get("is_persistent", False)
            ),
            "data": data_value,
            "dismissed": dismissed_at,
            "dismissed_version": dismissed_version_value,
            "ignored": existing.get("ignored", False),
        }
        self.issues[key] = details
        return details

    def async_ignore_issue(
        self, domain: str, issue_id: str, ignore: bool
    ) -> dict[str, object]:
        key = (domain, issue_id)
        if key not in self.issues:
            msg = f"Issue {domain}/{issue_id} not found"
            raise KeyError(msg)

        details = dict(self.issues[key])
        dismissed_version_value = HOME_ASSISTANT_VERSION if ignore else None

        if (
            details.get("dismissed_version") == dismissed_version_value
            and details.get("ignored") is ignore
        ):
            return details

        details["dismissed_version"] = dismissed_version_value
        details["dismissed"] = _utcnow() if ignore else None
        details["ignored"] = ignore
        details["active"] = not ignore
        self.issues[key] = details
        return details

    def async_delete_issue(self, domain: str, issue_id: str) -> bool:
        return self.issues.pop((domain, issue_id), None) is not None

    def async_get_issue(self, domain: str, issue_id: str) -> dict[str, object] | None:
        return self.issues.get((domain, issue_id))


class RegistryEntry:
    """Entity registry entry stub."""

    def __init__(self, entity_id: str, **kwargs: object) -> None:
        self.entity_id = entity_id
        self.device_id = kwargs.get("device_id")
        self.config_entries: set[str] = set()
        if isinstance(kwargs.get("config_entry_id"), str):
            self.config_entries.add(kwargs["config_entry_id"])
        self.config_entries.update(
            entry
            for entry in kwargs.get("config_entries", set())
            if isinstance(entry, str)
        )
        self.unique_id = kwargs.get("unique_id")
        self.platform = kwargs.get("platform")
        self.original_name = kwargs.get("original_name")
        self.name = kwargs.get("name")
        self.original_device_class = kwargs.get("original_device_class")
        self.device_class = kwargs.get("device_class")
        self.translation_key = kwargs.get("translation_key")
        self.has_entity_name = kwargs.get("has_entity_name")
        self.area_id = kwargs.get("area_id")
        self.disabled_by = kwargs.get("disabled_by")
        self.entity_category = kwargs.get("entity_category")
        self.icon = kwargs.get("icon")
        self.original_icon = kwargs.get("original_icon")
        self.aliases = set(kwargs.get("aliases", set()))
        self.hidden_by = kwargs.get("hidden_by")
        self.preferred_area_id = kwargs.get("preferred_area_id")
        self.options = dict(kwargs.get("options", {}))
        self.capabilities = dict(kwargs.get("capabilities", {}))
        self.supported_features = kwargs.get("supported_features")
        self.unit_of_measurement = kwargs.get("unit_of_measurement")
        self.original_unit_of_measurement = kwargs.get("original_unit_of_measurement")
        self.created_at: datetime = kwargs.get("created_at") or _utcnow()
        self.modified_at: datetime = kwargs.get("modified_at") or self.created_at
        for key, value in kwargs.items():
            if not hasattr(self, key):
                setattr(self, key, value)


class EntityRegistry:
    """Simple entity registry storing entries in a dict."""

    def __init__(self) -> None:
        self.entities: dict[str, RegistryEntry] = {}

    def async_get(self, entity_id: str) -> RegistryEntry | None:
        return self.entities.get(entity_id)

    def async_get_or_create(self, entity_id: str, **kwargs: object) -> RegistryEntry:
        unique_id = kwargs.get("unique_id")
        platform = kwargs.get("platform")

        entry = self.entities.get(entity_id)
        if entry is None and unique_id is not None:
            entry = next(
                (
                    candidate
                    for candidate in self.entities.values()
                    if candidate.unique_id == unique_id
                    and (platform is None or candidate.platform == platform)
                ),
                None,
            )

        if entry is None:
            entry = RegistryEntry(entity_id, **kwargs)
            self.entities[entity_id] = entry

        self._update_entry(entry, **kwargs)
        return entry

    def async_update_entity(self, entity_id: str, **kwargs: object) -> RegistryEntry:
        entry = self.entities.setdefault(entity_id, RegistryEntry(entity_id))
        self._update_entry(entry, **kwargs)
        return entry

    def async_entries_for_config_entry(self, entry_id: str) -> list[RegistryEntry]:
        return [
            entity
            for entity in self.entities.values()
            if entry_id in entity.config_entries
        ]

    def async_entries_for_device(self, device_id: str) -> list[RegistryEntry]:
        return [
            entity for entity in self.entities.values() if entity.device_id == device_id
        ]

    def async_remove(self, entity_id: str) -> bool:
        """Remove an entity by ID, mirroring Home Assistant's registry helper."""

        return self.entities.pop(entity_id, None) is not None

    def async_listen(self, callback):  # type: ignore[no-untyped-def]
        return None

    def _update_entry(self, entry: RegistryEntry, **kwargs: object) -> None:
        if isinstance(kwargs.get("config_entry_id"), str):
            entry.config_entries.add(kwargs["config_entry_id"])
        if "config_entries" in kwargs:
            entry.config_entries.update(
                entry_id
                for entry_id in kwargs["config_entries"]
                if isinstance(entry_id, str)
            )
        if "device_id" in kwargs:
            entry.device_id = kwargs["device_id"]
        if "unique_id" in kwargs:
            entry.unique_id = kwargs["unique_id"]
        if "platform" in kwargs:
            entry.platform = kwargs["platform"]
        if "original_name" in kwargs:
            entry.original_name = kwargs["original_name"]
        if "name" in kwargs:
            entry.name = kwargs["name"]
        if "original_device_class" in kwargs:
            entry.original_device_class = kwargs["original_device_class"]
        if "device_class" in kwargs:
            entry.device_class = kwargs["device_class"]
        if "translation_key" in kwargs:
            entry.translation_key = kwargs["translation_key"]
        if "has_entity_name" in kwargs:
            entry.has_entity_name = kwargs["has_entity_name"]
        if "area_id" in kwargs:
            entry.area_id = kwargs["area_id"]
        if "disabled_by" in kwargs:
            entry.disabled_by = kwargs["disabled_by"]
        if "entity_category" in kwargs:
            entry.entity_category = kwargs["entity_category"]
        if "icon" in kwargs:
            entry.icon = kwargs["icon"]
        if "original_icon" in kwargs:
            entry.original_icon = kwargs["original_icon"]
        if "aliases" in kwargs:
            entry.aliases = set(kwargs["aliases"])
        if "hidden_by" in kwargs:
            entry.hidden_by = kwargs["hidden_by"]
        if "preferred_area_id" in kwargs:
            entry.preferred_area_id = kwargs["preferred_area_id"]
        if "options" in kwargs:
            entry.options = dict(kwargs["options"])
        if "capabilities" in kwargs:
            entry.capabilities = dict(kwargs["capabilities"])
        if "supported_features" in kwargs:
            entry.supported_features = kwargs["supported_features"]
        if "unit_of_measurement" in kwargs:
            entry.unit_of_measurement = kwargs["unit_of_measurement"]
        if "original_unit_of_measurement" in kwargs:
            entry.original_unit_of_measurement = kwargs["original_unit_of_measurement"]
        if "created_at" in kwargs:
            entry.created_at = kwargs["created_at"]
        if "modified_at" in kwargs:
            entry.modified_at = kwargs["modified_at"]
        elif kwargs:
            entry.modified_at = _utcnow()
        for key, value in kwargs.items():
            if not hasattr(entry, key):
                setattr(entry, key, value)


def _async_get_entity_registry(*args: object, **kwargs: object) -> EntityRegistry:
    global _ENTITY_REGISTRY

    if _ENTITY_REGISTRY is None:
        _ENTITY_REGISTRY = EntityRegistry()

    return _ENTITY_REGISTRY


def _async_entries_for_registry_config(
    registry: EntityRegistry, entry_id: str
) -> list[RegistryEntry]:
    return registry.async_entries_for_config_entry(entry_id)


def _async_entries_for_registry_device(
    registry: EntityRegistry, device_id: str
) -> list[RegistryEntry]:
    return registry.async_entries_for_device(device_id)


def _async_remove_registry_entry(registry: EntityRegistry, entity_id: str) -> bool:
    return registry.async_remove(entity_id)


class Store:
    """Persistence helper used by coordinator storage tests."""

    def __init__(self) -> None:
        self.data: object | None = None

    async def async_load(self) -> object | None:
        return self.data

    async def async_save(self, data: object) -> None:
        self.data = data


class Entity:
    """Base entity stub."""

    pass


def _config_entry_only_config_schema(domain: str):
    def _schema(data: object) -> object:
        return data

    return _schema


async def _async_get_clientsession(hass: object) -> object:
    """Return a stub clientsession for aiohttp helper tests."""

    return object()


def _async_make_resolver(hass: object) -> Callable[[str], object]:
    """Return a zeroconf resolver stub compatible with HACC fixtures."""

    def _resolve(host: str) -> object:
        return host

    return _resolve


def _log_exception(format_err: Callable[..., str], *args: object) -> None:
    """Mimic the logging helper Home Assistant exposes."""

    format_err(*args)


async def _async_track_time_interval(*args: object, **kwargs: object):
    return None


async def _async_track_time_change(*args: object, **kwargs: object):
    return None


async def _async_call_later(*args: object, **kwargs: object):
    return None


async def _async_track_state_change_event(*args: object, **kwargs: object):
    return None


class DataUpdateCoordinator:
    """Simplified coordinator used by runtime data tests."""

    def __init__(
        self, hass: object, *, name: str | None = None, **kwargs: object
    ) -> None:
        self.hass = hass
        self.name = name or "stub"

    async def async_config_entry_first_refresh(self) -> None:
        return None

    async def async_request_refresh(self) -> None:
        return None

    @classmethod
    def __class_getitem__(cls, item):  # pragma: no cover - helper stub
        return cls


class CoordinatorUpdateFailed(Exception):  # noqa: N818
    """Error raised when DataUpdateCoordinator refreshes fail."""


class _SelectorBase:
    def __init__(self, config: object | None = None) -> None:
        self.config = config


class SelectSelectorMode(StrEnum):
    DROPDOWN = "dropdown"
    LIST = "list"


class SelectSelectorConfig:
    def __init__(self, **kwargs: object) -> None:
        self.options = kwargs


class SelectSelector(_SelectorBase):
    pass


class BooleanSelector(_SelectorBase):
    pass


class NumberSelectorMode(StrEnum):
    BOX = "box"
    SLIDER = "slider"


class NumberSelectorConfig:
    def __init__(self, **kwargs: object) -> None:
        self.options = kwargs


class NumberSelector(_SelectorBase):
    pass


class TextSelectorType(StrEnum):
    TEXT = "text"
    TEL = "tel"


class TextSelectorConfig:
    def __init__(self, **kwargs: object) -> None:
        self.options = kwargs


class TextSelector(_SelectorBase):
    pass


class TimeSelector(_SelectorBase):
    pass


class DateSelector(_SelectorBase):
    pass


def selector(config: object) -> object:
    """Return selector configuration unchanged for schema validation tests."""

    return config


def _register_custom_component_packages() -> None:
    custom_components_pkg = sys.modules.setdefault(
        "custom_components", types.ModuleType("custom_components")
    )
    custom_components_pkg.__path__ = [str(COMPONENT_ROOT)]

    pawcontrol_pkg = types.ModuleType("custom_components.pawcontrol")
    pawcontrol_pkg.__path__ = [str(PAWCONTROL_ROOT)]
    sys.modules["custom_components.pawcontrol"] = pawcontrol_pkg


def install_homeassistant_stubs() -> None:
    """Register lightweight Home Assistant modules required by the tests."""

    for module_name in [
        "homeassistant",
        "homeassistant.const",
        "homeassistant.core",
        "homeassistant.exceptions",
        "homeassistant.helpers",
        "homeassistant.helpers.entity",
        "homeassistant.helpers.config_validation",
        "homeassistant.helpers.aiohttp_client",
        "homeassistant.helpers.event",
        "homeassistant.helpers.update_coordinator",
        "homeassistant.helpers.selector",
        "homeassistant.helpers.device_registry",
        "homeassistant.helpers.entity_registry",
        "homeassistant.helpers.storage",
        "homeassistant.helpers.issue_registry",
        "homeassistant.util",
        "homeassistant.util.dt",
        "homeassistant.util.logging",
        "homeassistant.config_entries",
        "homeassistant.components",
        "homeassistant.components.repairs",
        "homeassistant.data_entry_flow",
    ]:
        sys.modules.pop(module_name, None)

    global _DEVICE_REGISTRY, _ENTITY_REGISTRY, _ISSUE_REGISTRY
    _DEVICE_REGISTRY = None
    _ENTITY_REGISTRY = None
    _ISSUE_REGISTRY = None

    _register_custom_component_packages()

    homeassistant = types.ModuleType("homeassistant")
    const_module = types.ModuleType("homeassistant.const")
    core_module = types.ModuleType("homeassistant.core")
    exceptions_module = types.ModuleType("homeassistant.exceptions")
    helpers_module = types.ModuleType("homeassistant.helpers")
    helpers_module.__path__ = []
    entity_module = types.ModuleType("homeassistant.helpers.entity")
    config_validation_module = types.ModuleType(
        "homeassistant.helpers.config_validation"
    )
    aiohttp_client_module = types.ModuleType("homeassistant.helpers.aiohttp_client")
    event_module = types.ModuleType("homeassistant.helpers.event")
    update_coordinator_module = types.ModuleType(
        "homeassistant.helpers.update_coordinator"
    )
    device_registry_module = types.ModuleType("homeassistant.helpers.device_registry")
    entity_registry_module = types.ModuleType("homeassistant.helpers.entity_registry")
    issue_registry_module = types.ModuleType("homeassistant.helpers.issue_registry")
    storage_module = types.ModuleType("homeassistant.helpers.storage")
    config_entries_module = types.ModuleType("homeassistant.config_entries")
    util_module = types.ModuleType("homeassistant.util")
    util_module.__path__ = []
    dt_util_module = types.ModuleType("homeassistant.util.dt")
    logging_util_module = types.ModuleType("homeassistant.util.logging")
    selector_module = types.ModuleType("homeassistant.helpers.selector")
    components_module = types.ModuleType("homeassistant.components")
    components_module.__path__ = []
    repairs_component_module = types.ModuleType("homeassistant.components.repairs")
    data_entry_flow_module = types.ModuleType("homeassistant.data_entry_flow")

    const_module.Platform = Platform
    const_module.__version__ = HOME_ASSISTANT_VERSION
    const_module.STATE_ON = "on"
    const_module.STATE_OFF = "off"
    const_module.STATE_UNKNOWN = "unknown"
    const_module.STATE_HOME = "home"
    const_module.STATE_NOT_HOME = "not_home"

    core_module.HomeAssistant = HomeAssistant
    core_module.Event = Event
    core_module.EventStateChangedData = dict[str, object]
    core_module.State = State
    core_module.Context = Context
    core_module.callback = _callback
    core_module.CALLBACK_TYPE = Callable[..., None]

    exceptions_module.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    exceptions_module.ConfigEntryNotReady = ConfigEntryNotReady
    exceptions_module.HomeAssistantError = HomeAssistantError

    config_entries_module.HANDLERS = HANDLERS
    config_entries_module.support_entry_unload = support_entry_unload
    config_entries_module.support_remove_from_device = support_remove_from_device
    config_entries_module.ConfigEntry = ConfigEntry
    config_entries_module.ConfigEntryState = ConfigEntryState
    config_entries_module.OptionsFlow = OptionsFlow
    config_entries_module.ConfigFlowResult = ConfigFlowResult

    device_registry_module.DeviceInfo = DeviceInfo
    device_registry_module.DeviceEntry = DeviceEntry
    device_registry_module.DeviceRegistry = DeviceRegistry
    device_registry_module.async_get = _async_get_device_registry
    device_registry_module.async_get_device = _async_get_device_by_hints
    device_registry_module.async_entries_for_config_entry = (
        _async_entries_for_device_config
    )
    device_registry_module.async_remove_device = _async_remove_device_entry

    entity_registry_module.RegistryEntry = RegistryEntry
    entity_registry_module.EntityRegistry = EntityRegistry
    entity_registry_module.async_get = _async_get_entity_registry
    entity_registry_module.async_entries_for_config_entry = (
        _async_entries_for_registry_config
    )
    entity_registry_module.async_entries_for_device = _async_entries_for_registry_device
    entity_registry_module.async_remove = _async_remove_registry_entry

    issue_registry_module.DOMAIN = "issue_registry"
    issue_registry_module.IssueSeverity = IssueSeverity
    issue_registry_module.async_get = _async_get_issue_registry
    issue_registry_module.async_get_issue = _async_get_issue
    issue_registry_module.async_create_issue = _async_create_issue
    issue_registry_module.async_delete_issue = _async_delete_issue
    issue_registry_module.async_ignore_issue = _async_ignore_issue

    storage_module.Store = Store

    entity_module.Entity = Entity

    config_validation_module.config_entry_only_config_schema = (
        _config_entry_only_config_schema
    )
    aiohttp_client_module.async_get_clientsession = _async_get_clientsession
    aiohttp_client_module._async_make_resolver = _async_make_resolver
    event_module.async_track_time_interval = _async_track_time_interval
    event_module.async_track_time_change = _async_track_time_change
    event_module.async_call_later = _async_call_later
    event_module.async_track_state_change_event = _async_track_state_change_event

    update_coordinator_module.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator_module.CoordinatorUpdateFailed = CoordinatorUpdateFailed

    dt_util_module.utcnow = _utcnow
    logging_util_module.log_exception = _log_exception

    class _RepairsFlow(_FlowBase):
        """Placeholder for Home Assistant repairs flow base class."""

    repairs_component_module.RepairsFlow = _RepairsFlow
    repairs_component_module.DOMAIN = "repairs"

    data_entry_flow_module.FlowResult = FlowResult
    config_entries_module.FlowResult = FlowResult

    selector_module.SelectSelectorMode = SelectSelectorMode
    selector_module.SelectSelectorConfig = SelectSelectorConfig
    selector_module.SelectSelector = SelectSelector
    selector_module.BooleanSelector = BooleanSelector
    selector_module.NumberSelectorMode = NumberSelectorMode
    selector_module.NumberSelectorConfig = NumberSelectorConfig
    selector_module.NumberSelector = NumberSelector
    selector_module.TextSelectorType = TextSelectorType
    selector_module.TextSelectorConfig = TextSelectorConfig
    selector_module.TextSelector = TextSelector
    selector_module.TimeSelector = TimeSelector
    selector_module.DateSelector = DateSelector
    selector_module.selector = selector

    homeassistant.const = const_module
    homeassistant.core = core_module
    homeassistant.exceptions = exceptions_module
    homeassistant.helpers = helpers_module
    homeassistant.config_entries = config_entries_module
    homeassistant.util = util_module

    helpers_module.entity = entity_module
    helpers_module.config_validation = config_validation_module
    helpers_module.aiohttp_client = aiohttp_client_module
    helpers_module.event = event_module
    helpers_module.update_coordinator = update_coordinator_module
    helpers_module.selector = selector_module
    helpers_module.device_registry = device_registry_module
    helpers_module.entity_registry = entity_registry_module
    helpers_module.issue_registry = issue_registry_module
    helpers_module.storage = storage_module

    util_module.dt = dt_util_module
    util_module.logging = logging_util_module

    components_module.repairs = repairs_component_module

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.const"] = const_module
    sys.modules["homeassistant.core"] = core_module
    sys.modules["homeassistant.exceptions"] = exceptions_module
    sys.modules["homeassistant.helpers"] = helpers_module
    sys.modules["homeassistant.helpers.entity"] = entity_module
    sys.modules["homeassistant.helpers.config_validation"] = config_validation_module
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client_module
    sys.modules["homeassistant.helpers.event"] = event_module
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator_module
    sys.modules["homeassistant.helpers.selector"] = selector_module
    sys.modules["homeassistant.helpers.device_registry"] = device_registry_module
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry_module
    sys.modules["homeassistant.helpers.issue_registry"] = issue_registry_module
    sys.modules["homeassistant.helpers.storage"] = storage_module
    sys.modules["homeassistant.util"] = util_module
    sys.modules["homeassistant.util.dt"] = dt_util_module
    sys.modules["homeassistant.util.logging"] = logging_util_module
    sys.modules["homeassistant.config_entries"] = config_entries_module
    sys.modules["homeassistant.components"] = components_module
    sys.modules["homeassistant.components.repairs"] = repairs_component_module
    sys.modules["homeassistant.data_entry_flow"] = data_entry_flow_module
