from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.const import (
    DOMAIN,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.entity_factory import EntityFactory
from custom_components.pawcontrol.feeding_manager import FeedingManager
from custom_components.pawcontrol.notifications import PawControlNotificationManager
from custom_components.pawcontrol.runtime_data import store_runtime_data
from custom_components.pawcontrol.text import (
    PawControlAllergiesText,
    PawControlBehaviorNotesText,
    PawControlBreederInfoText,
    PawControlCurrentWalkLabelText,
    PawControlCustomLabelText,
    PawControlCustomMessageText,
    PawControlDogNotesText,
    PawControlEmergencyContactText,
    PawControlGroomingNotesText,
    PawControlHealthNotesText,
    PawControlInsuranceText,
    PawControlLocationDescriptionText,
    PawControlMedicationNotesText,
    PawControlMicrochipText,
    PawControlRegistrationText,
    PawControlTextBase,
    PawControlTrainingNotesText,
    PawControlVetNotesText,
    PawControlWalkNotesText,
    _normalize_dog_configs,
    async_setup_entry,
)
from custom_components.pawcontrol.types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    DOG_TEXT_METADATA_FIELD,
    DOG_TEXT_VALUES_FIELD,
    CoordinatorRuntimeManagers,
    DogConfigData,
    JSONMutableMapping,
    PawControlConfigEntry,
    PawControlRuntimeData,
)
from custom_components.pawcontrol.walk_manager import WalkManager
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


class _CoordinatorStub:
    """Minimal coordinator implementation for text entity tests."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.config_entry = SimpleNamespace(entry_id="test-entry", runtime_data=None)
        self.data: JSONMutableMapping = cast(JSONMutableMapping, {})
        self.last_update_success = True
        self.last_update_success_time = None
        self.runtime_managers = CoordinatorRuntimeManagers()

    def async_add_listener(
        self, _callback: Any
    ) -> Any:  # pragma: no cover - interface hook
        return lambda: None

    async def async_request_refresh(self) -> None:  # pragma: no cover - interface hook
        return None

    async def async_set_updated_data(self, data: JSONMutableMapping) -> None:
        self.data = data

    def get_dog_data(self, dog_id: str) -> JSONMutableMapping | None:
        return cast(JSONMutableMapping | None, self.data.get(dog_id))

    def get_dog_info(self, dog_id: str) -> JSONMutableMapping | None:
        return self.get_dog_data(dog_id)

    @property
    def available(self) -> bool:
        return True


def test_normalize_dog_configs_filters_invalid_entries() -> None:
    """Ensure dog configuration normalization skips invalid payloads."""

    projection = SimpleNamespace(
        config={MODULE_HEALTH: True},
        mapping={MODULE_HEALTH: True},
    )

    raw_configs: list[Any] = [
        {
            DOG_ID_FIELD: "dog-1",
            DOG_NAME_FIELD: "Buddy",
            DOG_MODULES_FIELD: {MODULE_WALK: True, MODULE_NOTIFICATIONS: False},
        },
        {
            DOG_ID_FIELD: "dog-2",
        },
        {
            DOG_ID_FIELD: "dog-3",
            DOG_NAME_FIELD: "Rex",
            DOG_MODULES_FIELD: projection,
        },
        "not-a-mapping",
    ]

    normalized = _normalize_dog_configs(raw_configs)

    assert len(normalized) == 2
    first, second = normalized

    assert first[DOG_ID_FIELD] == "dog-1"
    modules_first = first[DOG_MODULES_FIELD]
    assert isinstance(modules_first, dict)
    assert modules_first[MODULE_WALK] is True
    assert MODULE_NOTIFICATIONS in modules_first

    assert second[DOG_ID_FIELD] == "dog-3"
    modules_second = second[DOG_MODULES_FIELD]
    assert isinstance(modules_second, dict)
    assert modules_second[MODULE_HEALTH] is True


@pytest.mark.asyncio
async def test_async_setup_entry_creates_text_entities_from_normalized_configs(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure setup filters invalid configs and registers text entities."""

    coordinator = cast(PawControlCoordinator, _CoordinatorStub(hass))

    runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=cast(PawControlDataManager, MagicMock(spec=PawControlDataManager)),
        notification_manager=cast(
            PawControlNotificationManager, MagicMock(spec=PawControlNotificationManager)
        ),
        feeding_manager=cast(FeedingManager, MagicMock(spec=FeedingManager)),
        walk_manager=cast(WalkManager, MagicMock(spec=WalkManager)),
        entity_factory=cast(EntityFactory, MagicMock(spec=EntityFactory)),
        entity_profile="standard",
        dogs=[
            cast(
                DogConfigData,
                {
                    DOG_ID_FIELD: "dog-1",
                    DOG_NAME_FIELD: "Buddy",
                    DOG_MODULES_FIELD: {
                        MODULE_WALK: True,
                        MODULE_HEALTH: True,
                        MODULE_NOTIFICATIONS: True,
                    },
                },
            ),
            {DOG_NAME_FIELD: "MissingId"},
            "invalid-entry",
        ],
    )

    def _get_runtime_data(
        _hass: HomeAssistant, _entry: PawControlConfigEntry
    ) -> PawControlRuntimeData:
        return runtime_data

    monkeypatch.setattr(
        "custom_components.pawcontrol.text.get_runtime_data", _get_runtime_data
    )

    added_entities: list[PawControlTextBase] = []

    def _add_entities(
        entities: Iterable[PawControlTextBase], update_before_add: bool = False
    ) -> None:
        assert not update_before_add
        added_entities.extend(list(entities))

    entry = cast(PawControlConfigEntry, SimpleNamespace(entry_id="test-entry"))

    await async_setup_entry(hass, entry, _add_entities)

    expected_types = {
        PawControlDogNotesText,
        PawControlCustomLabelText,
        PawControlMicrochipText,
        PawControlBreederInfoText,
        PawControlRegistrationText,
        PawControlInsuranceText,
        PawControlWalkNotesText,
        PawControlCurrentWalkLabelText,
        PawControlHealthNotesText,
        PawControlMedicationNotesText,
        PawControlVetNotesText,
        PawControlGroomingNotesText,
        PawControlAllergiesText,
        PawControlTrainingNotesText,
        PawControlBehaviorNotesText,
        PawControlCustomMessageText,
        PawControlEmergencyContactText,
    }

    assert len(added_entities) == len(expected_types)
    assert {type(entity) for entity in added_entities} == expected_types
    assert all(entity.dog_id == "dog-1" for entity in added_entities)

    for entity in added_entities:
        attrs = entity.extra_state_attributes
        assert attrs["dog_name"] == "Buddy"
        assert attrs["character_count"] == 0
        assert attrs["text_type"]
        assert "last_updated" in attrs
        assert attrs["last_updated"] is None

    assert not any(
        isinstance(entity, PawControlLocationDescriptionText)
        for entity in added_entities
    )


@pytest.mark.asyncio
async def test_async_setup_entry_adds_location_text_for_gps_module(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure the GPS module registers a location description text entity."""

    coordinator = cast(PawControlCoordinator, _CoordinatorStub(hass))

    runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=cast(PawControlDataManager, MagicMock(spec=PawControlDataManager)),
        notification_manager=cast(
            PawControlNotificationManager, MagicMock(spec=PawControlNotificationManager)
        ),
        feeding_manager=cast(FeedingManager, MagicMock(spec=FeedingManager)),
        walk_manager=cast(WalkManager, MagicMock(spec=WalkManager)),
        entity_factory=cast(EntityFactory, MagicMock(spec=EntityFactory)),
        entity_profile="standard",
        dogs=[
            cast(
                DogConfigData,
                {
                    DOG_ID_FIELD: "dog-42",
                    DOG_NAME_FIELD: "Scout",
                    DOG_MODULES_FIELD: {MODULE_GPS: True},
                },
            ),
        ],
    )

    def _get_runtime_data(
        _hass: HomeAssistant, _entry: PawControlConfigEntry
    ) -> PawControlRuntimeData:
        return runtime_data

    monkeypatch.setattr(
        "custom_components.pawcontrol.text.get_runtime_data", _get_runtime_data
    )

    added_entities: list[PawControlTextBase] = []

    def _add_entities(
        entities: Iterable[PawControlTextBase], update_before_add: bool = False
    ) -> None:
        assert not update_before_add
        added_entities.extend(list(entities))

    entry = cast(PawControlConfigEntry, SimpleNamespace(entry_id="entry-gps"))

    await async_setup_entry(hass, entry, _add_entities)

    assert any(
        isinstance(entity, PawControlLocationDescriptionText)
        for entity in added_entities
    )
    assert len(added_entities) == 7  # 6 base entries + GPS location description


@pytest.mark.asyncio
async def test_custom_label_character_count_updates_with_value(
    hass: HomeAssistant,
) -> None:
    """Text entities expose typed attributes and clamp native values."""

    coordinator = cast(PawControlCoordinator, _CoordinatorStub(hass))
    text = PawControlCustomLabelText(coordinator, "dog-4", "Luna")
    text.hass = hass
    text.async_write_ha_state = MagicMock()

    await text.async_set_value("Welcome home!")
    attrs = text.extra_state_attributes
    last_updated = attrs.pop("last_updated")
    assert isinstance(last_updated, str)
    assert dt_util.parse_datetime(last_updated) is not None
    assert attrs == {
        "dog_id": "dog-4",
        "dog_name": "Luna",
        "text_type": "custom_label",
        "character_count": len("Welcome home!"),
        "last_updated_context_id": None,
        "last_updated_parent_id": None,
        "last_updated_user_id": None,
    }


@pytest.mark.asyncio
async def test_async_set_value_skips_duplicate_updates(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure duplicate text submissions do not trigger redundant writes."""

    coordinator = cast(PawControlCoordinator, _CoordinatorStub(hass))
    data_manager = cast(PawControlDataManager, MagicMock(spec=PawControlDataManager))

    runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=data_manager,
        notification_manager=cast(
            PawControlNotificationManager, MagicMock(spec=PawControlNotificationManager)
        ),
        feeding_manager=cast(FeedingManager, MagicMock(spec=FeedingManager)),
        walk_manager=cast(WalkManager, MagicMock(spec=WalkManager)),
        entity_factory=cast(EntityFactory, MagicMock(spec=EntityFactory)),
        entity_profile="standard",
        dogs=[
            cast(
                DogConfigData,
                {
                    DOG_ID_FIELD: "dog-duplicate",
                    DOG_NAME_FIELD: "Indy",
                },
            )
        ],
    )

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    coordinator.config_entry = entry
    store_runtime_data(hass, entry, runtime_data)

    text = PawControlCustomLabelText(coordinator, "dog-duplicate", "Indy")
    text.hass = hass
    text.async_write_ha_state = MagicMock()

    timestamp = datetime(2024, 1, 5, 7, 8, 9, tzinfo=UTC)
    monkeypatch.setattr(dt_util, "utcnow", lambda: timestamp)

    await text.async_set_value("Hello there")
    expected_timestamp = timestamp.isoformat()
    data_manager.async_update_dog_data.assert_awaited_once_with(
        "dog-duplicate",
        {
            DOG_TEXT_VALUES_FIELD: {"custom_label": "Hello there"},
            DOG_TEXT_METADATA_FIELD: {
                "custom_label": {"last_updated": expected_timestamp}
            },
        },
    )
    text.async_write_ha_state.assert_called_once()

    data_manager.async_update_dog_data.reset_mock()
    text.async_write_ha_state.reset_mock()

    await text.async_set_value("Hello there")

    data_manager.async_update_dog_data.assert_not_called()
    text.async_write_ha_state.assert_not_called()


@pytest.mark.asyncio
async def test_async_set_value_persists_runtime_text_snapshot(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setting values stores snapshots in runtime and coordinator caches."""

    coordinator = cast(PawControlCoordinator, _CoordinatorStub(hass))
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    coordinator.config_entry = entry

    data_manager = MagicMock(spec=PawControlDataManager)
    data_manager.async_update_dog_data = AsyncMock(return_value=True)

    runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=cast(PawControlDataManager, data_manager),
        notification_manager=cast(
            PawControlNotificationManager, MagicMock(spec=PawControlNotificationManager)
        ),
        feeding_manager=cast(FeedingManager, MagicMock(spec=FeedingManager)),
        walk_manager=cast(WalkManager, MagicMock(spec=WalkManager)),
        entity_factory=cast(EntityFactory, MagicMock(spec=EntityFactory)),
        entity_profile="standard",
        dogs=[
            cast(
                DogConfigData,
                {
                    DOG_ID_FIELD: "dog-1",
                    DOG_NAME_FIELD: "Buddy",
                    DOG_MODULES_FIELD: {MODULE_WALK: True},
                },
            )
        ],
    )

    store_runtime_data(hass, entry, runtime_data)

    text = PawControlCustomLabelText(coordinator, "dog-1", "Buddy")
    text.hass = hass
    text.async_write_ha_state = MagicMock()

    timestamp = datetime(2024, 2, 3, 4, 5, tzinfo=UTC)
    monkeypatch.setattr(dt_util, "utcnow", lambda: timestamp)

    await text.async_set_value("Runtime snapshot")

    expected_timestamp = timestamp.isoformat()
    data_manager.async_update_dog_data.assert_awaited_once_with(
        "dog-1",
        {
            DOG_TEXT_VALUES_FIELD: {"custom_label": "Runtime snapshot"},
            DOG_TEXT_METADATA_FIELD: {
                "custom_label": {"last_updated": expected_timestamp}
            },
        },
    )

    dog_snapshot = runtime_data.dogs[0][DOG_TEXT_VALUES_FIELD]
    assert isinstance(dog_snapshot, dict)
    assert dog_snapshot["custom_label"] == "Runtime snapshot"

    dog_metadata = runtime_data.dogs[0][DOG_TEXT_METADATA_FIELD]
    assert isinstance(dog_metadata, dict)
    assert dog_metadata["custom_label"]["last_updated"] == expected_timestamp

    coordinator_snapshot = coordinator.data["dog-1"][DOG_TEXT_VALUES_FIELD]
    assert isinstance(coordinator_snapshot, dict)
    assert coordinator_snapshot["custom_label"] == "Runtime snapshot"

    coordinator_metadata = coordinator.data["dog-1"][DOG_TEXT_METADATA_FIELD]
    assert isinstance(coordinator_metadata, dict)
    assert coordinator_metadata["custom_label"]["last_updated"] == expected_timestamp


@pytest.mark.asyncio
async def test_async_set_value_captures_context_metadata(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Context metadata propagates through snapshots when available."""

    coordinator = cast(PawControlCoordinator, _CoordinatorStub(hass))
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    coordinator.config_entry = entry

    data_manager = MagicMock(spec=PawControlDataManager)
    data_manager.async_update_dog_data = AsyncMock(return_value=True)

    runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=cast(PawControlDataManager, data_manager),
        notification_manager=cast(
            PawControlNotificationManager, MagicMock(spec=PawControlNotificationManager)
        ),
        feeding_manager=cast(FeedingManager, MagicMock(spec=FeedingManager)),
        walk_manager=cast(WalkManager, MagicMock(spec=WalkManager)),
        entity_factory=cast(EntityFactory, MagicMock(spec=EntityFactory)),
        entity_profile="standard",
        dogs=[
            cast(
                DogConfigData,
                {
                    DOG_ID_FIELD: "dog-ctx",
                    DOG_NAME_FIELD: "Cooper",
                    DOG_MODULES_FIELD: {MODULE_HEALTH: True},
                },
            )
        ],
    )

    store_runtime_data(hass, entry, runtime_data)

    text = PawControlCustomLabelText(coordinator, "dog-ctx", "Cooper")
    text.hass = hass
    text.async_write_ha_state = MagicMock()
    text._context = SimpleNamespace(
        id="ctx-99", parent_id="parent-22", user_id="user-7"
    )

    timestamp = datetime(2024, 4, 10, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(dt_util, "utcnow", lambda: timestamp)

    await text.async_set_value("With context")

    expected_timestamp = timestamp.isoformat()
    data_manager.async_update_dog_data.assert_awaited_once_with(
        "dog-ctx",
        {
            DOG_TEXT_VALUES_FIELD: {"custom_label": "With context"},
            DOG_TEXT_METADATA_FIELD: {
                "custom_label": {
                    "last_updated": expected_timestamp,
                    "context_id": "ctx-99",
                    "parent_id": "parent-22",
                    "user_id": "user-7",
                }
            },
        },
    )

    metadata_entry = runtime_data.dogs[0][DOG_TEXT_METADATA_FIELD]["custom_label"]
    assert metadata_entry["context_id"] == "ctx-99"
    assert metadata_entry["parent_id"] == "parent-22"
    assert metadata_entry["user_id"] == "user-7"

    attributes = text.extra_state_attributes
    assert attributes["last_updated_context_id"] == "ctx-99"
    assert attributes["last_updated_parent_id"] == "parent-22"
    assert attributes["last_updated_user_id"] == "user-7"


@pytest.mark.asyncio
async def test_async_set_value_removes_snapshot_when_cleared(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clearing values removes stored snapshots across caches."""

    coordinator = cast(PawControlCoordinator, _CoordinatorStub(hass))
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    coordinator.config_entry = entry

    data_manager = MagicMock(spec=PawControlDataManager)
    data_manager.async_update_dog_data = AsyncMock(return_value=True)

    runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=cast(PawControlDataManager, data_manager),
        notification_manager=cast(
            PawControlNotificationManager, MagicMock(spec=PawControlNotificationManager)
        ),
        feeding_manager=cast(FeedingManager, MagicMock(spec=FeedingManager)),
        walk_manager=cast(WalkManager, MagicMock(spec=WalkManager)),
        entity_factory=cast(EntityFactory, MagicMock(spec=EntityFactory)),
        entity_profile="standard",
        dogs=[
            cast(
                DogConfigData,
                {
                    DOG_ID_FIELD: "dog-1",
                    DOG_NAME_FIELD: "Buddy",
                    DOG_MODULES_FIELD: {MODULE_WALK: True},
                },
            )
        ],
    )

    store_runtime_data(hass, entry, runtime_data)

    text = PawControlCustomLabelText(coordinator, "dog-1", "Buddy")
    text.hass = hass
    text.async_write_ha_state = MagicMock()

    first_dt = datetime(2024, 3, 1, 8, 30, tzinfo=UTC)
    second_dt = datetime(2024, 3, 2, 9, 45, tzinfo=UTC)
    timestamps = iter((first_dt, second_dt))
    monkeypatch.setattr(dt_util, "utcnow", lambda: next(timestamps))

    await text.async_set_value("Runtime snapshot")

    first_timestamp = first_dt.isoformat()
    data_manager.async_update_dog_data.assert_awaited_once_with(
        "dog-1",
        {
            DOG_TEXT_VALUES_FIELD: {"custom_label": "Runtime snapshot"},
            DOG_TEXT_METADATA_FIELD: {
                "custom_label": {"last_updated": first_timestamp}
            },
        },
    )

    text.async_write_ha_state.reset_mock()
    data_manager.async_update_dog_data.reset_mock()

    await text.async_set_value("   ")

    second_timestamp = second_dt.isoformat()
    data_manager.async_update_dog_data.assert_awaited_once_with(
        "dog-1",
        {
            DOG_TEXT_VALUES_FIELD: {"custom_label": None},
            DOG_TEXT_METADATA_FIELD: {
                "custom_label": {"last_updated": second_timestamp}
            },
        },
    )
    text.async_write_ha_state.assert_called_once()
    assert text.native_value == ""
    assert text.extra_state_attributes["last_updated"] == second_timestamp
    assert text.extra_state_attributes["last_updated_context_id"] is None
    assert text.extra_state_attributes["last_updated_parent_id"] is None
    assert text.extra_state_attributes["last_updated_user_id"] is None

    dog_payload = runtime_data.dogs[0]
    assert DOG_TEXT_VALUES_FIELD not in dog_payload
    metadata_entry = dog_payload[DOG_TEXT_METADATA_FIELD]["custom_label"]
    assert metadata_entry["last_updated"] == second_timestamp

    coordinator_payload = coordinator.data.get("dog-1", {})
    assert DOG_TEXT_VALUES_FIELD not in coordinator_payload
    assert (
        coordinator_payload[DOG_TEXT_METADATA_FIELD]["custom_label"]["last_updated"]
        == second_timestamp
    )


@pytest.mark.asyncio
async def test_async_added_to_hass_restores_runtime_snapshot(
    hass: HomeAssistant,
) -> None:
    """Runtime snapshots override restore state when available."""

    coordinator = cast(PawControlCoordinator, _CoordinatorStub(hass))
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    coordinator.config_entry = entry

    runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=cast(PawControlDataManager, MagicMock(spec=PawControlDataManager)),
        notification_manager=cast(
            PawControlNotificationManager, MagicMock(spec=PawControlNotificationManager)
        ),
        feeding_manager=cast(FeedingManager, MagicMock(spec=FeedingManager)),
        walk_manager=cast(WalkManager, MagicMock(spec=WalkManager)),
        entity_factory=cast(EntityFactory, MagicMock(spec=EntityFactory)),
        entity_profile="standard",
        dogs=[
            cast(
                DogConfigData,
                {
                    DOG_ID_FIELD: "dog-2",
                    DOG_NAME_FIELD: "Bailey",
                    DOG_TEXT_VALUES_FIELD: {"custom_label": "Runtime label"},
                    DOG_TEXT_METADATA_FIELD: {
                        "custom_label": {"last_updated": "2024-04-01T05:06:07+00:00"}
                    },
                },
            )
        ],
    )

    store_runtime_data(hass, entry, runtime_data)
    coordinator.data = {
        "dog-2": {
            DOG_TEXT_VALUES_FIELD: {"custom_label": "Coordinator label"},
            DOG_TEXT_METADATA_FIELD: {
                "custom_label": {"last_updated": "2024-04-02T05:06:07+00:00"}
            },
        }
    }

    text = PawControlCustomLabelText(coordinator, "dog-2", "Bailey")
    text.hass = hass
    text.async_write_ha_state = MagicMock()
    last_state_dt = dt_util.utcnow()
    last_state_timestamp = last_state_dt.isoformat()
    text.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="Legacy state",
            attributes={"last_updated": last_state_timestamp},
            last_updated=last_state_dt,
        )
    )

    await text.async_added_to_hass()

    assert text.native_value == "Runtime label"
    text.async_write_ha_state.assert_called()
    runtime_data.data_manager.async_update_dog_data.assert_not_called()
    assert text.extra_state_attributes["last_updated"] == "2024-04-01T05:06:07+00:00"
    assert text.extra_state_attributes["last_updated_context_id"] is None
    assert text.extra_state_attributes["last_updated_parent_id"] is None
    assert text.extra_state_attributes["last_updated_user_id"] is None

    native_max = getattr(text, "native_max", getattr(text, "_attr_native_max", 0))
    assert isinstance(native_max, int) and native_max > 0

    long_value = "x" * (native_max + 25)
    await text.async_set_value(long_value)
    assert text.native_value == "x" * native_max
    attrs_after_update = text.extra_state_attributes
    assert attrs_after_update["character_count"] == native_max
    updated_timestamp = attrs_after_update["last_updated"]
    assert isinstance(updated_timestamp, str)
    assert dt_util.parse_datetime(updated_timestamp) is not None


@pytest.mark.asyncio
async def test_async_added_to_hass_restores_context_metadata(
    hass: HomeAssistant,
) -> None:
    """Restore state metadata provides context identifiers when available."""

    coordinator = cast(PawControlCoordinator, _CoordinatorStub(hass))
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    coordinator.config_entry = entry

    data_manager = AsyncMock()

    runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=cast(PawControlDataManager, data_manager),
        notification_manager=cast(
            PawControlNotificationManager, MagicMock(spec=PawControlNotificationManager)
        ),
        feeding_manager=cast(FeedingManager, MagicMock(spec=FeedingManager)),
        walk_manager=cast(WalkManager, MagicMock(spec=WalkManager)),
        entity_factory=cast(EntityFactory, MagicMock(spec=EntityFactory)),
        entity_profile="standard",
        dogs=[
            cast(
                DogConfigData,
                {
                    DOG_ID_FIELD: "dog-restore-context",
                    DOG_NAME_FIELD: "Luna",
                },
            )
        ],
    )

    store_runtime_data(hass, entry, runtime_data)
    coordinator.data = {}

    text = PawControlCustomLabelText(coordinator, "dog-restore-context", "Luna")
    text.hass = hass
    text.async_write_ha_state = MagicMock()

    restore_state_timestamp = "2024-05-01T02:03:04+00:00"
    text.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="Restored label",
            attributes={
                "last_updated": restore_state_timestamp,
                "last_updated_context_id": "ctx-from-attrs",
                "last_updated_parent_id": "parent-from-attrs",
                "last_updated_user_id": "user-from-attrs",
            },
            last_updated=datetime(2024, 5, 1, 2, 3, 4, tzinfo=UTC),
            context=SimpleNamespace(
                id="ctx-from-context",
                parent_id="parent-from-context",
                user_id="user-from-context",
            ),
        )
    )

    await text.async_added_to_hass()

    assert text.native_value == "Restored label"
    assert text.extra_state_attributes["last_updated"] == restore_state_timestamp
    assert text.extra_state_attributes["last_updated_context_id"] == "ctx-from-attrs"
    assert text.extra_state_attributes["last_updated_parent_id"] == "parent-from-attrs"
    assert text.extra_state_attributes["last_updated_user_id"] == "user-from-attrs"

    data_manager.async_update_dog_data.assert_awaited_once_with(
        "dog-restore-context",
        {
            DOG_TEXT_VALUES_FIELD: {"custom_label": "Restored label"},
            DOG_TEXT_METADATA_FIELD: {
                "custom_label": {
                    "last_updated": restore_state_timestamp,
                    "context_id": "ctx-from-attrs",
                    "parent_id": "parent-from-attrs",
                    "user_id": "user-from-attrs",
                }
            },
        },
    )

    runtime_snapshot = runtime_data.dogs[0][DOG_TEXT_VALUES_FIELD]
    assert runtime_snapshot == {"custom_label": "Restored label"}

    runtime_metadata = runtime_data.dogs[0][DOG_TEXT_METADATA_FIELD]["custom_label"]
    assert runtime_metadata == {
        "last_updated": restore_state_timestamp,
        "context_id": "ctx-from-attrs",
        "parent_id": "parent-from-attrs",
        "user_id": "user-from-attrs",
    }

    coordinator_payload = coordinator.data["dog-restore-context"]
    assert coordinator_payload[DOG_TEXT_VALUES_FIELD] == {
        "custom_label": "Restored label"
    }
    assert coordinator_payload[DOG_TEXT_METADATA_FIELD]["custom_label"] == {
        "last_updated": restore_state_timestamp,
        "context_id": "ctx-from-attrs",
        "parent_id": "parent-from-attrs",
        "user_id": "user-from-attrs",
    }


@pytest.mark.asyncio
async def test_async_added_to_hass_persists_restore_state_when_snapshot_missing(
    hass: HomeAssistant,
) -> None:
    """Restore-state values repopulate runtime caches when snapshots are absent."""

    coordinator = cast(PawControlCoordinator, _CoordinatorStub(hass))
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    coordinator.config_entry = entry

    data_manager = cast(PawControlDataManager, MagicMock(spec=PawControlDataManager))
    runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=data_manager,
        notification_manager=cast(
            PawControlNotificationManager, MagicMock(spec=PawControlNotificationManager)
        ),
        feeding_manager=cast(FeedingManager, MagicMock(spec=FeedingManager)),
        walk_manager=cast(WalkManager, MagicMock(spec=WalkManager)),
        entity_factory=cast(EntityFactory, MagicMock(spec=EntityFactory)),
        entity_profile="standard",
        dogs=[
            cast(
                DogConfigData,
                {
                    DOG_ID_FIELD: "dog-restore",
                    DOG_NAME_FIELD: "Milo",
                },
            )
        ],
    )

    store_runtime_data(hass, entry, runtime_data)
    coordinator.data = {}

    text = PawControlCustomLabelText(coordinator, "dog-restore", "Milo")
    text.hass = hass
    text.async_write_ha_state = MagicMock()
    restore_state_dt = dt_util.utcnow()
    restore_state_timestamp = restore_state_dt.isoformat()
    text.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            state="Restored label",
            attributes={"last_updated": restore_state_timestamp},
            last_updated=restore_state_dt,
        )
    )

    await text.async_added_to_hass()

    data_manager.async_update_dog_data.assert_awaited_once_with(
        "dog-restore",
        {
            DOG_TEXT_VALUES_FIELD: {"custom_label": "Restored label"},
            DOG_TEXT_METADATA_FIELD: {
                "custom_label": {"last_updated": restore_state_timestamp}
            },
        },
    )
    text.async_write_ha_state.assert_called_once()
    assert text.native_value == "Restored label"
    assert text.extra_state_attributes["last_updated"] == restore_state_timestamp
    assert text.extra_state_attributes["last_updated_context_id"] is None
    assert text.extra_state_attributes["last_updated_parent_id"] is None
    assert text.extra_state_attributes["last_updated_user_id"] is None

    runtime_snapshot = runtime_data.dogs[0][DOG_TEXT_VALUES_FIELD]
    assert runtime_snapshot == {"custom_label": "Restored label"}

    runtime_metadata = runtime_data.dogs[0][DOG_TEXT_METADATA_FIELD]
    assert runtime_metadata == {
        "custom_label": {"last_updated": restore_state_timestamp}
    }

    coordinator_snapshot = coordinator.data["dog-restore"][DOG_TEXT_VALUES_FIELD]
    assert coordinator_snapshot == {"custom_label": "Restored label"}

    coordinator_metadata = coordinator.data["dog-restore"][DOG_TEXT_METADATA_FIELD]
    assert coordinator_metadata == {
        "custom_label": {"last_updated": restore_state_timestamp}
    }


@pytest.mark.asyncio
async def test_dog_notes_async_set_value_invokes_health_log_when_contentful(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure dog notes trigger health logging when content threshold met."""

    coordinator = cast(PawControlCoordinator, _CoordinatorStub(hass))
    notes = PawControlDogNotesText(coordinator, "dog-5", "Bailey")
    notes.hass = hass
    notes.async_write_ha_state = MagicMock()

    service_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(notes, "_async_call_hass_service", service_mock)

    await notes.async_set_value("  short  ")
    service_mock.assert_not_called()

    await notes.async_set_value("Important medication instructions for Bailey")
    service_mock.assert_awaited_once()
    await_args = service_mock.await_args
    assert await_args is not None
    args, _kwargs = await_args
    assert args[0] == "pawcontrol"
    assert args[1] == "log_health_data"
    assert args[2]["dog_id"] == "dog-5"
