"""Utility functions for PawControl integration.

Provides common utility functions, data validation, type conversion,
and helper methods used throughout the integration.

Quality Scale: Platinum target
P26.1.1++
Python: 3.13+
"""

import asyncio
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
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import partial, wraps
import hashlib
import inspect
import logging
import math
from numbers import Real
import re
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
  from homeassistant.core import Context, EventOrigin, HomeAssistant  # noqa: E111
  from homeassistant.exceptions import HomeAssistantError  # noqa: E111
  from homeassistant.helpers import (  # noqa: E111
    device_registry as dr,
    entity_registry as er,
  )
  from homeassistant.helpers.device_registry import (  # noqa: E111
    DeviceEntry,
    DeviceInfo,
  )
  from homeassistant.helpers.entity import Entity  # noqa: E111
  from homeassistant.helpers.entity_platform import AddEntitiesCallback  # noqa: E111
  from homeassistant.util import dt as dt_util  # noqa: E111

  from .coordinator import PawControlCoordinator  # noqa: E111
else:  # pragma: no branch - executed under tests without Home Assistant installed
  try:  # noqa: E111
    from homeassistant.core import Context, HomeAssistant

    try:
      from homeassistant.core import EventOrigin  # noqa: E111
    except ImportError:  # pragma: no cover - EventOrigin missing on older cores
      EventOrigin = object  # type: ignore[assignment]  # noqa: E111
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from homeassistant.helpers.device_registry import DeviceEntry, DeviceInfo
    from homeassistant.helpers.entity import Entity
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.util import dt as dt_util
  except (  # noqa: E111
    ModuleNotFoundError
  ):  # pragma: no cover - compatibility shim for tests

    class Context:  # type: ignore[override]
      """Placeholder for Home Assistant's request context."""  # noqa: E111

    class EventOrigin:  # type: ignore[override]
      """Enum stand-in representing the origin of a Home Assistant event."""  # noqa: E111

    class HomeAssistant:  # type: ignore[override]
      """Minimal stand-in mirroring :class:`homeassistant.core.HomeAssistant`."""  # noqa: E111

    class Entity:  # type: ignore[override]
      """Lightweight placeholder entity used for tests."""  # noqa: E111

    class HomeAssistantError(Exception):  # type: ignore[override]
      """Fallback Home Assistant error type for test environments."""  # noqa: E111

    @dataclass(slots=True)
    class DeviceEntry:  # type: ignore[override]
      """Fallback representation of Home Assistant's device registry entry."""  # noqa: E111

      id: str = ""  # noqa: E111
      manufacturer: str | None = None  # noqa: E111
      model: str | None = None  # noqa: E111
      sw_version: str | None = None  # noqa: E111
      configuration_url: str | None = None  # noqa: E111
      suggested_area: str | None = None  # noqa: E111
      serial_number: str | None = None  # noqa: E111
      hw_version: str | None = None  # noqa: E111

    class DeviceInfo(TypedDict, total=False):  # type: ignore[override]
      """Fallback device info payload matching Home Assistant expectations."""  # noqa: E111

      identifiers: set[tuple[str, str]]  # noqa: E111
      name: str  # noqa: E111
      manufacturer: str  # noqa: E111
      model: str  # noqa: E111
      sw_version: str  # noqa: E111
      configuration_url: str  # noqa: E111
      serial_number: str  # noqa: E111
      hw_version: str  # noqa: E111
      suggested_area: str  # noqa: E111

    class _AddEntitiesCallback(Protocol):
      """Callable signature mirroring ``AddEntitiesCallback``."""  # noqa: E111

      def __call__(  # noqa: E111
        self,
        entities: Iterable[Entity],
        update_before_add: bool = ...,
      ) -> Awaitable[Any] | None: ...

    AddEntitiesCallback = _AddEntitiesCallback

    def _missing_registry(*args: Any, **kwargs: Any) -> Any:
      raise RuntimeError(  # noqa: E111
        "Home Assistant registry helpers are unavailable in this environment",
      )

    dr = SimpleNamespace(async_get=_missing_registry)
    er = SimpleNamespace(async_get=_missing_registry)

    class _DateTimeModule:
      @staticmethod  # noqa: E111
      def utcnow() -> datetime:  # noqa: E111
        return datetime.now(UTC)

      @staticmethod  # noqa: E111
      def now() -> datetime:  # noqa: E111
        return datetime.now(UTC)

      @staticmethod  # noqa: E111
      def as_utc(value: datetime) -> datetime:  # noqa: E111
        if value.tzinfo is None:
          return value.replace(tzinfo=UTC)  # noqa: E111
        return value.astimezone(UTC)

      @staticmethod  # noqa: E111
      def as_local(value: datetime) -> datetime:  # noqa: E111
        if value.tzinfo is None:
          return value.replace(tzinfo=UTC)  # noqa: E111
        return value.astimezone(UTC)

      @staticmethod  # noqa: E111
      def parse_datetime(value: str) -> datetime | None:  # noqa: E111
        with suppress(ValueError):
          return datetime.fromisoformat(value)  # noqa: E111
        return None

      @staticmethod  # noqa: E111
      def parse_date(value: str) -> date | None:  # noqa: E111
        with suppress(ValueError):
          return date.fromisoformat(value)  # noqa: E111
        return None

      @staticmethod  # noqa: E111
      def utc_from_timestamp(timestamp: float) -> datetime:  # noqa: E111
        return datetime.fromtimestamp(timestamp, UTC)

    dt_util = _DateTimeModule()

from .const import DEFAULT_MODEL, DEFAULT_SW_VERSION, DOMAIN, MANUFACTURER
from .error_classification import classify_error_reason
from .service_guard import ServiceGuardResult

if TYPE_CHECKING:
  from .types import (  # noqa: E111
    DeviceLinkDetails,
    JSONLikeMapping,
    JSONMapping,
    JSONMutableMapping,
    JSONValue,
  )
else:
  JSONValue = object  # noqa: E111
  JSONMapping = Mapping[str, object]  # noqa: E111
  JSONMutableMapping = dict[str, object]  # noqa: E111

_LOGGER = logging.getLogger(__name__)

# Type variables for generic functions
T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")
P = ParamSpec("P")
R = TypeVar("R")
Number = Real

type DateTimeConvertible = datetime | date | str | float | int | Number
type JSONMappingLike = Mapping[str, "JSONValue"]


@dataclass(frozen=True, slots=True)
class ErrorContext:
  """Normalised error details for consistent classification."""  # noqa: E111

  classification: str  # noqa: E111
  reason: str | None  # noqa: E111
  message: str  # noqa: E111
  error: Exception | str | None  # noqa: E111


def build_error_context(
  reason: str | None,
  error: Exception | str | None,
) -> ErrorContext:
  """Build a stable error context for telemetry and diagnostics."""  # noqa: E111

  classification = classify_error_reason(reason, error=error)  # noqa: E111
  if error is not None:  # noqa: E111
    message = str(error)
  elif reason:  # noqa: E111
    message = str(reason)
  else:  # noqa: E111
    message = classification or "unknown"

  return ErrorContext(  # noqa: E111
    classification=classification,
    reason=reason,
    message=message,
    error=error,
  )


def normalise_json_value(
  value: object,
  _seen: set[int] | None = None,
) -> JSONValue:
  """Normalise values into JSON-serialisable primitives."""  # noqa: E111

  if isinstance(value, int | float | str | bool) or value is None:  # noqa: E111
    return value

  if isinstance(value, datetime):  # noqa: E111
    return value.isoformat()

  if isinstance(value, date):  # noqa: E111
    return value.isoformat()

  if isinstance(value, time):  # noqa: E111
    return value.isoformat()

  if isinstance(value, timedelta):  # noqa: E111
    return str(value)

  if _seen is None:  # noqa: E111
    _seen = set()

  obj_id = id(value)  # noqa: E111
  if obj_id in _seen:  # noqa: E111
    return None

  _seen.add(obj_id)  # noqa: E111
  try:  # noqa: E111
    if is_dataclass(value) and not isinstance(value, type):
      return normalise_json_value(asdict(value), _seen)  # noqa: E111

    if hasattr(value, "to_mapping") and callable(value.to_mapping):
      try:  # noqa: E111
        mapping_value = cast(Mapping[str, object], value.to_mapping())
        return normalise_json_value(mapping_value, _seen)
      except Exception:  # pragma: no cover - defensive guard  # noqa: E111
        _LOGGER.debug(
          "Failed to normalise to_mapping payload for %s",
          value,
        )

    if hasattr(value, "to_dict") and callable(value.to_dict):
      try:  # noqa: E111
        dict_value = cast(Mapping[str, object], value.to_dict())
        return normalise_json_value(dict_value, _seen)
      except Exception:  # pragma: no cover - defensive guard  # noqa: E111
        _LOGGER.debug(
          "Failed to normalise to_dict payload for %s",
          value,
        )

    if hasattr(value, "__dict__") and not isinstance(value, type):
      return normalise_json_value(vars(value), _seen)  # noqa: E111

    if isinstance(value, Mapping):
      return {  # noqa: E111
        str(key): normalise_json_value(item, _seen) for key, item in value.items()
      }

    if isinstance(value, set | frozenset):
      return [normalise_json_value(item, _seen) for item in value]  # noqa: E111

    if isinstance(value, Sequence) and not isinstance(
      value,
      str | bytes | bytearray,
    ):
      return [normalise_json_value(item, _seen) for item in value]  # noqa: E111

    return repr(value)
  finally:  # noqa: E111
    _seen.discard(obj_id)


def normalise_json_mapping(
  data: Mapping[str, object] | None,
) -> JSONMutableMapping:
  """Return JSON-serialisable mapping values for entity attributes."""  # noqa: E111

  if not data:  # noqa: E111
    return {}

  return {  # noqa: E111
    str(key): cast(JSONValue, normalise_json_value(value))
    for key, value in data.items()
  }


def normalize_value(value: object, _seen: set[int] | None = None) -> JSONValue:
  """Normalize values into JSON-serialisable primitives.

  Converts dataclasses, datetimes, and timedeltas into JSON-safe payloads so
  diagnostics and entity attributes stay serialisable.
  """  # noqa: E111

  return normalise_json_value(value, _seen)  # noqa: E111


def normalise_entity_attributes(
  data: Mapping[str, object] | None,
) -> JSONMutableMapping:
  """Return JSON-serialisable entity attributes."""  # noqa: E111

  if data is None:  # noqa: E111
    return {}

  return cast(JSONMutableMapping, normalize_value(data))  # noqa: E111


def resolve_default_feeding_amount(
  coordinator: PawControlCoordinator,
  dog_id: str,
  meal_type: str | None,
) -> float:
  """Resolve a default feeding amount for the specified dog."""  # noqa: E111

  from .runtime_data import get_runtime_data  # noqa: E111

  runtime_data = get_runtime_data(coordinator.hass, coordinator.config_entry)  # noqa: E111
  if runtime_data is None:  # noqa: E111
    raise HomeAssistantError("Runtime data not available")

  managers = runtime_data.runtime_managers  # noqa: E111
  feeding_manager = managers.feeding_manager or getattr(  # noqa: E111
    runtime_data,
    "feeding_manager",
    None,
  )
  if feeding_manager is None:  # noqa: E111
    raise HomeAssistantError("Feeding manager not available")

  config = feeding_manager.get_feeding_config(dog_id)  # noqa: E111
  if not config:  # noqa: E111
    raise HomeAssistantError(
      "Feeding configuration not available; configure feeding settings first.",
    )

  meal_enum = None  # noqa: E111
  if isinstance(meal_type, str):  # noqa: E111
    from .feeding_manager import MealType

    try:
      meal_enum = MealType(meal_type)  # noqa: E111
    except ValueError:
      _LOGGER.warning(  # noqa: E111
        "Unknown meal type '%s' for %s; using default portion size",
        meal_type,
        dog_id,
      )

  amount = config.calculate_portion_size(meal_enum)  # noqa: E111
  if amount <= 0:  # noqa: E111
    raise HomeAssistantError(
      "Feeding amount could not be resolved; check feeding settings.",
    )

  return amount  # noqa: E111


class ServiceCallKeywordArgs(TypedDict, total=False):
  """Keyword arguments forwarded to Home Assistant service calls."""  # noqa: E111

  blocking: bool  # noqa: E111
  target: JSONMutableMapping  # noqa: E111
  context: Context  # noqa: E111


class FireEventKeywordArgs(TypedDict, total=False):
  """Keyword arguments supported by Home Assistant bus events."""  # noqa: E111

  context: Context  # noqa: E111
  origin: EventOrigin  # noqa: E111
  time_fired: datetime  # noqa: E111


class ConfigurationValidationResult(TypedDict):
  """Validation report returned by :func:`validate_configuration_schema`."""  # noqa: E111

  valid: bool  # noqa: E111
  missing_keys: list[str]  # noqa: E111
  unknown_keys: list[str]  # noqa: E111
  has_all_required: bool  # noqa: E111
  has_unknown: bool  # noqa: E111


class DeviceRegistryUpdate(TypedDict, total=False):
  """Fields forwarded to ``device_registry.async_update_device``."""  # noqa: E111

  suggested_area: str  # noqa: E111
  serial_number: str  # noqa: E111
  hw_version: str  # noqa: E111
  sw_version: str  # noqa: E111
  configuration_url: str  # noqa: E111


def _coerce_json_mutable(
  mapping: JSONMappingLike | JSONMutableMapping | None,
) -> JSONMutableMapping:
  """Create a JSON-compatible mutable mapping copy from any mapping input."""  # noqa: E111

  if mapping is None:  # noqa: E111
    return {}

  if isinstance(mapping, dict):  # noqa: E111
    return cast(JSONMutableMapping, dict(mapping))

  return {key: cast(JSONValue, value) for key, value in mapping.items()}  # noqa: E111


def normalise_json(value: Any, _seen: set[int] | None = None) -> JSONValue:
  """Normalise values into JSON-serialisable payloads."""  # noqa: E111

  if isinstance(value, int | float | str | bool) or value is None:  # noqa: E111
    return value

  if isinstance(value, datetime):  # noqa: E111
    return value.isoformat()

  if isinstance(value, date):  # noqa: E111
    return value.isoformat()

  if isinstance(value, time):  # noqa: E111
    return value.isoformat()

  if isinstance(value, timedelta):  # noqa: E111
    return value.total_seconds()

  if _seen is None:  # noqa: E111
    _seen = set()

  obj_id = id(value)  # noqa: E111
  if obj_id in _seen:  # noqa: E111
    return None

  _seen.add(obj_id)  # noqa: E111
  try:  # noqa: E111
    if is_dataclass(value) and not isinstance(value, type):
      return normalise_json(asdict(value), _seen)  # noqa: E111

    if hasattr(value, "to_mapping") and callable(value.to_mapping):
      try:  # noqa: E111
        mapping_value = cast(Mapping[str, object], value.to_mapping())
        return normalise_json(mapping_value, _seen)
      except Exception:  # pragma: no cover - defensive guard  # noqa: E111
        _LOGGER.debug(
          "Failed to normalise to_mapping payload for %s",
          value,
        )

    if hasattr(value, "to_dict") and callable(value.to_dict):
      try:  # noqa: E111
        dict_value = cast(Mapping[str, object], value.to_dict())
        return normalise_json(dict_value, _seen)
      except Exception:  # pragma: no cover - defensive guard  # noqa: E111
        _LOGGER.debug(
          "Failed to normalise to_dict payload for %s",
          value,
        )

    if hasattr(value, "__dict__") and not isinstance(value, type):
      return normalise_json(vars(value), _seen)  # noqa: E111

    if isinstance(value, Mapping):
      return {str(key): normalise_json(item, _seen) for key, item in value.items()}  # noqa: E111

    if isinstance(
      value,
      list | tuple | set | frozenset | Sequence,
    ) and not isinstance(value, str | bytes | bytearray):
      return [normalise_json(item, _seen) for item in value]  # noqa: E111

    return repr(value)
  finally:  # noqa: E111
    _seen.discard(obj_id)


async def async_call_hass_service_if_available(
  hass: HomeAssistant | None,
  domain: str,
  service: str,
  service_data: JSONMappingLike | JSONMutableMapping | None = None,
  *,
  target: JSONMappingLike | JSONMutableMapping | None = None,
  blocking: bool = False,
  context: Context | None = None,
  description: str | None = None,
  logger: logging.Logger | None = None,
) -> ServiceGuardResult:
  """Call a Home Assistant service when the instance is available."""  # noqa: E111

  active_logger = logger or _LOGGER  # noqa: E111
  description_hint = description or None  # noqa: E111

  if hass is None:  # noqa: E111
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
      capture.append(guard_result)  # noqa: E111
    return guard_result

  services = getattr(hass, "services", None)  # noqa: E111
  async_call = getattr(services, "async_call", None)  # noqa: E111
  if not callable(async_call):  # noqa: E111
    context_hint = f" for {description}" if description_hint else ""
    active_logger.debug(
      "Skipping %s.%s service call%s because the Home Assistant services API is not available",  # noqa: E501
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
      capture.append(guard_result)  # noqa: E111
    return guard_result

  payload = _coerce_json_mutable(service_data)  # noqa: E111
  target_payload = (  # noqa: E111
    _coerce_json_mutable(
      target,
    )
    if target is not None
    else None
  )

  kwargs: ServiceCallKeywordArgs = ServiceCallKeywordArgs(blocking=blocking)  # noqa: E111
  if target_payload is not None:  # noqa: E111
    kwargs["target"] = target_payload
  if context is not None:  # noqa: E111
    kwargs["context"] = context

  await async_call(  # noqa: E111
    domain,
    service,
    payload,
    **kwargs,
  )
  guard_result = ServiceGuardResult(  # noqa: E111
    domain=domain,
    service=service,
    executed=True,
    description=description_hint,
  )
  capture = _GUARD_CAPTURE.get(None)  # noqa: E111
  if capture is not None:  # noqa: E111
    capture.append(guard_result)
  return guard_result  # noqa: E111


class PortionValidationResult(TypedDict):
  """Validation outcome for a single portion size."""  # noqa: E111

  valid: bool  # noqa: E111
  warnings: list[str]  # noqa: E111
  recommendations: list[str]  # noqa: E111
  percentage_of_daily: float  # noqa: E111


async def async_fire_event(
  hass: HomeAssistant,
  event_type: str,
  event_data: JSONLikeMapping | None = None,
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
  """  # noqa: E111

  bus_async_fire = hass.bus.async_fire  # noqa: E111

  accepts_any_kw, supported_keywords = _get_bus_keyword_support(  # noqa: E111
    bus_async_fire,
  )

  def _supports(keyword: str) -> bool:  # noqa: E111
    return accepts_any_kw or keyword in supported_keywords

  kwargs: FireEventKeywordArgs = FireEventKeywordArgs()  # noqa: E111
  if context is not None and _supports("context"):  # noqa: E111
    kwargs["context"] = context
  if origin is not None and _supports("origin"):  # noqa: E111
    kwargs["origin"] = origin
  sanitized_time_fired: datetime | None = None  # noqa: E111
  if time_fired is not None:  # noqa: E111
    sanitized_time_fired = ensure_utc_datetime(time_fired)
    if sanitized_time_fired is None:
      _LOGGER.warning(  # noqa: E111
        "Dropping invalid time_fired payload %r for %s event",
        time_fired,
        event_type,
      )
  if sanitized_time_fired is not None and _supports("time_fired"):  # noqa: E111
    kwargs["time_fired"] = sanitized_time_fired

  result = bus_async_fire(event_type, event_data, **kwargs)  # noqa: E111
  if inspect.isawaitable(result):  # noqa: E111
    return await result
  return result  # noqa: E111


# Cache Home Assistant bus signature support to avoid repeated inspection.
_SIGNATURE_SUPPORT_CACHE: WeakKeyDictionary[object, tuple[bool, frozenset[str]]] = (
  WeakKeyDictionary()
)


def _get_bus_keyword_support(
  bus_async_fire: Callable[..., Any],
) -> tuple[bool, frozenset[str]]:
  """Return metadata describing which keywords the bus supports."""  # noqa: E111

  cache_key: object = getattr(bus_async_fire, "__func__", bus_async_fire)  # noqa: E111

  try:  # noqa: E111
    return _SIGNATURE_SUPPORT_CACHE[cache_key]
  except KeyError:  # noqa: E111
    support = _introspect_bus_keywords(bus_async_fire)
    with suppress(TypeError):  # pragma: no cover - object not weak-referenceable
      _SIGNATURE_SUPPORT_CACHE[cache_key] = support  # noqa: E111
    return support


def _introspect_bus_keywords(
  bus_async_fire: Callable[..., Any],
) -> tuple[bool, frozenset[str]]:
  """Inspect the bus callable for supported keyword arguments."""  # noqa: E111

  try:  # noqa: E111
    signature = inspect.signature(bus_async_fire)
  except ValueError:  # noqa: E111
    return True, frozenset()
  except TypeError:  # noqa: E111
    return True, frozenset()

  parameters = signature.parameters  # noqa: E111
  accepts_any_kw = any(  # noqa: E111
    parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
  )

  supported_keywords = frozenset(parameters)  # noqa: E111
  return accepts_any_kw, supported_keywords  # noqa: E111


def is_number(value: Any) -> TypeGuard[Number]:
  """Return whether ``value`` is a real number (excluding booleans)."""  # noqa: E111

  if isinstance(value, bool):  # noqa: E111
    return False
  return isinstance(value, Real)  # noqa: E111


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
  """  # noqa: E111

  if isinstance(identifier, tuple):  # noqa: E111
    candidate = identifier
  elif isinstance(identifier, Sequence) and not isinstance(  # noqa: E111
    identifier,
    str | bytes | bytearray,
  ):
    candidate = tuple(identifier)
  else:  # noqa: E111
    return None

  if len(candidate) != 2:  # noqa: E111
    return None

  domain, value = candidate  # noqa: E111
  if domain is None or value is None:  # noqa: E111
    return None

  domain_str = str(domain).strip()  # noqa: E111
  value_str = str(value).strip()  # noqa: E111

  if not domain_str or not value_str:  # noqa: E111
    return None

  return domain_str, value_str  # noqa: E111


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
  """  # noqa: E111
  # Sanitize dog_id for device identifier  # noqa: E114
  sanitized_id = sanitize_dog_id(dog_id)  # noqa: E111

  identifiers: set[tuple[str, str]] = {(DOMAIN, sanitized_id)}  # noqa: E111

  if extra_identifiers:  # noqa: E111
    for identifier in extra_identifiers:
      normalized = _normalize_identifier_pair(identifier)  # noqa: E111
      if normalized is not None:  # noqa: E111
        identifiers.add(normalized)

  if microchip_id is not None:  # noqa: E111
    sanitized_microchip = sanitize_microchip_id(str(microchip_id))
    if sanitized_microchip:
      identifiers.add(("microchip", sanitized_microchip))  # noqa: E111

  computed_model = f"{model} - {breed}" if breed else model  # noqa: E111

  device_info: DeviceInfo = {  # noqa: E111
    "identifiers": identifiers,
    "name": dog_name,
    "manufacturer": manufacturer,
    "model": computed_model,
  }

  if sw_version:  # noqa: E111
    device_info["sw_version"] = sw_version

  if configuration_url:  # noqa: E111
    device_info["configuration_url"] = configuration_url

  if serial_number:  # noqa: E111
    device_info["serial_number"] = str(serial_number)

  if hw_version:  # noqa: E111
    device_info["hw_version"] = str(hw_version)

  if suggested_area:  # noqa: E111
    device_info["suggested_area"] = suggested_area

  return device_info  # noqa: E111


async def async_call_add_entities(
  add_entities_callback: AddEntitiesCallback,
  entities: Iterable[Entity],
  *,
  update_before_add: bool = False,
) -> None:
  """Invoke Home Assistant's async_add_entities callback and await when needed."""  # noqa: E111

  entities_list = list(entities)  # noqa: E111
  result = add_entities_callback(entities_list, update_before_add)  # noqa: E111

  if inspect.isawaitable(result):  # noqa: E111
    awaitable_result = result
    await awaitable_result


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
  """Link a dog to a device registry entry and return it."""  # noqa: E111

  device_info = create_device_info(  # noqa: E111
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

  device_registry = dr.async_get(hass)  # noqa: E111
  device = device_registry.async_get_or_create(  # noqa: E111
    config_entry_id=config_entry_id,
    identifiers=device_info["identifiers"],
    manufacturer=device_info["manufacturer"],
    model=device_info["model"],
    name=device_info["name"],
    sw_version=device_info.get("sw_version"),
    configuration_url=device_info.get("configuration_url"),
  )

  update_kwargs: DeviceRegistryUpdate = DeviceRegistryUpdate()  # noqa: E111
  for field in (  # noqa: E111
    "suggested_area",
    "serial_number",
    "hw_version",
    "sw_version",
    "configuration_url",
  ):
    value = device_info.get(field)
    if value and getattr(device, field, None) != value:
      update_kwargs[field] = value  # noqa: E111

  if update_kwargs:  # noqa: E111
    try:
      if updated_device := device_registry.async_update_device(  # noqa: E111
        device.id,
        **update_kwargs,
      ):
        device = updated_device
    except Exception as err:  # pragma: no cover - defensive, HA guarantees API
      _LOGGER.debug(  # noqa: E111
        "Failed to update device registry entry %s for dog %s: %s",
        device.id,
        dog_id,
        err,
      )

  return device  # noqa: E111


class PawControlDeviceLinkMixin:
  """Mixin providing device registry linking for PawControl entities."""  # noqa: E111

  def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: E111
    """Set up default device link metadata."""

    super().__init__(*args, **kwargs)
    self._device_link_defaults: DeviceLinkDetails = {
      "manufacturer": MANUFACTURER,
      "model": DEFAULT_MODEL,
      "sw_version": DEFAULT_SW_VERSION,
      "configuration_url": "https://github.com/BigDaddy1990/pawcontrol",
    }
    self._linked_device_entry: DeviceEntry | None = None
    self._device_link_initialized = False

  def _set_device_link_info(self, **info: Any) -> None:  # noqa: E111
    """Update device link metadata used when creating the device entry."""

    self._device_link_defaults.update(cast("DeviceLinkDetails", info))

  def _device_link_details(self) -> DeviceLinkDetails:  # noqa: E111
    """Return a copy of the device metadata for linking."""

    return cast("DeviceLinkDetails", dict(self._device_link_defaults))

  async def async_added_to_hass(self) -> None:  # noqa: E111
    """Link entity to device entry after regular setup."""

    # CoordinatorEntity and RestoreEntity expose incompatible type hints for
    # async_added_to_hass(), so we silence the mismatch on the cooperative
    # super() call used by Home Assistant's entity model.
    await super().async_added_to_hass()  # type: ignore[misc]
    await self._async_link_device_entry()

  @property  # noqa: E111
  def device_info(self) -> DeviceInfo | None:  # noqa: E111
    """Return device metadata for entity registry registration."""

    dog_id = getattr(self, "_dog_id", None)
    dog_name = getattr(self, "_dog_name", None)
    if not dog_id or not dog_name:
      return None  # noqa: E111

    info = self._device_link_details()
    suggested_area = info.get("suggested_area") or getattr(
      self,
      "_attr_suggested_area",
      None,
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
        Iterable[tuple[str, str]] | None,
        info.get("extra_identifiers"),
      ),
    )

  async def _async_link_device_entry(self) -> None:  # noqa: E111
    """Create or fetch the device entry and attach it to the entity."""

    if self._device_link_initialized:
      return  # noqa: E111

    hass: HomeAssistant | None = getattr(self, "hass", None)
    coordinator = getattr(self, "coordinator", None)
    if hass is None or coordinator is None:
      return  # noqa: E111

    config_entry = getattr(coordinator, "config_entry", None)
    dog_id = getattr(self, "_dog_id", None)
    dog_name = getattr(self, "_dog_name", None)

    if config_entry is None or dog_id is None or dog_name is None:
      return  # noqa: E111

    try:
      device = await async_get_or_create_dog_device_entry(  # noqa: E111
        hass,
        config_entry_id=config_entry.entry_id,
        dog_id=dog_id,
        dog_name=dog_name,
        **self._device_link_details(),
      )
    except Exception as err:  # pragma: no cover - defensive logging
      _LOGGER.warning(  # noqa: E111
        "Failed to link PawControl entity %s to device: %s",
        getattr(self, "entity_id", f"pawcontrol_{dog_id}"),
        err,
      )
      return  # noqa: E111

    self.device_entry = device
    self._linked_device_entry = device
    self._device_link_initialized = True

    entity_id = cast(str | None, getattr(self, "entity_id", None))
    if entity_id:
      entity_registry = er.async_get(hass)  # noqa: E111
      entity_entry = entity_registry.async_get(entity_id)  # noqa: E111
      if entity_entry and entity_entry.device_id != device.id:  # noqa: E111
        entity_registry.async_update_entity(
          entity_id,
          device_id=device.id,
        )


def deep_merge_dicts[T: JSONMutableMapping](
  base: T,
  updates: Mapping[str, JSONValue],
) -> T:
  """Recursively merge JSON-compatible mappings without mutating inputs."""  # noqa: E111

  result = cast(T, base.copy())  # noqa: E111

  for key, value in updates.items():  # noqa: E111
    existing = result.get(key)
    if isinstance(existing, dict) and isinstance(value, Mapping):
      result[key] = deep_merge_dicts(  # noqa: E111
        cast(JSONMutableMapping, existing),
        cast(Mapping[str, JSONValue], value),
      )
    else:
      result[key] = value  # noqa: E111

  return result  # noqa: E111


def safe_get_nested[DefaultT](
  data: JSONMapping,
  path: str,
  *,
  default: DefaultT | None = None,
  separator: str = ".",
) -> JSONValue | DefaultT | None:
  """Safely resolve a dotted path from a JSON-compatible mapping."""  # noqa: E111
  try:  # noqa: E111
    keys = path.split(separator)
    current: JSONValue | Mapping[str, JSONValue] = data

    for key in keys:
      if isinstance(current, dict) and key in current:  # noqa: E111
        current = current[key]
      else:  # noqa: E111
        return default

    return current
  except AttributeError, KeyError, TypeError:  # noqa: E111
    return default


def safe_set_nested[T: JSONMutableMapping](
  data: T,
  path: str,
  value: JSONValue,
  *,
  separator: str = ".",
) -> T:
  """Safely set a dotted path within a JSON-compatible mapping."""  # noqa: E111
  keys = path.split(separator)  # noqa: E111
  current: JSONMutableMapping = cast(JSONMutableMapping, data)  # noqa: E111

  # Navigate to parent of target key  # noqa: E114
  for key in keys[:-1]:  # noqa: E111
    next_value = current.get(key)
    if not isinstance(next_value, dict):
      branch: JSONMutableMapping = {}  # noqa: E111
      current[key] = branch  # noqa: E111
      current = branch  # noqa: E111
    else:
      current = cast(JSONMutableMapping, next_value)  # noqa: E111

  # Set the final value  # noqa: E114
  current[keys[-1]] = value  # noqa: E111
  return data  # noqa: E111


def validate_time_string(time_str: str | None) -> time | None:
  """Validate and parse time string.

  Args:
      time_str: Time string in HH:MM or HH:MM:SS format

  Returns:
      Parsed time object or None if invalid
  """  # noqa: E111
  if not time_str:  # noqa: E111
    return None

  try:  # noqa: E111
    # Support both HH:MM and HH:MM:SS formats
    if re.match(r"^\d{1,2}:\d{2}$", time_str):
      hour, minute = map(int, time_str.split(":"))  # noqa: E111
      return time(hour, minute)  # noqa: E111
    if re.match(r"^\d{1,2}:\d{2}:\d{2}$", time_str):
      hour, minute, second = map(int, time_str.split(":"))  # noqa: E111
      return time(hour, minute, second)  # noqa: E111
  except ValueError, AttributeError:  # noqa: E111
    pass

  return None  # noqa: E111


def validate_email(email: str | None) -> bool:
  """Validate email address format.

  Args:
      email: Email address to validate

  Returns:
      True if valid email format
  """  # noqa: E111
  if not email:  # noqa: E111
    return False

  # Simple but effective email regex  # noqa: E114
  pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"  # noqa: E111
  return bool(re.match(pattern, email))  # noqa: E111


def sanitize_dog_id(dog_id: str) -> str:
  """Sanitize dog ID for use as entity identifier.

  Args:
      dog_id: Raw dog ID

  Returns:
      Sanitized dog ID suitable for entity IDs
  """  # noqa: E111
  # Convert to lowercase and replace invalid characters  # noqa: E114
  sanitized = re.sub(r"[^a-z0-9_]", "_", dog_id.lower())  # noqa: E111
  sanitized = re.sub(r"_+", "_", sanitized).strip("_")  # noqa: E111

  if not sanitized:  # noqa: E111
    digest = hashlib.sha256(dog_id.encode("utf-8", "ignore")).hexdigest()
    sanitized = f"dog_{digest[:8]}"
  elif not sanitized[0].isalpha():  # noqa: E111
    sanitized = f"dog_{sanitized}"

  return sanitized  # noqa: E111


def sanitize_microchip_id(microchip_id: str) -> str | None:
  """Normalize microchip identifiers for consistent device registry entries."""  # noqa: E111

  sanitized = re.sub(r"[^A-Za-z0-9]", "", microchip_id).upper()  # noqa: E111
  return sanitized or None  # noqa: E111


def format_duration(seconds: int | float) -> str:
  """Format duration in seconds to human-readable string.

  Args:
      seconds: Duration in seconds

  Returns:
      Formatted duration string
  """  # noqa: E111
  if seconds < 60:  # noqa: E111
    return f"{int(seconds)}s"
  if seconds < 3600:  # noqa: E111
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    if remaining_seconds > 0:
      return f"{minutes}m {remaining_seconds}s"  # noqa: E111
    return f"{minutes}m"
  hours = int(seconds // 3600)  # noqa: E111
  remaining_minutes = int((seconds % 3600) // 60)  # noqa: E111
  if remaining_minutes > 0:  # noqa: E111
    return f"{hours}h {remaining_minutes}m"
  return f"{hours}h"  # noqa: E111


def format_distance(meters: float, unit: str = "metric") -> str:
  """Format distance with appropriate units.

  Args:
      meters: Distance in meters
      unit: Unit system ("metric" or "imperial")

  Returns:
      Formatted distance string
  """  # noqa: E111
  if unit == "imperial":  # noqa: E111
    feet = meters * 3.28084
    if feet < 5280:
      return f"{int(feet)} ft"  # noqa: E111
    miles = feet / 5280
    return f"{miles:.1f} mi"
  if meters < 1000:  # noqa: E111
    return f"{int(meters)} m"
  kilometers = meters / 1000  # noqa: E111
  return f"{kilometers:.1f} km"  # noqa: E111


def calculate_age_from_months(age_months: int) -> dict[str, int]:
  """Calculate years and months from total months.

  Args:
      age_months: Total age in months

  Returns:
      Dictionary with years and months

  Raises:
      TypeError: If ``age_months`` is not an integer value
      ValueError: If ``age_months`` is negative
  """  # noqa: E111
  if isinstance(age_months, bool) or not isinstance(age_months, int):  # noqa: E111
    raise TypeError("age_months must be provided as an integer")

  if age_months < 0:  # noqa: E111
    raise ValueError("age_months must be non-negative")

  years = age_months // 12  # noqa: E111
  months = age_months % 12  # noqa: E111

  return {  # noqa: E111
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
  """  # noqa: E111
  if is_number(weight_input):  # noqa: E111
    numeric_weight = float(weight_input)
    return numeric_weight if numeric_weight > 0 else None

  if not isinstance(weight_input, str):  # noqa: E111
    return None

  # Remove whitespace and convert to lowercase  # noqa: E114
  weight_str = weight_input.strip().lower()  # noqa: E111

  # Handle common weight formats  # noqa: E114
  if "kg" in weight_str:  # noqa: E111
    try:
      return float(weight_str.replace("kg", "").strip())  # noqa: E111
    except ValueError:
      pass  # noqa: E111
  elif "lb" in weight_str or "lbs" in weight_str:  # noqa: E111
    try:
      # Convert pounds to kilograms  # noqa: E114
      lbs = float(  # noqa: E111
        weight_str
        .replace(
          "lbs",
          "",
        )
        .replace("lb", "")
        .strip(),
      )
      return lbs * 0.453592  # noqa: E111
    except ValueError:
      pass  # noqa: E111
  else:  # noqa: E111
    # Try parsing as plain number (assume kg)
    try:
      return float(weight_str)  # noqa: E111
    except ValueError:
      pass  # noqa: E111

  return None  # noqa: E111


def generate_entity_id(domain: str, dog_id: str, entity_type: str) -> str:
  """Generate entity ID following Home Assistant conventions.

  Args:
      domain: Integration domain
      dog_id: Dog identifier
      entity_type: Type of entity

  Returns:
      Generated entity ID
  """  # noqa: E111
  sanitized_dog_id = sanitize_dog_id(dog_id)  # noqa: E111
  sanitized_type = re.sub(r"[^a-z0-9_]", "_", entity_type.lower())  # noqa: E111

  return f"{domain}.{sanitized_dog_id}_{sanitized_type}"  # noqa: E111


def calculate_bmi_equivalent(weight_kg: float, breed_size: str) -> float | None:
  """Calculate BMI equivalent for dogs based on breed size.

  Args:
      weight_kg: Weight in kilograms
      breed_size: Size category ("toy", "small", "medium", "large", "giant")

  Returns:
      BMI equivalent or None if invalid
  """  # noqa: E111
  # Standard weight ranges for breed sizes (kg)  # noqa: E114
  size_ranges = {  # noqa: E111
    "toy": (1.0, 6.0),
    "small": (4.0, 15.0),
    "medium": (8.0, 30.0),
    "large": (22.0, 50.0),
    "giant": (35.0, 90.0),
  }

  if breed_size not in size_ranges:  # noqa: E111
    return None

  min_weight, max_weight = size_ranges[breed_size]  # noqa: E111

  # Calculate relative position within breed size range  # noqa: E114
  if weight_kg <= min_weight:  # noqa: E111
    return 15.0  # Underweight
  if weight_kg >= max_weight:  # noqa: E111
    return 30.0  # Overweight
  # Linear interpolation between 18.5 (normal low) and 25 (normal high)  # noqa: E114
  ratio = (weight_kg - min_weight) / (max_weight - min_weight)  # noqa: E111
  return 18.5 + (ratio * 6.5)  # 18.5 to 25  # noqa: E111


def validate_portion_size(
  portion: float,
  daily_amount: float,
  meals_per_day: int = 2,
) -> PortionValidationResult:
  """Validate portion size against daily requirements.

  Args:
      portion: Portion size in grams
      daily_amount: Total daily food amount
      meals_per_day: Number of meals per day

  Returns:
      Validation result with warnings and recommendations
  """  # noqa: E111

  result: PortionValidationResult = {  # noqa: E111
    "valid": True,
    "warnings": [],
    "recommendations": [],
    "percentage_of_daily": 0.0,
  }

  if not is_number(portion):  # noqa: E111
    result["valid"] = False
    result["warnings"].append("Portion must be a real number")
    result["recommendations"].append("Provide the portion size in grams")
    return result

  portion_value = float(portion)  # noqa: E111
  if not math.isfinite(portion_value):  # noqa: E111
    result["valid"] = False
    result["warnings"].append("Portion must be a finite number")
    result["recommendations"].append(
      "Replace NaN or infinite values with real numbers",
    )
    return result

  if portion_value <= 0:  # noqa: E111
    result["valid"] = False
    result["warnings"].append("Portion must be greater than zero")
    result["recommendations"].append(
      "Increase the portion size or remove the feeding entry",
    )
    return result

  if not is_number(daily_amount):  # noqa: E111
    result["valid"] = False
    result["warnings"].append("Daily food amount must be a real number")
    result["recommendations"].append(
      "Update the feeding configuration with a numeric daily amount",
    )
    return result

  daily_amount_value = float(daily_amount)  # noqa: E111
  if not math.isfinite(daily_amount_value) or daily_amount_value <= 0:  # noqa: E111
    result["valid"] = False
    result["warnings"].append(
      "Daily food amount must be positive to validate portion sizes",
    )
    result["recommendations"].append(
      "Set a positive daily food amount for the feeding configuration",
    )
    return result

  if meals_per_day <= 0:  # noqa: E111
    result["warnings"].append(
      "Meals per day is not positive; assuming a single meal for validation",
    )
    result["recommendations"].append(
      "Adjust meals per day to a positive value in the feeding configuration",
    )
    meals_per_day = 1

  percentage = (portion_value / daily_amount_value) * 100  # noqa: E111
  result["percentage_of_daily"] = percentage  # noqa: E111

  expected_percentage = 100 / meals_per_day  # noqa: E111

  if portion_value > daily_amount_value:  # noqa: E111
    result["valid"] = False
    result["warnings"].append(
      "Portion exceeds the configured daily amount",
    )
    result["recommendations"].append(
      "Reduce the portion size or increase the daily food amount",
    )

  if percentage > 70:  # noqa: E111
    result["valid"] = False
    result["warnings"].append("Portion exceeds 70% of daily requirement")
    result["recommendations"].append("Consider reducing portion size")
  elif percentage > expected_percentage * 1.5:  # noqa: E111
    result["warnings"].append(
      "Portion is larger than typical for meal frequency",
    )
    result["recommendations"].append("Verify portion calculation")
  elif percentage < 5:  # noqa: E111
    result["warnings"].append(
      "Portion is very small compared to daily requirement",
    )
    result["recommendations"].append(
      "Consider increasing portion or meal frequency",
    )

  return result  # noqa: E111


def chunk_list[T](items: Sequence[T], chunk_size: int) -> list[list[T]]:
  """Split a list into chunks of specified size.

  Args:
      items: List to chunk
      chunk_size: Maximum size of each chunk

  Returns:
      List of chunks
  """  # noqa: E111
  if chunk_size <= 0:  # noqa: E111
    raise ValueError("Chunk size must be positive")

  return [list(items[i : i + chunk_size]) for i in range(0, len(items), chunk_size)]  # noqa: E111


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
  """Safely divide two numbers with default for division by zero.

  Args:
      numerator: Number to divide
      denominator: Number to divide by
      default: Default value if denominator is zero

  Returns:
      Division result or default
  """  # noqa: E111
  try:  # noqa: E111
    return numerator / denominator if denominator != 0 else default
  except TypeError, ZeroDivisionError:  # noqa: E111
    return default


def clamp(value: float, min_value: float, max_value: float) -> float:
  """Clamp value between minimum and maximum.

  Args:
      value: Value to clamp
      min_value: Minimum allowed value
      max_value: Maximum allowed value

  Returns:
      Clamped value
  """  # noqa: E111
  return max(min_value, min(value, max_value))  # noqa: E111


def is_dict_subset[K, V](subset: Mapping[K, V], superset: Mapping[K, V]) -> bool:
  """Check if one dictionary is a subset of another.

  Args:
      subset: Dictionary to check if it's a subset
      superset: Dictionary to check against

  Returns:
      True if subset is contained in superset
  """  # noqa: E111
  try:  # noqa: E111
    return all(
      key in superset and superset[key] == value for key, value in subset.items()
    )
  except AttributeError, TypeError:  # noqa: E111
    return False


def flatten_dict(
  data: JSONMapping,
  *,
  separator: str = ".",
  prefix: str = "",
) -> JSONMutableMapping:
  """Flatten a JSON mapping using dot notation for nested keys."""  # noqa: E111

  flattened: JSONMutableMapping = {}  # noqa: E111

  for key, value in data.items():  # noqa: E111
    new_key = f"{prefix}{separator}{key}" if prefix else key

    if isinstance(value, Mapping):
      flattened.update(  # noqa: E111
        flatten_dict(
          cast(Mapping[str, JSONValue], value),
          separator=separator,
          prefix=new_key,
        ),
      )
    else:
      flattened[new_key] = value  # noqa: E111

  return flattened  # noqa: E111


def unflatten_dict(
  data: Mapping[str, JSONValue],
  *,
  separator: str = ".",
) -> JSONMutableMapping:
  """Expand a flattened JSON mapping that uses dot notation keys."""  # noqa: E111

  result: JSONMutableMapping = {}  # noqa: E111

  for key, value in data.items():  # noqa: E111
    safe_set_nested(result, key, value, separator=separator)

  return result  # noqa: E111


def extract_numbers(text: str) -> list[float]:
  """Extract all numbers from text string.

  Args:
      text: Text to extract numbers from

  Returns:
      List of extracted numbers
  """  # noqa: E111
  pattern = r"-?\d+(?:\.\d+)?"  # noqa: E111
  matches = re.findall(pattern, text)  # noqa: E111

  try:  # noqa: E111
    return [float(match) for match in matches]
  except ValueError:  # noqa: E111
    return []


def generate_unique_id(*parts: str) -> str:
  """Generate unique ID from multiple parts.

  Args:
      *parts: Parts to combine into unique ID

  Returns:
      Generated unique ID
  """  # noqa: E111
  # Sanitize each part and join with underscores  # noqa: E114
  sanitized_parts = []  # noqa: E111
  for part in parts:  # noqa: E111
    if part:
      sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", str(part))  # noqa: E111
      sanitized = re.sub(r"_+", "_", sanitized).strip("_")  # noqa: E111
      if sanitized:  # noqa: E111
        sanitized_parts.append(sanitized.lower())

  return "_".join(sanitized_parts) if sanitized_parts else "unknown"  # noqa: E111


def retry_on_exception(
  max_retries: int = 3,
  delay: float = 1.0,
  backoff_factor: float = 2.0,
  exceptions: tuple[type[Exception], ...] = (Exception,),
  hass: HomeAssistant | None = None,
) -> Callable[
  [Callable[P, Awaitable[R]] | Callable[P, R]],
  Callable[P, Awaitable[R]],
]:
  """Retry a callable when it raises one of the provided exceptions.

  The returned decorator always exposes an async callable. When applied to a
  synchronous function the wrapped callable is executed in an executor via
  ``HomeAssistant.async_add_executor_job`` when available, ensuring the Home
  Assistant event loop stays responsive and avoiding blocking sleeps.

  Args:
      max_retries: Maximum number of retries
      delay: Initial delay between retries
      backoff_factor: Factor to multiply delay by each retry
      exceptions: Exception types to retry on
      hass: Home Assistant instance used to offload sync work to the executor

  Returns:
      Decorator that provides retry behaviour for async and sync callables.
  """  # noqa: E111

  def decorator(  # noqa: E111
    func: Callable[P, Awaitable[R]] | Callable[P, R],
  ) -> Callable[P, Awaitable[R]]:
    """Wrap `func` with retry handling that always returns an async callable."""

    is_coroutine = inspect.iscoroutinefunction(func)

    @wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
      """Execute the wrapped function with retry and backoff support."""  # noqa: E111

      last_exception: Exception | None = None  # noqa: E111
      current_delay = delay  # noqa: E111

      for attempt in range(max_retries + 1):  # noqa: E111
        try:
          if is_coroutine:  # noqa: E111
            coroutine = cast(Callable[P, Awaitable[R]], func)
            return await coroutine(*args, **kwargs)
          sync_func = cast(Callable[P, R], func)  # noqa: E111
          if hass is not None:  # noqa: E111
            if kwargs:
              sync_func = partial(sync_func, **kwargs)  # noqa: E111
            return await hass.async_add_executor_job(sync_func, *args)
          loop = asyncio.get_running_loop()  # noqa: E111
          if kwargs:  # noqa: E111
            return await loop.run_in_executor(
              None,
              partial(sync_func, *args, **kwargs),
            )
          return await loop.run_in_executor(None, partial(sync_func, *args))  # noqa: E111
        except exceptions as err:
          last_exception = err  # noqa: E111
          if attempt < max_retries:  # noqa: E111
            _LOGGER.debug(
              "Attempt %d failed for %s: %s. Retrying in %.1fs",
              attempt + 1,
              func.__name__,
              err,
              current_delay,
            )
            await asyncio.sleep(current_delay)
            current_delay *= backoff_factor
          else:  # noqa: E111
            _LOGGER.error(
              "All %d attempts failed for %s",
              max_retries + 1,
              func.__name__,
            )

      if last_exception is None:  # pragma: no cover - safety net  # noqa: E111
        last_exception = Exception(
          f"{func.__name__} failed without raising a captured exception",
        )
      raise last_exception  # noqa: E111

    return async_wrapper

  return decorator  # noqa: E111


def calculate_time_until(target_time: time) -> timedelta:
  """Calculate time until next occurrence of target time.

  Args:
      target_time: Target time of day

  Returns:
      Time delta until next occurrence
  """  # noqa: E111
  now = dt_util.now()  # noqa: E111
  today = now.date()  # noqa: E111

  # Try today first  # noqa: E114
  target_datetime = datetime.combine(today, target_time)  # noqa: E111
  target_datetime = dt_util.as_local(target_datetime)  # noqa: E111

  if target_datetime > now:  # noqa: E111
    return target_datetime - now
  # Must be tomorrow  # noqa: E114
  tomorrow = today + timedelta(days=1)  # noqa: E111
  target_datetime = datetime.combine(tomorrow, target_time)  # noqa: E111
  target_datetime = dt_util.as_local(target_datetime)  # noqa: E111
  return target_datetime - now  # noqa: E111


def format_relative_time(dt: datetime) -> str:
  """Format datetime as relative time string.

  Args:
      dt: Datetime to format

  Returns:
      Relative time string
  """  # noqa: E111
  now = dt_util.now()  # noqa: E111

  # Make both timezone-aware for comparison  # noqa: E114
  if dt.tzinfo is None:  # noqa: E111
    dt = cast(datetime, dt_util.as_local(dt))
  if now.tzinfo is None:  # noqa: E111
    now = cast(datetime, dt_util.as_local(now))

  delta = now - dt  # noqa: E111

  if delta.total_seconds() < 60:  # noqa: E111
    return "just now"
  if delta.total_seconds() < 3600:  # noqa: E111
    minutes = int(delta.total_seconds() / 60)
    return f"{minutes}m ago"
  if delta.total_seconds() < 86400:  # noqa: E111
    hours = int(delta.total_seconds() / 3600)
    return f"{hours}h ago"
  if delta.days == 1:  # noqa: E111
    return "yesterday"
  if delta.days < 7:  # noqa: E111
    return f"{delta.days} days ago"
  if delta.days < 30:  # noqa: E111
    weeks = delta.days // 7
    return f"{weeks} week{'s' if weeks > 1 else ''} ago"
  months = delta.days // 30  # noqa: E111
  return f"{months} month{'s' if months > 1 else ''} ago"  # noqa: E111


@overload
def ensure_utc_datetime(value: None) -> None:  # pragma: no cover - typing helper
  """Return ``None`` when no value is provided."""  # noqa: E111


@overload
def ensure_utc_datetime(value: DateTimeConvertible) -> datetime | None:
  """Convert supported input types to aware UTC datetimes."""  # noqa: E111


def ensure_utc_datetime(value: DateTimeConvertible | None) -> datetime | None:
  """Return a timezone-aware UTC datetime from various input formats."""  # noqa: E111

  if value is None:  # noqa: E111
    return None

  if isinstance(value, datetime):  # noqa: E111
    dt_value = value
  elif isinstance(value, date):  # noqa: E111
    dt_value = datetime.combine(value, datetime.min.time())
  elif isinstance(value, str):  # noqa: E111
    if not value:
      return None  # noqa: E111
    if not any(character.isdigit() for character in value):
      return None  # noqa: E111
    parsed_value = _parse_datetime_string(value)
    if parsed_value is None:
      return None  # noqa: E111
    dt_value = parsed_value
  elif is_number(value):  # noqa: E111
    timestamp_value = _datetime_from_timestamp(value)
    if timestamp_value is None:
      return None  # noqa: E111
    dt_value = timestamp_value
  else:  # noqa: E111
    return None

  if dt_value.tzinfo is None:  # noqa: E111
    dt_value = dt_value.replace(tzinfo=UTC)

  return dt_util.as_utc(dt_value)  # noqa: E111


def _parse_datetime_string(value: str) -> datetime | None:
  """Parse ``value`` into a timezone-aware datetime when possible."""  # noqa: E111

  try:  # noqa: E111
    dt_value = dt_util.parse_datetime(value)
  except ValueError:  # noqa: E111
    dt_value = None

  if dt_value is not None:  # noqa: E111
    return dt_value

  date_parser = getattr(dt_util, "parse_date", None)  # noqa: E111
  date_value: date | None = None  # noqa: E111

  if callable(date_parser):  # noqa: E111
    with suppress(ValueError):
      date_value = date_parser(value)  # noqa: E111

  if date_value is None:  # noqa: E111
    with suppress(ValueError):
      date_value = date.fromisoformat(value)  # noqa: E111

  if date_value is None:  # noqa: E111
    return None

  return datetime.combine(date_value, datetime.min.time())  # noqa: E111


def _datetime_from_timestamp(value: Number) -> datetime | None:
  """Convert ``value`` into a UTC datetime when it represents a timestamp."""  # noqa: E111

  try:  # noqa: E111
    timestamp = float(value)
  except ValueError:  # noqa: E111
    return None
  except TypeError:  # noqa: E111
    return None

  utc_from_timestamp = getattr(dt_util, "utc_from_timestamp", None)  # noqa: E111
  if callable(utc_from_timestamp):  # noqa: E111
    with suppress(OverflowError, OSError, ValueError):
      return utc_from_timestamp(timestamp)  # noqa: E111

  with suppress(OverflowError, OSError, ValueError):  # noqa: E111
    return datetime.fromtimestamp(timestamp, UTC)

  return None  # noqa: E111


def ensure_local_datetime(value: datetime | str | None) -> datetime | None:
  """Return a timezone-aware datetime in the configured local timezone."""  # noqa: E111

  if value is None:  # noqa: E111
    return None

  if isinstance(value, datetime):  # noqa: E111
    dt_value = value
  elif isinstance(value, str) and value:  # noqa: E111
    dt_value = dt_util.parse_datetime(value)
    if dt_value is None:
      date_value = dt_util.parse_date(value)  # noqa: E111
      if date_value is None:  # noqa: E111
        return None
      dt_value = datetime.combine(date_value, datetime.min.time())  # noqa: E111
  else:  # noqa: E111
    return None

  return dt_util.as_local(dt_value)  # noqa: E111


def merge_configurations(
  base_config: JSONMappingLike | JSONMutableMapping,
  user_config: JSONMappingLike | JSONMutableMapping,
  protected_keys: set[str] | None = None,
) -> JSONMutableMapping:
  """Merge two JSON-compatible configuration mappings."""  # noqa: E111

  protected_keys = set() if protected_keys is None else set(protected_keys)  # noqa: E111
  merged = _coerce_json_mutable(base_config)  # noqa: E111

  for key, value in user_config.items():  # noqa: E111
    if key in protected_keys:
      _LOGGER.warning("Ignoring protected configuration key: %s", key)  # noqa: E111
      continue  # noqa: E111

    existing_value = merged.get(key)
    if isinstance(value, Mapping):
      base_child: JSONMutableMapping  # noqa: E111
      if isinstance(existing_value, dict):  # noqa: E111
        base_child = cast(JSONMutableMapping, existing_value)
      else:  # noqa: E111
        base_child = cast(JSONMutableMapping, {})
      merged[key] = merge_configurations(  # noqa: E111
        base_child,
        cast(JSONMappingLike, value),
        protected_keys,
      )
      continue  # noqa: E111

    merged[key] = cast(JSONValue, value)

  return merged  # noqa: E111


def validate_configuration_schema(
  config: JSONMappingLike | JSONMutableMapping,
  required_keys: set[str],
  optional_keys: set[str] | None = None,
) -> ConfigurationValidationResult:
  """Validate configuration keys against a simple schema definition."""  # noqa: E111

  optional_keys = set() if optional_keys is None else set(optional_keys)  # noqa: E111
  all_valid_keys = required_keys | optional_keys  # noqa: E111
  config_keys = set(config)  # noqa: E111

  missing_keys = required_keys - config_keys  # noqa: E111
  unknown_keys = config_keys - all_valid_keys  # noqa: E111

  return ConfigurationValidationResult(  # noqa: E111
    valid=not missing_keys,
    missing_keys=sorted(missing_keys),
    unknown_keys=sorted(unknown_keys),
    has_all_required=not missing_keys,
    has_unknown=bool(unknown_keys),
  )


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
  """  # noqa: E111
  # Weight conversions  # noqa: E114
  weight_conversions: dict[tuple[str, str], Callable[[float], float]] = {  # noqa: E111
    ("kg", "lb"): lambda x: x * 2.20462,
    ("lb", "kg"): lambda x: x * 0.453592,
    ("g", "kg"): lambda x: x / 1000,
    ("kg", "g"): lambda x: x * 1000,
    ("oz", "g"): lambda x: x * 28.3495,
    ("g", "oz"): lambda x: x / 28.3495,
  }

  # Distance conversions  # noqa: E114
  distance_conversions: dict[tuple[str, str], Callable[[float], float]] = {  # noqa: E111
    ("m", "ft"): lambda x: x * 3.28084,
    ("ft", "m"): lambda x: x / 3.28084,
    ("km", "mi"): lambda x: x * 0.621371,
    ("mi", "km"): lambda x: x / 0.621371,
    ("m", "km"): lambda x: x / 1000,
    ("km", "m"): lambda x: x * 1000,
  }

  # Temperature conversions  # noqa: E114
  temp_conversions: dict[tuple[str, str], Callable[[float], float]] = {  # noqa: E111
    ("c", "f"): lambda x: (x * 9 / 5) + 32,
    ("f", "c"): lambda x: (x - 32) * 5 / 9,
  }

  # Combine all conversions  # noqa: E114
  all_conversions = {  # noqa: E111
    **weight_conversions,
    **distance_conversions,
    **temp_conversions,
  }

  # Normalize unit names  # noqa: E114
  from_unit = from_unit.lower().strip()  # noqa: E111
  to_unit = to_unit.lower().strip()  # noqa: E111

  # Handle same unit  # noqa: E114
  if from_unit == to_unit:  # noqa: E111
    return value

  # Look up conversion  # noqa: E114
  conversion_key = (from_unit, to_unit)  # noqa: E111
  if conversion_key in all_conversions:  # noqa: E111
    return all_conversions[conversion_key](value)

  raise ValueError(f"Conversion from {from_unit} to {to_unit} not supported")  # noqa: E111


_GUARD_CAPTURE: ContextVar[list[ServiceGuardResult] | None] = ContextVar(
  "pawcontrol_service_guard_capture",
  default=None,
)


@asynccontextmanager
async def async_capture_service_guard_results() -> AsyncIterator[
  list[ServiceGuardResult]
]:
  """Capture guard outcomes for Home Assistant service invocations."""  # noqa: E111

  previous = _GUARD_CAPTURE.get(None)  # noqa: E111
  guard_results: list[ServiceGuardResult] = []  # noqa: E111
  token = _GUARD_CAPTURE.set(guard_results)  # noqa: E111
  try:  # noqa: E111
    yield guard_results
  finally:  # noqa: E111
    _GUARD_CAPTURE.reset(token)
    if previous is not None:
      previous.extend(guard_results)  # noqa: E111
