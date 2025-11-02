"""Utility functions for PawControl integration.

Provides common utility functions, data validation, type conversion,
and helper methods used throughout the integration.

Quality Scale: Platinum target
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import math
import re
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
    Mapping,
    Sequence,
)
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import wraps
from numbers import Real
from types import SimpleNamespace
from typing import (
    TYPE_CHECKING,
    Any,
    ParamSpec,
    Protocol,
    TypedDict,
    TypeGuard,
    TypeVar,
    cast,
    overload,
)
from weakref import WeakKeyDictionary

if TYPE_CHECKING:  # pragma: no cover - import heavy HA modules for typing only
    from homeassistant.core import Context, EventOrigin, HomeAssistant
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.device_registry import DeviceEntry, DeviceInfo
    from homeassistant.helpers.entity import Entity
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.util import dt as dt_util
else:  # pragma: no branch - executed under tests without Home Assistant installed
    try:
        from homeassistant.core import Context, HomeAssistant

        try:
            from homeassistant.core import EventOrigin
        except ImportError:  # pragma: no cover - EventOrigin missing on older cores
            EventOrigin = object  # type: ignore[assignment]
        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers import entity_registry as er
        from homeassistant.helpers.device_registry import DeviceEntry, DeviceInfo
        from homeassistant.helpers.entity import Entity
        from homeassistant.helpers.entity_platform import AddEntitiesCallback
        from homeassistant.util import dt as dt_util
    except ModuleNotFoundError:  # pragma: no cover - compatibility shim for tests

        class Context:  # type: ignore[override]
            """Placeholder for Home Assistant's request context."""

        class EventOrigin:  # type: ignore[override]
            """Enum stand-in representing the origin of a Home Assistant event."""

        class HomeAssistant:  # type: ignore[override]
            """Minimal stand-in mirroring :class:`homeassistant.core.HomeAssistant`."""

        class Entity:  # type: ignore[override]
            """Lightweight placeholder entity used for tests."""

        @dataclass(slots=True)
        class DeviceEntry:  # type: ignore[override]
            """Fallback representation of Home Assistant's device registry entry."""

            id: str = ""
            manufacturer: str | None = None
            model: str | None = None
            sw_version: str | None = None
            configuration_url: str | None = None
            suggested_area: str | None = None
            serial_number: str | None = None
            hw_version: str | None = None

        class DeviceInfo(TypedDict, total=False):  # type: ignore[override]
            """Fallback device info payload matching Home Assistant expectations."""

            identifiers: set[tuple[str, str]]
            name: str
            manufacturer: str
            model: str
            sw_version: str
            configuration_url: str
            serial_number: str
            hw_version: str
            suggested_area: str

        class _AddEntitiesCallback(Protocol):
            """Callable signature mirroring ``AddEntitiesCallback``."""

            def __call__(
                self, entities: Iterable[Entity], update_before_add: bool = ...
            ) -> Awaitable[Any] | None: ...

        AddEntitiesCallback = _AddEntitiesCallback

        def _missing_registry(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError(
                "Home Assistant registry helpers are unavailable in this environment"
            )

        dr = SimpleNamespace(async_get=_missing_registry)
        er = SimpleNamespace(async_get=_missing_registry)

        class _DateTimeModule:
            @staticmethod
            def utcnow() -> datetime:
                return datetime.now(UTC)

            @staticmethod
            def now() -> datetime:
                return datetime.now(UTC)

            @staticmethod
            def as_utc(value: datetime) -> datetime:
                if value.tzinfo is None:
                    return value.replace(tzinfo=UTC)
                return value.astimezone(UTC)

            @staticmethod
            def as_local(value: datetime) -> datetime:
                if value.tzinfo is None:
                    return value.replace(tzinfo=UTC)
                return value.astimezone(UTC)

            @staticmethod
            def parse_datetime(value: str) -> datetime | None:
                with suppress(ValueError):
                    return datetime.fromisoformat(value)
                return None

            @staticmethod
            def parse_date(value: str) -> date | None:
                with suppress(ValueError):
                    return date.fromisoformat(value)
                return None

            @staticmethod
            def utc_from_timestamp(timestamp: float) -> datetime:
                return datetime.fromtimestamp(timestamp, UTC)

        dt_util = _DateTimeModule()

from .const import DEFAULT_MODEL, DOMAIN, MANUFACTURER
from .service_guard import ServiceGuardResult

_LOGGER = logging.getLogger(__name__)

# Type variables for generic functions
T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")
P = ParamSpec("P")
R = TypeVar("R")
Number = Real

type DateTimeConvertible = datetime | date | str | float | int | Number


async def async_call_hass_service_if_available(
    hass: HomeAssistant | None,
    domain: str,
    service: str,
    service_data: Mapping[str, Any] | None = None,
    *,
    target: Mapping[str, Any] | None = None,
    blocking: bool = False,
    context: Context | None = None,
    description: str | None = None,
    logger: logging.Logger | None = None,
) -> ServiceGuardResult:
    """Call a Home Assistant service when the instance is available."""

    active_logger = logger or _LOGGER
    description_hint = description or None

    if hass is None:
        context_hint = f" for {description}" if description_hint else ""
        active_logger.debug(
            "Skipping %s.%s service call%s because Home Assistant is not available",
            domain,
            service,
            context_hint,
        )
        guard_result = ServiceGuardResult(
            domain=domain,
            service=service,
            executed=False,
            reason="missing_instance",
            description=description_hint,
        )
        capture = _GUARD_CAPTURE.get(None)
        if capture is not None:
            capture.append(guard_result)
        return guard_result

    services = getattr(hass, "services", None)
    async_call = getattr(services, "async_call", None)
    if not callable(async_call):
        context_hint = f" for {description}" if description_hint else ""
        active_logger.debug(
            "Skipping %s.%s service call%s because the Home Assistant services API is not available",
            domain,
            service,
            context_hint,
        )
        guard_result = ServiceGuardResult(
            domain=domain,
            service=service,
            executed=False,
            reason="missing_services_api",
            description=description_hint,
        )
        capture = _GUARD_CAPTURE.get(None)
        if capture is not None:
            capture.append(guard_result)
        return guard_result

    payload = dict(service_data) if service_data is not None else {}
    target_payload = dict(target) if target is not None else None

    kwargs: dict[str, Any] = {"blocking": blocking}
    if target_payload is not None:
        kwargs["target"] = target_payload
    if context is not None:
        kwargs["context"] = context

    await async_call(
        domain,
        service,
        payload,
        **kwargs,
    )
    guard_result = ServiceGuardResult(
        domain=domain,
        service=service,
        executed=True,
        description=description_hint,
    )
    capture = _GUARD_CAPTURE.get(None)
    if capture is not None:
        capture.append(guard_result)
    return guard_result


class PortionValidationResult(TypedDict):
    """Validation outcome for a single portion size."""

    valid: bool
    warnings: list[str]
    recommendations: list[str]
    percentage_of_daily: float


async def async_fire_event(
    hass: HomeAssistant,
    event_type: str,
    event_data: Mapping[str, Any] | None = None,
    *,
    context: Context | None = None,
    origin: EventOrigin | None = None,
    time_fired: datetime | date | str | float | int | None = None,
) -> Any:
    """Fire a Home Assistant bus event and await coroutine-based mocks.

    Home Assistant's ``Bus.async_fire`` returns ``None`` but unit tests frequently
    replace it with :class:`unittest.mock.AsyncMock`. Awaiting the mock keeps the
    helper compatible with coroutine-based fakes while only forwarding optional
    keyword arguments that the active Home Assistant core accepts. Metadata such
    as ``context``, ``origin``, and ``time_fired`` is therefore passed through when
    provided (supporting :class:`datetime.datetime`, :class:`datetime.date`, ISO
    strings, or Unix epoch numbers), but gracefully omitted on legacy cores whose
    bus implementation predates those parameters. The awaited or direct return
    value is propagated so call sites that previously consumed the bus result keep
    functioning unchanged.
    """

    bus_async_fire = hass.bus.async_fire

    accepts_any_kw, supported_keywords = _get_bus_keyword_support(bus_async_fire)

    def _supports(keyword: str) -> bool:
        return accepts_any_kw or keyword in supported_keywords

    kwargs: dict[str, Any] = {}
    if context is not None and _supports("context"):
        kwargs["context"] = context
    if origin is not None and _supports("origin"):
        kwargs["origin"] = origin
    sanitized_time_fired: datetime | None = None
    if time_fired is not None:
        sanitized_time_fired = ensure_utc_datetime(time_fired)
        if sanitized_time_fired is None:
            _LOGGER.debug(
                "Dropping invalid time_fired payload %r for %s event",
                time_fired,
                event_type,
            )
    if sanitized_time_fired is not None and _supports("time_fired"):
        kwargs["time_fired"] = sanitized_time_fired

    result = bus_async_fire(event_type, event_data, **kwargs)
    if inspect.isawaitable(result):
        return await cast(Awaitable[Any], result)
    return result


# Cache Home Assistant bus signature support to avoid repeated inspection.
_SIGNATURE_SUPPORT_CACHE: WeakKeyDictionary[object, tuple[bool, frozenset[str]]] = (
    WeakKeyDictionary()
)


def _get_bus_keyword_support(
    bus_async_fire: Callable[..., Any],
) -> tuple[bool, frozenset[str]]:
    """Return metadata describing which keywords the bus supports."""

    cache_key: object = getattr(bus_async_fire, "__func__", bus_async_fire)

    try:
        return _SIGNATURE_SUPPORT_CACHE[cache_key]
    except KeyError:
        support = _introspect_bus_keywords(bus_async_fire)
        with suppress(TypeError):  # pragma: no cover - object not weak-referenceable
            _SIGNATURE_SUPPORT_CACHE[cache_key] = support
        return support


def _introspect_bus_keywords(
    bus_async_fire: Callable[..., Any],
) -> tuple[bool, frozenset[str]]:
    """Inspect the bus callable for supported keyword arguments."""

    try:
        signature = inspect.signature(bus_async_fire)
    except (TypeError, ValueError):
        return True, frozenset()

    parameters = signature.parameters
    accepts_any_kw = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )

    supported_keywords = frozenset(parameters)
    return accepts_any_kw, supported_keywords


def is_number(value: Any) -> TypeGuard[Number]:
    """Return whether ``value`` is a real number (excluding booleans)."""

    if isinstance(value, bool):
        return False
    return isinstance(value, Real)


def _normalize_identifier_pair(
    identifier: object,
) -> tuple[str, str] | None:
    """Normalize an identifier tuple used for Home Assistant device registry entries.

    The Home Assistant device registry expects identifiers to be pairs of strings.
    Many PawControl call sites build identifier tuples dynamically which means we
    occasionally encounter stray whitespace, ``None`` values, or non-string objects.
    The registry would silently coerce those values which results in confusing and
    hard-to-deduplicate entries.  Normalising them in a single helper keeps the
    behaviour predictable and ensures we never pass malformed identifiers to Home
    Assistant.
    """

    if isinstance(identifier, tuple):
        candidate = identifier
    elif isinstance(identifier, Sequence) and not isinstance(
        identifier, str | bytes | bytearray
    ):
        candidate = tuple(identifier)
    else:
        return None

    if len(candidate) != 2:
        return None

    domain, value = candidate
    if domain is None or value is None:
        return None

    domain_str = str(domain).strip()
    value_str = str(value).strip()

    if not domain_str or not value_str:
        return None

    return domain_str, value_str


def create_device_info(
    dog_id: str,
    dog_name: str,
    *,
    manufacturer: str = MANUFACTURER,
    model: str = DEFAULT_MODEL,
    sw_version: str | None = None,
    configuration_url: str | None = None,
    breed: str | None = None,
    microchip_id: str | None = None,
    serial_number: str | None = None,
    hw_version: str | None = None,
    suggested_area: str | None = None,
    extra_identifiers: Iterable[tuple[str, str]] | None = None,
) -> DeviceInfo:
    """Create device info for a dog entity.

    Args:
        dog_id: Unique dog identifier
        dog_name: Display name for the dog
        manufacturer: Manufacturer name for the device entry
        model: Model string for the device entry
        sw_version: Optional software version metadata
        configuration_url: Optional configuration URL for the device
        breed: Optional breed information used to enrich the model string
        microchip_id: Optional microchip identifier used for device identifiers
        serial_number: Optional serial number metadata
        hw_version: Optional hardware version metadata
        suggested_area: Optional suggested area assignment for the device
        extra_identifiers: Optional iterable of additional identifiers

    Returns:
        DeviceInfo dictionary for Home Assistant device registry
    """
    # Sanitize dog_id for device identifier
    sanitized_id = sanitize_dog_id(dog_id)

    identifiers: set[tuple[str, str]] = {(DOMAIN, sanitized_id)}

    if extra_identifiers:
        for identifier in extra_identifiers:
            normalized = _normalize_identifier_pair(identifier)
            if normalized is not None:
                identifiers.add(normalized)

    if microchip_id is not None:
        sanitized_microchip = sanitize_microchip_id(str(microchip_id))
        if sanitized_microchip:
            identifiers.add(("microchip", sanitized_microchip))

    computed_model = f"{model} - {breed}" if breed else model

    device_info: DeviceInfo = {
        "identifiers": identifiers,
        "name": dog_name,
        "manufacturer": manufacturer,
        "model": computed_model,
    }

    if sw_version:
        device_info["sw_version"] = sw_version

    if configuration_url:
        device_info["configuration_url"] = configuration_url

    if serial_number:
        device_info["serial_number"] = str(serial_number)

    if hw_version:
        device_info["hw_version"] = str(hw_version)

    if suggested_area:
        device_info["suggested_area"] = suggested_area

    return device_info


async def async_call_add_entities(
    add_entities_callback: AddEntitiesCallback,
    entities: Iterable[Entity],
    *,
    update_before_add: bool = False,
) -> None:
    """Invoke Home Assistant's async_add_entities callback and await when needed."""

    entities_list = list(entities)
    result = add_entities_callback(entities_list, update_before_add)

    if inspect.isawaitable(result):
        await cast(Awaitable[Any], result)


async def async_get_or_create_dog_device_entry(
    hass: HomeAssistant,
    *,
    config_entry_id: str,
    dog_id: str,
    dog_name: str,
    manufacturer: str = MANUFACTURER,
    model: str = DEFAULT_MODEL,
    sw_version: str | None = None,
    configuration_url: str | None = None,
    breed: str | None = None,
    microchip_id: str | None = None,
    suggested_area: str | None = None,
    serial_number: str | None = None,
    hw_version: str | None = None,
    extra_identifiers: Iterable[tuple[str, str]] | None = None,
) -> DeviceEntry:
    """Link a dog to a device registry entry and return it."""

    device_info = create_device_info(
        dog_id,
        dog_name,
        manufacturer=manufacturer,
        model=model,
        sw_version=sw_version,
        configuration_url=configuration_url,
        breed=breed,
        microchip_id=microchip_id,
        suggested_area=suggested_area,
        serial_number=serial_number,
        hw_version=hw_version,
        extra_identifiers=extra_identifiers,
    )

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry_id,
        identifiers=device_info["identifiers"],
        manufacturer=device_info["manufacturer"],
        model=device_info["model"],
        name=device_info["name"],
        sw_version=device_info.get("sw_version"),
        configuration_url=device_info.get("configuration_url"),
    )

    update_kwargs: dict[str, Any] = {}
    for field in (
        "suggested_area",
        "serial_number",
        "hw_version",
        "sw_version",
        "configuration_url",
    ):
        value = device_info.get(field)
        if value and getattr(device, field, None) != value:
            update_kwargs[field] = value

    if update_kwargs:
        try:
            if updated_device := device_registry.async_update_device(
                device.id, **update_kwargs
            ):
                device = updated_device
        except Exception as err:  # pragma: no cover - defensive, HA guarantees API
            _LOGGER.debug(
                "Failed to update device registry entry %s for dog %s: %s",
                device.id,
                dog_id,
                err,
            )

    return device


class PawControlDeviceLinkMixin:
    """Mixin providing device registry linking for PawControl entities."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Set up default device link metadata."""

        super().__init__(*args, **kwargs)
        self._device_link_defaults: dict[str, Any] = {
            "manufacturer": MANUFACTURER,
            "model": DEFAULT_MODEL,
            "sw_version": "1.0.0",
            "configuration_url": "https://github.com/BigDaddy1990/pawcontrol",
        }
        self._linked_device_entry: DeviceEntry | None = None
        self._device_link_initialized = False

    def _set_device_link_info(self, **info: Any) -> None:
        """Update device link metadata used when creating the device entry."""

        self._device_link_defaults.update(info)

    def _device_link_details(self) -> dict[str, Any]:
        """Return a copy of the device metadata for linking."""

        return dict(self._device_link_defaults)

    # Home Assistant's cooperative multiple inheritance confuses type checkers
    # about the precise async_added_to_hass signature, so we silence the
    # override warning here.
    async def async_added_to_hass(self) -> None:  # type: ignore[override]
        """Link entity to device entry after regular setup."""

        # CoordinatorEntity and RestoreEntity expose incompatible type hints for
        # async_added_to_hass(), so we silence the mismatch on the cooperative
        # super() call used by Home Assistant's entity model.
        await super().async_added_to_hass()  # type: ignore[misc]
        await self._async_link_device_entry()

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device metadata for entity registry registration."""

        dog_id = getattr(self, "_dog_id", None)
        dog_name = getattr(self, "_dog_name", None)
        if not dog_id or not dog_name:
            return None

        info = self._device_link_details()
        suggested_area = info.get("suggested_area") or getattr(
            self, "_attr_suggested_area", None
        )

        return create_device_info(
            dog_id,
            dog_name,
            manufacturer=info.get("manufacturer", MANUFACTURER),
            model=info.get("model", DEFAULT_MODEL),
            sw_version=info.get("sw_version"),
            configuration_url=info.get("configuration_url"),
            breed=info.get("breed"),
            microchip_id=info.get("microchip_id"),
            serial_number=info.get("serial_number"),
            hw_version=info.get("hw_version"),
            suggested_area=suggested_area,
            extra_identifiers=cast(
                Iterable[tuple[str, str]] | None, info.get("extra_identifiers")
            ),
        )

    async def _async_link_device_entry(self) -> None:
        """Create or fetch the device entry and attach it to the entity."""

        if self._device_link_initialized:
            return

        hass: HomeAssistant | None = getattr(self, "hass", None)
        coordinator = getattr(self, "coordinator", None)
        if hass is None or coordinator is None:
            return

        config_entry = getattr(coordinator, "config_entry", None)
        dog_id = getattr(self, "_dog_id", None)
        dog_name = getattr(self, "_dog_name", None)

        if config_entry is None or dog_id is None or dog_name is None:
            return

        try:
            device = await async_get_or_create_dog_device_entry(
                hass,
                config_entry_id=config_entry.entry_id,
                dog_id=dog_id,
                dog_name=dog_name,
                **self._device_link_details(),
            )
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.warning(
                "Failed to link PawControl entity %s to device: %s",
                getattr(self, "entity_id", f"pawcontrol_{dog_id}"),
                err,
            )
            return

        self.device_entry = device
        self._linked_device_entry = device
        self._device_link_initialized = True

        entity_id = cast(str | None, getattr(self, "entity_id", None))
        if entity_id:
            entity_registry = er.async_get(hass)
            entity_entry = entity_registry.async_get(entity_id)
            if entity_entry and entity_entry.device_id != device.id:
                entity_registry.async_update_entity(
                    entity_id,
                    device_id=device.id,
                )


def deep_merge_dicts(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries.

    Args:
        base: Base dictionary to merge into
        updates: Updates to apply

    Returns:
        New dictionary with merged values
    """
    result = base.copy()

    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def safe_get_nested(
    data: dict[str, Any], path: str, default: Any = None, separator: str = "."
) -> Any:
    """Safely get nested dictionary value using dot notation.

    Args:
        data: Dictionary to search
        path: Dot-separated path (e.g., "dog.health.weight")
        default: Default value if path not found
        separator: Path separator character

    Returns:
        Value at path or default
    """
    try:
        keys = path.split(separator)
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        return current
    except (AttributeError, KeyError, TypeError):
        return default


def safe_set_nested(
    data: dict[str, Any], path: str, value: Any, separator: str = "."
) -> dict[str, Any]:
    """Safely set nested dictionary value using dot notation.

    Args:
        data: Dictionary to update
        path: Dot-separated path
        value: Value to set
        separator: Path separator character

    Returns:
        Updated dictionary
    """
    keys = path.split(separator)
    current = data

    # Navigate to parent of target key
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]

    # Set the final value
    current[keys[-1]] = value
    return data


def validate_time_string(time_str: str | None) -> time | None:
    """Validate and parse time string.

    Args:
        time_str: Time string in HH:MM or HH:MM:SS format

    Returns:
        Parsed time object or None if invalid
    """
    if not time_str:
        return None

    try:
        # Support both HH:MM and HH:MM:SS formats
        if re.match(r"^\d{1,2}:\d{2}$", time_str):
            hour, minute = map(int, time_str.split(":"))
            return time(hour, minute)
        elif re.match(r"^\d{1,2}:\d{2}:\d{2}$", time_str):
            hour, minute, second = map(int, time_str.split(":"))
            return time(hour, minute, second)
    except (ValueError, AttributeError):
        pass

    return None


def validate_email(email: str | None) -> bool:
    """Validate email address format.

    Args:
        email: Email address to validate

    Returns:
        True if valid email format
    """
    if not email:
        return False

    # Simple but effective email regex
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def sanitize_dog_id(dog_id: str) -> str:
    """Sanitize dog ID for use as entity identifier.

    Args:
        dog_id: Raw dog ID

    Returns:
        Sanitized dog ID suitable for entity IDs
    """
    # Convert to lowercase and replace invalid characters
    sanitized = re.sub(r"[^a-z0-9_]", "_", dog_id.lower())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")

    if not sanitized:
        digest = hashlib.sha256(dog_id.encode("utf-8", "ignore")).hexdigest()
        sanitized = f"dog_{digest[:8]}"
    elif not sanitized[0].isalpha():
        sanitized = f"dog_{sanitized}"

    return sanitized


def sanitize_microchip_id(microchip_id: str) -> str | None:
    """Normalize microchip identifiers for consistent device registry entries."""

    sanitized = re.sub(r"[^A-Za-z0-9]", "", microchip_id).upper()
    return sanitized or None


def format_duration(seconds: int | float) -> str:
    """Format duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{minutes}m"
    else:
        hours = int(seconds // 3600)
        remaining_minutes = int((seconds % 3600) // 60)
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{hours}h"


def format_distance(meters: float, unit: str = "metric") -> str:
    """Format distance with appropriate units.

    Args:
        meters: Distance in meters
        unit: Unit system ("metric" or "imperial")

    Returns:
        Formatted distance string
    """
    if unit == "imperial":
        feet = meters * 3.28084
        if feet < 5280:
            return f"{int(feet)} ft"
        else:
            miles = feet / 5280
            return f"{miles:.1f} mi"
    else:
        if meters < 1000:
            return f"{int(meters)} m"
        else:
            kilometers = meters / 1000
            return f"{kilometers:.1f} km"


def calculate_age_from_months(age_months: int) -> dict[str, int]:
    """Calculate years and months from total months.

    Args:
        age_months: Total age in months

    Returns:
        Dictionary with years and months

    Raises:
        TypeError: If ``age_months`` is not an integer value
        ValueError: If ``age_months`` is negative
    """
    if isinstance(age_months, bool) or not isinstance(age_months, int):
        raise TypeError("age_months must be provided as an integer")

    if age_months < 0:
        raise ValueError("age_months must be non-negative")

    years = age_months // 12
    months = age_months % 12

    return {
        "years": years,
        "months": months,
        "total_months": age_months,
    }


def parse_weight(weight_input: str | float | int) -> float | None:
    """Parse weight input in various formats.

    Args:
        weight_input: Weight as string, float, or int

    Returns:
        Weight in kilograms or None if invalid
    """
    if is_number(weight_input):
        numeric_weight = float(weight_input)
        return numeric_weight if numeric_weight > 0 else None

    if not isinstance(weight_input, str):
        return None

    # Remove whitespace and convert to lowercase
    weight_str = weight_input.strip().lower()

    # Handle common weight formats
    if "kg" in weight_str:
        try:
            return float(weight_str.replace("kg", "").strip())
        except ValueError:
            pass
    elif "lb" in weight_str or "lbs" in weight_str:
        try:
            # Convert pounds to kilograms
            lbs = float(weight_str.replace("lbs", "").replace("lb", "").strip())
            return lbs * 0.453592
        except ValueError:
            pass
    else:
        # Try parsing as plain number (assume kg)
        try:
            return float(weight_str)
        except ValueError:
            pass

    return None


def generate_entity_id(domain: str, dog_id: str, entity_type: str) -> str:
    """Generate entity ID following Home Assistant conventions.

    Args:
        domain: Integration domain
        dog_id: Dog identifier
        entity_type: Type of entity

    Returns:
        Generated entity ID
    """
    sanitized_dog_id = sanitize_dog_id(dog_id)
    sanitized_type = re.sub(r"[^a-z0-9_]", "_", entity_type.lower())

    return f"{domain}.{sanitized_dog_id}_{sanitized_type}"


def calculate_bmi_equivalent(weight_kg: float, breed_size: str) -> float | None:
    """Calculate BMI equivalent for dogs based on breed size.

    Args:
        weight_kg: Weight in kilograms
        breed_size: Size category ("toy", "small", "medium", "large", "giant")

    Returns:
        BMI equivalent or None if invalid
    """
    # Standard weight ranges for breed sizes (kg)
    size_ranges = {
        "toy": (1.0, 6.0),
        "small": (4.0, 15.0),
        "medium": (8.0, 30.0),
        "large": (22.0, 50.0),
        "giant": (35.0, 90.0),
    }

    if breed_size not in size_ranges:
        return None

    min_weight, max_weight = size_ranges[breed_size]

    # Calculate relative position within breed size range
    if weight_kg <= min_weight:
        return 15.0  # Underweight
    elif weight_kg >= max_weight:
        return 30.0  # Overweight
    else:
        # Linear interpolation between 18.5 (normal low) and 25 (normal high)
        ratio = (weight_kg - min_weight) / (max_weight - min_weight)
        return 18.5 + (ratio * 6.5)  # 18.5 to 25


def validate_portion_size(
    portion: float, daily_amount: float, meals_per_day: int = 2
) -> PortionValidationResult:
    """Validate portion size against daily requirements.

    Args:
        portion: Portion size in grams
        daily_amount: Total daily food amount
        meals_per_day: Number of meals per day

    Returns:
        Validation result with warnings and recommendations
    """

    result: PortionValidationResult = {
        "valid": True,
        "warnings": [],
        "recommendations": [],
        "percentage_of_daily": 0.0,
    }

    if not is_number(portion):
        result["valid"] = False
        result["warnings"].append("Portion must be a real number")
        result["recommendations"].append("Provide the portion size in grams")
        return result

    portion_value = float(portion)
    if not math.isfinite(portion_value):
        result["valid"] = False
        result["warnings"].append("Portion must be a finite number")
        result["recommendations"].append(
            "Replace NaN or infinite values with real numbers"
        )
        return result

    if portion_value <= 0:
        result["valid"] = False
        result["warnings"].append("Portion must be greater than zero")
        result["recommendations"].append(
            "Increase the portion size or remove the feeding entry"
        )
        return result

    if not is_number(daily_amount):
        result["valid"] = False
        result["warnings"].append("Daily food amount must be a real number")
        result["recommendations"].append(
            "Update the feeding configuration with a numeric daily amount"
        )
        return result

    daily_amount_value = float(daily_amount)
    if not math.isfinite(daily_amount_value) or daily_amount_value <= 0:
        result["valid"] = False
        result["warnings"].append(
            "Daily food amount must be positive to validate portion sizes"
        )
        result["recommendations"].append(
            "Set a positive daily food amount for the feeding configuration"
        )
        return result

    if meals_per_day <= 0:
        result["warnings"].append(
            "Meals per day is not positive; assuming a single meal for validation"
        )
        result["recommendations"].append(
            "Adjust meals per day to a positive value in the feeding configuration"
        )
        meals_per_day = 1

    percentage = (portion_value / daily_amount_value) * 100
    result["percentage_of_daily"] = percentage

    expected_percentage = 100 / meals_per_day

    if portion_value > daily_amount_value:
        result["valid"] = False
        result["warnings"].append("Portion exceeds the configured daily amount")
        result["recommendations"].append(
            "Reduce the portion size or increase the daily food amount"
        )

    if percentage > 70:
        result["valid"] = False
        result["warnings"].append("Portion exceeds 70% of daily requirement")
        result["recommendations"].append("Consider reducing portion size")
    elif percentage > expected_percentage * 1.5:
        result["warnings"].append("Portion is larger than typical for meal frequency")
        result["recommendations"].append("Verify portion calculation")
    elif percentage < 5:
        result["warnings"].append("Portion is very small compared to daily requirement")
        result["recommendations"].append(
            "Consider increasing portion or meal frequency"
        )

    return result


def chunk_list[T](items: Sequence[T], chunk_size: int) -> list[list[T]]:
    """Split a list into chunks of specified size.

    Args:
        items: List to chunk
        chunk_size: Maximum size of each chunk

    Returns:
        List of chunks
    """
    if chunk_size <= 0:
        raise ValueError("Chunk size must be positive")

    return [list(items[i : i + chunk_size]) for i in range(0, len(items), chunk_size)]


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers with default for division by zero.

    Args:
        numerator: Number to divide
        denominator: Number to divide by
        default: Default value if denominator is zero

    Returns:
        Division result or default
    """
    try:
        return numerator / denominator if denominator != 0 else default
    except (TypeError, ZeroDivisionError):
        return default


def clamp(value: float, min_value: float, max_value: float) -> float:
    """Clamp value between minimum and maximum.

    Args:
        value: Value to clamp
        min_value: Minimum allowed value
        max_value: Maximum allowed value

    Returns:
        Clamped value
    """
    return max(min_value, min(value, max_value))


def is_dict_subset(subset: Mapping[K, V], superset: Mapping[K, V]) -> bool:
    """Check if one dictionary is a subset of another.

    Args:
        subset: Dictionary to check if it's a subset
        superset: Dictionary to check against

    Returns:
        True if subset is contained in superset
    """
    try:
        return all(
            key in superset and superset[key] == value for key, value in subset.items()
        )
    except (AttributeError, TypeError):
        return False


def flatten_dict(
    data: dict[str, Any], separator: str = ".", prefix: str = ""
) -> dict[str, Any]:
    """Flatten nested dictionary using dot notation.

    Args:
        data: Dictionary to flatten
        separator: Separator for keys
        prefix: Prefix for keys

    Returns:
        Flattened dictionary
    """
    flattened: dict[str, Any] = {}

    for key, value in data.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key

        if isinstance(value, dict):
            flattened.update(flatten_dict(value, separator, new_key))
        else:
            flattened[new_key] = value

    return flattened


def unflatten_dict(data: dict[str, Any], separator: str = ".") -> dict[str, Any]:
    """Unflatten dictionary from dot notation.

    Args:
        data: Flattened dictionary
        separator: Key separator

    Returns:
        Nested dictionary
    """
    result: dict[str, Any] = {}

    for key, value in data.items():
        safe_set_nested(result, key, value, separator)

    return result


def extract_numbers(text: str) -> list[float]:
    """Extract all numbers from text string.

    Args:
        text: Text to extract numbers from

    Returns:
        List of extracted numbers
    """
    pattern = r"-?\d+(?:\.\d+)?"
    matches = re.findall(pattern, text)

    try:
        return [float(match) for match in matches]
    except ValueError:
        return []


def generate_unique_id(*parts: str) -> str:
    """Generate unique ID from multiple parts.

    Args:
        *parts: Parts to combine into unique ID

    Returns:
        Generated unique ID
    """
    # Sanitize each part and join with underscores
    sanitized_parts = []
    for part in parts:
        if part:
            sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", str(part))
            sanitized = re.sub(r"_+", "_", sanitized).strip("_")
            if sanitized:
                sanitized_parts.append(sanitized.lower())

    return "_".join(sanitized_parts) if sanitized_parts else "unknown"


def retry_on_exception(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[
    [Callable[P, Awaitable[R]] | Callable[P, R]],
    Callable[P, Awaitable[R]],
]:
    """Retry a callable when it raises one of the provided exceptions.

    The returned decorator always exposes an async callable. When applied to a
    synchronous function the wrapped callable is executed in an executor via
    :func:`asyncio.to_thread`, ensuring the Home Assistant event loop stays
    responsive and avoiding blocking sleeps.

    Args:
        max_retries: Maximum number of retries
        delay: Initial delay between retries
        backoff_factor: Factor to multiply delay by each retry
        exceptions: Exception types to retry on

    Returns:
        Decorator that provides retry behaviour for async and sync callables.
    """

    def decorator(
        func: Callable[P, Awaitable[R]] | Callable[P, R],
    ) -> Callable[P, Awaitable[R]]:
        """Wrap `func` with retry handling that always returns an async callable."""

        is_coroutine = asyncio.iscoroutinefunction(func)

        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            """Execute the wrapped function with retry and backoff support."""

            last_exception: Exception | None = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    if is_coroutine:
                        coroutine = cast(Callable[P, Awaitable[R]], func)
                        return await coroutine(*args, **kwargs)
                    sync_func = cast(Callable[P, R], func)
                    return await asyncio.to_thread(sync_func, *args, **kwargs)
                except exceptions as err:
                    last_exception = err
                    if attempt < max_retries:
                        _LOGGER.debug(
                            "Attempt %d failed for %s: %s. Retrying in %.1fs",
                            attempt + 1,
                            func.__name__,
                            err,
                            current_delay,
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        _LOGGER.error(
                            "All %d attempts failed for %s",
                            max_retries + 1,
                            func.__name__,
                        )

            if last_exception is None:  # pragma: no cover - safety net
                last_exception = Exception(
                    f"{func.__name__} failed without raising a captured exception"
                )
            raise last_exception

        return async_wrapper

    return decorator


def calculate_time_until(target_time: time) -> timedelta:
    """Calculate time until next occurrence of target time.

    Args:
        target_time: Target time of day

    Returns:
        Time delta until next occurrence
    """
    now = dt_util.now()
    today = now.date()

    # Try today first
    target_datetime = datetime.combine(today, target_time)
    target_datetime = dt_util.as_local(target_datetime)

    if target_datetime > now:
        return target_datetime - now
    else:
        # Must be tomorrow
        tomorrow = today + timedelta(days=1)
        target_datetime = datetime.combine(tomorrow, target_time)
        target_datetime = dt_util.as_local(target_datetime)
        return target_datetime - now


def format_relative_time(dt: datetime) -> str:
    """Format datetime as relative time string.

    Args:
        dt: Datetime to format

    Returns:
        Relative time string
    """
    now = dt_util.now()

    # Make both timezone-aware for comparison
    if dt.tzinfo is None:
        dt = cast(datetime, dt_util.as_local(dt))
    if now.tzinfo is None:
        now = cast(datetime, dt_util.as_local(now))

    delta = now - dt

    if delta.total_seconds() < 60:
        return "just now"
    elif delta.total_seconds() < 3600:
        minutes = int(delta.total_seconds() / 60)
        return f"{minutes}m ago"
    elif delta.total_seconds() < 86400:
        hours = int(delta.total_seconds() / 3600)
        return f"{hours}h ago"
    elif delta.days == 1:
        return "yesterday"
    elif delta.days < 7:
        return f"{delta.days} days ago"
    elif delta.days < 30:
        weeks = delta.days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    else:
        months = delta.days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"


@overload
def ensure_utc_datetime(value: None) -> None:  # pragma: no cover - typing helper
    """Return ``None`` when no value is provided."""


@overload
def ensure_utc_datetime(value: DateTimeConvertible) -> datetime | None:
    """Convert supported input types to aware UTC datetimes."""


def ensure_utc_datetime(value: DateTimeConvertible | None) -> datetime | None:
    """Return a timezone-aware UTC datetime from various input formats."""

    if value is None:
        return None

    if isinstance(value, datetime):
        dt_value = value
    elif isinstance(value, date):
        dt_value = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        if not value:
            return None
        parsed_value = _parse_datetime_string(value)
        if parsed_value is None:
            return None
        dt_value = parsed_value
    elif is_number(value):
        timestamp_value = _datetime_from_timestamp(value)
        if timestamp_value is None:
            return None
        dt_value = timestamp_value
    else:
        return None

    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=UTC)

    return dt_util.as_utc(dt_value)


def _parse_datetime_string(value: str) -> datetime | None:
    """Parse ``value`` into a timezone-aware datetime when possible."""

    try:
        dt_value = dt_util.parse_datetime(value)
    except ValueError:
        dt_value = None

    if dt_value is not None:
        return dt_value

    date_parser = getattr(dt_util, "parse_date", None)
    date_value: date | None = None

    if callable(date_parser):
        with suppress(ValueError):
            date_value = date_parser(value)

    if date_value is None:
        with suppress(ValueError):
            date_value = date.fromisoformat(value)

    if date_value is None:
        return None

    return datetime.combine(date_value, datetime.min.time())


def _datetime_from_timestamp(value: Number) -> datetime | None:
    """Convert ``value`` into a UTC datetime when it represents a timestamp."""

    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None

    utc_from_timestamp = getattr(dt_util, "utc_from_timestamp", None)
    if callable(utc_from_timestamp):
        with suppress(OverflowError, OSError, ValueError):
            return utc_from_timestamp(timestamp)

    with suppress(OverflowError, OSError, ValueError):
        return datetime.fromtimestamp(timestamp, UTC)

    return None


def ensure_local_datetime(value: datetime | str | None) -> datetime | None:
    """Return a timezone-aware datetime in the configured local timezone."""

    if value is None:
        return None

    if isinstance(value, datetime):
        dt_value = value
    elif isinstance(value, str) and value:
        dt_value = dt_util.parse_datetime(value)
        if dt_value is None:
            date_value = dt_util.parse_date(value)
            if date_value is None:
                return None
            dt_value = datetime.combine(date_value, datetime.min.time())
    else:
        return None

    return dt_util.as_local(dt_value)


def merge_configurations(
    base_config: dict[str, Any],
    user_config: dict[str, Any],
    protected_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Merge user configuration with base configuration.

    Args:
        base_config: Base configuration with defaults
        user_config: User-provided configuration
        protected_keys: Keys that cannot be overridden

    Returns:
        Merged configuration
    """
    protected_keys = protected_keys or set()
    merged = base_config.copy()

    for key, value in user_config.items():
        if key in protected_keys:
            _LOGGER.warning("Ignoring protected configuration key: %s", key)
            continue

        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_configurations(merged[key], value, protected_keys)
        else:
            merged[key] = value

    return merged


def validate_configuration_schema(
    config: dict[str, Any],
    required_keys: set[str],
    optional_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Validate configuration against schema.

    Args:
        config: Configuration to validate
        required_keys: Required configuration keys
        optional_keys: Optional configuration keys

    Returns:
        Validation result with missing/unknown keys
    """
    optional_keys = optional_keys or set()
    all_valid_keys = required_keys | optional_keys

    missing_keys = required_keys - config.keys()
    unknown_keys = config.keys() - all_valid_keys

    return {
        "valid": len(missing_keys) == 0,
        "missing_keys": list(missing_keys),
        "unknown_keys": list(unknown_keys),
        "has_all_required": len(missing_keys) == 0,
        "has_unknown": len(unknown_keys) > 0,
    }


def convert_units(value: float, from_unit: str, to_unit: str) -> float:
    """Convert between different units.

    Args:
        value: Value to convert
        from_unit: Source unit
        to_unit: Target unit

    Returns:
        Converted value

    Raises:
        ValueError: If unit conversion not supported
    """
    # Weight conversions
    weight_conversions = {
        ("kg", "lb"): lambda x: x * 2.20462,
        ("lb", "kg"): lambda x: x * 0.453592,
        ("g", "kg"): lambda x: x / 1000,
        ("kg", "g"): lambda x: x * 1000,
        ("oz", "g"): lambda x: x * 28.3495,
        ("g", "oz"): lambda x: x / 28.3495,
    }

    # Distance conversions
    distance_conversions = {
        ("m", "ft"): lambda x: x * 3.28084,
        ("ft", "m"): lambda x: x / 3.28084,
        ("km", "mi"): lambda x: x * 0.621371,
        ("mi", "km"): lambda x: x / 0.621371,
        ("m", "km"): lambda x: x / 1000,
        ("km", "m"): lambda x: x * 1000,
    }

    # Temperature conversions
    temp_conversions = {
        ("c", "f"): lambda x: (x * 9 / 5) + 32,
        ("f", "c"): lambda x: (x - 32) * 5 / 9,
    }

    # Combine all conversions
    all_conversions = {
        **weight_conversions,
        **distance_conversions,
        **temp_conversions,
    }

    # Normalize unit names
    from_unit = from_unit.lower().strip()
    to_unit = to_unit.lower().strip()

    # Handle same unit
    if from_unit == to_unit:
        return value

    # Look up conversion
    conversion_key = (from_unit, to_unit)
    if conversion_key in all_conversions:
        return all_conversions[conversion_key](value)

    raise ValueError(f"Conversion from {from_unit} to {to_unit} not supported")


_GUARD_CAPTURE: ContextVar[list[ServiceGuardResult] | None] = ContextVar(
    "pawcontrol_service_guard_capture",
    default=None,
)


@asynccontextmanager
async def async_capture_service_guard_results() -> AsyncIterator[
    list[ServiceGuardResult]
]:
    """Capture guard outcomes for Home Assistant service invocations."""

    previous = _GUARD_CAPTURE.get(None)
    guard_results: list[ServiceGuardResult] = []
    token = _GUARD_CAPTURE.set(guard_results)
    try:
        yield guard_results
    finally:
        _GUARD_CAPTURE.reset(token)
        if previous is not None:
            previous.extend(guard_results)
