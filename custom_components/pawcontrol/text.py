"""Text platform for Paw Control integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any, cast

from homeassistant.components import text as text_component
from homeassistant.components.text import TextEntity, TextMode
from homeassistant.const import (
  ATTR_ENTITY_ID,
  ATTR_VALUE,
)
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
  ATTR_DOG_ID,
  DOMAIN,
  MODULE_GPS,
  MODULE_HEALTH,
  MODULE_NOTIFICATIONS,
  MODULE_WALK,
)
from .coordinator import PawControlCoordinator
from .entity import PawControlDogEntityBase
from .notifications import NotificationPriority, NotificationType
from .reproduce_state import async_reproduce_platform_states
from .runtime_data import get_runtime_data
from .types import (
  DOG_ID_FIELD,
  DOG_MODULES_FIELD,
  DOG_NAME_FIELD,
  DOG_TEXT_METADATA_FIELD,
  DOG_TEXT_VALUES_FIELD,
  ConfigFlowUserInput,
  CoordinatorDogData,
  DogConfigData,
  DogModulesConfig,
  DogModulesProjection,
  DogTextMetadataEntry,
  DogTextMetadataSnapshot,
  DogTextSnapshot,
  JSONMapping,
  JSONMutableMapping,
  JSONValue,
  ModuleToggleKey,
  PawControlConfigEntry,
  TextSnapshotKey,
  _normalise_text_metadata_entry,
  coerce_dog_modules_config,
  ensure_dog_config_data,
  ensure_dog_text_metadata_snapshot,
  ensure_dog_text_snapshot,
)
from .utils import async_call_add_entities

_LOGGER = logging.getLogger(__name__)

# Text helpers persist updates back to the coordinator. Coordinator-side
# locking keeps writes safe, so we remove the entity-level concurrency cap.
PARALLEL_UPDATES = 0

MODULE_GPS_KEY = cast(ModuleToggleKey, MODULE_GPS)
MODULE_WALK_KEY = cast(ModuleToggleKey, MODULE_WALK)
MODULE_HEALTH_KEY = cast(ModuleToggleKey, MODULE_HEALTH)
MODULE_NOTIFICATIONS_KEY = cast(ModuleToggleKey, MODULE_NOTIFICATIONS)


def _normalize_dog_configs(
  raw_configs: Iterable[Any] | None,
) -> list[DogConfigData]:
  """Return validated dog configurations for text entity creation.

  The runtime data path provides fully typed ``DogConfigData`` entries, but the
  legacy fallback path may contain partially defined dictionaries. This helper
  filters out invalid items and ensures a mutable modules mapping is available
  for each configuration so downstream code can rely on Platinum-targeted types.
  """

  normalized_configs: list[DogConfigData] = []

  if raw_configs is None:
    return normalized_configs

  for index, config in enumerate(raw_configs):
    if not isinstance(config, Mapping):
      _LOGGER.warning(
        "Skipping dog configuration at index %d: expected mapping but got %s",
        index,
        type(config),
      )
      continue

    typed_mapping = cast(JSONMapping, config)
    typed_config = ensure_dog_config_data(typed_mapping)
    if typed_config is None:
      _LOGGER.warning(
        "Skipping dog configuration at index %d: missing required identifiers",
        index,
      )
      continue

    modules_payload = typed_mapping.get(DOG_MODULES_FIELD)
    modules_source: ConfigFlowUserInput | DogModulesProjection | DogModulesConfig | None
    if isinstance(modules_payload, Mapping):
      modules_source = cast(ConfigFlowUserInput, modules_payload)
    elif isinstance(modules_payload, DogModulesProjection) or (
      hasattr(modules_payload, "config")
      and hasattr(
        modules_payload,
        "mapping",
      )
    ):
      modules_source = cast(DogModulesProjection, modules_payload)
    else:
      modules_source = None
    modules: DogModulesConfig = coerce_dog_modules_config(modules_source)
    typed_config = {**typed_config, DOG_MODULES_FIELD: modules}
    normalized_configs.append(cast(DogConfigData, typed_config))

  return normalized_configs


async def _async_add_entities_in_batches(
  async_add_entities_func: AddEntitiesCallback,
  entities: Sequence[PawControlTextBase],
  *,
  batch_size: int = 8,
  delay_between_batches: float = 0.1,
) -> None:
  """Add text entities in small batches to prevent registry overload.

  Home Assistant logs warnings if large volumes of entity registry updates are
  submitted simultaneously. Batching entity creation limits the peak load
  while still yielding responsive setup times.
  """

  if batch_size <= 0:
    raise ValueError("batch_size must be greater than zero")

  total_entities = len(entities)

  if not total_entities:
    _LOGGER.debug("No text entities to register for PawControl")
    return

  total_batches = (total_entities + batch_size - 1) // batch_size

  _LOGGER.debug(
    "Adding %d text entities across %d batches (size=%d, delay=%.2fs)",
    total_entities,
    total_batches,
    batch_size,
    delay_between_batches,
  )

  for batch_index in range(total_batches):
    start = batch_index * batch_size
    batch = list(entities[start : start + batch_size])

    _LOGGER.debug(
      "Processing text batch %d/%d with %d entities",
      batch_index + 1,
      total_batches,
      len(batch),
    )

    await async_call_add_entities(
      async_add_entities_func,
      batch,
      update_before_add=False,
    )

    if delay_between_batches > 0 and batch_index + 1 < total_batches:
      await asyncio.sleep(delay_between_batches)


async def async_setup_entry(
  hass: HomeAssistant,
  entry: PawControlConfigEntry,
  async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up the PawControl text platform for a config entry."""

  runtime_data = get_runtime_data(hass, entry)
  if runtime_data is None:
    _LOGGER.error("Runtime data missing for entry %s", entry.entry_id)
    return

  coordinator = runtime_data.coordinator
  raw_dogs = list(cast(Iterable[Any], runtime_data.dogs))
  dogs = _normalize_dog_configs(raw_dogs)

  skipped_configs = len(raw_dogs) - len(dogs)
  if skipped_configs:
    _LOGGER.debug(
      "Filtered %d invalid dog configurations for entry %s",
      skipped_configs,
      entry.entry_id,
    )

  if not dogs:
    _LOGGER.info(
      "No dogs configured for PawControl entry %s",
      entry.entry_id,
    )
    return

  entities: list[PawControlTextBase] = []

  for dog in dogs:
    dog_id = dog[DOG_ID_FIELD]
    dog_name = dog[DOG_NAME_FIELD]
    modules: DogModulesConfig = coerce_dog_modules_config(
      dog.get(DOG_MODULES_FIELD),
    )

    # Basic dog configuration texts
    entities.extend(
      [
        PawControlDogNotesText(coordinator, dog_id, dog_name),
        PawControlCustomLabelText(coordinator, dog_id, dog_name),
        PawControlMicrochipText(coordinator, dog_id, dog_name),
        PawControlBreederInfoText(coordinator, dog_id, dog_name),
        PawControlRegistrationText(coordinator, dog_id, dog_name),
        PawControlInsuranceText(coordinator, dog_id, dog_name),
      ],
    )

    # Walk texts
    if bool(modules.get(MODULE_WALK_KEY, False)):
      entities.extend(
        [
          PawControlWalkNotesText(coordinator, dog_id, dog_name),
          PawControlCurrentWalkLabelText(
            coordinator,
            dog_id,
            dog_name,
          ),
        ],
      )

    # Health texts
    if bool(modules.get(MODULE_HEALTH_KEY, False)):
      entities.extend(
        [
          PawControlHealthNotesText(coordinator, dog_id, dog_name),
          PawControlMedicationNotesText(
            coordinator,
            dog_id,
            dog_name,
          ),
          PawControlVetNotesText(coordinator, dog_id, dog_name),
          PawControlGroomingNotesText(coordinator, dog_id, dog_name),
          PawControlAllergiesText(coordinator, dog_id, dog_name),
          PawControlTrainingNotesText(coordinator, dog_id, dog_name),
          PawControlBehaviorNotesText(coordinator, dog_id, dog_name),
        ],
      )

    # Notification texts
    if bool(modules.get(MODULE_NOTIFICATIONS_KEY, False)):
      entities.extend(
        [
          PawControlCustomMessageText(coordinator, dog_id, dog_name),
          PawControlEmergencyContactText(
            coordinator,
            dog_id,
            dog_name,
          ),
        ],
      )

    if bool(modules.get(MODULE_GPS_KEY, False)):
      entities.append(
        PawControlLocationDescriptionText(
          coordinator,
          dog_id,
          dog_name,
        ),
      )

  # Add entities in smaller batches to prevent Entity Registry overload
  # With 24+ text entities (2 dogs), batching prevents Registry flooding
  await _async_add_entities_in_batches(async_add_entities, entities, batch_size=8)

  _LOGGER.info(
    "Created %d text entities for %d dogs using batched approach",
    len(entities),
    len(dogs),
  )


async def async_reproduce_state(
  hass: HomeAssistant,
  states: Sequence[State],
  *,
  context: Context | None = None,
) -> None:
  """Reproduce text states for PawControl entities."""
  await async_reproduce_platform_states(
    hass,
    states,
    "text",
    _preprocess_text_state,
    _async_reproduce_text_state,
    context=context,
  )


def _preprocess_text_state(state: State) -> str:
  return state.state


async def _async_reproduce_text_state(
  hass: HomeAssistant,
  state: State,
  current_state: State,
  target_value: str,
  context: Context | None,
) -> None:
  if current_state.state == target_value:
    return

  await hass.services.async_call(
    text_component.DOMAIN,
    text_component.SERVICE_SET_VALUE,
    {ATTR_ENTITY_ID: state.entity_id, ATTR_VALUE: target_value},
    context=context,
    blocking=True,
  )


class PawControlTextBase(PawControlDogEntityBase, TextEntity, RestoreEntity):
  """Base class for Paw Control text entities."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
    text_type: TextSnapshotKey,
    max_length: int = 255,
    mode: TextMode = TextMode.TEXT,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(coordinator, dog_id, dog_name)
    self._text_type: TextSnapshotKey = text_type
    self._current_value: str = ""
    self._last_updated: str | None = None
    self._last_updated_context_id: str | None = None
    self._last_updated_parent_id: str | None = None
    self._last_updated_user_id: str | None = None

    self._attr_unique_id = f"pawcontrol_{dog_id}_{text_type}"
    self._attr_translation_key = text_type
    self._attr_native_max = max_length
    self._attr_mode = mode

    # Link entity to PawControl device entry for the dog
    self.update_device_metadata(
      model="Smart Dog",
      sw_version="1.0.0",
      configuration_url="https://github.com/BigDaddy1990/pawcontrol",
    )

  @property
  def native_value(self) -> str:
    """Return the current value."""
    return self._current_value

  @property
  def extra_state_attributes(self) -> JSONMutableMapping:
    """Return extra state attributes."""
    merged = self._build_base_state_attributes(
      {
        "text_type": self._text_type,
        "character_count": len(self._current_value),
        "last_updated": self._last_updated,
        "last_updated_context_id": self._last_updated_context_id,
        "last_updated_parent_id": self._last_updated_parent_id,
        "last_updated_user_id": self._last_updated_user_id,
      },
    )

    return self._finalize_entity_attributes(merged)

  def _clamp_value(self, value: str) -> str:
    """Clamp ``value`` to the configured maximum length when necessary."""

    max_length = getattr(
      self,
      "native_max",
      getattr(self, "_attr_native_max", None),
    )
    if isinstance(max_length, int) and len(value) > max_length:
      return value[:max_length]
    return value

  def _get_stored_text_value(
    self,
  ) -> tuple[str | None, DogTextMetadataEntry | None, bool]:
    """Return stored text data and whether it originated from runtime state."""

    runtime_value: str | None = None
    runtime_metadata: DogTextMetadataEntry | None = None

    runtime_data = self._get_runtime_data()
    if runtime_data is not None:
      for dog in runtime_data.dogs:
        if dog.get(DOG_ID_FIELD) != self._dog_id:
          continue

        value_snapshot = dog.get(DOG_TEXT_VALUES_FIELD)
        if isinstance(value_snapshot, Mapping):
          candidate = value_snapshot.get(self._text_type)
          if isinstance(candidate, str):
            runtime_value = candidate

        metadata_snapshot = dog.get(DOG_TEXT_METADATA_FIELD)
        if isinstance(metadata_snapshot, Mapping):
          runtime_metadata = _normalise_text_metadata_entry(
            metadata_snapshot.get(self._text_type),
          )

        break

      if runtime_value is not None or runtime_metadata is not None:
        return runtime_value, runtime_metadata, True

    coordinator_value: str | None = None
    coordinator_metadata: DogTextMetadataEntry | None = None

    coordinator_data = getattr(self.coordinator, "data", None)
    if isinstance(coordinator_data, Mapping):
      dog_payload = coordinator_data.get(self._dog_id)
      if isinstance(dog_payload, Mapping):
        value_snapshot = dog_payload.get(DOG_TEXT_VALUES_FIELD)
        if isinstance(value_snapshot, Mapping):
          candidate = value_snapshot.get(self._text_type)
          if isinstance(candidate, str):
            coordinator_value = candidate

        metadata_snapshot = dog_payload.get(DOG_TEXT_METADATA_FIELD)
        if isinstance(metadata_snapshot, Mapping):
          coordinator_metadata = _normalise_text_metadata_entry(
            metadata_snapshot.get(self._text_type),
          )

        if coordinator_value is not None or coordinator_metadata is not None:
          return coordinator_value, coordinator_metadata, False

    return None, None, False

  async def _async_persist_text_value(
    self,
    value: str,
    *,
    metadata: DogTextMetadataEntry | None,
  ) -> None:
    """Persist updated text values and metadata to runtime caches and storage."""

    should_remove = value == ""
    update_payload: JSONMutableMapping = cast(
      JSONMutableMapping,
      {self._text_type: None if should_remove else value},
    )
    snapshot_update: DogTextSnapshot | None = None
    if not should_remove:
      snapshot_update = cast(DogTextSnapshot, {self._text_type: value})

    metadata_update: DogTextMetadataSnapshot | None = None
    remove_metadata = metadata is None and should_remove
    if metadata is not None:
      metadata_update = cast(
        DogTextMetadataSnapshot,
        {self._text_type: cast(DogTextMetadataEntry, dict(metadata))},
      )

    runtime_data = self._get_runtime_data()
    data_manager: Any = self._get_data_manager()
    if data_manager is None and runtime_data is not None:
      candidate = getattr(runtime_data, "data_manager", None)
      if candidate is not None:
        data_manager = candidate

    def apply_in_memory_updates() -> None:
      if runtime_data is not None:
        for dog in runtime_data.dogs:
          if dog.get(DOG_ID_FIELD) != self._dog_id:
            continue
          existing = dog.get(DOG_TEXT_VALUES_FIELD)
          merged = (
            ensure_dog_text_snapshot(cast(JSONMapping, existing))
            if isinstance(existing, Mapping)
            else None
          ) or cast(DogTextSnapshot, {})

          if should_remove:
            merged.pop(self._text_type, None)
          elif snapshot_update is not None:
            merged.update(snapshot_update)

          if merged:
            dog[DOG_TEXT_VALUES_FIELD] = cast(
              DogTextSnapshot,
              merged,
            )
          else:
            dog.pop(DOG_TEXT_VALUES_FIELD, None)

          metadata_existing = dog.get(DOG_TEXT_METADATA_FIELD)
          metadata_merged_snapshot = (
            ensure_dog_text_metadata_snapshot(
              cast(JSONMapping, metadata_existing),
            )
            if isinstance(metadata_existing, Mapping)
            else None
          )
          metadata_merged: dict[str, DogTextMetadataEntry] = dict(
            cast(
              Mapping[str, DogTextMetadataEntry],
              metadata_merged_snapshot or {},
            ),
          )

          if metadata_update is not None:
            for key, entry in metadata_update.items():
              metadata_merged[str(key)] = cast(
                DogTextMetadataEntry,
                entry,
              )
          elif remove_metadata:
            metadata_merged.pop(self._text_type, None)

          if metadata_merged:
            dog[DOG_TEXT_METADATA_FIELD] = cast(
              DogTextMetadataSnapshot,
              dict(metadata_merged),
            )
          else:
            dog.pop(DOG_TEXT_METADATA_FIELD, None)
          break

      coordinator_data = getattr(self.coordinator, "data", None)
      if isinstance(coordinator_data, dict):
        dog_payload = coordinator_data.get(self._dog_id)
        if isinstance(dog_payload, Mapping):
          mutable_payload: JSONMutableMapping = cast(
            JSONMutableMapping,
            dict(dog_payload),
          )
        else:
          mutable_payload = cast(JSONMutableMapping, {})

        existing_snapshot = mutable_payload.get(DOG_TEXT_VALUES_FIELD)
        merged_snapshot = (
          ensure_dog_text_snapshot(
            cast(JSONMapping, existing_snapshot),
          )
          if isinstance(existing_snapshot, Mapping)
          else None
        ) or cast(DogTextSnapshot, {})

        if should_remove:
          merged_snapshot.pop(self._text_type, None)
        elif snapshot_update is not None:
          merged_snapshot.update(snapshot_update)

        if merged_snapshot:
          mutable_payload[DOG_TEXT_VALUES_FIELD] = cast(
            JSONValue,
            merged_snapshot,
          )
        else:
          mutable_payload.pop(DOG_TEXT_VALUES_FIELD, None)

        existing_metadata = mutable_payload.get(
          DOG_TEXT_METADATA_FIELD,
        )
        merged_metadata_snapshot = (
          ensure_dog_text_metadata_snapshot(
            cast(JSONMapping, existing_metadata),
          )
          if isinstance(existing_metadata, Mapping)
          else None
        )
        merged_metadata: dict[str, DogTextMetadataEntry] = dict(
          cast(
            Mapping[str, DogTextMetadataEntry],
            merged_metadata_snapshot or {},
          ),
        )

        if metadata_update is not None:
          for key, entry in metadata_update.items():
            merged_metadata[str(key)] = cast(
              DogTextMetadataEntry,
              entry,
            )
        elif remove_metadata:
          merged_metadata.pop(self._text_type, None)

        if merged_metadata:
          mutable_payload[DOG_TEXT_METADATA_FIELD] = cast(
            JSONValue,
            dict(merged_metadata),
          )
        else:
          mutable_payload.pop(DOG_TEXT_METADATA_FIELD, None)

        coordinator_data[self._dog_id] = cast(
          CoordinatorDogData,
          mutable_payload,
        )

    if data_manager is not None:
      update_sections: JSONMutableMapping = cast(
        JSONMutableMapping,
        {DOG_TEXT_VALUES_FIELD: update_payload},
      )
      if metadata_update is not None:
        update_sections[DOG_TEXT_METADATA_FIELD] = cast(
          JSONMutableMapping,
          metadata_update,
        )
      elif remove_metadata:
        update_sections[DOG_TEXT_METADATA_FIELD] = cast(
          JSONMutableMapping,
          cast(DogTextMetadataSnapshot, {self._text_type: None}),
        )
      try:
        await data_manager.async_update_dog_data(
          self._dog_id,
          update_sections,
        )
      except HomeAssistantError:  # pragma: no cover - defensive log
        _LOGGER.exception(
          "Failed to persist %s text value for %s",
          self._text_type,
          self._dog_name,
        )
        return
      else:
        apply_in_memory_updates()
        return

    apply_in_memory_updates()

  def _build_metadata_entry(self, timestamp: str) -> DogTextMetadataEntry:
    """Return metadata describing an update at ``timestamp`` with context."""

    metadata: DogTextMetadataEntry = cast(
      DogTextMetadataEntry,
      {"last_updated": timestamp},
    )
    context = getattr(self, "context", None)
    if context is None:
      context = getattr(self, "_context", None)
    context_id = getattr(context, "id", None)
    if isinstance(context_id, str) and context_id:
      metadata["context_id"] = context_id
    parent_id = getattr(context, "parent_id", None)
    if isinstance(parent_id, str) and parent_id:
      metadata["parent_id"] = parent_id
    user_id = getattr(context, "user_id", None)
    if isinstance(user_id, str) and user_id:
      metadata["user_id"] = user_id

    return metadata

  def _set_metadata_fields(self, metadata: DogTextMetadataEntry | None) -> None:
    """Update cached metadata fields for ``self`` from ``metadata``."""

    timestamp = (
      metadata.get(
        "last_updated",
      )
      if metadata is not None
      else None
    )
    self._last_updated = timestamp
    self._last_updated_context_id = (
      metadata.get("context_id") if metadata is not None else None
    )
    self._last_updated_parent_id = (
      metadata.get("parent_id") if metadata is not None else None
    )
    self._last_updated_user_id = (
      metadata.get("user_id") if metadata is not None else None
    )

  async def async_added_to_hass(self) -> None:
    """When entity is added to hass."""
    await super().async_added_to_hass()

    stored_value, stored_metadata, from_runtime = self._get_stored_text_value()
    needs_persist = not from_runtime

    last_state = await self.async_get_last_state()
    last_state_value: str | None = None
    last_state_timestamp: str | None = None

    if last_state is not None:
      if getattr(last_state, "state", None) not in ("unknown", "unavailable"):
        last_state_value = cast(str, last_state.state)

      attributes = getattr(last_state, "attributes", {})
      if isinstance(attributes, Mapping):
        attribute_timestamp = attributes.get("last_updated")
        if isinstance(attribute_timestamp, str):
          last_state_timestamp = attribute_timestamp

      if last_state_timestamp is None:
        last_updated_dt = getattr(last_state, "last_updated", None)
        if isinstance(last_updated_dt, datetime):
          last_state_timestamp = dt_util.as_utc(
            last_updated_dt,
          ).isoformat()

    metadata_from_state: DogTextMetadataEntry | None = None
    if last_state_timestamp is not None:
      attr_context_id: str | None = None
      attr_parent_id: str | None = None
      attr_user_id: str | None = None

      if isinstance(attributes, Mapping):
        raw_context_id = attributes.get("last_updated_context_id")
        if isinstance(raw_context_id, str) and raw_context_id:
          attr_context_id = raw_context_id

        raw_parent_id = attributes.get("last_updated_parent_id")
        if isinstance(raw_parent_id, str) and raw_parent_id:
          attr_parent_id = raw_parent_id

        raw_user_id = attributes.get("last_updated_user_id")
        if isinstance(raw_user_id, str) and raw_user_id:
          attr_user_id = raw_user_id

      state_context = getattr(last_state, "context", None)
      if attr_context_id is None:
        context_id = getattr(state_context, "id", None)
        if isinstance(context_id, str) and context_id:
          attr_context_id = context_id

      if attr_parent_id is None:
        parent_id = getattr(state_context, "parent_id", None)
        if isinstance(parent_id, str) and parent_id:
          attr_parent_id = parent_id

      if attr_user_id is None:
        user_id = getattr(state_context, "user_id", None)
        if isinstance(user_id, str) and user_id:
          attr_user_id = user_id

      metadata_from_state = _normalise_text_metadata_entry(
        {
          "last_updated": last_state_timestamp,
          "context_id": attr_context_id,
          "parent_id": attr_parent_id,
          "user_id": attr_user_id,
        },
      )

    if stored_value is None and last_state_value is not None:
      stored_value = last_state_value
      if stored_metadata is None:
        stored_metadata = metadata_from_state
      needs_persist = True

    metadata_to_apply = stored_metadata

    if stored_value is not None and metadata_to_apply is None:
      if metadata_from_state is not None:
        metadata_to_apply = metadata_from_state
      else:
        metadata_to_apply = self._build_metadata_entry(
          dt_util.utcnow().isoformat(),
        )
      needs_persist = True

    self._set_metadata_fields(metadata_to_apply)

    if stored_value is not None:
      clamped_value = self._clamp_value(stored_value)
      self._current_value = clamped_value
      if self._last_updated is None:
        now_iso = dt_util.utcnow().isoformat()
        metadata_to_apply = self._build_metadata_entry(now_iso)
        self._set_metadata_fields(metadata_to_apply)
        needs_persist = True
      self.async_write_ha_state()
      if needs_persist:
        await self._async_persist_text_value(
          clamped_value,
          metadata=metadata_to_apply,
        )
    elif metadata_to_apply is not None:
      self._set_metadata_fields(metadata_to_apply)

  async def async_set_value(self, value: str) -> None:
    """Set new value."""
    clamped_value = self._clamp_value(value)
    normalized_value = clamped_value if clamped_value.strip() else ""
    if normalized_value == self._current_value:
      _LOGGER.debug(
        "Skipping %s update for %s; value unchanged",
        self._text_type,
        self._dog_name,
      )
      return

    self._current_value = normalized_value
    timestamp = dt_util.utcnow().isoformat()
    metadata_entry = self._build_metadata_entry(timestamp)
    self._set_metadata_fields(metadata_entry)
    self.async_write_ha_state()
    await self._async_persist_text_value(normalized_value, metadata=metadata_entry)
    _LOGGER.debug(
      "Set %s for %s to: %s",
      self._text_type,
      self._dog_name,
      normalized_value[:50],
    )


class PawControlDogNotesText(PawControlTextBase):
  """Text entity for general dog notes."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "notes",
      max_length=1000,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:note-text"

  async def async_set_value(self, value: str) -> None:
    """Set new notes value."""
    await super().async_set_value(value)

    # Log notes update as health data if meaningful content
    trimmed_value = value.strip()
    if len(trimmed_value) > 10 and not await self._async_call_hass_service(
      DOMAIN,
      "log_health_data",
      {
        ATTR_DOG_ID: self._dog_id,
        "note": f"Notes updated: {value[:100]}",
      },
    ):
      return


class PawControlCustomLabelText(PawControlTextBase):
  """Text entity for custom dog label."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(coordinator, dog_id, dog_name, "custom_label", max_length=50)
    self._attr_icon = "mdi:label"


class PawControlWalkNotesText(PawControlTextBase):
  """Text entity for walk notes."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "walk_notes",
      max_length=500,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:walk"

  async def async_set_value(self, value: str) -> None:
    """Set new walk notes."""
    await super().async_set_value(value)

    # Add notes to current walk if one is active
    dog_data = self.coordinator.get_dog_data(self._dog_id)
    if dog_data and dog_data.get("walk", {}).get("walk_in_progress", False):
      _LOGGER.debug("Added notes to active walk for %s", self._dog_name)


class PawControlCurrentWalkLabelText(PawControlTextBase):
  """Text entity for current walk label."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "current_walk_label",
      max_length=100,
    )
    self._attr_icon = "mdi:tag"

  @property
  def available(self) -> bool:
    """Return if entity is available."""
    dog_data = self.coordinator.get_dog_data(self._dog_id)
    if not dog_data:
      return False

    # Only available when walk is in progress
    return dog_data.get("walk", {}).get("walk_in_progress", False)


class PawControlHealthNotesText(PawControlTextBase):
  """Text entity for health notes."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "health_notes",
      max_length=1000,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:heart-pulse"

  async def async_set_value(self, value: str) -> None:
    """Set new health notes."""
    await super().async_set_value(value)

    # Log health notes
    trimmed_value = value.strip()
    if trimmed_value and not await self._async_call_hass_service(
      DOMAIN,
      "log_health_data",
      {
        ATTR_DOG_ID: self._dog_id,
        "note": value,
      },
    ):
      return


class PawControlMedicationNotesText(PawControlTextBase):
  """Text entity for medication notes."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "medication_notes",
      max_length=500,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:pill"

  async def async_set_value(self, value: str) -> None:
    """Set new medication notes."""
    await super().async_set_value(value)

    # Log medication if notes contain meaningful information
    trimmed_value = value.strip()
    if (
      trimmed_value
      and len(trimmed_value) > 5
      and not await self._async_call_hass_service(
        DOMAIN,
        "log_medication",
        {
          ATTR_DOG_ID: self._dog_id,
          "medication_name": "Manual Entry",
          "dose": value,
        },
      )
    ):
      return


class PawControlVetNotesText(PawControlTextBase):
  """Text entity for veterinary notes."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "vet_notes",
      max_length=1000,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:medical-bag"

  async def async_set_value(self, value: str) -> None:
    """Set new vet notes."""
    await super().async_set_value(value)

    # Log as health data with vet context
    trimmed_value = value.strip()
    if trimmed_value and not await self._async_call_hass_service(
      DOMAIN,
      "log_health_data",
      {
        ATTR_DOG_ID: self._dog_id,
        "note": f"Vet notes: {value}",
      },
    ):
      return


class PawControlGroomingNotesText(PawControlTextBase):
  """Text entity for grooming notes."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "grooming_notes",
      max_length=500,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:content-cut"

  async def async_set_value(self, value: str) -> None:
    """Set new grooming notes."""
    await super().async_set_value(value)

    # Start grooming session if notes are added
    trimmed_value = value.strip()
    if (
      trimmed_value
      and len(trimmed_value) > 10
      and not await self._async_call_hass_service(
        DOMAIN,
        "start_grooming",
        {
          ATTR_DOG_ID: self._dog_id,
          "type": "brush",
          "notes": value,
        },
      )
    ):
      return


class PawControlCustomMessageText(PawControlTextBase):
  """Text entity for custom notification message."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "custom_message",
      max_length=300,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:message-text"

  async def async_set_value(self, value: str) -> None:
    """Set new custom message and send notification."""
    await super().async_set_value(value)

    # Send custom message as notification if not empty
    if value.strip():
      message = value.strip()
      notification_manager = self._get_notification_manager()

      if notification_manager is not None:
        await notification_manager.async_send_notification(
          notification_type=NotificationType.SYSTEM_INFO,
          title=f"Custom message for {self._dog_name}",
          message=message,
          dog_id=self._dog_id,
          priority=NotificationPriority.NORMAL,
          data={"source": "text.custom_message"},
          allow_batching=False,
        )
        return

      if not await self._async_call_hass_service(
        DOMAIN,
        "notify_test",
        {
          ATTR_DOG_ID: self._dog_id,
          "message": message,
        },
      ):
        return


class PawControlEmergencyContactText(PawControlTextBase):
  """Text entity for emergency contact information."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "emergency_contact",
      max_length=200,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:phone-alert"


class PawControlMicrochipText(PawControlTextBase):
  """Text entity for microchip number."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(coordinator, dog_id, dog_name, "microchip", max_length=20)
    self._attr_icon = "mdi:chip"
    self._attr_mode = TextMode.PASSWORD  # Hide microchip number


class PawControlBreederInfoText(PawControlTextBase):
  """Text entity for breeder information."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "breeder_info",
      max_length=300,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:account-group"


class PawControlRegistrationText(PawControlTextBase):
  """Text entity for registration information."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(coordinator, dog_id, dog_name, "registration", max_length=100)
    self._attr_icon = "mdi:certificate"


class PawControlInsuranceText(PawControlTextBase):
  """Text entity for insurance information."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "insurance_info",
      max_length=300,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:shield-account"


class PawControlAllergiesText(PawControlTextBase):
  """Text entity for allergies and restrictions."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "allergies",
      max_length=500,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:alert-circle"

  async def async_set_value(self, value: str) -> None:
    """Set new allergies information."""
    await super().async_set_value(value)

    # Log allergies as important health data
    trimmed_value = value.strip()
    if trimmed_value and not await self._async_call_hass_service(
      DOMAIN,
      "log_health_data",
      {
        ATTR_DOG_ID: self._dog_id,
        "note": f"Allergies/Restrictions updated: {value}",
      },
    ):
      return


class PawControlTrainingNotesText(PawControlTextBase):
  """Text entity for training notes."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "training_notes",
      max_length=1000,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:school"


class PawControlBehaviorNotesText(PawControlTextBase):
  """Text entity for behavior notes."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "behavior_notes",
      max_length=1000,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:emoticon-happy"

  async def async_set_value(self, value: str) -> None:
    """Set new behavior notes."""
    await super().async_set_value(value)

    # Log behavior changes as health data
    trimmed_value = value.strip()
    if (
      trimmed_value
      and len(trimmed_value) > 10
      and not await self._async_call_hass_service(
        DOMAIN,
        "log_health_data",
        {
          ATTR_DOG_ID: self._dog_id,
          "note": f"Behavior notes: {value}",
        },
      )
    ):
      return


class PawControlLocationDescriptionText(PawControlTextBase):
  """Text entity for custom location description."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    """Initialize the text entity."""
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "location_description",
      max_length=200,
      mode=TextMode.TEXT,
    )
    self._attr_icon = "mdi:map-marker-outline"

  @property
  def available(self) -> bool:
    """Return if entity is available."""
    dog_data = self.coordinator.get_dog_data(self._dog_id)
    if not dog_data:
      return False

    # Available when GPS module is enabled
    dog_info = self.coordinator.get_dog_info(self._dog_id)
    if not dog_info:
      return False

    modules = coerce_dog_modules_config(dog_info.get(DOG_MODULES_FIELD))
    return bool(modules.get(MODULE_GPS))
