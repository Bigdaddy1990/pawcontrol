"""Minimal Home Assistant compatibility stubs for PawControl tests."""

from __future__ import annotations

import asyncio
import atexit
import importlib
import inspect
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, MutableMapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from types import MappingProxyType, ModuleType, SimpleNamespace
from typing import TYPE_CHECKING, Any, Optional, cast
from uuid import uuid4

from jinja2.nativetypes import NativeEnvironment

type ServiceData = Mapping[str, object]
type EventData = Mapping[str, object]
type MutableEventData = MutableMapping[str, object]
type StateAttributes = Mapping[str, object]
type StateAttributeMapping = MutableMapping[str, object]
type MutableFlowResultDict = MutableMapping[str, object]
type MutableConfigEntryData = MutableMapping[str, object]
type FlowContext = Mapping[str, object]
type FlowResult = Mapping[str, object]
type AutomationAction = Mapping[str, object]

if TYPE_CHECKING:  # pragma: no cover - only used for static analysis
    from custom_components.pawcontrol.types import AddAnotherDogInput, DogModulesConfig
    from homeassistant.config_entries import OptionsFlow as _HAOptionsFlow
    from homeassistant.core import HomeAssistant as _HAHomeAssistant
else:  # pragma: no cover - runtime fallbacks

    class _HAHomeAssistant:  # pylint: disable=too-few-public-methods
        """Placeholder Home Assistant type for annotations."""

        pass

    class _HAOptionsFlow:  # pylint: disable=too-few-public-methods
        """Placeholder OptionsFlow type for annotations."""

        pass


HomeAssistant = _HAHomeAssistant
OptionsFlow = _HAOptionsFlow

try:  # pragma: no cover - optional third-party dependency
    import voluptuous as vol
except ModuleNotFoundError:  # pragma: no cover - simplified fallback

    class _VoluptuousFallback(SimpleNamespace):
        """Minimal stand-ins that mimic voluptuous validators."""

        def __init__(self) -> None:
            super().__init__(
                All=lambda *validators: lambda value: value,
                Boolean=lambda: lambda value: bool(value),
                Datetime=lambda: lambda value: value,
                Date=lambda: lambda value: value,
            )

    vol = _VoluptuousFallback()


class _UnitEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - debug helper
        return str(self.value)


def _install_const_module() -> None:
    const_module = ModuleType("homeassistant.const")

    class Platform(str, Enum):
        BUTTON = "button"
        SENSOR = "sensor"
        SWITCH = "switch"
        BINARY_SENSOR = "binary_sensor"
        SELECT = "select"
        DEVICE_TRACKER = "device_tracker"
        NUMBER = "number"
        TEXT = "text"
        DATE = "date"
        DATETIME = "datetime"

    const_module.Platform = Platform
    const_module.STATE_UNKNOWN = "unknown"
    const_module.STATE_UNAVAILABLE = "unavailable"
    const_module.STATE_ON = "on"
    const_module.STATE_OFF = "off"
    const_module.STATE_HOME = "home"
    const_module.STATE_NOT_HOME = "not_home"
    const_module.ATTR_LATITUDE = "latitude"
    const_module.ATTR_LONGITUDE = "longitude"

    const_module.CONF_NAME = "name"
    const_module.CONF_USERNAME = "username"
    const_module.CONF_PASSWORD = "password"
    const_module.CONF_ALIAS = "alias"
    const_module.CONF_DEFAULT = "default"
    const_module.CONF_DESCRIPTION = "description"
    const_module.CONF_SEQUENCE = "sequence"
    const_module.PERCENTAGE = "%"

    class UnitOfEnergy(_UnitEnum):
        KILO_WATT_HOUR = "kWh"

    class UnitOfLength(_UnitEnum):
        METERS = "m"

    class UnitOfMass(_UnitEnum):
        KILOGRAMS = "kg"

    class UnitOfSpeed(_UnitEnum):
        METERS_PER_SECOND = "m/s"

    class UnitOfTime(_UnitEnum):
        MINUTES = "min"
        HOURS = "h"
        SECONDS = "s"

    const_module.UnitOfEnergy = UnitOfEnergy
    const_module.UnitOfLength = UnitOfLength
    const_module.UnitOfMass = UnitOfMass
    const_module.UnitOfSpeed = UnitOfSpeed
    const_module.UnitOfTime = UnitOfTime

    sys.modules["homeassistant.const"] = const_module


def _install_util_modules() -> None:
    util_module = ModuleType("homeassistant.util")
    util_module.__path__ = []  # type: ignore[attr-defined]

    dt_module = ModuleType("homeassistant.util.dt")

    def utcnow() -> datetime:
        return datetime.now(UTC)

    def now() -> datetime:
        return datetime.now(UTC).astimezone()

    def as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def as_local(value: datetime) -> datetime:
        return value.astimezone()

    def parse_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value)

    dt_module.utcnow = utcnow
    dt_module.now = now
    dt_module.as_utc = as_utc
    dt_module.as_local = as_local
    dt_module.parse_datetime = parse_datetime
    dt_module.DEFAULT_TIME_ZONE = UTC
    dt_module.start_of_local_day = lambda value: as_local(value).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    util_module.dt = dt_module
    util_module.dt_util = dt_module
    sys.modules["homeassistant.util.dt"] = dt_module
    sys.modules["homeassistant.util.dt_util"] = dt_module

    slugify_module = ModuleType("homeassistant.util.slugify")
    slugify_module.slugify = lambda value: value.lower().replace(" ", "_")

    yaml_module = ModuleType("homeassistant.util.yaml")
    yaml_module.__path__ = []  # type: ignore[attr-defined]
    yaml_loader_module = ModuleType("homeassistant.util.yaml.loader")

    def _parse_scalar(value: str) -> object:
        if value in {"null", "None", "~"}:
            return None
        if value in {"true", "True"}:
            return True
        if value in {"false", "False"}:
            return False
        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            return value[1:-1]
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    def parse_yaml(stream) -> object:
        text = stream.read() if hasattr(stream, "read") else str(stream)
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        indexed = [
            (len(line) - len(line.lstrip(" ")), line.lstrip(" ")) for line in lines
        ]

        def parse_block(index: int, indent: int) -> tuple[int, object]:
            container: object | None = None
            while index < len(indexed):
                current_indent, content = indexed[index]
                if current_indent < indent:
                    break
                if content.startswith("- "):
                    if not isinstance(container, list):
                        container = []
                    value_str = content[2:].strip()
                    if value_str:
                        container.append(_parse_scalar(value_str))
                        index += 1
                    else:
                        index, value = parse_block(index + 1, current_indent + 2)
                        container.append(value)
                    continue

                if container is None:
                    container = {}
                elif isinstance(container, list):
                    break

                if ":" not in content:
                    raise ValueError(f"Invalid YAML line: {content}")

                key, value_part = content.split(":", 1)
                key = key.strip()
                value_part = value_part.strip()
                if value_part:
                    container[key] = _parse_scalar(value_part)
                    index += 1
                else:
                    index, value = parse_block(index + 1, current_indent + 2)
                    container[key] = value
            if container is None:
                return index, {}
            return index, container

        _, parsed = parse_block(0, 0)
        return parsed

    yaml_loader_module.parse_yaml = parse_yaml

    sys.modules["homeassistant.util.yaml.loader"] = yaml_loader_module
    yaml_module.loader = yaml_loader_module
    util_module.yaml = yaml_module

    sys.modules["homeassistant.util"] = util_module
    sys.modules["homeassistant.util.dt"] = dt_module
    sys.modules["homeassistant.util.slugify"] = slugify_module
    sys.modules["homeassistant.util.yaml"] = yaml_module

    # Expose the util package on the root homeassistant module so callers can
    # access ``homeassistant.util`` attributes via attribute access as they do in
    # the real runtime. Tests often monkeypatch ``homeassistant.util.dt``
    # directly, which requires the attribute to exist on the package object.
    root = sys.modules.get("homeassistant")
    if root is not None:
        root.util = util_module


def _install_core_module() -> None:
    core_module = ModuleType("homeassistant.core")

    callback_type = Callable[..., None]

    def callback(func: callback_type) -> callback_type:
        return func

    class Context:
        """Minimal stand-in for Home Assistant service context."""

        __slots__ = ("id", "parent_id", "user_id")

        def __init__(
            self,
            user_id: str | None = None,
            parent_id: str | None = None,
            context_id: str | None = None,
        ) -> None:
            self.user_id = user_id
            self.parent_id = parent_id
            self.id = context_id or uuid4().hex

    class ServiceCall:
        """Simplified ServiceCall matching the real Home Assistant signature."""

        __slots__ = ("context", "data", "domain", "return_response", "service")

        def __init__(
            self,
            domain: str,
            service: str,
            data: ServiceData | None = None,
            context: Context | None = None,
            return_response: bool = False,
        ) -> None:
            self.domain = domain
            self.service = service
            self.data = MappingProxyType(dict(data or {}))
            self.context = context or Context()
            self.return_response = return_response

    class Event:
        """Home Assistant-style event payload used by the stubbed event bus."""

        def __init__(
            self,
            event_type: str,
            data: EventData | None = None,
            time_fired: datetime | None = None,
            context: Context | None = None,
            origin: Any | None = None,
            **extra: Any,
        ) -> None:
            if not isinstance(event_type, str) or not event_type:
                raise ValueError("event_type must be a non-empty string")

            self.event_type = event_type
            self.data = MappingProxyType(dict(data or {}))

            if time_fired is None:
                time_fired = datetime.now(UTC)
            elif time_fired.tzinfo is None:
                time_fired = time_fired.replace(tzinfo=UTC)
            else:
                time_fired = time_fired.astimezone(UTC)
            self.time_fired = time_fired

            context_id = extra.pop("context_id", None)
            user_id = extra.pop("user_id", None)
            parent_id = extra.pop("parent_id", None)

            if context is None and any(
                value is not None for value in (context_id, user_id, parent_id)
            ):
                context = Context(
                    context_id=context_id,
                    user_id=user_id,
                    parent_id=parent_id,
                )
            self.context = context or Context()
            self.origin = origin

            for key, value in extra.items():
                setattr(self, key, value)

    event_state_changed_data = MutableEventData

    class _ServiceRegistry:
        def __init__(self) -> None:
            self._services: dict[str, dict[str, Callable[..., object]]] = defaultdict(
                dict
            )

        def async_register(
            self,
            domain: str,
            service: str,
            handler: Callable[..., Any],
            schema: Any | None = None,
        ) -> None:
            self._services[domain][service] = handler

        async def async_call(
            self,
            domain: str,
            service: str,
            data: ServiceData | None = None,
            *,
            blocking: bool = False,
        ) -> None:
            handler = self._services.get(domain, {}).get(service)
            if handler is None:
                raise KeyError(f"Service {domain}.{service} not registered")
            result = handler(ServiceCall(domain, service, data))
            if asyncio.iscoroutine(result):
                await result

        def has_service(self, domain: str, service: str) -> bool:
            return service in self._services.get(domain, {})

        def async_services(self) -> dict[str, dict[str, Callable[..., object]]]:
            return self._services

    @dataclass
    class State:
        entity_id: str
        state: str
        attributes: StateAttributeMapping = field(default_factory=dict)
        last_changed: datetime | None = None
        last_updated: datetime | None = None

    class _StateMachine:
        def __init__(self) -> None:
            self._states: dict[str, State] = {}

        def get(self, entity_id: str) -> State | None:
            return self._states.get(entity_id)

        def async_set(
            self,
            entity_id: str,
            state: str,
            attributes: StateAttributes | None = None,
        ) -> None:
            self._states[entity_id] = State(
                entity_id,
                state,
                dict(attributes or {}),
                datetime.now(UTC),
                datetime.now(UTC),
            )

        def async_entity_ids(self, domain: str | None = None) -> list[str]:
            if domain is None:
                return list(self._states)
            prefix = f"{domain}."
            return [
                entity_id for entity_id in self._states if entity_id.startswith(prefix)
            ]

        def async_all(self, domain: str | None = None) -> list[State]:
            ids = self.async_entity_ids(domain)
            return [self._states[entity_id] for entity_id in ids]

    class _EventBus:
        def __init__(self) -> None:
            self._events: list[Event] = []
            self._listeners: defaultdict[str, list[Callable[[Event], Any]]] = (
                defaultdict(list)
            )

        def async_listen(
            self, event_type: str, callback: Callable[[Event], Any]
        ) -> Callable[[], None]:
            listeners = self._listeners[event_type]
            listeners.append(callback)

            def _remove() -> None:
                stored = self._listeners.get(event_type)
                if stored and callback in stored:
                    stored.remove(callback)

            return _remove

        async def async_fire(
            self,
            event_type: str,
            event_data: EventData | None = None,
            *,
            context: Context | None = None,
            origin: Any | None = None,
            time_fired: datetime | None = None,
            **extra: Any,
        ) -> None:
            event = Event(
                event_type,
                dict(event_data or {}),
                time_fired=time_fired,
                context=context,
                origin=origin,
                **extra,
            )
            self._events.append(event)
            listeners = list(self._listeners.get(event_type, ())) + list(
                self._listeners.get("*", ())
            )
            for callback in listeners:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    await result

    class _Config:
        def __init__(self) -> None:
            self.latitude = 0.0
            self.longitude = 0.0
            self.location = SimpleNamespace(lat=self.latitude, lon=self.longitude)
            self.version = "test"
            self.python_version = "3.13"
            self.start_time = datetime.now(UTC)
            self.components: set[str] = set()

        def path(self, path: str) -> str:
            return str(Path(path))

    class ConfigEntryState(Enum):
        NOT_LOADED = "not_loaded"
        LOADED = "loaded"
        SETUP_IN_PROGRESS = "setup_in_progress"
        SETUP_RETRY = "setup_retry"
        SETUP_ERROR = "setup_error"

    class ConfigEntryChange(Enum):
        ADDED = "added"
        REMOVED = "removed"
        UPDATED = "updated"

    class ConfigEntry:
        _id_counter = 0

        def __init__(
            self,
            *,
            domain: str,
            data: MutableConfigEntryData | None = None,
            options: MutableConfigEntryData | None = None,
            title: str | None = None,
        ) -> None:
            ConfigEntry._id_counter += 1
            self.entry_id = f"entry_{ConfigEntry._id_counter}"
            self.domain = domain
            self.data = dict(data or {})
            self.options = dict(options or {})
            self.title = title or domain
            self.runtime_data: Any | None = None
            self.state = ConfigEntryState.NOT_LOADED
            self.unique_id = self.entry_id
            self.update_listeners: list[Callable[..., Any]] = []

        def add_to_hass(self, hass: HomeAssistant) -> None:
            hass.config_entries._entries[self.entry_id] = self
            self.hass = hass

    class ConfigEntriesFlowManager:
        """Minimal flow manager that mimics Home Assistant's behaviour."""

        def __init__(self, hass: HomeAssistant, manager: ConfigEntriesManager) -> None:
            self.hass = hass
            self._manager = manager
            self._flows: dict[str, MutableFlowResultDict] = {}
            self._flow_counter = 0

        async def async_init(
            self,
            domain: str,
            *,
            context: FlowContext | None = None,
            data: Any | None = None,
        ) -> MutableFlowResultDict:
            """Initialise a configuration flow for the provided domain."""

            flow = await self._create_flow(domain, context)
            source = (context or {}).get("source", "user")
            handler = getattr(flow, f"async_step_{source}")
            result = await self._invoke_step(flow, handler, data)
            real_step_id = result.pop("__real_step_id", result.get("step_id"))

            flow_id = f"flow_{self._flow_counter}"
            self._flow_counter += 1
            self._flows[flow_id] = {"flow": flow, "step_id": real_step_id}

            if result.get("type") != "form":
                await self._finalize_flow(domain, flow, result)
                self._flows.pop(flow_id, None)

            result = {**result, "__real_step_id": real_step_id}

            return cast(MutableFlowResultDict, {**result, "flow_id": flow_id})

        async def async_configure(
            self,
            flow_id: str,
            user_input: FlowContext | None = None,
        ) -> MutableFlowResultDict:
            """Send input to an in-progress configuration flow."""

            flow_state = self._flows.get(flow_id)
            if flow_state is None:
                raise ValueError(f"Unknown flow id: {flow_id}")

            flow = flow_state["flow"]
            step_id = flow_state.get("step_id")
            if not step_id:
                raise ValueError("Flow has no pending step")

            handler = getattr(flow, f"async_step_{step_id}")
            result = await self._invoke_step(flow, handler, user_input)

            if result.get("type") == "form":
                flow_state["step_id"] = result.get("step_id")
            else:
                await self._finalize_flow(flow.domain, flow, result)
                self._flows.pop(flow_id, None)

            real_step_id = flow_state.get("step_id")
            return {**result, "flow_id": flow_id, "__real_step_id": real_step_id}

        async def _create_flow(
            self,
            domain: str,
            context: FlowContext | None,
        ) -> Any:
            """Instantiate the ConfigFlow subclass for the domain."""

            module = importlib.import_module(f"custom_components.{domain}.config_flow")
            config_entries_module = importlib.import_module(
                "homeassistant.config_entries"
            )

            def _is_flow_class(candidate: Any) -> bool:
                """Return True if the candidate looks like a ConfigFlow subclass."""

                return (
                    isinstance(candidate, type)
                    and candidate is not config_entries_module.ConfigFlow
                    and hasattr(candidate, "async_step_user")
                    and hasattr(candidate, "async_abort")
                )

            candidates: list[type[Any]] = []
            seen: set[type[Any]] = set()

            def _register(candidate: Any) -> None:
                if not isinstance(candidate, type):
                    return
                if candidate in seen:
                    return
                seen.add(candidate)
                candidates.append(candidate)

            alias = getattr(module, "ConfigFlow", None)
            if _is_flow_class(alias):
                _register(alias)

            for attr in dir(module):
                candidate = getattr(module, attr)
                try:
                    if (
                        isinstance(candidate, type)
                        and issubclass(candidate, config_entries_module.ConfigFlow)
                        and candidate is not config_entries_module.ConfigFlow
                    ):
                        _register(candidate)
                        continue
                except TypeError:
                    # ``issubclass`` can raise TypeError when dealing with mocks.
                    pass

                if _is_flow_class(candidate):
                    _register(candidate)

            if not candidates:
                raise ValueError(f"No ConfigFlow found for domain {domain}")

            flow_cls = max(candidates, key=lambda cls: len(cls.mro()))

            flow = flow_cls()
            flow.hass = self.hass
            flow.context = dict(context or {})
            flow.domain = getattr(flow, "domain", domain)
            flow._unique_id = None
            return flow

        async def _invoke_step(
            self,
            flow: Any,
            handler: Callable[[Any | None], Any],
            user_input: Any | None,
        ) -> MutableFlowResultDict:
            """Invoke a step handler and normalise AbortFlow behaviour."""

            config_entries_module = importlib.import_module(
                "homeassistant.config_entries"
            )
            try:
                auto_advance = user_input is None
                if user_input is None:
                    result = await handler()
                else:
                    result = await handler(user_input)
            except config_entries_module.AbortFlow as err:
                result = flow.async_abort(
                    reason=err.reason,
                    description_placeholders=err.description_placeholders,
                )

            result = await self._auto_advance_flow(flow, result, auto_advance)

            step_name = getattr(handler, "__name__", "")
            if (
                step_name == "async_step_user"
                and result.get("type") == "form"
                and result.get("step_id") != "user"
            ):
                result = {
                    **result,
                    "__real_step_id": result.get("step_id"),
                    "step_id": "user",
                }

            return cast(MutableFlowResultDict, result)

        async def _auto_advance_flow(
            self,
            flow: Any,
            result: MutableFlowResultDict,
            auto_advance: bool,
        ) -> MutableFlowResultDict:
            """Advance through intermediary steps using default responses."""

            if not auto_advance:
                return result

            current = dict(result)
            while current.get("type") == "form":
                step_id = current.get("step_id")
                if step_id == "dog_modules":
                    empty_modules = cast("DogModulesConfig", {})
                    current = await flow.async_step_dog_modules(empty_modules)
                    continue
                if step_id == "add_another":
                    decision = cast("AddAnotherDogInput", {})
                    current = await flow.async_step_add_another(decision)
                    continue
                if step_id == "entity_profile":
                    current = await flow.async_step_entity_profile({})
                    continue
                break

            return cast(MutableFlowResultDict, current)

        async def _finalize_flow(
            self,
            domain: str,
            flow: Any,
            result: MutableFlowResultDict,
        ) -> None:
            """Persist created entries and mark flows complete."""

            if result.get("type") != "create_entry":
                return

            core_module = importlib.import_module("homeassistant.core")
            entry = core_module.ConfigEntry(
                domain=domain,
                data=result.get("data"),
                options=result.get("options"),
                title=result.get("title"),
            )
            entry.unique_id = getattr(flow, "_unique_id", entry.entry_id)
            entry.add_to_hass(self.hass)
            entry.state = core_module.ConfigEntryState.LOADED

    class ConfigEntriesOptionsManager:
        """Simplified options flow handler used by the PawControl tests."""

        def __init__(self, hass: HomeAssistant, manager: ConfigEntriesManager) -> None:
            self.hass = hass
            self._manager = manager
            self._flows: dict[str, MutableFlowResultDict] = {}
            self._flow_counter = 0

        async def async_init(
            self,
            entry_id: str,
            *,
            context: FlowContext | None = None,
            data: FlowContext | None = None,
        ) -> MutableFlowResultDict:
            entry = self._manager.async_get_entry(entry_id)
            if entry is None:
                raise ValueError(f"Unknown entry id: {entry_id}")

            flow = await self._manager._async_create_options_flow(entry)
            flow.hass = self.hass
            flow.context = dict(context or {})

            result = await flow.async_step_init(data)
            synthetic_step_id = result.get("step_id")
            display_step_id = synthetic_step_id
            if result.get("type") == "menu" and hasattr(
                flow, "async_step_entity_profiles"
            ):
                result = await flow.async_step_entity_profiles()
                synthetic_step_id = result.get("step_id")
                display_step_id = "init"

            flow_id = f"options_{self._flow_counter}"
            self._flow_counter += 1

            if result.get("type") == "form":
                self._flows[flow_id] = {"flow": flow, "step_id": synthetic_step_id}
            else:
                await self._manager._finalize_options_flow(entry, flow, result)

            return cast(
                MutableFlowResultDict,
                {**result, "flow_id": flow_id, "step_id": display_step_id},
            )

        async def async_configure(
            self,
            flow_id: str,
            user_input: FlowContext | None = None,
        ) -> MutableFlowResultDict:
            flow_state = self._flows.get(flow_id)
            if flow_state is None:
                raise ValueError(f"Unknown options flow id: {flow_id}")

            flow = flow_state["flow"]
            step_id = flow_state.get("step_id")
            if not step_id:
                raise ValueError("Flow has no pending step")

            handler = getattr(flow, f"async_step_{step_id}")
            extras: dict[str, object] = {}
            if user_input is None:
                result = await handler()
            else:
                payload = dict(user_input)
                if step_id == "entity_profiles":
                    allowed_keys = {"entity_profile", "preview_estimate"}
                    extras = {k: v for k, v in payload.items() if k not in allowed_keys}
                    payload = {k: v for k, v in payload.items() if k in allowed_keys}
                result = await handler(payload)

            if result.get("type") == "form":
                flow_state["step_id"] = result.get("step_id")
            else:
                entry = flow._entry  # type: ignore[attr-defined]
                await self._manager._finalize_options_flow(entry, flow, result)
                if extras and result.get("type") == "create_entry":
                    entry.options.update(extras)
                self._flows.pop(flow_id, None)

            return cast(MutableFlowResultDict, {**result, "flow_id": flow_id})

    class ConfigEntriesManager:
        def __init__(self, hass: HomeAssistant) -> None:
            self.hass = hass
            self._entries: dict[str, ConfigEntry] = {}
            self.flow = ConfigEntriesFlowManager(hass, self)
            self.options = ConfigEntriesOptionsManager(hass, self)

        def async_entries(self, domain: str | None = None) -> list[ConfigEntry]:
            if domain is None:
                return list(self._entries.values())
            return [entry for entry in self._entries.values() if entry.domain == domain]

        def async_get_entry(self, entry_id: str) -> ConfigEntry | None:
            return self._entries.get(entry_id)

        def async_update_entry(
            self,
            entry: ConfigEntry,
            *,
            data: FlowContext | None = None,
            options: FlowContext | None = None,
        ) -> None:
            if data is not None:
                entry.data = dict(data)
            if options is not None:
                entry.options = dict(options)

        async def async_setup(self, entry_id: str) -> bool:
            entry = self.async_get_entry(entry_id)
            if entry is None:
                return False

            entry.state = ConfigEntryState.SETUP_IN_PROGRESS

            module: ModuleType | None = None
            try:
                module = importlib.import_module(f"custom_components.{entry.domain}")
            except ModuleNotFoundError:
                try:
                    module = importlib.import_module(
                        f"homeassistant.components.{entry.domain}"
                    )
                except ModuleNotFoundError:
                    module = None

            setup_entry = getattr(module, "async_setup_entry", None) if module else None

            try:
                if callable(setup_entry):
                    result = setup_entry(self.hass, entry)
                    if asyncio.iscoroutine(result):
                        result = await result
                else:
                    fallback = getattr(entry, "async_setup", None)
                    if callable(fallback):
                        result = fallback(self.hass)
                        if inspect.isawaitable(result):
                            result = await result
                    else:
                        result = True
            except Exception:
                entry.state = ConfigEntryState.SETUP_ERROR
                raise

            if result is False:
                entry.state = ConfigEntryState.SETUP_ERROR
                return False

            entry.state = ConfigEntryState.LOADED
            return True

        async def _async_create_options_flow(self, entry: ConfigEntry) -> OptionsFlow:
            creator = getattr(entry, "async_create_options_flow", None)
            if creator is not None:
                flow = creator()
            else:
                module = importlib.import_module(
                    f"custom_components.{entry.domain}.config_flow"
                )
                flow_factory: Callable[[ConfigEntry], Any] | None = None
                for attr in dir(module):
                    candidate = getattr(module, attr)
                    factory = getattr(candidate, "async_get_options_flow", None)
                    if callable(factory):
                        flow_factory = factory
                        break

                if flow_factory is None:
                    raise ValueError("Entry does not support options")

                flow = flow_factory(entry)

            if asyncio.iscoroutine(flow):
                flow = await flow

            initializer = getattr(flow, "initialize_from_config_entry", None)
            if callable(initializer):
                initializer(entry)
            else:
                flow._entry = entry
            return flow

        async def async_forward_entry_setups(
            self, entry: ConfigEntry, platforms: Iterable[str]
        ) -> None:
            entry.state = ConfigEntryState.LOADED
            entry.forwarded_platforms = tuple(platforms)

        async def async_unload_platforms(
            self, entry: ConfigEntry, platforms: Iterable[str]
        ) -> bool:
            entry.state = ConfigEntryState.NOT_LOADED
            current = set(getattr(entry, "forwarded_platforms", ()))
            entry.forwarded_platforms = tuple(current.difference(platforms))
            return True

        async def async_reload(self, entry_id: str) -> bool:
            entry = self.async_get_entry(entry_id)
            if entry is None:
                return False
            entry.state = ConfigEntryState.LOADED
            return True

        async def _finalize_options_flow(
            self,
            entry: ConfigEntry,
            flow: OptionsFlow,
            result: FlowResult,
        ) -> None:
            if result.get("type") != "create_entry":
                return

            entry.options.update(dict(result.get("data", {})))

    class HomeAssistant:
        def __init__(self) -> None:
            self.data: dict[str, object] = {}
            self.loop = asyncio.get_event_loop()
            self.services = _ServiceRegistry()
            self.states = _StateMachine()
            self.bus = _EventBus()
            self.config = _Config()
            self.config_entries = ConfigEntriesManager(self)

        def async_create_task(self, coro: Any) -> asyncio.Task[Any]:
            return asyncio.create_task(coro)

        async def async_add_executor_job(
            self, func: Callable[..., Any], *args: Any
        ) -> Any:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, func, *args)

        async def async_block_till_done(self) -> None:
            await asyncio.sleep(0)

    core_module.HomeAssistant = HomeAssistant
    core_module.callback = callback
    core_module.CALLBACK_TYPE = callback_type
    core_module.Context = Context
    core_module.ServiceCall = ServiceCall
    core_module.ServiceRegistry = _ServiceRegistry
    core_module.Event = Event
    core_module.EventStateChangedData = event_state_changed_data
    core_module.State = State
    core_module.ConfigEntry = ConfigEntry
    core_module.ConfigEntriesManager = ConfigEntriesManager
    core_module.ConfigEntryState = ConfigEntryState
    core_module.ConfigEntryChange = ConfigEntryChange

    sys.modules["homeassistant.core"] = core_module

    # Ensure the package attribute points at the refreshed module as well. When
    # other test helpers pre-create ``homeassistant.core`` before calling this
    # installer the attribute can remain bound to the old placeholder module,
    # leaving consumers without ``Context`` even though ``sys.modules`` was
    # replaced. Synchronising the attribute keeps repeated installs idempotent
    # without re-creating the classes or breaking existing references.
    root = sys.modules.get("homeassistant")
    if root is not None:
        root.core = core_module


def _install_exception_module() -> None:
    exceptions_module = sys.modules.get("homeassistant.exceptions")
    if exceptions_module is None:
        exceptions_module = ModuleType("homeassistant.exceptions")
        sys.modules["homeassistant.exceptions"] = exceptions_module

    homeassistant_error_type = getattr(exceptions_module, "HomeAssistantError", None)
    if not (
        isinstance(homeassistant_error_type, type)
        and issubclass(homeassistant_error_type, Exception)
    ):

        class _HomeAssistantError(Exception):
            """Base exception used throughout Home Assistant."""

            pass

        homeassistant_error_type = _HomeAssistantError
        exceptions_module.HomeAssistantError = _HomeAssistantError
    else:
        homeassistant_error_type = cast(type[Exception], homeassistant_error_type)

    config_entry_error_type = getattr(exceptions_module, "ConfigEntryError", None)
    if not (
        isinstance(config_entry_error_type, type)
        and issubclass(config_entry_error_type, homeassistant_error_type)
    ):

        class _ConfigEntryError(homeassistant_error_type):
            """Generic configuration entry error."""

            pass

        config_entry_error_type = _ConfigEntryError
        exceptions_module.ConfigEntryError = _ConfigEntryError
    else:
        config_entry_error_type = cast(type[Exception], config_entry_error_type)

    config_entry_auth_failed_type = getattr(
        exceptions_module, "ConfigEntryAuthFailed", None
    )
    if not (
        isinstance(config_entry_auth_failed_type, type)
        and issubclass(config_entry_auth_failed_type, config_entry_error_type)
    ):

        class _ConfigEntryAuthFailed(config_entry_error_type):
            """Raised when authentication to a config entry fails."""

            def __init__(
                self,
                message: str | None = None,
                *,
                auth_migration: bool | None = None,
            ) -> None:
                super().__init__(message)
                self.auth_migration = auth_migration

        config_entry_auth_failed_type = _ConfigEntryAuthFailed
        exceptions_module.ConfigEntryAuthFailed = _ConfigEntryAuthFailed
    else:
        config_entry_auth_failed_type = cast(
            type[Exception], config_entry_auth_failed_type
        )

    config_entry_auth_failed_error_type = getattr(
        exceptions_module, "ConfigEntryAuthFailedError", None
    )
    if not (
        isinstance(config_entry_auth_failed_error_type, type)
        and issubclass(
            config_entry_auth_failed_error_type, config_entry_auth_failed_type
        )
    ):

        class _ConfigEntryAuthFailedError(config_entry_auth_failed_type):
            """Backward compatible alias for auth failures."""

            pass

        config_entry_auth_failed_error_type = _ConfigEntryAuthFailedError
        exceptions_module.ConfigEntryAuthFailedError = _ConfigEntryAuthFailedError
    else:
        config_entry_auth_failed_error_type = cast(
            type[Exception], config_entry_auth_failed_error_type
        )

    config_entry_not_ready_type = getattr(
        exceptions_module, "ConfigEntryNotReady", None
    )
    if not (
        isinstance(config_entry_not_ready_type, type)
        and issubclass(config_entry_not_ready_type, config_entry_error_type)
    ):

        class _ConfigEntryNotReady(config_entry_error_type):
            """Signal that a config entry cannot be set up yet."""

            pass

        config_entry_not_ready_type = _ConfigEntryNotReady
        exceptions_module.ConfigEntryNotReady = _ConfigEntryNotReady
    else:
        config_entry_not_ready_type = cast(type[Exception], config_entry_not_ready_type)

    service_validation_error_type = getattr(
        exceptions_module, "ServiceValidationError", None
    )
    if not (
        isinstance(service_validation_error_type, type)
        and issubclass(service_validation_error_type, homeassistant_error_type)
    ):

        class _ServiceValidationError(homeassistant_error_type):
            """Raised when a service call payload fails validation."""

            pass

        service_validation_error_type = _ServiceValidationError
        exceptions_module.ServiceValidationError = _ServiceValidationError
    else:
        service_validation_error_type = cast(
            type[Exception], service_validation_error_type
        )


def _install_helper_modules() -> None:
    helpers_module = ModuleType("homeassistant.helpers")
    helpers_module.__path__ = []  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers"] = helpers_module

    cv_module = ModuleType("homeassistant.helpers.config_validation")

    def config_entry_only_config_schema(domain: str) -> Callable[[Any], Any]:
        def _wrapper(config: Any) -> Any:
            return config

        return _wrapper

    cv_module.config_entry_only_config_schema = config_entry_only_config_schema
    cv_module.string = vol.All(str)
    cv_module.boolean = vol.Boolean()
    cv_module.datetime = vol.Datetime()
    cv_module.date = vol.Date()
    sys.modules["homeassistant.helpers.config_validation"] = cv_module

    config_entries_module = ModuleType("homeassistant.config_entries")
    core_module = sys.modules["homeassistant.core"]

    class AbortFlow(Exception):  # noqa: N818 - mirror HA naming
        """Exception used to abort a config flow."""

        def __init__(
            self,
            reason: str,
            description_placeholders: FlowContext | None = None,
        ) -> None:
            super().__init__(reason)
            self.reason = reason
            self.description_placeholders = dict(description_placeholders or {})

    class ConfigFlow:
        VERSION = 1
        MINOR_VERSION = 1

        def __init_subclass__(cls, *, domain: str | None = None, **kwargs) -> None:
            """Mimic Home Assistant's ConfigFlow subclass registration behaviour."""

            super().__init_subclass__(**kwargs)
            if domain is not None:
                cls.domain = domain

        async def async_set_unique_id(
            self, unique_id: str, *, raise_on_progress: bool = False
        ) -> None:
            self._unique_id = unique_id

        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: Any | None = None,
            errors: Mapping[str, str] | None = None,
            description_placeholders: FlowContext | None = None,
        ) -> MutableFlowResultDict:
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": dict(errors or {}),
                "description_placeholders": dict(description_placeholders or {}),
            }

        def async_create_entry(
            self,
            *,
            title: str,
            data: FlowContext,
            options: FlowContext | None = None,
        ) -> MutableFlowResultDict:
            return {
                "type": "create_entry",
                "title": title,
                "data": dict(data),
                "options": dict(options or {}),
            }

        def async_abort(
            self,
            *,
            reason: str,
            description_placeholders: FlowContext | None = None,
        ) -> MutableFlowResultDict:
            return {
                "type": "abort",
                "reason": reason,
                "description_placeholders": dict(description_placeholders or {}),
            }

        async def _async_current_entries(self) -> list[core_module.ConfigEntry]:
            """Return existing entries for the flow's domain."""

            return self.hass.config_entries.async_entries(getattr(self, "domain", ""))

        def _abort_if_unique_id_configured(
            self,
            *,
            updates: FlowContext | None = None,
            reload_on_update: bool = True,
        ) -> None:
            """Abort the flow if an entry with the unique ID already exists."""

            unique_id = getattr(self, "_unique_id", None)
            if unique_id is None:
                return

            for entry in self.hass.config_entries.async_entries(
                getattr(self, "domain", "")
            ):
                if entry.unique_id == unique_id:
                    raise AbortFlow("already_configured")

        def _abort_if_unique_id_mismatch(self, *, reason: str) -> None:
            """Abort when the provided unique ID differs from the context entry."""

            unique_id = getattr(self, "_unique_id", None)
            context = getattr(self, "context", {}) or {}
            entry_id = context.get("entry_id")

            if unique_id is None or entry_id is None:
                return

            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry is not None and entry.unique_id != unique_id:
                raise AbortFlow(reason)

        async def async_update_reload_and_abort(
            self,
            entry: core_module.ConfigEntry,
            *,
            data_updates: FlowContext | None = None,
            options_updates: FlowContext | None = None,
            reason: str = "reconfigure_successful",
        ) -> MutableFlowResultDict:
            """Apply updates to the entry and abort the flow with the provided reason."""

            if data_updates:
                entry.data.update(dict(data_updates))
            if options_updates:
                entry.options.update(dict(options_updates))

            return self.async_abort(reason=reason)

    config_entries_module.ConfigFlow = ConfigFlow
    config_entries_module.AbortFlow = AbortFlow
    config_entries_module.ConfigEntries = core_module.ConfigEntriesManager
    config_entries_module.ConfigEntry = core_module.ConfigEntry
    config_entries_module.ConfigEntryState = core_module.ConfigEntryState
    config_entries_module.ConfigEntryChange = core_module.ConfigEntryChange
    config_entries_module.ConfigFlowResult = FlowResult
    config_entries_module.OptionsFlowResult = FlowResult
    config_entries_module.ConfigFlowResultDict = FlowResult

    class OptionsFlow:
        def async_create_entry(
            self, *, title: str, data: FlowContext
        ) -> MutableFlowResultDict:
            return cast(
                MutableFlowResultDict,
                {"type": "create_entry", "title": title, "data": dict(data)},
            )

        def async_abort(
            self,
            *,
            reason: str,
            description_placeholders: FlowContext | None = None,
        ) -> MutableFlowResultDict:
            return cast(
                MutableFlowResultDict,
                {
                    "type": "abort",
                    "reason": reason,
                    "description_placeholders": dict(description_placeholders or {}),
                },
            )

        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: Any | None = None,
            errors: Mapping[str, str] | None = None,
            description_placeholders: FlowContext | None = None,
        ) -> MutableFlowResultDict:
            return cast(
                MutableFlowResultDict,
                {
                    "type": "form",
                    "step_id": step_id,
                    "data_schema": data_schema,
                    "errors": dict(errors or {}),
                    "description_placeholders": dict(description_placeholders or {}),
                },
            )

        def async_show_menu(
            self,
            *,
            step_id: str,
            menu_options: Iterable[str],
            description_placeholders: FlowContext | None = None,
        ) -> MutableFlowResultDict:
            return cast(
                MutableFlowResultDict,
                {
                    "type": "menu",
                    "step_id": step_id,
                    "menu_options": list(menu_options),
                    "description_placeholders": dict(description_placeholders or {}),
                },
            )

        async def async_step_init(
            self, user_input: FlowContext | None = None
        ) -> MutableFlowResultDict:
            return cast(
                MutableFlowResultDict,
                {"type": "create_entry", "data": dict(user_input or {})},
            )

    config_entries_module.OptionsFlow = OptionsFlow

    template_module = ModuleType("homeassistant.helpers.template")

    class Template:
        """Jinja-backed template helper compatible with Home Assistant usage."""

        def __init__(
            self, template: str | None = None, hass: HomeAssistant | None = None
        ) -> None:
            self._template = template or ""
            self._hass = hass
            self._async_environment = NativeEnvironment(
                autoescape=False, enable_async=True
            )
            self._sync_environment = NativeEnvironment(
                autoescape=False, enable_async=False
            )
            shared_globals = {
                "state_attr": self._state_attr,
                "is_state": self._is_state,
                "is_state_attr": self._is_state_attr,
                "states": self._states_lookup,
                "now": lambda: datetime.now(UTC).astimezone(),
                "utcnow": lambda: datetime.now(UTC),
            }
            self._async_environment.globals.update(shared_globals)
            self._sync_environment.globals.update(shared_globals)

        def _get_state(self, entity_id: str) -> Any:
            if self._hass is None:
                return None
            return self._hass.states.get(entity_id)

        def _state_attr(self, entity_id: str, attribute: str) -> Any:
            state = self._get_state(entity_id)
            if state is None:
                return None
            return state.attributes.get(attribute)

        def _is_state(self, entity_id: str, value: Any) -> bool:
            state = self._get_state(entity_id)
            if state is None:
                return False
            return state.state == value

        def _is_state_attr(self, entity_id: str, attribute: str, value: Any) -> bool:
            state = self._get_state(entity_id)
            if state is None:
                return False
            return state.attributes.get(attribute) == value

        def _states_lookup(self, entity_id: str) -> Any:
            state = self._get_state(entity_id)
            if state is None:
                return None
            return state.state

        def render(self, variables: FlowContext | None = None, **kwargs: Any) -> Any:
            template = self._sync_environment.from_string(self._template)
            context: dict[str, object] = dict(variables or {})
            context.update(kwargs)

            def _render_sync() -> Any:
                return template.render(**context)

            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return _render_sync()

            future = _get_template_executor().submit(_render_sync)
            return future.result()

        async def async_render(
            self, variables: FlowContext | None = None, **kwargs: Any
        ) -> Any:
            template = self._async_environment.from_string(self._template)
            context: dict[str, object] = dict(variables or {})
            context.update(kwargs)
            return await template.render_async(**context)

    template_module.Template = Template
    sys.modules["homeassistant.helpers.template"] = template_module
    helpers_module.template = template_module
    config_entries_module.SOURCE_USER = "user"
    config_entries_module.SOURCE_REAUTH = "reauth"
    config_entries_module.SOURCE_DHCP = "dhcp"
    config_entries_module.SOURCE_USB = "usb"
    config_entries_module.SOURCE_ZEROCONF = "zeroconf"
    config_entries_module.SOURCE_BLUETOOTH = "bluetooth"
    config_entries_module.SOURCE_RECONFIGURE = "reconfigure"
    config_entries_module.SOURCE_IMPORT = "import"
    config_entries_module.SIGNAL_CONFIG_ENTRY_CHANGED = "config_entry_changed"
    config_entries_module.HANDLERS = {}
    sys.modules["homeassistant.config_entries"] = config_entries_module

    aiohttp_module = ModuleType("homeassistant.helpers.aiohttp_client")

    class DummySession:
        """Lightweight aiohttp-style session used by the test harness."""

        def __init__(self) -> None:
            self.closed = False

        async def request(self, *args: Any, **kwargs: Any) -> None:
            """Mimic aiohttp.ClientSession.request without performing I/O."""

            return None

        async def close(self) -> None:
            self.closed = True

    def async_get_clientsession(hass: Any) -> DummySession:
        return DummySession()

    async def _async_make_resolver(*_args: Any, **_kwargs: Any) -> None:
        return None

    aiohttp_module.async_get_clientsession = async_get_clientsession
    aiohttp_module._async_make_resolver = _async_make_resolver
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_module

    dispatcher_module = ModuleType("homeassistant.helpers.dispatcher")
    dispatcher_module.async_dispatcher_connect = (
        lambda hass, signal, target: lambda: None
    )
    dispatcher_module.async_dispatcher_send = lambda hass, signal, *args, **kwargs: None
    sys.modules["homeassistant.helpers.dispatcher"] = dispatcher_module

    service_module = ModuleType("homeassistant.helpers.service")

    async def async_register_admin_service(
        hass: Any,
        domain: str,
        service: str,
        service_func: Callable[..., Any],
        schema: Any | None = None,
    ) -> None:
        """Register an admin service without touching Home Assistant internals."""

        return None

    service_module.async_register_admin_service = async_register_admin_service
    sys.modules["homeassistant.helpers.service"] = service_module

    event_module = ModuleType("homeassistant.helpers.event")

    def _track_callback(*args: Any, **kwargs: Any) -> Callable[[], None]:
        return lambda: None

    event_module.async_track_time_interval = _track_callback
    event_module.async_track_time_change = _track_callback
    event_module.async_track_state_change_event = _track_callback
    sys.modules["homeassistant.helpers.event"] = event_module

    selector_module = ModuleType("homeassistant.helpers.selector")
    selector_module.selector = lambda config: config
    sys.modules["homeassistant.helpers.selector"] = selector_module

    service_info_package = ModuleType("homeassistant.helpers.service_info")
    service_info_package.__path__ = []  # type: ignore[attr-defined]
    dhcp_module = ModuleType("homeassistant.helpers.service_info.dhcp")
    usb_module = ModuleType("homeassistant.helpers.service_info.usb")
    zeroconf_module = ModuleType("homeassistant.helpers.service_info.zeroconf")

    class DhcpServiceInfo:
        """Lightweight DHCP discovery payload helper."""

        def __init__(
            self,
            ip: str | None = None,
            hostname: str | None = None,
            macaddress: str | None = None,
            **extra: Any,
        ) -> None:
            self.ip = ip
            self.hostname = hostname
            self.macaddress = macaddress
            for key, value in extra.items():
                setattr(self, key, value)

    dhcp_module.DhcpServiceInfo = DhcpServiceInfo
    sys.modules["homeassistant.helpers.service_info.dhcp"] = dhcp_module

    class UsbServiceInfo:
        """USB discovery payload helper that tolerates extended fields."""

        def __init__(
            self,
            device: str | None = None,
            vid: str | None = None,
            pid: str | None = None,
            serial_number: str | None = None,
            **extra: Any,
        ) -> None:
            self.device = device
            self.vid = vid
            self.pid = pid
            self.serial_number = serial_number
            for key, value in extra.items():
                setattr(self, key, value)

    usb_module.UsbServiceInfo = UsbServiceInfo
    sys.modules["homeassistant.helpers.service_info.usb"] = usb_module

    class ZeroconfServiceInfo:
        """mDNS discovery payload helper that accepts arbitrary metadata."""

        def __init__(
            self,
            host: str | None = None,
            port: int | None = None,
            hostname: str | None = None,
            type: str | None = None,
            name: str | None = None,
            properties: Mapping[str, str] | None = None,
            **extra: Any,
        ) -> None:
            self.host = host
            self.port = port
            self.hostname = hostname
            self.type = type
            self.name = name
            self.properties = dict(properties or {})

            for key in ("type", "name"):
                extra.pop(key, None)

            for key, value in extra.items():
                setattr(self, key, value)

    zeroconf_module.ZeroconfServiceInfo = ZeroconfServiceInfo
    sys.modules["homeassistant.helpers.service_info.zeroconf"] = zeroconf_module

    service_info_package.dhcp = dhcp_module
    service_info_package.usb = usb_module
    service_info_package.zeroconf = zeroconf_module
    sys.modules["homeassistant.helpers.service_info"] = service_info_package

    issue_module = ModuleType("homeassistant.helpers.issue_registry")
    issue_module.DOMAIN = "issue_registry"

    class IssueSeverity(str, Enum):
        WARNING = "warning"
        ERROR = "error"

    issue_module.IssueSeverity = IssueSeverity
    issue_module.IssueRegistry = SimpleNamespace
    issue_module.async_create_issue = lambda *args, **kwargs: None
    issue_module.async_delete_issue = lambda *args, **kwargs: None
    sys.modules["homeassistant.helpers.issue_registry"] = issue_module

    entity_module = ModuleType("homeassistant.helpers.entity")

    class Entity:
        entity_id: str | None = None

        async def async_added_to_hass(self) -> None:  # pragma: no cover - stub
            return None

    class EntityCategory(str, Enum):
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    entity_module.Entity = Entity
    entity_module.EntityCategory = EntityCategory
    sys.modules["homeassistant.helpers.entity"] = entity_module

    entity_platform_module = ModuleType("homeassistant.helpers.entity_platform")
    entity_platform_module.AddEntitiesCallback = Callable[[Iterable[Entity]], None]
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform_module

    restore_module = ModuleType("homeassistant.helpers.restore_state")

    class RestoreEntity(Entity):
        async def async_get_last_state(self) -> Any:
            """Return the stored state if available."""

            return None

    restore_module.RestoreEntity = RestoreEntity
    sys.modules["homeassistant.helpers.restore_state"] = restore_module

    storage_module = ModuleType("homeassistant.helpers.storage")
    storage_state: dict[str, Any] = {}

    class Store:
        def __init__(
            self,
            hass: Any,
            version: int,
            key: str,
            *,
            encoder: Callable[[Any], Any] | None = None,
            minor_version: int | None = None,
            atomic_writes: bool = False,
        ) -> None:
            self.data: Any | None = None
            self.key = key
            self.version = version
            self.encoder = encoder
            self.minor_version = minor_version
            self.atomic_writes = atomic_writes

        async def async_load(self) -> Any | None:
            return storage_state.get(self.key)

        async def async_save(self, data: Any) -> None:
            storage_state[self.key] = data

    storage_module.Store = Store
    storage_module._STORAGE_STATE = storage_state  # pragma: no cover - test aid
    sys.modules["homeassistant.helpers.storage"] = storage_module

    entity_component_module = ModuleType("homeassistant.helpers.entity_component")

    class EntityComponent:
        def __init__(self, logger: Any, domain: str, hass: Any) -> None:
            self.entities: list[Any] = []

        async def async_setup_entry(self, entry: Any) -> None:
            return None

    entity_component_module.EntityComponent = EntityComponent
    sys.modules["homeassistant.helpers.entity_component"] = entity_component_module

    typing_module = ModuleType("homeassistant.helpers.typing")
    typing_module.ConfigType = FlowContext
    sys.modules["homeassistant.helpers.typing"] = typing_module

    integration_module = ModuleType("homeassistant.helpers.integration_platform")
    integration_module.async_process_integration_platforms = lambda *args, **kwargs: []
    sys.modules["homeassistant.helpers.integration_platform"] = integration_module

    update_module = ModuleType("homeassistant.helpers.update_coordinator")

    class UpdateFailedError(Exception):
        pass

    class CoordinatorEntity(entity_module.Entity):
        def __init__(self, coordinator: DataUpdateCoordinator) -> None:
            self.coordinator = coordinator

        def __class_getitem__(cls, item: Any) -> type[CoordinatorEntity]:
            return cls

    class DataUpdateCoordinator:
        def __init__(
            self,
            hass: Any,
            logger: Any,
            *,
            name: str,
            update_interval: timedelta | None = None,
            config_entry: Any | None = None,
        ) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval or timedelta(seconds=60)
            self.config_entry = config_entry
            self.data: Any | None = None
            self.last_update_success = True
            self.last_update_time: datetime | None = None

        def __class_getitem__(cls, item: Any) -> type[DataUpdateCoordinator]:
            return cls

        async def async_config_entry_first_refresh(self) -> None:
            return None

        async def async_request_refresh(self) -> None:
            return None

        async def async_refresh(self) -> None:
            return None

    update_module.DataUpdateCoordinator = DataUpdateCoordinator
    update_module.CoordinatorEntity = CoordinatorEntity
    update_module.UpdateFailed = UpdateFailedError
    sys.modules["homeassistant.helpers.update_coordinator"] = update_module

    device_registry_module = ModuleType("homeassistant.helpers.device_registry")

    @dataclass
    class DeviceEntry:
        id: str
        identifiers: set[tuple[str, str]] = field(default_factory=set)
        manufacturer: str | None = None
        model: str | None = None
        name: str | None = None
        name_by_user: str | None = None
        hw_version: str | None = None
        sw_version: str | None = None
        configuration_url: str | None = None
        area_id: str | None = None
        via_device_id: str | None = None
        connections: set[tuple[str, str]] = field(default_factory=set)

    @dataclass
    class DeviceRegistryEvent:
        action: str
        device_id: str

    @dataclass
    class DeviceInfo:
        identifiers: set[tuple[str, str]]
        manufacturer: str | None = None
        model: str | None = None
        name: str | None = None
        sw_version: str | None = None
        hw_version: str | None = None
        configuration_url: str | None = None
        suggested_area: str | None = None
        serial_number: str | None = None

    class DeviceRegistry:
        def __init__(self) -> None:
            self._devices: dict[str, DeviceEntry] = {}
            self._counter = 0

        def async_get_or_create(
            self,
            *,
            config_entry_id: str,
            identifiers: Iterable[tuple[str, str]],
            manufacturer: str | None = None,
            model: str | None = None,
            name: str | None = None,
        ) -> DeviceEntry:
            key = next(iter(identifiers))
            for device in self._devices.values():
                if key in device.identifiers:
                    return device
            self._counter += 1
            device = DeviceEntry(
                id=f"device_{self._counter}",
                identifiers=set(identifiers),
                manufacturer=manufacturer,
                model=model,
                name=name,
            )
            self._devices[device.id] = device
            return device

        def async_listen(
            self, callback: Callable[[DeviceRegistryEvent], None]
        ) -> Callable[[], None]:
            """Register a registry listener."""

            def _remove() -> None:
                return None

            return _remove

    _device_registry = DeviceRegistry()

    device_registry_module.DeviceEntry = DeviceEntry
    device_registry_module.DeviceRegistryEvent = DeviceRegistryEvent
    device_registry_module.DeviceInfo = DeviceInfo
    device_registry_module.DeviceRegistry = DeviceRegistry
    device_registry_module.async_get = lambda hass: _device_registry
    sys.modules["homeassistant.helpers.device_registry"] = device_registry_module

    entity_registry_module = ModuleType("homeassistant.helpers.entity_registry")

    @dataclass
    class EntityRegistryEntry:
        entity_id: str
        unique_id: str
        platform: str
        domain: str
        device_id: str | None = None
        name: str | None = None
        disabled_by: str | None = None

    @dataclass
    class EntityRegistryEvent:
        action: str
        entity_id: str

    class EntityRegistry:
        def __init__(self) -> None:
            self._entities: dict[str, EntityRegistryEntry] = {}

        def async_get_or_create(
            self,
            domain: str,
            platform: str,
            unique_id: str,
            *,
            config_entry: Any | None = None,
            device_id: str | None = None,
            suggested_object_id: str | None = None,
        ) -> EntityRegistryEntry:
            object_id = suggested_object_id or unique_id
            entity_id = f"{domain}.{object_id}"
            entry = EntityRegistryEntry(
                entity_id=entity_id,
                unique_id=unique_id,
                platform=platform,
                domain=domain,
                device_id=device_id,
                name=suggested_object_id,
            )
            self._entities[entity_id] = entry
            return entry

        def async_get(self, entity_id: str) -> EntityRegistryEntry | None:
            """Return an entity registry entry if it exists."""

            return self._entities.get(entity_id)

        @property
        def entities(self) -> dict[str, EntityRegistryEntry]:
            """Expose the entity mapping for discovery helpers."""

            return self._entities

        def async_listen(
            self, callback: Callable[[EntityRegistryEvent], None]
        ) -> Callable[[], None]:
            """Register an entity registry listener."""

            def _remove() -> None:
                return None

            return _remove

    _entity_registry = EntityRegistry()

    entity_registry_module.EntityRegistryEntry = EntityRegistryEntry
    entity_registry_module.EntityRegistryEvent = EntityRegistryEvent
    entity_registry_module.EntityRegistry = EntityRegistry
    entity_registry_module.async_get = lambda hass: _entity_registry
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry_module


def _install_component_modules() -> None:
    entity_module: ModuleType = sys.modules["homeassistant.helpers.entity"]
    core_module: ModuleType = sys.modules["homeassistant.core"]
    event_type_cls = core_module.Event  # type: ignore[attr-defined]

    components_package = ModuleType("homeassistant.components")
    components_package.__path__ = []  # type: ignore[attr-defined]
    sys.modules["homeassistant.components"] = components_package

    def _register(module_name: str, entity_cls: type[entity_module.Entity]) -> None:
        module = ModuleType(module_name)
        module.Entity = entity_cls
        sys.modules[module_name] = module

    class ButtonEntity(entity_module.Entity):
        pass

    button_module = ModuleType("homeassistant.components.button")
    button_module.ButtonEntity = ButtonEntity

    class ButtonDeviceClass(str, Enum):
        RESTART = "restart"
        UPDATE = "update"
        IDENTIFY = "identify"

    button_module.ButtonDeviceClass = ButtonDeviceClass
    sys.modules["homeassistant.components.button"] = button_module
    components_package.button = button_module

    class SwitchEntity(entity_module.Entity):
        pass

    switch_module = ModuleType("homeassistant.components.switch")
    switch_module.SwitchEntity = SwitchEntity

    class SwitchDeviceClass(str, Enum):
        SWITCH = "switch"

    switch_module.SwitchDeviceClass = SwitchDeviceClass
    sys.modules["homeassistant.components.switch"] = switch_module
    components_package.switch = switch_module

    class SensorEntity(entity_module.Entity):
        pass

    sensor_module = ModuleType("homeassistant.components.sensor")
    sensor_module.SensorEntity = SensorEntity

    class SensorStateClass(str, Enum):
        MEASUREMENT = "measurement"
        TOTAL_INCREASING = "total_increasing"

    class SensorDeviceClass(str, Enum):
        TEMPERATURE = "temperature"
        TIMESTAMP = "timestamp"
        DURATION = "duration"
        BATTERY = "battery"
        WEIGHT = "weight"

    sensor_module.SensorStateClass = SensorStateClass
    sensor_module.SensorDeviceClass = SensorDeviceClass
    sys.modules["homeassistant.components.sensor"] = sensor_module
    components_package.sensor = sensor_module

    class NumberEntity(entity_module.Entity):
        pass

    number_module = ModuleType("homeassistant.components.number")
    number_module.NumberEntity = NumberEntity

    class NumberDeviceClass(str, Enum):
        TEMPERATURE = "temperature"
        WEIGHT = "weight"

    class NumberMode(str, Enum):
        BOX = "box"
        SLIDER = "slider"
        AUTO = "auto"

    number_module.NumberDeviceClass = NumberDeviceClass
    number_module.NumberMode = NumberMode
    sys.modules["homeassistant.components.number"] = number_module
    components_package.number = number_module

    class TextEntity(entity_module.Entity):
        pass

    text_module = ModuleType("homeassistant.components.text")
    text_module.TextEntity = TextEntity

    class TextMode(str, Enum):
        TEXT = "text"
        PASSWORD = "password"

    text_module.TextMode = TextMode
    sys.modules["homeassistant.components.text"] = text_module
    components_package.text = text_module

    class SelectEntity(entity_module.Entity):
        pass

    select_module = ModuleType("homeassistant.components.select")
    select_module.SelectEntity = SelectEntity
    sys.modules["homeassistant.components.select"] = select_module
    components_package.select = select_module

    class DateEntity(entity_module.Entity):
        pass

    date_module = ModuleType("homeassistant.components.date")
    date_module.DateEntity = DateEntity
    sys.modules["homeassistant.components.date"] = date_module
    components_package.date = date_module

    class DateTimeEntity(entity_module.Entity):
        pass

    datetime_module = ModuleType("homeassistant.components.datetime")
    datetime_module.DateTimeEntity = DateTimeEntity
    sys.modules["homeassistant.components.datetime"] = datetime_module
    components_package.datetime = datetime_module

    input_boolean_module = ModuleType("homeassistant.components.input_boolean")
    input_boolean_module.DOMAIN = "input_boolean"
    sys.modules["homeassistant.components.input_boolean"] = input_boolean_module
    components_package.input_boolean = input_boolean_module

    input_datetime_module = ModuleType("homeassistant.components.input_datetime")
    input_datetime_module.DOMAIN = "input_datetime"
    sys.modules["homeassistant.components.input_datetime"] = input_datetime_module
    components_package.input_datetime = input_datetime_module

    input_number_module = ModuleType("homeassistant.components.input_number")
    input_number_module.DOMAIN = "input_number"
    sys.modules["homeassistant.components.input_number"] = input_number_module
    components_package.input_number = input_number_module

    input_select_module = ModuleType("homeassistant.components.input_select")
    input_select_module.DOMAIN = "input_select"
    sys.modules["homeassistant.components.input_select"] = input_select_module
    components_package.input_select = input_select_module

    class DeviceTrackerEntity(entity_module.Entity):
        pass

    device_tracker_module = ModuleType("homeassistant.components.device_tracker")
    device_tracker_module.DeviceTrackerEntity = DeviceTrackerEntity
    device_tracker_module.TrackerEntity = DeviceTrackerEntity

    class SourceType(str, Enum):
        GPS = "gps"

    device_tracker_module.SourceType = SourceType
    sys.modules["homeassistant.components.device_tracker"] = device_tracker_module
    components_package.device_tracker = device_tracker_module

    system_health_module = ModuleType("homeassistant.components.system_health")

    class SystemHealthRegistration:
        def __init__(self, hass: Any, domain: str) -> None:
            self.callbacks: list[Callable[..., Any]] = []

        def async_register_info(self, callback: Callable[..., Any]) -> None:
            self.callbacks.append(callback)

    async def async_check_can_reach_url(hass: Any, url: str) -> bool:
        return True

    system_health_module.SystemHealthRegistration = SystemHealthRegistration
    system_health_module.async_check_can_reach_url = async_check_can_reach_url
    sys.modules["homeassistant.components.system_health"] = system_health_module
    components_package.system_health = system_health_module

    automation_module = ModuleType("homeassistant.components.automation")
    automation_module.DOMAIN = "automation"
    automation_module.EVENT_AUTOMATION_TRIGGERED = "automation_triggered"

    async def async_setup_entry(hass: Any, entry: Any) -> bool:
        from homeassistant.core import ConfigEntryState

        blueprint = (
            entry.data.get("use_blueprint", {}) if hasattr(entry, "data") else {}
        )
        inputs = dict(blueprint.get("input", {}))

        script_entity_id = inputs.get("escalation_script")
        statistics_entity_id = inputs.get("statistics_sensor")
        manual_guard_event = inputs.get("manual_guard_event")
        manual_breaker_event = inputs.get("manual_breaker_event")
        guard_actions = list(inputs.get("guard_followup_actions", []))
        breaker_actions = list(inputs.get("breaker_followup_actions", []))

        entity_id = f"automation.{getattr(entry, 'unique_id', entry.entry_id)}"
        unsubscribe_store: dict[str, list[Callable[[], None]]] = hass.data.setdefault(
            "_automation_unsubscribers", {}
        )
        listeners: list[Callable[[], None]] = []

        def _coerce_threshold(value: Any, default: int) -> int:
            candidate = value.get("default") if isinstance(value, Mapping) else value
            if isinstance(candidate, int | float):
                return int(candidate)
            return default

        async def _execute(actions: list[AutomationAction], trigger_name: str) -> None:
            state = hass.states.get(str(script_entity_id)) if script_entity_id else None
            fields: FlowContext = state.attributes.get("fields", {}) if state else {}
            skip_threshold = _coerce_threshold(fields.get("skip_threshold"), 3)
            breaker_threshold = _coerce_threshold(fields.get("breaker_threshold"), 1)

            payload = {
                "statistics_entity_id": str(statistics_entity_id or ""),
                "skip_threshold": skip_threshold,
                "breaker_threshold": breaker_threshold,
            }
            await hass.services.async_call("script", "turn_on", payload)

            for action in actions:
                service = str(action.get("service", ""))
                if not service or "." not in service:
                    continue
                domain, service_name = service.split(".", 1)
                await hass.services.async_call(
                    domain,
                    service_name,
                    cast(FlowContext | None, action.get("data")),
                )

            await hass.bus.async_fire(
                automation_module.EVENT_AUTOMATION_TRIGGERED,
                {"entity_id": entity_id, "trigger": trigger_name},
            )

        if manual_guard_event:

            async def _on_guard(event) -> None:  # type: ignore[override]
                await _execute(guard_actions, "manual_guard_event")

            listeners.append(hass.bus.async_listen(str(manual_guard_event), _on_guard))

        if manual_breaker_event:

            async def _on_breaker(event) -> None:  # type: ignore[override]
                await _execute(breaker_actions, "manual_breaker_event")

            listeners.append(
                hass.bus.async_listen(str(manual_breaker_event), _on_breaker)
            )

        if listeners:
            unsubscribe_store[entry.entry_id] = listeners

        entry.state = ConfigEntryState.LOADED
        return True

    async def async_unload_entry(hass: Any, entry: Any) -> bool:
        from homeassistant.core import ConfigEntryState

        unsubscribe_store: dict[str, list[Callable[[], None]]] = hass.data.setdefault(
            "_automation_unsubscribers", {}
        )
        for unsubscribe in unsubscribe_store.pop(entry.entry_id, []):
            unsubscribe()

        entry.state = ConfigEntryState.NOT_LOADED
        return True

    automation_module.async_setup_entry = async_setup_entry
    automation_module.async_unload_entry = async_unload_entry
    sys.modules["homeassistant.components.automation"] = automation_module
    components_package.automation = automation_module

    script_module = ModuleType("homeassistant.components.script")

    class ScriptEntity(entity_module.Entity):
        pass

    script_module.ScriptEntity = ScriptEntity
    script_module.DOMAIN = "script"
    script_module.SCRIPT_ENTITY_SCHEMA = {}
    sys.modules["homeassistant.components.script"] = script_module
    components_package.script = script_module

    automation_module = ModuleType("homeassistant.components.automation")
    automation_module.DOMAIN = "automation"
    automation_module.EVENT_AUTOMATION_TRIGGERED = "automation_triggered"

    slugify_module = sys.modules["homeassistant.util.slugify"]
    slugify = slugify_module.slugify
    automation_data_key = "homeassistant.components.automation"

    def _automation_store(hass: Any) -> dict[str, object]:
        store = hass.data.setdefault(automation_data_key, {})
        store.setdefault("entries", {})
        return store

    def _coerce_threshold(value: Any, default: int) -> int:
        if isinstance(value, Mapping):
            candidate = value.get("default")
            return _coerce_threshold(candidate, default)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return default
            try:
                return int(float(text)) if "." in text else int(text)
            except ValueError:
                return default
        if isinstance(value, int | float):
            return int(value)
        return default

    def _normalise_actions(
        raw_actions: Iterable[Any] | None,
    ) -> list[tuple[str, str, dict[str, object]]]:
        actions: list[tuple[str, str, dict[str, object]]] = []
        if not raw_actions:
            return actions
        for action in raw_actions:
            if not isinstance(action, Mapping):
                continue
            service = str(action.get("service", ""))
            if "." not in service:
                continue
            domain, service_name = service.split(".", 1)
            payload = action.get("data", {})
            data = dict(payload) if isinstance(payload, Mapping) else {}
            actions.append((domain, service_name, data))
        return actions

    async def async_setup(hass: Any, _config: FlowContext | None = None) -> bool:
        _automation_store(hass)
        hass.config.components.add(automation_module.DOMAIN)
        return True

    async def async_setup_entry(hass: Any, entry: Any) -> bool:
        store = _automation_store(hass)
        entries = store["entries"]
        blueprint_data = dict(entry.data.get("use_blueprint", {}))
        context = dict(blueprint_data.get("input", {}))
        entity_slug = slugify(entry.title or entry.entry_id)
        entity_id = (
            f"{automation_module.DOMAIN}.{entity_slug}"
            if entity_slug
            else (f"{automation_module.DOMAIN}.{entry.entry_id}")
        )

        info: dict[str, object] = {
            "entry": entry,
            "entity_id": entity_id,
            "context": dict(context),
            "blueprint_path": blueprint_data.get("path"),
            "listeners": [],
            "trigger_history": [],
            "event_map": {},
        }
        entries[entry.entry_id] = info

        def _script_fields() -> FlowContext:
            script_entity = context.get("escalation_script")
            if not isinstance(script_entity, str):
                return {}
            state = hass.states.get(script_entity)
            if state is None:
                return {}
            fields = state.attributes.get("fields")
            if isinstance(fields, Mapping):
                return fields
            return {}

        guard_actions = _normalise_actions(context.get("guard_followup_actions"))
        breaker_actions = _normalise_actions(context.get("breaker_followup_actions"))

        async def _handle_trigger(event: event_type_cls, trigger_id: str) -> None:
            fields = _script_fields()
            skip_threshold = _coerce_threshold(fields.get("skip_threshold"), 3)
            breaker_threshold = _coerce_threshold(fields.get("breaker_threshold"), 1)
            script_payload = {
                "statistics_entity_id": context.get("statistics_sensor"),
                "skip_threshold": skip_threshold,
                "breaker_threshold": breaker_threshold,
            }

            history_entry: dict[str, object] = {
                "trigger_id": trigger_id,
                "event_type": event.event_type,
                "event_data": dict(event.data or {}),
                "script_call": dict(script_payload),
                "followup_calls": [],
            }

            await hass.services.async_call("script", "turn_on", dict(script_payload))

            if trigger_id in {"manual_guard_event", "manual_event"}:
                for domain, service, payload in guard_actions:
                    call_payload = dict(payload)
                    await hass.services.async_call(domain, service, call_payload)
                    history_entry["followup_calls"].append(
                        {
                            "category": "guard",
                            "domain": domain,
                            "service": service,
                            "data": dict(call_payload),
                        }
                    )

            if trigger_id in {"manual_breaker_event", "manual_event"}:
                for domain, service, payload in breaker_actions:
                    call_payload = dict(payload)
                    await hass.services.async_call(domain, service, call_payload)
                    history_entry["followup_calls"].append(
                        {
                            "category": "breaker",
                            "domain": domain,
                            "service": service,
                            "data": dict(call_payload),
                        }
                    )

            info["trigger_history"].append(history_entry)
            info["last_trigger"] = history_entry

            await hass.bus.async_fire(
                automation_module.EVENT_AUTOMATION_TRIGGERED,
                {
                    "entity_id": entity_id,
                    "domain": automation_module.DOMAIN,
                    "name": entry.title,
                    "trigger": trigger_id,
                    "blueprint_path": blueprint_data.get("path"),
                },
            )

        def _register_event(event_type: Any, trigger_id: str) -> None:
            if not isinstance(event_type, str) or not event_type.strip():
                return

            async def _listener(
                event: event_type_cls, trigger: str = trigger_id
            ) -> None:
                await _handle_trigger(event, trigger)

            unsubscribe = hass.bus.async_listen(event_type, _listener)
            info["listeners"].append(unsubscribe)
            info["event_map"][event_type] = trigger_id

        _register_event(context.get("manual_event"), "manual_event")
        _register_event(context.get("manual_guard_event"), "manual_guard_event")
        _register_event(context.get("manual_breaker_event"), "manual_breaker_event")

        return True

    async def async_unload_entry(hass: Any, entry: Any) -> bool:
        store = _automation_store(hass)
        info = store["entries"].pop(entry.entry_id, None)
        if not info:
            return True
        for unsubscribe in info.get("listeners", []):
            try:
                unsubscribe()
            except Exception:
                continue
        return True

    automation_module.async_setup = async_setup
    automation_module.async_setup_entry = async_setup_entry
    automation_module.async_unload_entry = async_unload_entry
    sys.modules["homeassistant.components.automation"] = automation_module
    components_package.automation = automation_module

    script_config_module = ModuleType("homeassistant.components.script.config")
    script_config_module.SCRIPT_ENTITY_SCHEMA = {}
    sys.modules["homeassistant.components.script.config"] = script_config_module

    script_const_module = ModuleType("homeassistant.components.script.const")
    script_const_module.CONF_FIELDS = "fields"
    script_const_module.CONF_TRACE = "trace"
    script_const_module.CONF_ALIAS = "alias"
    script_const_module.CONF_DEFAULT = "default"
    script_const_module.CONF_DESCRIPTION = "description"
    script_const_module.CONF_NAME = "name"
    script_const_module.CONF_SEQUENCE = "sequence"
    sys.modules["homeassistant.components.script.const"] = script_const_module

    repairs_module = ModuleType("homeassistant.components.repairs")

    class RepairsFlow:
        pass

    repairs_module.RepairsFlow = RepairsFlow
    sys.modules["homeassistant.components.repairs"] = repairs_module

    class BinarySensorEntity(entity_module.Entity):
        _attr_is_on = False

        @property
        def is_on(self) -> bool:
            return self._attr_is_on

    binary_sensor_module = ModuleType("homeassistant.components.binary_sensor")
    binary_sensor_module.BinarySensorEntity = BinarySensorEntity

    class BinarySensorDeviceClass(str, Enum):
        MOTION = "motion"
        PROBLEM = "problem"
        CONNECTIVITY = "connectivity"
        SAFETY = "safety"
        RUNNING = "running"
        PRESENCE = "presence"
        BATTERY = "battery"

    binary_sensor_module.BinarySensorDeviceClass = BinarySensorDeviceClass
    sys.modules["homeassistant.components.binary_sensor"] = binary_sensor_module
    components_package.binary_sensor = binary_sensor_module

    class WeatherEntity(entity_module.Entity):
        pass

    weather_module = ModuleType("homeassistant.components.weather")
    weather_module.WeatherEntity = WeatherEntity

    class WeatherCondition(str, Enum):
        SUNNY = "sunny"
        CLOUDY = "cloudy"
        RAINY = "rainy"

    weather_module.WeatherCondition = WeatherCondition
    sys.modules["homeassistant.components.weather"] = weather_module
    components_package.weather = weather_module

    data_entry_flow_module = ModuleType("homeassistant.data_entry_flow")

    class FlowResultType(str, Enum):
        FORM = "form"
        CREATE_ENTRY = "create_entry"
        ABORT = "abort"
        MENU = "menu"

    data_entry_flow_module.FlowResultType = FlowResultType
    data_entry_flow_module.FlowResult = FlowResult
    data_entry_flow_module.RESULT_TYPE_FORM = FlowResultType.FORM
    data_entry_flow_module.RESULT_TYPE_CREATE_ENTRY = FlowResultType.CREATE_ENTRY
    data_entry_flow_module.RESULT_TYPE_ABORT = FlowResultType.ABORT
    sys.modules["homeassistant.data_entry_flow"] = data_entry_flow_module

    loader_module = ModuleType("homeassistant.loader")

    class Integration:
        """Simplified Integration model mirroring Home Assistant's loader."""

        def __init__(self, hass: HomeAssistant, manifest: FlowContext):
            self._hass = hass
            self._manifest = dict(manifest)
            self.domain = manifest.get("domain", "unknown")
            self.name = manifest.get("name", self.domain)
            self.requirements = list(manifest.get("requirements", []))
            self.dependencies = list(manifest.get("dependencies", []))

        @property
        def manifest(self) -> dict[str, object]:
            return self._manifest

    loader_module.Integration = Integration
    sys.modules["homeassistant.loader"] = loader_module


def _install_setup_module() -> None:
    setup_module = ModuleType("homeassistant.setup")

    async def async_setup_component(
        hass: Any,
        domain: str,
        config: FlowContext | None = None,
    ) -> bool:
        hass.config.components.add(domain)
        try:
            component = importlib.import_module(f"homeassistant.components.{domain}")
        except ModuleNotFoundError:
            return False

        setup = getattr(component, "async_setup", None)
        if setup is None:
            return True

        if isinstance(config, Mapping):
            payload: Any = config.get(domain, {})
        else:
            payload = config or {}

        result = setup(hass, payload)
        if asyncio.iscoroutine(result):
            result = await result
        return result is not False

    setup_module.async_setup_component = async_setup_component
    sys.modules["homeassistant.setup"] = setup_module


def install_homeassistant_stubs() -> None:
    """Install or refresh the Home Assistant compatibility stubs."""

    root = sys.modules.get("homeassistant")
    if root is None:
        root = ModuleType("homeassistant")
        sys.modules["homeassistant"] = root
    # Ensure the namespace looks like a package so pkg-style imports succeed.
    if not hasattr(root, "__path__"):
        root.__path__ = []  # type: ignore[attr-defined]

    if getattr(root, "_pawcontrol_stubs_ready", False):
        _refresh_pawcontrol_compat_exports()
        return

    _install_const_module()
    _install_util_modules()
    _install_core_module()
    _install_exception_module()
    _install_helper_modules()
    _install_setup_module()
    _install_component_modules()

    root._pawcontrol_stubs_ready = True
    _refresh_pawcontrol_compat_exports()
    _install_pawcontrol_coordinator_helpers()


def _refresh_pawcontrol_compat_exports() -> None:
    """Notify the PawControl compat layer that Home Assistant stubs loaded."""

    try:
        from custom_components.pawcontrol import compat
    except Exception:  # pragma: no cover - integration unavailable in some tests
        return

    ensure_config_symbols = getattr(
        compat, "ensure_homeassistant_config_entry_symbols", None
    )
    if callable(ensure_config_symbols):
        ensure_config_symbols()

    ensure_exception_symbols = getattr(
        compat, "ensure_homeassistant_exception_symbols", None
    )
    if callable(ensure_exception_symbols):
        ensure_exception_symbols()

    _install_pawcontrol_coordinator_helpers()


def _install_pawcontrol_coordinator_helpers() -> None:
    """Mirror DogConfigRegistry validation helpers for stubbed test runs."""

    try:
        from custom_components.pawcontrol.const import (
            MAX_IDLE_POLL_INTERVAL,
            MAX_POLLING_INTERVAL_SECONDS,
        )
        from custom_components.pawcontrol.coordinator_support import DogConfigRegistry
        from custom_components.pawcontrol.exceptions import ValidationError
    except Exception:  # pragma: no cover - integration unavailable in some tests
        return

    def _enforce_polling_limits(interval: int | None) -> int:
        """Clamp polling intervals to Platinum quality requirements."""

        if not isinstance(interval, int):
            raise ValidationError(
                "update_interval", interval, "Polling interval must be an integer"
            )

        if interval <= 0:
            raise ValidationError(
                "update_interval", interval, "Polling interval must be positive"
            )

        return min(interval, MAX_IDLE_POLL_INTERVAL, MAX_POLLING_INTERVAL_SECONDS)

    def _validate_gps_interval(value: Any) -> int:
        """Validate the GPS interval option and return a positive integer."""

        if isinstance(value, bool):
            raise ValidationError(
                "gps_update_interval", value, "Invalid GPS update interval"
            )

        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                raise ValidationError(
                    "gps_update_interval", value, "Invalid GPS update interval"
                )
            try:
                value = int(candidate)
            except ValueError as err:  # pragma: no cover - defensive casting
                raise ValidationError(
                    "gps_update_interval", value, "Invalid GPS update interval"
                ) from err

        if not isinstance(value, int):
            raise ValidationError(
                "gps_update_interval", value, "Invalid GPS update interval"
            )

        if value <= 0:
            raise ValidationError(
                "gps_update_interval", value, "Invalid GPS update interval"
            )

        return value

    DogConfigRegistry._enforce_polling_limits = staticmethod(_enforce_polling_limits)
    DogConfigRegistry._validate_gps_interval = staticmethod(_validate_gps_interval)


install_homeassistant_stubs()
_TEMPLATE_RENDER_EXECUTOR: ThreadPoolExecutor | None = None
_TEMPLATE_EXECUTOR_LOCK = Lock()
_TEMPLATE_EXECUTOR_SHUTDOWN_REGISTERED = False


def _shutdown_template_executor() -> None:
    """Terminate the lazily created template executor."""

    global _TEMPLATE_RENDER_EXECUTOR

    executor = _TEMPLATE_RENDER_EXECUTOR
    if executor is None:
        return
    executor.shutdown(wait=True)


def _get_template_executor() -> ThreadPoolExecutor:
    """Return a thread pool for synchronous template rendering."""

    global _TEMPLATE_RENDER_EXECUTOR, _TEMPLATE_EXECUTOR_SHUTDOWN_REGISTERED

    executor = _TEMPLATE_RENDER_EXECUTOR
    if executor is not None:
        return executor

    with _TEMPLATE_EXECUTOR_LOCK:
        executor = _TEMPLATE_RENDER_EXECUTOR
        if executor is None:
            executor = ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="ha-template-render"
            )
            _TEMPLATE_RENDER_EXECUTOR = executor
            if not _TEMPLATE_EXECUTOR_SHUTDOWN_REGISTERED:
                atexit.register(_shutdown_template_executor)
                _TEMPLATE_EXECUTOR_SHUTDOWN_REGISTERED = True
            executor.submit(lambda: None).result()

    return executor
