"""Tests for the PawControl text platform.

Covers _normalize_dog_configs, _async_add_entities_in_batches,
PawControlTextBase core behaviour, and concrete text entity subclasses.
"""

from collections.abc import Mapping
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.text import (
    PawControlBreederInfoText,
    PawControlCurrentWalkLabelText,
    PawControlCustomLabelText,
    PawControlDogNotesText,
    PawControlHealthNotesText,
    PawControlMicrochipText,
    PawControlTextBase,
    PawControlWalkNotesText,
    _async_add_entities_in_batches,
    _normalize_dog_configs,
)
from custom_components.pawcontrol.types import CoordinatorDogData

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _CoordStub:
    """Minimal coordinator stub for text entity tests."""

    def __init__(self, dog_data: CoordinatorDogData | None = None) -> None:
        self.available = True
        self.last_update_success_time = None
        self._dog_data: CoordinatorDogData = dog_data or cast(CoordinatorDogData, {})
        self.data: dict[str, CoordinatorDogData] = {}
        if dog_data:
            self.data["rex"] = dog_data

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        return self._dog_data if self._dog_data else None

    def get_module_data(self, dog_id: str, module: str) -> Any:
        return self._dog_data.get(module, {})

    def get_enabled_modules(self, dog_id: str) -> list[str]:
        return []


def _make_coordinator(
    dog_data: CoordinatorDogData | None = None,
) -> PawControlCoordinator:  # noqa: E501
    return cast(PawControlCoordinator, _CoordStub(dog_data))


# ---------------------------------------------------------------------------
# _normalize_dog_configs
# ---------------------------------------------------------------------------


class TestNormalizeDogConfigs:
    """Tests for the _normalize_dog_configs helper."""

    def test_returns_empty_list_for_none(self) -> None:
        result = _normalize_dog_configs(None)
        assert result == []

    def test_skips_non_mapping_entries(self) -> None:
        result = _normalize_dog_configs(["not-a-dict", 42, None])
        assert result == []

    def test_skips_mapping_missing_required_fields(self) -> None:
        result = _normalize_dog_configs([{"random_key": "value"}])
        assert result == []

    def test_accepts_minimal_valid_config(self) -> None:
        result = _normalize_dog_configs([{"dog_id": "rex", "dog_name": "Rex"}])
        assert len(result) == 1
        assert result[0]["dog_id"] == "rex"

    def test_modules_dict_is_preserved(self) -> None:
        config = {
            "dog_id": "rex",
            "dog_name": "Rex",
            "modules": {"feeding": True, "walk": False},
        }
        result = _normalize_dog_configs([config])
        assert len(result) == 1

    def test_multiple_valid_configs_returned(self) -> None:
        configs = [
            {"dog_id": "rex", "dog_name": "Rex"},
            {"dog_id": "max", "dog_name": "Max"},
        ]
        result = _normalize_dog_configs(configs)
        assert len(result) == 2

    def test_mixed_valid_invalid_returns_only_valid(self) -> None:
        configs = [
            {"dog_id": "rex", "dog_name": "Rex"},
            "invalid",
            {"dog_id": "max", "dog_name": "Max"},
        ]
        result = _normalize_dog_configs(configs)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _async_add_entities_in_batches
# ---------------------------------------------------------------------------


class TestAsyncAddTextEntitiesInBatches:
    """Tests for _async_add_entities_in_batches."""

    @pytest.mark.asyncio
    async def test_raises_on_zero_batch_size(self) -> None:
        coord = _make_coordinator()
        entities = [PawControlCustomLabelText(coord, "rex", "Rex")]
        callback = AsyncMock()
        with pytest.raises(ValueError, match="batch_size"):
            await _async_add_entities_in_batches(callback, entities, batch_size=0)

    @pytest.mark.asyncio
    async def test_empty_list_does_nothing(self) -> None:
        callback = AsyncMock()
        with patch(
            "custom_components.pawcontrol.text.async_call_add_entities",
            new=AsyncMock(),
        ) as mock_add:
            await _async_add_entities_in_batches(callback, [])
            mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_small_batch_calls_add_once(self) -> None:
        coord = _make_coordinator()
        entities = [PawControlCustomLabelText(coord, "rex", "Rex")]
        call_count = 0

        async def fake_add(batch, **kwargs) -> None:
            nonlocal call_count
            call_count += 1

        with patch(
            "custom_components.pawcontrol.text.async_call_add_entities",
            side_effect=fake_add,
        ):
            await _async_add_entities_in_batches(
                AsyncMock(), entities, batch_size=8, delay_between_batches=0
            )
        assert call_count == 1


# ---------------------------------------------------------------------------
# PawControlTextBase
# ---------------------------------------------------------------------------


class TestPawControlTextBase:
    """Tests for PawControlTextBase core behaviour."""

    def _make_notes(
        self, dog_data: CoordinatorDogData | None = None
    ) -> PawControlDogNotesText:
        coord = _make_coordinator(dog_data)
        return PawControlDogNotesText(coord, "rex", "Rex")

    def test_unique_id_format(self) -> None:
        entity = self._make_notes()
        assert entity._attr_unique_id == "pawcontrol_rex_notes"

    def test_native_value_default_is_empty_string(self) -> None:
        entity = self._make_notes()
        assert entity.native_value == ""

    def test_translation_key_set(self) -> None:
        entity = self._make_notes()
        assert entity._attr_translation_key == "notes"

    def test_extra_state_attributes_include_text_type(self) -> None:
        entity = self._make_notes()
        attrs = entity.extra_state_attributes
        assert attrs.get("text_type") == "notes"

    def test_character_count_is_zero_initially(self) -> None:
        entity = self._make_notes()
        attrs = entity.extra_state_attributes
        assert attrs.get("character_count") == 0

    @pytest.mark.asyncio
    async def test_async_set_value_updates_current_value(self) -> None:
        entity = self._make_notes()
        entity.async_write_ha_state = MagicMock()
        # Bypass actual persist by patching it
        with patch.object(entity, "_async_persist_text_value", new=AsyncMock()):
            await entity.async_set_value("Hello dog!")
        assert entity.native_value == "Hello dog!"

    @pytest.mark.asyncio
    async def test_async_set_value_ignores_duplicate(self) -> None:
        entity = self._make_notes()
        entity.async_write_ha_state = MagicMock()
        entity._current_value = "same"
        with patch.object(
            entity, "_async_persist_text_value", new=AsyncMock()
        ) as mock_persist:  # noqa: E501
            await entity.async_set_value("same")
        mock_persist.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_set_value_whitespace_only_becomes_empty(self) -> None:
        entity = self._make_notes()
        entity.async_write_ha_state = MagicMock()
        with patch.object(entity, "_async_persist_text_value", new=AsyncMock()):
            await entity.async_set_value("   ")
        assert entity.native_value == ""

    def test_clamp_value_truncates_to_max_length(self) -> None:
        entity = self._make_notes()
        entity._attr_native_max = 10
        result = entity._clamp_value("a" * 20)
        assert len(result) == 10

    def test_clamp_value_preserves_short_strings(self) -> None:
        entity = self._make_notes()
        entity._attr_native_max = 100
        result = entity._clamp_value("short")
        assert result == "short"


# ---------------------------------------------------------------------------
# Concrete text entity subclasses
# ---------------------------------------------------------------------------


class TestConcreteTextEntities:
    """Smoke tests for concrete text entity classes."""

    def _coord(self) -> PawControlCoordinator:
        return _make_coordinator()

    def test_custom_label_max_length(self) -> None:
        entity = PawControlCustomLabelText(self._coord(), "rex", "Rex")
        assert entity._attr_native_max == 50

    def test_dog_notes_max_length(self) -> None:
        entity = PawControlDogNotesText(self._coord(), "rex", "Rex")
        assert entity._attr_native_max == 1000

    def test_walk_notes_max_length(self) -> None:
        entity = PawControlWalkNotesText(self._coord(), "rex", "Rex")
        assert entity._attr_native_max == 500

    def test_health_notes_translation_key(self) -> None:
        entity = PawControlHealthNotesText(self._coord(), "rex", "Rex")
        assert entity._attr_translation_key == "health_notes"

    def test_microchip_translation_key(self) -> None:
        entity = PawControlMicrochipText(self._coord(), "rex", "Rex")
        assert entity._attr_translation_key == "microchip"

    def test_breeder_info_translation_key(self) -> None:
        entity = PawControlBreederInfoText(self._coord(), "rex", "Rex")
        assert entity._attr_translation_key == "breeder_info"

    def test_current_walk_label_unavailable_when_no_walk(self) -> None:
        entity = PawControlCurrentWalkLabelText(
            _make_coordinator(
                cast(CoordinatorDogData, {"walk": {"walk_in_progress": False}})
            ),  # noqa: E501
            "rex",
            "Rex",
        )
        assert entity.available is False

    def test_current_walk_label_available_during_walk(self) -> None:
        entity = PawControlCurrentWalkLabelText(
            _make_coordinator(
                cast(CoordinatorDogData, {"walk": {"walk_in_progress": True}})
            ),  # noqa: E501
            "rex",
            "Rex",
        )
        assert entity.available is True
