"""Shared base entity classes for the PawControl integration."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any, cast

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTR_DOG_ID, ATTR_DOG_NAME
from .coordinator import PawControlCoordinator
from .dog_status import build_dog_status_snapshot
from .runtime_data import get_runtime_data
from .service_guard import ServiceGuardResult
from .types import (
  CoordinatorDogData,
  CoordinatorModuleLookupResult,
  CoordinatorRuntimeManagers,
  CoordinatorUntypedModuleState,
  DogConfigData,
  DogStatusSnapshot,
  JSONMutableMapping,
)
from .utils import (
  JSONMappingLike,
  PawControlDeviceLinkMixin,
  async_call_hass_service_if_available,
  normalise_entity_attributes,
)

__all__ = ["PawControlDogEntityBase", "PawControlEntity"]


if TYPE_CHECKING:
  from .data_manager import PawControlDataManager  # noqa: E111
  from .notifications import PawControlNotificationManager  # noqa: E111
  from .types import PawControlRuntimeData  # noqa: E111


_LOGGER = logging.getLogger(__name__)


class PawControlEntity(
  PawControlDeviceLinkMixin,
  CoordinatorEntity[PawControlCoordinator],
):
  """Common base class shared across all PawControl entities."""  # noqa: E111

  _attr_should_poll = False  # noqa: E111
  _attr_has_entity_name = True  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialise the entity and attach device metadata."""

    super().__init__(coordinator)
    self._dog_id = dog_id
    self._dog_name = dog_name
    self._attr_extra_state_attributes = {
      ATTR_DOG_ID: dog_id,
      ATTR_DOG_NAME: dog_name,
    }
    # The Home Assistant entity base class sets ``hass`` when entities are
    # added to the registry. The lightweight stubs used in the test suite
    # instantiate entities directly, so we provide a safe default here to
    # avoid attribute errors in helper routines that guard on ``self.hass``.
    self.hass = getattr(self, "hass", None)

  @property  # noqa: E111
  def dog_id(self) -> str:  # noqa: E111
    """Return the identifier for the dog this entity represents."""

    return self._dog_id

  @property  # noqa: E111
  def dog_name(self) -> str:  # noqa: E111
    """Return the friendly dog name."""

    return self._dog_name

  @property  # noqa: E111
  def has_entity_name(self) -> bool:  # noqa: E111
    """Expose the entity-name flag for simplified test doubles."""

    return bool(getattr(self, "_attr_has_entity_name", False))

  @property  # noqa: E111
  def name(self) -> str | None:  # noqa: E111
    """Return the entity name, defaulting to dog name when appropriate."""

    name = getattr(self, "_attr_name", None)
    if name is not None:
      return name  # noqa: E111

    if not self.translation_key or not self.has_entity_name:
      return self._dog_name  # noqa: E111

    return None

  @property  # noqa: E111
  def unique_id(self) -> str | None:  # noqa: E111
    """Expose the generated unique ID for compatibility with stubs."""

    return getattr(self, "_attr_unique_id", None)

  @property  # noqa: E111
  def translation_key(self) -> str | None:  # noqa: E111
    """Expose the translation key assigned during entity construction."""

    return getattr(self, "_attr_translation_key", None)

  @property  # noqa: E111
  def device_class(self) -> str | None:  # noqa: E111
    """Return the configured device class if set.

    The Home Assistant test doubles only expose plain attributes rather
    than the full entity helper stack. Surfacing the device class through
    an explicit property keeps the behaviour consistent with Home
    Assistant's core entity implementation while remaining compatible with
    the lightweight stubs used in the test harness.
    """

    return getattr(self, "_attr_device_class", None)

  @property  # noqa: E111
  def icon(self) -> str | None:  # noqa: E111
    """Return the configured Material Design icon for the entity."""

    return getattr(self, "_attr_icon", None)

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Expose the entity's extra state attributes payload."""

    attrs = getattr(self, "_attr_extra_state_attributes", None)
    attributes = normalise_entity_attributes(attrs)

    last_update = getattr(
      self.coordinator,
      "last_update_success_time",
      None,
    )
    if isinstance(last_update, datetime):
      attributes["last_updated"] = dt_util.as_local(  # noqa: E111
        last_update,
      ).isoformat()
    else:
      attributes["last_updated"] = None  # noqa: E111

    # Expose last update success and error details for richer diagnostics. This
    # surface aligns with the coordinator error classification logic and aids
    # troubleshooting by providing direct context on the most recent update.
    attributes["last_update_success"] = bool(
      getattr(self.coordinator, "last_update_success", False),
    )
    last_exception = getattr(self.coordinator, "last_exception", None)
    if last_exception is not None:
      attributes["last_update_error"] = str(last_exception)  # noqa: E111
      attributes["last_update_error_type"] = last_exception.__class__.__name__  # noqa: E111
    else:
      attributes["last_update_error"] = None  # noqa: E111
      attributes["last_update_error_type"] = None  # noqa: E111

    # Normalise attributes to ensure all values are JSON-serialisable using the
    # shared helper so entity attributes stay consistent with diagnostics.
    return normalise_entity_attributes(attributes)

  @callback  # noqa: E111
  def update_device_metadata(self, **details: Any) -> None:  # noqa: E111
    """Update device metadata shared with the device registry."""

    self._set_device_link_info(**details)

  def _get_runtime_data(self) -> PawControlRuntimeData | None:  # noqa: E111
    """Return runtime data attached to this entity's config entry."""

    if self.hass is None:
      return None  # noqa: E111

    config_entry = getattr(self.coordinator, "config_entry", None)
    if config_entry is None:
      return None  # noqa: E111

    return get_runtime_data(self.hass, config_entry)

  def _get_runtime_managers(self) -> CoordinatorRuntimeManagers:  # noqa: E111
    """Return the runtime manager container for this entity."""

    runtime_data = self._get_runtime_data()
    if runtime_data is not None:
      container = runtime_data.runtime_managers  # noqa: E111
      for attr in CoordinatorRuntimeManagers.attribute_names():  # noqa: E111
        if getattr(container, attr) is None and hasattr(runtime_data, attr):
          setattr(container, attr, getattr(runtime_data, attr))  # noqa: E111
      return container  # noqa: E111

    manager_container = getattr(self.coordinator, "runtime_managers", None)
    if isinstance(manager_container, CoordinatorRuntimeManagers):
      return manager_container  # noqa: E111

    manager_kwargs = {
      attr: getattr(self.coordinator, attr, None)
      for attr in CoordinatorRuntimeManagers.attribute_names()
    }

    if any(value is not None for value in manager_kwargs.values()):
      container = CoordinatorRuntimeManagers(**manager_kwargs)  # noqa: E111
      self.coordinator.runtime_managers = container  # noqa: E111
      return container  # noqa: E111

    return CoordinatorRuntimeManagers()

  def _get_data_manager(self) -> PawControlDataManager | None:  # noqa: E111
    """Return the data manager from runtime data or fallback containers."""

    runtime_data = self._get_runtime_data()
    if runtime_data is not None and runtime_data.data_manager is not None:
      return runtime_data.data_manager  # noqa: E111

    return self._get_runtime_managers().data_manager

  def _get_notification_manager(self) -> PawControlNotificationManager | None:  # noqa: E111
    """Return the notification manager from the runtime container."""

    return self._get_runtime_managers().notification_manager

  async def _async_call_hass_service(  # noqa: E111
    self,
    domain: str,
    service: str,
    service_data: JSONMappingLike | JSONMutableMapping | None = None,
    *,
    blocking: bool = False,
  ) -> ServiceGuardResult:
    """Safely call a Home Assistant service when the instance is available.

    Returns the guard result describing whether Home Assistant executed the
    service call. ``bool(result)`` evaluates to ``True`` when the service ran
    successfully and ``False`` when the guard short-circuited the request.
    """

    return await async_call_hass_service_if_available(
      self.hass,
      domain,
      service,
      service_data,
      blocking=blocking,
      description=(
        f"dog {self._dog_id} ({getattr(self, 'entity_id', 'unregistered')})"
      ),
      logger=_LOGGER,
    )


class PawControlDogEntityBase(PawControlEntity):
  """Shared base class that caches dog data and enriches attributes."""  # noqa: E111

  _cache_ttl: float = 30.0  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize dog entity cache state."""

    super().__init__(coordinator, dog_id, dog_name)
    self._dog_data_cache: dict[str, CoordinatorDogData | None] = {}
    self._cache_timestamp: dict[str, float] = {}

  def _set_cache_ttl(self, ttl: float) -> None:  # noqa: E111
    """Update the cache TTL for dog data lookups."""

    self._cache_ttl = float(ttl)

  def _get_dog_data_cached(self) -> CoordinatorDogData | None:  # noqa: E111
    """Return cached dog data when available."""

    cache_key = f"dog_data_{self._dog_id}"
    now = dt_util.utcnow().timestamp()

    if (
      cache_key in self._dog_data_cache
      and cache_key in self._cache_timestamp
      and now - self._cache_timestamp[cache_key] < self._cache_ttl
    ):
      return self._dog_data_cache[cache_key]  # noqa: E111

    if not self.coordinator.available:
      return None  # noqa: E111

    data = self.coordinator.get_dog_data(self._dog_id)
    self._dog_data_cache[cache_key] = data
    self._cache_timestamp[cache_key] = now
    return data

  def _get_dog_data(self) -> CoordinatorDogData | None:  # noqa: E111
    """Return cached dog data when available."""

    return self._get_dog_data_cached()

  def _append_dog_info_attributes(self, attrs: JSONMutableMapping) -> None:  # noqa: E111
    """Append dog info attributes when available."""

    dog_data = self._get_dog_data_cached()
    if not isinstance(dog_data, Mapping):
      return  # noqa: E111

    dog_info = dog_data.get("dog_info")
    if not isinstance(dog_info, Mapping):
      return  # noqa: E111

    info = cast(DogConfigData, dog_info)
    if (breed := info.get("dog_breed")) is not None:
      attrs["dog_breed"] = breed  # noqa: E111
    if (age := info.get("dog_age")) is not None:
      attrs["dog_age"] = age  # noqa: E111
    if (size := info.get("dog_size")) is not None:
      attrs["dog_size"] = size  # noqa: E111
    if (weight := info.get("dog_weight")) is not None:
      attrs["dog_weight"] = weight  # noqa: E111

  def _build_base_state_attributes(  # noqa: E111
    self,
    extra: Mapping[str, object] | None = None,
  ) -> JSONMutableMapping:
    """Return base attributes enriched with dog info."""

    attrs = dict(super().extra_state_attributes)
    attrs.setdefault(ATTR_DOG_ID, self._dog_id)
    attrs.setdefault(ATTR_DOG_NAME, self._dog_name)
    self._append_dog_info_attributes(attrs)
    if extra:
      attrs.update(normalise_entity_attributes(extra))  # noqa: E111
    return attrs

  def _build_entity_attributes(  # noqa: E111
    self,
    extra: Mapping[str, object] | None = None,
  ) -> JSONMutableMapping:
    """Return base attributes optionally augmented by ``extra``."""

    return self._build_base_state_attributes(extra)

  def _finalize_entity_attributes(  # noqa: E111
    self,
    attrs: JSONMutableMapping,
  ) -> JSONMutableMapping:
    """Normalize entity attributes for Home Assistant."""

    return normalise_entity_attributes(attrs)

  def _extra_state_attributes(self) -> Mapping[str, object] | None:  # noqa: E111
    """Return extra attributes for the base entity payload."""

    return None

  @property  # noqa: E111
  def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
    """Expose the entity's extra state attributes payload."""

    attrs = self._build_entity_attributes(self._extra_state_attributes())
    return self._finalize_entity_attributes(attrs)

  def _get_module_data(self, module: str) -> CoordinatorModuleLookupResult:  # noqa: E111
    """Return coordinator module data with strict mapping validation."""

    if not isinstance(module, str) or not module:
      return cast(CoordinatorUntypedModuleState, {})  # noqa: E111

    try:
      if hasattr(self.coordinator, "get_module_data"):  # noqa: E111
        payload = self.coordinator.get_module_data(self._dog_id, module)
      else:  # noqa: E111
        dog_data = self.coordinator.get_dog_data(self._dog_id) or {}
        payload = dog_data.get(module, {})
    except Exception as err:  # pragma: no cover - defensive log path
      _LOGGER.error(  # noqa: E111
        "Error fetching module data for %s/%s: %s",
        self._dog_id,
        module,
        err,
      )
      return cast(CoordinatorUntypedModuleState, {})  # noqa: E111

    if not isinstance(payload, Mapping):
      _LOGGER.warning(  # noqa: E111
        "Invalid module payload for %s/%s: expected mapping, got %s",
        self._dog_id,
        module,
        type(payload).__name__,
      )
      return cast(CoordinatorUntypedModuleState, {})  # noqa: E111

    return cast(CoordinatorModuleLookupResult, payload)

  def _get_status_snapshot(self) -> DogStatusSnapshot | None:  # noqa: E111
    """Return the centralized dog status snapshot when available."""

    dog_data = self._get_dog_data_cached()
    if not isinstance(dog_data, Mapping):
      return None  # noqa: E111

    snapshot = dog_data.get("status_snapshot")
    if isinstance(snapshot, Mapping):
      return cast(DogStatusSnapshot, snapshot)  # noqa: E111

    return build_dog_status_snapshot(self._dog_id, dog_data)
