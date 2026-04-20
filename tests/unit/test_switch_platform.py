"""Tests for the PawControl switch platform.

Covers OptimizedSwitchBase, ProfileOptimizedSwitchFactory,
_async_add_entities_in_batches, and core switch subclasses.
"""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.switch import (
    OptimizedSwitchBase,
    PawControlDoNotDisturbSwitch,
    PawControlFeatureSwitch,
    PawControlMainPowerSwitch,
    PawControlModuleSwitch,
    PawControlVisitorModeSwitch,
    ProfileOptimizedSwitchFactory,
    _async_add_entities_in_batches,
    _async_reproduce_switch_state,
    _preprocess_switch_state,
    async_reproduce_state,
    async_setup_entry,
)
from custom_components.pawcontrol.types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    CoordinatorDogData,
    DogModulesConfig,
)

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _CoordStub:
    """Minimal coordinator stub for switch tests."""

    def __init__(self, dog_data: CoordinatorDogData | None = None) -> None:
        self.available = True
        self.last_update_success_time = None
        self._dog_data: CoordinatorDogData = dog_data or cast(CoordinatorDogData, {})
        self.hass = MagicMock()
        self.config_entry = MagicMock()
        self.config_entry.data = {"dogs": []}

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        return self._dog_data if self._dog_data else None

    def get_module_data(self, dog_id: str, module: str) -> Any:
        return self._dog_data.get(module, {})

    def get_enabled_modules(self, dog_id: str) -> list[str]:
        return []


def _make_coordinator(
    dog_data: CoordinatorDogData | None = None,
) -> PawControlCoordinator:
    return cast(PawControlCoordinator, _CoordStub(dog_data))


def _full_modules(**overrides: bool) -> DogModulesConfig:
    """Return a modules dict with all keys enabled by default."""
    base: DogModulesConfig = {
        "feeding": True,
        "walk": True,
        "gps": True,
        "health": True,
        "notifications": True,
        "grooming": False,
        "medication": False,
        "training": False,
        "visitor": False,
    }
    for k, v in overrides.items():
        base[k] = v  # type: ignore[literal-required]
    return base


# ---------------------------------------------------------------------------
# ProfileOptimizedSwitchFactory
# ---------------------------------------------------------------------------


class TestProfileOptimizedSwitchFactory:
    """Tests for the profile-based switch factory."""

    def test_always_creates_main_power_and_dnd_switches(self) -> None:  # noqa: D102
        coord = _make_coordinator()
        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coord, "rex", "Rex", _full_modules()
        )
        types = {type(s).__name__ for s in switches}
        assert "PawControlMainPowerSwitch" in types
        assert "PawControlDoNotDisturbSwitch" in types

    def test_visitor_switch_created_when_visitor_module_enabled(self) -> None:  # noqa: D102
        coord = _make_coordinator()
        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coord, "rex", "Rex", _full_modules(visitor=True)
        )
        assert any(isinstance(s, PawControlVisitorModeSwitch) for s in switches)

    def test_visitor_switch_created_when_no_modules_enabled(self) -> None:  # noqa: D102
        coord = _make_coordinator()
        empty_modules: DogModulesConfig = {
            "feeding": False,
            "walk": False,
            "gps": False,
            "health": False,
            "notifications": False,
            "grooming": False,
            "medication": False,
            "training": False,
            "visitor": False,
        }
        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coord, "rex", "Rex", empty_modules
        )
        assert any(isinstance(s, PawControlVisitorModeSwitch) for s in switches)

    def test_module_switch_created_per_enabled_module(self) -> None:  # noqa: D102
        coord = _make_coordinator()
        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coord, "rex", "Rex", _full_modules(grooming=True)
        )
        module_switches = [s for s in switches if isinstance(s, PawControlModuleSwitch)]
        assert len(module_switches) >= 1

    def test_feature_switches_created_for_enabled_gps_module(self) -> None:  # noqa: D102
        coord = _make_coordinator()
        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coord, "rex", "Rex", _full_modules()
        )
        feature_switches = [
            s for s in switches if isinstance(s, PawControlFeatureSwitch)
        ]
        assert len(feature_switches) >= 1

    def test_returns_list_of_switch_instances(self) -> None:  # noqa: D102
        coord = _make_coordinator()
        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coord, "rex", "Rex", _full_modules()
        )
        assert all(isinstance(s, OptimizedSwitchBase) for s in switches)

    def test_unique_ids_are_unique(self) -> None:  # noqa: D102
        coord = _make_coordinator()
        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coord, "rex", "Rex", _full_modules()
        )
        unique_ids = [s._attr_unique_id for s in switches]
        assert len(unique_ids) == len(set(unique_ids))


# ---------------------------------------------------------------------------
# OptimizedSwitchBase
# ---------------------------------------------------------------------------


class TestOptimizedSwitchBase:
    """Tests for OptimizedSwitchBase core functionality."""

    def _make(self, initial_state: bool = False) -> OptimizedSwitchBase:
        coord = _make_coordinator(cast(CoordinatorDogData, {"status": "online"}))
        switch = OptimizedSwitchBase(
            coord, "rex", "Rex", "test_switch", initial_state=initial_state
        )
        return switch

    def test_unique_id_set_correctly(self) -> None:  # noqa: D102
        switch = self._make()
        assert switch._attr_unique_id == "pawcontrol_rex_test_switch"

    def test_is_on_reflects_initial_state_false(self) -> None:  # noqa: D102
        switch = self._make(initial_state=False)
        assert switch.is_on is False

    def test_is_on_reflects_initial_state_true(self) -> None:  # noqa: D102
        switch = self._make(initial_state=True)
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on_sets_state_true(self) -> None:  # noqa: D102
        switch = self._make(initial_state=False)
        switch.hass = MagicMock()
        switch.async_write_ha_state = MagicMock()
        await switch.async_turn_on()
        assert switch._is_on is True

    @pytest.mark.asyncio
    async def test_turn_off_sets_state_false(self) -> None:  # noqa: D102
        switch = self._make(initial_state=True)
        switch.hass = MagicMock()
        switch.async_write_ha_state = MagicMock()
        await switch.async_turn_off()
        assert switch._is_on is False

    def test_extra_state_attributes_includes_switch_type(self) -> None:  # noqa: D102
        switch = self._make()
        switch.hass = MagicMock()
        attrs = switch.extra_state_attributes
        assert attrs.get("switch_type") == "test_switch"

    def test_translation_key_matches_switch_type(self) -> None:  # noqa: D102
        switch = self._make()
        assert switch._attr_translation_key == "test_switch"

    @pytest.mark.asyncio
    async def test_async_added_to_hass_restores_last_state(self) -> None:  # noqa: D102
        from unittest.mock import patch

        switch = self._make()
        switch.hass = MagicMock()
        switch.async_get_last_state = AsyncMock(return_value=MagicMock(state="on"))
        with patch(
            "custom_components.pawcontrol.switch.PawControlDogEntityBase.async_added_to_hass",
            new=AsyncMock(),
        ):
            await switch.async_added_to_hass()
        assert switch._is_on is True

    def test_is_on_uses_hot_cache_before_internal_state(self) -> None:  # noqa: D102
        switch = self._make(initial_state=False)
        switch._state_cache[f"{switch._dog_id}_{switch._switch_type}"] = (
            True,
            9_999_999_999.0,
        )
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on_wraps_errors_as_homeassistant_error(self) -> None:  # noqa: D102
        switch = self._make()
        switch._async_set_state = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
        with pytest.raises(HomeAssistantError):
            await switch.async_turn_on()

    @pytest.mark.asyncio
    async def test_turn_off_wraps_errors_as_homeassistant_error(self) -> None:  # noqa: D102
        switch = self._make(initial_state=True)
        switch._async_set_state = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
        with pytest.raises(HomeAssistantError):
            await switch.async_turn_off()

    @pytest.mark.asyncio
    async def test_turn_on_without_hass_skips_state_write(self) -> None:  # noqa: D102
        switch = self._make(initial_state=False)
        switch.hass = None
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_on()

        switch.async_write_ha_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_turn_off_without_hass_skips_state_write(self) -> None:  # noqa: D102
        switch = self._make(initial_state=True)
        switch.hass = None
        switch.async_write_ha_state = MagicMock()

        await switch.async_turn_off()

        switch.async_write_ha_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_added_to_hass_ignores_non_switch_state(self) -> None:  # noqa: D102
        from unittest.mock import patch

        switch = self._make(initial_state=False)
        switch.hass = MagicMock()
        switch.async_get_last_state = AsyncMock(return_value=MagicMock(state="unknown"))
        with patch(
            "custom_components.pawcontrol.switch.PawControlDogEntityBase.async_added_to_hass",
            new=AsyncMock(),
        ):
            await switch.async_added_to_hass()

        assert switch._is_on is False

    def test_is_on_refreshes_cache_when_entry_is_stale(self) -> None:  # noqa: D102
        switch = self._make(initial_state=True)
        cache_key = f"{switch._dog_id}_{switch._switch_type}"
        switch._state_cache[cache_key] = (False, 0.0)

        assert switch.is_on is True
        assert switch._state_cache[cache_key][0] is True

    def test_is_on_rebuilds_cache_when_entry_is_missing(self) -> None:  # noqa: D102
        switch = self._make(initial_state=False)
        cache_key = f"{switch._dog_id}_{switch._switch_type}"
        switch._state_cache.pop(cache_key, None)

        assert switch.is_on is False
        assert cache_key in switch._state_cache

    def test_extra_state_attributes_include_enabled_modules_from_dog_config(  # noqa: D102
        self,
    ) -> None:
        coordinator = _make_coordinator(
            cast(
                CoordinatorDogData,
                {
                    "dog_info": {
                        DOG_MODULES_FIELD: _full_modules(
                            walk=False,
                            gps=False,
                            health=False,
                            notifications=False,
                            grooming=False,
                            medication=False,
                            training=False,
                            visitor=False,
                        )
                    }
                },
            )
        )
        switch = OptimizedSwitchBase(coordinator, "rex", "Rex", "test_switch")
        switch.hass = MagicMock()

        attrs = switch.extra_state_attributes

        assert attrs["enabled_modules"] == ["feeding"]
        assert attrs["total_modules"] == 1

    def test_get_coordinator_dog_data_returns_none_when_unavailable(self) -> None:  # noqa: D102
        switch = self._make()
        switch.coordinator.available = False

        assert switch._get_coordinator_dog_data() is None

    def test_get_dog_config_returns_mapping_when_present(self) -> None:  # noqa: D102
        coordinator = _make_coordinator(
            cast(
                CoordinatorDogData, {"dog_info": {"name": "Rex", DOG_MODULES_FIELD: {}}}
            )
        )
        switch = OptimizedSwitchBase(coordinator, "rex", "Rex", "test_switch")

        assert switch._get_dog_config() == {"name": "Rex", DOG_MODULES_FIELD: {}}

    def test_available_is_false_when_coordinator_is_unavailable(self) -> None:  # noqa: D102
        switch = self._make()
        switch.coordinator.available = False

        assert switch.available is False


# ---------------------------------------------------------------------------
# PawControlMainPowerSwitch
# ---------------------------------------------------------------------------


class TestPawControlMainPowerSwitch:
    """Tests for PawControlMainPowerSwitch."""

    def _make(self) -> PawControlMainPowerSwitch:
        coord = _make_coordinator()
        return PawControlMainPowerSwitch(coord, "rex", "Rex")

    def test_initial_state_is_on(self) -> None:  # noqa: D102
        switch = self._make()
        assert switch._is_on is True

    def test_unique_id_format(self) -> None:  # noqa: D102
        switch = self._make()
        assert switch._attr_unique_id == "pawcontrol_rex_main_power"

    @pytest.mark.asyncio
    async def test_set_state_skips_when_hass_missing(self) -> None:  # noqa: D102
        switch = self._make()
        switch.hass = None
        switch.coordinator.async_request_selective_refresh = AsyncMock()
        await switch._async_set_state(True)
        switch.coordinator.async_request_selective_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_state_refreshes_when_data_manager_available(self) -> None:  # noqa: D102
        switch = self._make()
        switch.hass = MagicMock()
        data_manager = AsyncMock()
        switch._get_data_manager = MagicMock(return_value=data_manager)  # type: ignore[method-assign]
        switch.coordinator.async_request_selective_refresh = AsyncMock()
        await switch._async_set_state(True)
        data_manager.async_set_dog_power_state.assert_awaited_once_with("rex", True)
        switch.coordinator.async_request_selective_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_state_refreshes_even_when_data_manager_missing(self) -> None:  # noqa: D102
        switch = self._make()
        switch.hass = MagicMock()
        switch._get_data_manager = MagicMock(return_value=None)  # type: ignore[method-assign]
        switch.coordinator.async_request_selective_refresh = AsyncMock()

        await switch._async_set_state(False)

        switch.coordinator.async_request_selective_refresh.assert_awaited_once_with(
            ["rex"],
            priority=10,
        )

    @pytest.mark.asyncio
    async def test_set_state_swallows_refresh_exception(self) -> None:  # noqa: D102
        switch = self._make()
        switch.hass = MagicMock()
        switch._get_data_manager = MagicMock(return_value=None)  # type: ignore[method-assign]
        switch.coordinator.async_request_selective_refresh = AsyncMock(
            side_effect=RuntimeError("boom")
        )

        await switch._async_set_state(True)


# ---------------------------------------------------------------------------
# PawControlDoNotDisturbSwitch
# ---------------------------------------------------------------------------


class TestPawControlDoNotDisturbSwitch:
    """Tests for PawControlDoNotDisturbSwitch."""

    def _make(self) -> PawControlDoNotDisturbSwitch:
        coord = _make_coordinator()
        return PawControlDoNotDisturbSwitch(coord, "rex", "Rex")

    def test_initial_state_is_off(self) -> None:  # noqa: D102
        switch = self._make()
        assert switch._is_on is False

    def test_unique_id_format(self) -> None:  # noqa: D102
        switch = self._make()
        assert switch._attr_unique_id == "pawcontrol_rex_do_not_disturb"

    @pytest.mark.asyncio
    async def test_set_state_skips_when_hass_missing(self) -> None:  # noqa: D102
        switch = self._make()
        switch.hass = None
        notification_manager = object()
        switch._get_notification_manager = MagicMock(  # type: ignore[method-assign]
            return_value=notification_manager
        )

        await switch._async_set_state(True)

    @pytest.mark.asyncio
    async def test_set_state_swallows_notification_exception(self) -> None:  # noqa: D102
        switch = self._make()
        switch.hass = MagicMock()
        notification_manager = MagicMock()
        notification_manager.async_set_dnd_mode = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        switch._get_notification_manager = MagicMock(  # type: ignore[method-assign]
            return_value=notification_manager
        )

        await switch._async_set_state(False)

    @pytest.mark.asyncio
    async def test_set_state_handles_missing_notification_manager(self) -> None:  # noqa: D102
        switch = self._make()
        switch.hass = MagicMock()
        switch._get_notification_manager = MagicMock(return_value=None)  # type: ignore[method-assign]

        await switch._async_set_state(True)


# ---------------------------------------------------------------------------
# PawControlVisitorModeSwitch
# ---------------------------------------------------------------------------


class TestPawControlVisitorModeSwitch:
    """Tests for PawControlVisitorModeSwitch helper paths."""

    def test_is_on_uses_coordinator_payload(self) -> None:  # noqa: D102
        switch = PawControlVisitorModeSwitch(
            _make_coordinator(cast(CoordinatorDogData, {"visitor_mode_active": 1})),
            "rex",
            "Rex",
        )
        assert switch.is_on is True

    def test_is_on_falls_back_to_internal_state(self) -> None:  # noqa: D102
        switch = PawControlVisitorModeSwitch(_make_coordinator(), "rex", "Rex")
        switch._is_on = True

        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_set_state_returns_when_service_declines_and_hass_missing(  # noqa: D102
        self,
    ) -> None:
        switch = PawControlVisitorModeSwitch(_make_coordinator(), "rex", "Rex")
        switch.hass = None
        switch._async_call_hass_service = AsyncMock(return_value=False)  # type: ignore[method-assign]

        await switch._async_set_state(True)

    @pytest.mark.asyncio
    async def test_set_state_returns_when_service_succeeds(self) -> None:  # noqa: D102
        switch = PawControlVisitorModeSwitch(_make_coordinator(), "rex", "Rex")
        switch.hass = MagicMock()
        switch._async_call_hass_service = AsyncMock(return_value=True)  # type: ignore[method-assign]

        await switch._async_set_state(True)

        switch._async_call_hass_service.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_state_raises_when_service_declines_with_hass(self) -> None:  # noqa: D102
        switch = PawControlVisitorModeSwitch(_make_coordinator(), "rex", "Rex")
        switch.hass = MagicMock()
        switch._async_call_hass_service = AsyncMock(return_value=False)  # type: ignore[method-assign]

        with pytest.raises(HomeAssistantError, match="Failed to update visitor mode"):
            await switch._async_set_state(True)


# ---------------------------------------------------------------------------
# PawControlFeatureSwitch
# ---------------------------------------------------------------------------


class TestPawControlFeatureSwitch:
    """Tests for PawControlFeatureSwitch."""

    def _make(
        self, feature_id: str = "gps_tracking", module: str = "gps"
    ) -> PawControlFeatureSwitch:
        coord = _make_coordinator()
        return PawControlFeatureSwitch(
            coord, "rex", "Rex", feature_id, "GPS Tracking", "mdi:gps", module
        )

    def test_feature_id_stored(self) -> None:  # noqa: D102
        switch = self._make()
        assert switch._feature_id == "gps_tracking"

    def test_module_stored(self) -> None:  # noqa: D102
        switch = self._make()
        assert switch._module == "gps"

    def test_extra_state_attributes_contain_parent_module(self) -> None:  # noqa: D102
        switch = self._make()
        switch.hass = MagicMock()
        attrs = switch.extra_state_attributes
        assert attrs.get("parent_module") == "gps"

    @pytest.mark.asyncio
    async def test_set_state_dispatches_to_gps_handler(self) -> None:  # noqa: D102
        switch = self._make()
        switch.hass = MagicMock()
        switch._set_gps_tracking = AsyncMock()  # type: ignore[method-assign]
        await switch._async_set_state(True)
        switch._set_gps_tracking.assert_awaited_once_with(True)

    @pytest.mark.asyncio
    async def test_set_notifications_calls_expected_service(self) -> None:  # noqa: D102
        switch = self._make(feature_id="notifications", module="notifications")
        switch._async_call_hass_service = AsyncMock(return_value=True)  # type: ignore[method-assign]
        await switch._set_notifications(False)
        switch._async_call_hass_service.assert_awaited_once()
        args = switch._async_call_hass_service.await_args.args
        assert args[1] == "configure_alerts"

    def test_init_without_hass_config_uses_grooming_translation_path(self) -> None:  # noqa: D102
        from unittest.mock import patch

        coordinator = _make_coordinator()
        coordinator.hass = None
        with patch(
            "custom_components.pawcontrol.switch.translated_grooming_label",
            return_value="Pflegefunktionen",
        ):
            switch = PawControlFeatureSwitch(
                coordinator,
                "rex",
                "Rex",
                "grooming_tracking",
                "Grooming Tracking",
                "mdi:content-cut",
                "grooming",
            )
        assert switch._feature_name == "Pflegefunktionen"

    @pytest.mark.asyncio
    async def test_set_state_returns_when_hass_missing(self) -> None:  # noqa: D102
        switch = self._make(feature_id="notifications", module="notifications")
        switch.hass = None
        switch._async_call_hass_service = AsyncMock(return_value=True)  # type: ignore[method-assign]

        await switch._async_set_state(True)

        switch._async_call_hass_service.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("feature_id", "module", "expected_service"),
        [
            ("notifications", "notifications", "configure_alerts"),
            ("feeding_schedule", "feeding", "set_feeding_schedule"),
            ("health_monitoring", "health", "configure_health_monitoring"),
            ("medication_reminders", "medication", "configure_medication_reminders"),
        ],
    )
    async def test_set_state_dispatches_supported_service_features(  # noqa: D102
        self,
        feature_id: str,
        module: str,
        expected_service: str,
    ) -> None:
        switch = self._make(feature_id=feature_id, module=module)
        switch.hass = MagicMock()
        switch._async_call_hass_service = AsyncMock(return_value=True)  # type: ignore[method-assign]

        await switch._async_set_state(True)

        switch._async_call_hass_service.assert_awaited_once()
        assert switch._async_call_hass_service.await_args.args[1] == expected_service

    @pytest.mark.asyncio
    async def test_set_state_swallows_feature_handler_exception(self) -> None:  # noqa: D102
        switch = self._make(feature_id="notifications", module="notifications")
        switch.hass = MagicMock()
        switch._set_notifications = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

        await switch._async_set_state(True)

    @pytest.mark.asyncio
    async def test_set_state_with_unhandled_feature_is_noop(self) -> None:  # noqa: D102
        switch = self._make(feature_id="unhandled_feature", module="feeding")
        switch.hass = MagicMock()
        switch._async_call_hass_service = AsyncMock(return_value=True)  # type: ignore[method-assign]

        await switch._async_set_state(True)

        switch._async_call_hass_service.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_gps_tracking_swallows_data_manager_exception(self) -> None:  # noqa: D102
        switch = self._make(feature_id="gps_tracking", module="gps")
        switch._get_data_manager = MagicMock(  # type: ignore[method-assign]
            return_value=SimpleNamespace(
                async_set_gps_tracking=AsyncMock(side_effect=RuntimeError("boom"))
            )
        )

        await switch._set_gps_tracking(True)

    @pytest.mark.asyncio
    async def test_set_gps_tracking_handles_missing_data_manager(self) -> None:  # noqa: D102
        switch = self._make(feature_id="gps_tracking", module="gps")
        switch._get_data_manager = MagicMock(return_value=None)  # type: ignore[method-assign]

        await switch._set_gps_tracking(False)


# ---------------------------------------------------------------------------
# _async_add_entities_in_batches
# ---------------------------------------------------------------------------


class TestAsyncAddEntitiesInBatches:
    """Tests for the batch entity addition helper."""

    @pytest.mark.asyncio
    async def test_empty_list_does_not_call_add_entities(self) -> None:  # noqa: D102
        callback = AsyncMock()
        # Patch async_call_add_entities to avoid import complexity
        from unittest.mock import patch

        with patch(
            "custom_components.pawcontrol.switch.async_call_add_entities",
            new=AsyncMock(),
        ) as mock_add:
            await _async_add_entities_in_batches(callback, [])
            mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_single_batch_when_few_entities(self) -> None:  # noqa: D102
        coord = _make_coordinator()
        entities = [
            PawControlDoNotDisturbSwitch(coord, f"dog{i}", f"Dog{i}") for i in range(3)
        ]
        batch_sizes: list[int] = []

        async def fake_add(_callback, entities_arg, **kwargs) -> None:
            batch_sizes.append(len(entities_arg))

        from unittest.mock import patch

        with patch(
            "custom_components.pawcontrol.switch.async_call_add_entities",
            side_effect=fake_add,
        ):
            await _async_add_entities_in_batches(
                AsyncMock(), entities, batch_size=15, delay_between_batches=0
            )

        assert batch_sizes == [3]

    @pytest.mark.asyncio
    async def test_batches_split_correctly(self) -> None:
        """Verify the batch logic splits at the right boundaries."""
        coord = _make_coordinator()
        entities = [
            PawControlDoNotDisturbSwitch(coord, f"dog{i}", f"Dog{i}") for i in range(20)
        ]
        batches_added: list[int] = []

        async def fake_callback(_callback, entities_arg, **kwargs) -> None:
            batches_added.append(len(entities_arg))

        from unittest.mock import patch

        with patch(
            "custom_components.pawcontrol.switch.async_call_add_entities",
            side_effect=fake_callback,
        ):
            await _async_add_entities_in_batches(
                AsyncMock(), entities, batch_size=15, delay_between_batches=0
            )

        assert batches_added == [15, 5]


class TestSwitchSetupAndReproduction:
    """Coverage for setup and reproduce-state helper flows."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_returns_when_runtime_data_missing(self) -> None:  # noqa: D102
        from unittest.mock import patch

        hass = MagicMock()
        entry = MagicMock()

        with (
            patch(
                "custom_components.pawcontrol.switch.get_runtime_data",
                return_value=None,
            ),
            patch(
                "custom_components.pawcontrol.switch._async_add_entities_in_batches",
                new=AsyncMock(),
            ) as mock_add,
        ):
            await async_setup_entry(hass, entry, AsyncMock())

        mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_setup_entry_builds_entities_and_batches(self) -> None:  # noqa: D102
        from unittest.mock import patch

        coordinator = _make_coordinator()
        runtime_data = MagicMock()
        runtime_data.coordinator = coordinator
        runtime_data.dogs = [
            {
                DOG_ID_FIELD: "rex",
                DOG_NAME_FIELD: "Rex",
                DOG_MODULES_FIELD: _full_modules(
                    walk=False,
                    gps=False,
                    health=False,
                    notifications=False,
                    grooming=False,
                    medication=False,
                    training=False,
                    visitor=False,
                ),
            }
        ]

        with (
            patch(
                "custom_components.pawcontrol.switch.get_runtime_data",
                return_value=runtime_data,
            ),
            patch(
                "custom_components.pawcontrol.switch._async_add_entities_in_batches",
                new=AsyncMock(),
            ) as mock_add,
        ):
            await async_setup_entry(MagicMock(), MagicMock(), AsyncMock())

        assert mock_add.await_count == 1
        entities = mock_add.await_args.args[1]
        assert len(entities) == 8

    @pytest.mark.asyncio
    async def test_async_reproduce_state_delegates_to_platform_helper(self) -> None:  # noqa: D102
        from unittest.mock import patch

        hass = MagicMock()
        states = [MagicMock()]
        with patch(
            "custom_components.pawcontrol.switch.async_reproduce_platform_states",
            new=AsyncMock(),
        ) as reproduce:
            await async_reproduce_state(hass, states, context=None)

        reproduce.assert_awaited_once()

    def test_preprocess_switch_state_rejects_invalid(self) -> None:  # noqa: D102
        invalid_state = MagicMock(state="invalid", entity_id="switch.test")
        assert _preprocess_switch_state(invalid_state) is None

    def test_preprocess_switch_state_accepts_on_off(self) -> None:  # noqa: D102
        on_state = MagicMock(state="on")
        off_state = MagicMock(state="off")
        assert _preprocess_switch_state(on_state) == "on"
        assert _preprocess_switch_state(off_state) == "off"

    @pytest.mark.asyncio
    async def test_async_reproduce_switch_state_skips_when_no_change(self) -> None:  # noqa: D102
        hass = MagicMock()
        hass.services.async_call = AsyncMock()
        current = MagicMock(state="on")
        target = MagicMock(entity_id="switch.test")

        await _async_reproduce_switch_state(
            hass,
            target,
            current,
            "on",
            None,
        )

        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_reproduce_switch_state_calls_turn_off_service(self) -> None:  # noqa: D102
        hass = MagicMock()
        hass.services.async_call = AsyncMock()
        current = MagicMock(state="on")
        target = MagicMock(entity_id="switch.test")
        context = object()

        await _async_reproduce_switch_state(
            hass,
            target,
            current,
            "off",
            context,
        )

        hass.services.async_call.assert_awaited_once()
        called_service = hass.services.async_call.await_args.args[1]
        assert called_service == "turn_off"


class TestModuleSwitchUpdates:
    """Coverage for module switch config mutation branch."""

    def test_module_switch_init_without_hass_config(self) -> None:  # noqa: D102
        coordinator = _make_coordinator()
        coordinator.hass = None

        switch = PawControlModuleSwitch(
            coordinator,
            "rex",
            "Rex",
            "feeding",
            "Feeding Tracking",
            "mdi:food-drumstick",
            True,
        )

        assert switch._module_name == "Feeding Tracking"

    @pytest.mark.asyncio
    async def test_module_switch_updates_dog_modules_in_config_entry(self) -> None:  # noqa: D102
        coordinator = _make_coordinator()
        coordinator.config_entry = MagicMock()
        coordinator.config_entry.data = {
            "dogs": [
                {
                    DOG_ID_FIELD: "rex",
                    DOG_NAME_FIELD: "Rex",
                    DOG_MODULES_FIELD: {"feeding": False, "walk": True},
                }
            ]
        }
        coordinator.async_request_selective_refresh = AsyncMock()
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        switch = PawControlModuleSwitch(
            coordinator,
            "rex",
            "Rex",
            "feeding",
            "Feeding Tracking",
            "mdi:food-drumstick",
            False,
        )
        switch.hass = hass
        await switch._async_set_state(True)

        hass.config_entries.async_update_entry.assert_called_once()
        new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
        updated_modules = new_data["dogs"][0][DOG_MODULES_FIELD]
        assert updated_modules["feeding"] is True

    @pytest.mark.asyncio
    async def test_module_switch_set_state_returns_when_hass_missing(self) -> None:  # noqa: D102
        coordinator = _make_coordinator()
        coordinator.async_request_selective_refresh = AsyncMock()
        switch = PawControlModuleSwitch(
            coordinator,
            "rex",
            "Rex",
            "feeding",
            "Feeding Tracking",
            "mdi:food-drumstick",
            False,
        )
        switch.hass = None

        await switch._async_set_state(True)

        coordinator.async_request_selective_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_module_switch_set_state_skips_non_dict_and_other_dogs(self) -> None:  # noqa: D102
        coordinator = _make_coordinator()
        coordinator.config_entry = MagicMock()
        coordinator.config_entry.data = {
            "dogs": [
                "not-a-dict",
                {DOG_ID_FIELD: "other", DOG_MODULES_FIELD: {"feeding": False}},
            ]
        }
        coordinator.async_request_selective_refresh = AsyncMock()
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        switch = PawControlModuleSwitch(
            coordinator,
            "rex",
            "Rex",
            "feeding",
            "Feeding Tracking",
            "mdi:food-drumstick",
            False,
        )
        switch.hass = hass
        await switch._async_set_state(True)

        hass.config_entries.async_update_entry.assert_called_once()
        coordinator.async_request_selective_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_module_switch_set_state_swallows_update_exception(self) -> None:  # noqa: D102
        coordinator = _make_coordinator()
        coordinator.config_entry = MagicMock()
        coordinator.config_entry.data = {"dogs": []}
        coordinator.async_request_selective_refresh = AsyncMock()
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock(
            side_effect=RuntimeError("boom")
        )

        switch = PawControlModuleSwitch(
            coordinator,
            "rex",
            "Rex",
            "feeding",
            "Feeding Tracking",
            "mdi:food-drumstick",
            True,
        )
        switch.hass = hass

        await switch._async_set_state(False)
