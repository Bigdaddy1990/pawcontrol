from __future__ import annotations

from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.const import (
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.entity_factory import EntityFactory
from custom_components.pawcontrol.feeding_manager import FeedingManager
from custom_components.pawcontrol.notifications import PawControlNotificationManager
from custom_components.pawcontrol.text import (
    PawControlCustomLabelText,
    PawControlDogNotesText,
    PawControlTextBase,
    _normalize_dog_configs,
    async_setup_entry,
)
from custom_components.pawcontrol.types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    CoordinatorRuntimeManagers,
    DogConfigData,
    JSONMutableMapping,
    PawControlConfigEntry,
    PawControlRuntimeData,
)
from custom_components.pawcontrol.walk_manager import WalkManager
from homeassistant.core import HomeAssistant


class _CoordinatorStub:
    """Minimal coordinator implementation for text entity tests."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.config_entry = SimpleNamespace(entry_id="test-entry", runtime_data=None)
        self.data: JSONMutableMapping = cast(JSONMutableMapping, {})
        self.last_update_success = True
        self.last_update_success_time = None
        self.runtime_managers = CoordinatorRuntimeManagers()

    def async_add_listener(self, _callback: Any) -> Any:  # pragma: no cover - interface hook
        return lambda: None

    async def async_request_refresh(self) -> None:  # pragma: no cover - interface hook
        return None

    async def async_set_updated_data(self, data: JSONMutableMapping) -> None:
        self.data = data

    def get_dog_data(self, dog_id: str) -> JSONMutableMapping | None:
        return cast(JSONMutableMapping | None, self.data.get(dog_id))

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

    def _get_runtime_data(_hass: HomeAssistant, _entry: PawControlConfigEntry) -> PawControlRuntimeData:
        return runtime_data

    monkeypatch.setattr("custom_components.pawcontrol.text.get_runtime_data", _get_runtime_data)

    added_entities: list[PawControlTextBase] = []

    def _add_entities(entities: Iterable[PawControlTextBase], update_before_add: bool = False) -> None:
        assert not update_before_add
        added_entities.extend(list(entities))

    entry = cast(PawControlConfigEntry, SimpleNamespace(entry_id="test-entry"))

    await async_setup_entry(hass, entry, _add_entities)

    assert len(added_entities) == 10  # 2 base + 4 health + 2 walk + 2 notifications
    assert all(entity.dog_id == "dog-1" for entity in added_entities)

    for entity in added_entities:
        attrs = entity.extra_state_attributes
        assert attrs["dog_name"] == "Buddy"
        assert attrs["character_count"] == 0
        assert attrs["text_type"]


@pytest.mark.asyncio
async def test_custom_label_character_count_updates_with_value(hass: HomeAssistant) -> None:
    """Text entities expose typed attributes and clamp native values."""

    coordinator = cast(PawControlCoordinator, _CoordinatorStub(hass))
    text = PawControlCustomLabelText(coordinator, "dog-4", "Luna")
    text.hass = hass
    text.async_write_ha_state = MagicMock()

    await text.async_set_value("Welcome home!")
    attrs = text.extra_state_attributes
    assert attrs == {
        "dog_id": "dog-4",
        "dog_name": "Luna",
        "text_type": "custom_label",
        "character_count": len("Welcome home!"),
    }

    native_max = getattr(text, "native_max", getattr(text, "_attr_native_max", 0))
    assert isinstance(native_max, int) and native_max > 0

    long_value = "x" * (native_max + 25)
    await text.async_set_value(long_value)
    assert text.native_value == "x" * native_max
    assert text.extra_state_attributes["character_count"] == native_max


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
    args, _kwargs = service_mock.await_args
    assert args[0] == "pawcontrol"
    assert args[1] == "log_health_data"
    assert args[2]["dog_id"] == "dog-5"
