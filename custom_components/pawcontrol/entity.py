"""Shared base entity classes for the PawControl integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
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
  ensure_json_mapping,
)
from .utils import (
  JSONMappingLike,
  PawControlDeviceLinkMixin,
  async_call_hass_service_if_available,
  normalise_json_mapping,
)

__all__ = ["PawControlDogEntityBase", "PawControlEntity"]


if TYPE_CHECKING:
  from .data_manager import PawControlDataManager
  from .notifications import PawControlNotificationManager
  from .types import PawControlRuntimeData


_LOGGER = logging.getLogger(__name__)


class PawControlEntity(
  PawControlDeviceLinkMixin,
  CoordinatorEntity[PawControlCoordinator],
):
  """Common base class shared across all PawControl entities."""

  _attr_should_poll = False
  _attr_has_entity_name = True

  def __init__(
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

  @property
  def dog_id(self) -> str:
    """Return the identifier for the dog this entity represents."""

    return self._dog_id

  @property
  def dog_name(self) -> str:
    """Return the friendly dog name."""

    return self._dog_name

  @property
  def has_entity_name(self) -> bool:
    """Expose the entity-name flag for simplified test doubles."""

    return bool(getattr(self, "_attr_has_entity_name", False))

  @property
  def name(self) -> str | None:
    """Return the entity name, defaulting to dog name when appropriate."""

    name = getattr(self, "_attr_name", None)
    if name is not None:
      return name

    if not self.translation_key or not self.has_entity_name:
      return self._dog_name

    return None

  @property
  def unique_id(self) -> str | None:
    """Expose the generated unique ID for compatibility with stubs."""

    return getattr(self, "_attr_unique_id", None)

  @property
  def translation_key(self) -> str | None:
    """Expose the translation key assigned during entity construction."""

    return getattr(self, "_attr_translation_key", None)

  @property
  def device_class(self) -> str | None:
    """Return the configured device class if set.

    The Home Assistant test doubles only expose plain attributes rather
    than the full entity helper stack. Surfacing the device class through
    an explicit property keeps the behaviour consistent with Home
    Assistant's core entity implementation while remaining compatible with
    the lightweight stubs used in the test harness.
    """

    return getattr(self, "_attr_device_class", None)

  @property
  def icon(self) -> str | None:
    """Return the configured Material Design icon for the entity."""

    return getattr(self, "_attr_icon", None)

  @property
  def extra_state_attributes(self) -> JSONMutableMapping:
    """Expose the entity's extra state attributes payload."""

    attrs = getattr(self, "_attr_extra_state_attributes", None)
    attributes = ensure_json_mapping(attrs)

    last_update = getattr(
      self.coordinator,
      "last_update_success_time",
      None,
    )
    if isinstance(last_update, datetime):
      attributes["last_updated"] = dt_util.as_local(
        last_update,
      ).isoformat()
    else:
      attributes["last_updated"] = None

    attributes["last_update_success"] = bool(
      getattr(self.coordinator, "last_update_success", False),
    )
    last_exception = getattr(self.coordinator, "last_exception", None)
    if last_exception is not None:
      attributes["last_update_error"] = str(last_exception)
      attributes["last_update_error_type"] = last_exception.__class__.__name__
    else:
      attributes["last_update_error"] = None
      attributes["last_update_error_type"] = None

    # Normalise attributes to ensure all values are JSON-serialisable using the
    # shared helper so entity attributes stay consistent with diagnostics.
    return normalise_json_mapping(attributes)

  @callback
  def update_device_metadata(self, **details: Any) -> None:
    """Update device metadata shared with the device registry."""

    self._set_device_link_info(**details)

  def _get_runtime_data(self) -> PawControlRuntimeData | None:
    """Return runtime data attached to this entity's config entry."""

    if self.hass is None:
      return None

    return get_runtime_data(self.hass, self.coordinator.config_entry)

  def _get_runtime_managers(self) -> CoordinatorRuntimeManagers:
    """Return the runtime manager container for this entity."""

    runtime_data = self._get_runtime_data()
    if runtime_data is not None:
      return runtime_data.runtime_managers

    manager_container = getattr(self.coordinator, "runtime_managers", None)
    if isinstance(manager_container, CoordinatorRuntimeManagers):
      return manager_container

    manager_kwargs = {
      attr: getattr(self.coordinator, attr, None)
      for attr in CoordinatorRuntimeManagers.attribute_names()
    }

    if any(value is not None for value in manager_kwargs.values()):
      container = CoordinatorRuntimeManagers(**manager_kwargs)
      self.coordinator.runtime_managers = container
      return container

    return CoordinatorRuntimeManagers()

  def _get_data_manager(self) -> PawControlDataManager | None:
    """Return the data manager from the runtime container when available."""

    return self._get_runtime_managers().data_manager

  def _get_notification_manager(self) -> PawControlNotificationManager | None:
    """Return the notification manager from the runtime container."""

    return self._get_runtime_managers().notification_manager

  async def _async_call_hass_service(
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
  """Shared base class that caches dog data and enriches attributes."""

  _cache_ttl: float = 30.0

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize dog entity cache state."""

    super().__init__(coordinator, dog_id, dog_name)
    self._dog_data_cache: dict[str, CoordinatorDogData | None] = {}
    self._cache_timestamp: dict[str, float] = {}

  def _set_cache_ttl(self, ttl: float) -> None:
    """Update the cache TTL for dog data lookups."""

    self._cache_ttl = float(ttl)

  def _get_dog_data_cached(self) -> CoordinatorDogData | None:
    """Return cached dog data when available."""

    cache_key = f"dog_data_{self._dog_id}"
    now = dt_util.utcnow().timestamp()

    if (
      cache_key in self._dog_data_cache
      and cache_key in self._cache_timestamp
      and now - self._cache_timestamp[cache_key] < self._cache_ttl
    ):
      return self._dog_data_cache[cache_key]

    if not self.coordinator.available:
      return None

    data = self.coordinator.get_dog_data(self._dog_id)
    self._dog_data_cache[cache_key] = data
    self._cache_timestamp[cache_key] = now
    return data

  def _get_dog_data(self) -> CoordinatorDogData | None:
    """Return cached dog data when available."""

    return self._get_dog_data_cached()

  def _append_dog_info_attributes(self, attrs: JSONMutableMapping) -> None:
    """Append dog info attributes when available."""

    dog_data = self._get_dog_data_cached()
    if not isinstance(dog_data, Mapping):
      return

    dog_info = dog_data.get("dog_info")
    if not isinstance(dog_info, Mapping):
      return

    info = cast(DogConfigData, dog_info)
    if (breed := info.get("dog_breed")) is not None:
      attrs["dog_breed"] = breed
    if (age := info.get("dog_age")) is not None:
      attrs["dog_age"] = age
    if (size := info.get("dog_size")) is not None:
      attrs["dog_size"] = size
    if (weight := info.get("dog_weight")) is not None:
      attrs["dog_weight"] = weight

  def _build_base_state_attributes(
    self,
    extra: Mapping[str, object] | None = None,
  ) -> JSONMutableMapping:
    """Return base attributes enriched with dog info."""

    attrs = ensure_json_mapping(super().extra_state_attributes)
    attrs.setdefault(ATTR_DOG_ID, self._dog_id)
    attrs.setdefault(ATTR_DOG_NAME, self._dog_name)
    if extra:
      attrs.update(ensure_json_mapping(extra))
    self._append_dog_info_attributes(attrs)
    return attrs

  def _build_entity_attributes(
    self,
    extra: Mapping[str, object] | None = None,
  ) -> JSONMutableMapping:
    """Return base attributes optionally augmented by ``extra``."""

    return self._build_base_state_attributes(extra)

  def _finalize_entity_attributes(
    self,
    attrs: JSONMutableMapping,
  ) -> JSONMutableMapping:
    """Normalize entity attributes for Home Assistant."""

    return normalise_json_mapping(attrs)

  def _extra_state_attributes(self) -> Mapping[str, object] | None:
    """Return extra attributes for the base entity payload."""

    return None

  @property
  def extra_state_attributes(self) -> JSONMutableMapping:
    """Expose the entity's extra state attributes payload."""

    attrs = self._build_entity_attributes(self._extra_state_attributes())
    return self._finalize_entity_attributes(attrs)

  def _get_module_data(self, module: str) -> CoordinatorModuleLookupResult:
    """Return coordinator module data with strict mapping validation."""

    if not isinstance(module, str) or not module:
      return cast(CoordinatorUntypedModuleState, {})

    try:
      if hasattr(self.coordinator, "get_module_data"):
        payload = self.coordinator.get_module_data(self._dog_id, module)
      else:
        dog_data = self.coordinator.get_dog_data(self._dog_id) or {}
        payload = dog_data.get(module, {})
    except Exception as err:  # pragma: no cover - defensive log path
      _LOGGER.error(
        "Error fetching module data for %s/%s: %s",
        self._dog_id,
        module,
        err,
      )
      return cast(CoordinatorUntypedModuleState, {})

    if not isinstance(payload, Mapping):
      _LOGGER.warning(
        "Invalid module payload for %s/%s: expected mapping, got %s",
        self._dog_id,
        module,
        type(payload).__name__,
      )
      return cast(CoordinatorUntypedModuleState, {})

    return cast(CoordinatorModuleLookupResult, payload)

  def _get_status_snapshot(self) -> DogStatusSnapshot | None:
    """Return the centralized dog status snapshot when available."""

    dog_data = self._get_dog_data_cached()
    if not isinstance(dog_data, Mapping):
      return None

    snapshot = dog_data.get("status_snapshot")
    if isinstance(snapshot, Mapping):
      return cast(DogStatusSnapshot, snapshot)

    return build_dog_status_snapshot(self._dog_id, dog_data)
