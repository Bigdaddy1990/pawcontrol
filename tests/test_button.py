"""Comprehensive tests for PawControl button platform with profile optimization."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.button import (
    BUTTON_PRIORITIES,
    PROFILE_BUTTON_LIMITS,
    PawControlButtonBase,
    PawControlCallDogButton,
    PawControlCenterMapButton,
    PawControlEndWalkButton,
    PawControlExportRouteButton,
    PawControlFeedMealButton,
    PawControlHealthCheckButton,
    PawControlLogCustomFeedingButton,
    PawControlLogMedicationButton,
    PawControlLogWalkManuallyButton,
    PawControlLogWeightButton,
    PawControlMarkFedButton,
    PawControlQuickWalkButton,
    PawControlRefreshLocationButton,
    PawControlResetDailyStatsButton,
    PawControlScheduleVetButton,
    PawControlStartGroomingButton,
    PawControlStartWalkButton,
    PawControlTestNotificationButton,
    PawControlToggleVisitorModeButton,
    ProfileAwareButtonFactory,
    async_setup_entry,
)
from custom_components.pawcontrol.const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    SERVICE_END_WALK,
    SERVICE_FEED_DOG,
    SERVICE_LOG_HEALTH,
    SERVICE_NOTIFY_TEST,
    SERVICE_START_GROOMING,
    SERVICE_START_WALK,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.exceptions import (
    WalkAlreadyInProgressError,
    WalkNotInProgressError,
)
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import ButtonDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util


class TestProfileAwareButtonFactory:
    """Test the ProfileAwareButtonFactory class."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock(
            return_value={
                "feeding": {"last_feeding": "2023-01-01T12:00:00"},
                "walk": {"walk_in_progress": False, "last_walk": "2023-01-01T10:00:00"},
                "gps": {"zone": "home", "source": "gps_tracker"},
                "health": {"health_status": "good"},
                "visitor_mode_active": False,
            }
        )
        coordinator.config_entry = Mock()
        coordinator.config_entry.entry_id = "test_entry"
        return coordinator

    @pytest.fixture
    def button_factory_basic(self, mock_coordinator):
        """Create a basic profile button factory."""
        return ProfileAwareButtonFactory(mock_coordinator, "basic")

    @pytest.fixture
    def button_factory_standard(self, mock_coordinator):
        """Create a standard profile button factory."""
        return ProfileAwareButtonFactory(mock_coordinator, "standard")

    @pytest.fixture
    def button_factory_advanced(self, mock_coordinator):
        """Create an advanced profile button factory."""
        return ProfileAwareButtonFactory(mock_coordinator, "advanced")

    def test_factory_initialization(self, mock_coordinator):
        """Test factory initialization with different profiles."""
        # Test basic profile
        factory_basic = ProfileAwareButtonFactory(mock_coordinator, "basic")
        assert factory_basic.profile == "basic"
        assert factory_basic.max_buttons == PROFILE_BUTTON_LIMITS["basic"]
        assert factory_basic.coordinator == mock_coordinator

        # Test unknown profile falls back to 6
        factory_unknown = ProfileAwareButtonFactory(mock_coordinator, "unknown")
        assert factory_unknown.profile == "unknown"
        assert factory_unknown.max_buttons == 6

    def test_create_buttons_for_dog_basic_profile(self, button_factory_basic):
        """Test button creation for basic profile."""
        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: False,
            MODULE_HEALTH: False,
        }

        buttons = button_factory_basic.create_buttons_for_dog(
            "test_dog", "Test Dog", modules
        )

        # Basic profile should limit to 3 buttons
        assert len(buttons) == 3
        assert len(buttons) <= PROFILE_BUTTON_LIMITS["basic"]

        # Should include core buttons
        button_types = [type(button).__name__ for button in buttons]
        assert any("TestNotification" in name for name in button_types)
        assert any("ResetDailyStats" in name for name in button_types)

    def test_create_buttons_for_dog_standard_profile(self, button_factory_standard):
        """Test button creation for standard profile."""
        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
        }

        buttons = button_factory_standard.create_buttons_for_dog(
            "test_dog", "Test Dog", modules
        )

        # Standard profile should allow more buttons
        assert len(buttons) > 3
        assert len(buttons) <= PROFILE_BUTTON_LIMITS["standard"]

        # Should include module-specific buttons
        button_types = [type(button).__name__ for button in buttons]
        assert any("MarkFed" in name for name in button_types)
        assert any("StartWalk" in name for name in button_types)

    def test_create_buttons_for_dog_advanced_profile(self, button_factory_advanced):
        """Test button creation for advanced profile."""
        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
        }

        buttons = button_factory_advanced.create_buttons_for_dog(
            "test_dog", "Test Dog", modules
        )

        # Advanced profile should allow most buttons
        assert len(buttons) > 6
        assert len(buttons) <= PROFILE_BUTTON_LIMITS["advanced"]

        # Should include advanced buttons
        button_types = [type(button).__name__ for button in buttons]
        assert any("LogCustomFeeding" in name for name in button_types)
        assert any("ToggleVisitorMode" in name for name in button_types)

    def test_create_buttons_no_modules(self, button_factory_standard):
        """Test button creation with no modules enabled."""
        modules = {
            MODULE_FEEDING: False,
            MODULE_WALK: False,
            MODULE_GPS: False,
            MODULE_HEALTH: False,
        }

        buttons = button_factory_standard.create_buttons_for_dog(
            "test_dog", "Test Dog", modules
        )

        # Should still create core buttons
        assert len(buttons) >= 2  # At least core buttons
        button_types = [type(button).__name__ for button in buttons]
        assert any("TestNotification" in name for name in button_types)
        assert any("ResetDailyStats" in name for name in button_types)

    def test_create_feeding_buttons(self, button_factory_advanced):
        """Test feeding button creation."""
        feeding_buttons = button_factory_advanced._create_feeding_buttons(
            "test_dog", "Test Dog"
        )

        # Advanced profile should create multiple feeding buttons
        assert len(feeding_buttons) > 1

        # Check priority assignment
        for button_info in feeding_buttons:
            assert "button" in button_info
            assert "type" in button_info
            assert "priority" in button_info
            assert button_info["priority"] in BUTTON_PRIORITIES.values()

    def test_create_walk_buttons(self, button_factory_standard):
        """Test walk button creation."""
        walk_buttons = button_factory_standard._create_walk_buttons(
            "test_dog", "Test Dog"
        )

        # Should create essential walk buttons
        assert len(walk_buttons) >= 2  # start_walk, end_walk

        button_types = [info["type"] for info in walk_buttons]
        assert "start_walk" in button_types
        assert "end_walk" in button_types

    def test_create_gps_buttons(self, button_factory_advanced):
        """Test GPS button creation."""
        gps_buttons = button_factory_advanced._create_gps_buttons(
            "test_dog", "Test Dog"
        )

        # Advanced profile should create multiple GPS buttons
        assert len(gps_buttons) > 1

        button_types = [info["type"] for info in gps_buttons]
        assert "refresh_location" in button_types

    def test_create_health_buttons(self, button_factory_advanced):
        """Test health button creation."""
        health_buttons = button_factory_advanced._create_health_buttons(
            "test_dog", "Test Dog"
        )

        # Advanced profile should create multiple health buttons
        assert len(health_buttons) > 1

        button_types = [info["type"] for info in health_buttons]
        assert "log_weight" in button_types

    def test_priority_sorting(self, button_factory_advanced):
        """Test that buttons are sorted by priority."""
        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
        }

        # Mock to create many buttons for testing sorting
        with patch.object(
            button_factory_advanced, "max_buttons", 20
        ):  # Allow more buttons
            buttons = button_factory_advanced.create_buttons_for_dog(
                "test_dog", "Test Dog", modules
            )

        # Should have buttons (limited by mock max_buttons)
        assert len(buttons) > 5

    def test_profile_button_limit_enforcement(self, button_factory_basic):
        """Test that profile limits are enforced."""
        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
        }

        buttons = button_factory_basic.create_buttons_for_dog(
            "test_dog", "Test Dog", modules
        )

        # Should not exceed basic profile limit
        assert len(buttons) <= PROFILE_BUTTON_LIMITS["basic"]


class TestAsyncSetupEntry:
    """Test the async_setup_entry function."""

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "test_dog",
                    CONF_DOG_NAME: "Test Dog",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: False,
                        MODULE_HEALTH: False,
                    },
                }
            ]
        }
        entry.options = {"entity_profile": "standard"}
        return entry

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock(
            return_value={
                "feeding": {},
                "walk": {},
                "gps": {},
                "health": {},
            }
        )
        return coordinator

    @pytest.fixture
    def mock_runtime_data(self, mock_coordinator):
        """Create mock runtime data."""
        return {
            "coordinator": mock_coordinator,
            "dogs": [
                {
                    CONF_DOG_ID: "test_dog",
                    CONF_DOG_NAME: "Test Dog",
                    "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_runtime_data(
        self, hass: HomeAssistant, mock_config_entry, mock_runtime_data
    ):
        """Test setup entry with runtime data."""
        mock_config_entry.runtime_data = mock_runtime_data

        added_entities = []

        def mock_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should create entities
        assert len(added_entities) > 0

        # All entities should be button instances
        for entity in added_entities:
            assert isinstance(entity, PawControlButtonBase)

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_legacy_data(
        self, hass: HomeAssistant, mock_config_entry, mock_coordinator
    ):
        """Test setup entry with legacy data storage."""
        # No runtime_data, use legacy storage
        mock_config_entry.runtime_data = None
        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {"coordinator": mock_coordinator}
        }

        added_entities = []

        def mock_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should create entities from legacy data
        assert len(added_entities) > 0

    @pytest.mark.asyncio
    async def test_async_setup_entry_no_dogs(
        self, hass: HomeAssistant, mock_config_entry, mock_runtime_data
    ):
        """Test setup entry with no dogs configured."""
        mock_runtime_data["dogs"] = []
        mock_config_entry.runtime_data = mock_runtime_data

        added_entities = []

        def mock_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should not create entities
        assert len(added_entities) == 0

    @pytest.mark.asyncio
    async def test_async_setup_entry_profile_integration(
        self, hass: HomeAssistant, mock_config_entry, mock_runtime_data
    ):
        """Test setup entry integrates profile correctly."""
        mock_config_entry.options = {"entity_profile": "basic"}
        mock_config_entry.runtime_data = mock_runtime_data

        added_entities = []

        def mock_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Basic profile should create fewer entities
        assert len(added_entities) <= PROFILE_BUTTON_LIMITS["basic"]

    @pytest.mark.asyncio
    async def test_async_setup_entry_multiple_dogs(
        self, hass: HomeAssistant, mock_config_entry, mock_runtime_data
    ):
        """Test setup entry with multiple dogs."""
        mock_runtime_data["dogs"] = [
            {
                CONF_DOG_ID: "dog1",
                CONF_DOG_NAME: "Dog 1",
                "modules": {MODULE_FEEDING: True},
            },
            {
                CONF_DOG_ID: "dog2",
                CONF_DOG_NAME: "Dog 2",
                "modules": {MODULE_WALK: True},
            },
        ]
        mock_config_entry.runtime_data = mock_runtime_data

        added_entities = []

        def mock_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should create entities for both dogs
        assert len(added_entities) > 2

        # Check that entities exist for both dogs
        dog_ids = {entity._dog_id for entity in added_entities}
        assert "dog1" in dog_ids
        assert "dog2" in dog_ids

    @pytest.mark.asyncio
    async def test_async_setup_entry_batch_optimization(
        self, hass: HomeAssistant, mock_config_entry, mock_runtime_data
    ):
        """Test setup entry batch optimization for many entities."""
        # Create many dogs to trigger batching
        many_dogs = [
            {
                CONF_DOG_ID: f"dog{i}",
                CONF_DOG_NAME: f"Dog {i}",
                "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
            }
            for i in range(10)
        ]
        mock_runtime_data["dogs"] = many_dogs
        mock_config_entry.runtime_data = mock_runtime_data

        added_entities = []
        batch_calls = []

        def mock_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)
            batch_calls.append(len(entities))

        with patch("asyncio.gather") as mock_gather:
            await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should create many entities
        assert len(added_entities) > 20

        # For large setups, should use batching
        if len(added_entities) > 15:
            mock_gather.assert_called()


class TestPawControlButtonBase:
    """Test the base button class."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock(
            return_value={
                "feeding": {"last_feeding": "2023-01-01T12:00:00"},
                "walk": {"walk_in_progress": False},
            }
        )
        return coordinator

    @pytest.fixture
    def button_base(self, mock_coordinator):
        """Create a base button instance."""
        return PawControlButtonBase(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "test_button",
            icon="mdi:test",
        )

    def test_button_base_initialization(self, button_base):
        """Test base button initialization."""
        assert button_base._dog_id == "test_dog"
        assert button_base._dog_name == "Test Dog"
        assert button_base._button_type == "test_button"
        assert button_base._attr_unique_id == "pawcontrol_test_dog_test_button"
        assert button_base._attr_name == "Test Dog Test Button"
        assert button_base._attr_icon == "mdi:test"

    def test_button_base_device_info(self, button_base):
        """Test device info generation."""
        device_info = button_base._attr_device_info

        assert device_info["identifiers"] == {(DOMAIN, "test_dog")}
        assert device_info["name"] == "Test Dog"
        assert device_info["manufacturer"] == "Paw Control"
        assert device_info["model"] == "Smart Dog Monitoring"

    def test_extra_state_attributes(self, button_base):
        """Test extra state attributes."""
        attrs = button_base.extra_state_attributes

        assert attrs[ATTR_DOG_ID] == "test_dog"
        assert attrs[ATTR_DOG_NAME] == "Test Dog"
        assert attrs["button_type"] == "test_button"

    def test_get_dog_data_cached(self, button_base, mock_coordinator):
        """Test cached dog data retrieval."""
        # First call should fetch from coordinator
        data = button_base._get_dog_data_cached()
        assert data is not None
        mock_coordinator.get_dog_data.assert_called_with("test_dog")

        # Second call within cache TTL should use cache
        mock_coordinator.get_dog_data.reset_mock()
        data2 = button_base._get_dog_data_cached()
        assert data2 == data
        # Should not call coordinator again due to caching
        mock_coordinator.get_dog_data.assert_not_called()

    def test_get_module_data(self, button_base):
        """Test module data retrieval."""
        feeding_data = button_base._get_module_data("feeding")
        assert feeding_data == {"last_feeding": "2023-01-01T12:00:00"}

        walk_data = button_base._get_module_data("walk")
        assert walk_data == {"walk_in_progress": False}

        # Non-existent module
        nonexistent_data = button_base._get_module_data("nonexistent")
        assert nonexistent_data == {}

    def test_available_property(self, button_base, mock_coordinator):
        """Test availability property."""
        # Should be available when coordinator is available and has data
        assert button_base.available is True

        # Should be unavailable when coordinator is unavailable
        mock_coordinator.available = False
        assert button_base.available is False

        # Should be unavailable when no dog data
        mock_coordinator.available = True
        mock_coordinator.get_dog_data.return_value = None
        # Clear cache to force refresh
        button_base._dog_data_cache.clear()
        assert button_base.available is False

    @pytest.mark.asyncio
    async def test_async_press_base(self, button_base):
        """Test base async_press method."""
        await button_base.async_press()

        # Should set last_pressed timestamp
        assert hasattr(button_base, "_last_pressed")
        assert button_base._last_pressed is not None

    def test_cache_cleanup(self, button_base):
        """Test cache cleanup after TTL."""
        # Get data to populate cache
        button_base._get_dog_data_cached()

        # Manually expire cache by manipulating timestamp
        cache_key = f"{button_base._dog_id}_data"
        if cache_key in button_base._dog_data_cache:
            cached_data, _ = button_base._dog_data_cache[cache_key]
            # Set old timestamp
            button_base._dog_data_cache[cache_key] = (
                cached_data,
                dt_util.utcnow().timestamp() - 10,  # 10 seconds ago
            )

        # Should fetch fresh data
        data2 = button_base._get_dog_data_cached()
        assert data2 is not None


class TestSpecificButtonClasses:
    """Test specific button implementations."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock(
            return_value={
                "feeding": {"last_feeding": "2023-01-01T12:00:00"},
                "walk": {"walk_in_progress": False, "last_walk": "2023-01-01T10:00:00"},
                "gps": {"zone": "home", "source": "gps_tracker"},
                "health": {"health_status": "good"},
                "visitor_mode_active": False,
            }
        )
        coordinator.config_entry = Mock()
        coordinator.config_entry.entry_id = "test_entry"
        return coordinator

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock()
        hass.data = {
            DOMAIN: {
                "test_entry": {
                    "data": Mock(),
                }
            }
        }
        return hass

    def test_test_notification_button(self, mock_coordinator):
        """Test notification button initialization."""
        button = PawControlTestNotificationButton(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert button._button_type == "test_notification"
        assert button._attr_icon == "mdi:message-alert"
        assert button._action_description == "Send a test notification"

    @pytest.mark.asyncio
    async def test_test_notification_button_press(self, mock_coordinator, mock_hass):
        """Test notification button press."""
        button = PawControlTestNotificationButton(
            mock_coordinator, "test_dog", "Test Dog"
        )
        button.hass = mock_hass

        await button.async_press()

        # Should call notification service
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            SERVICE_NOTIFY_TEST,
            {
                ATTR_DOG_ID: "test_dog",
                "message": "Test notification for Test Dog",
            },
            blocking=False,
        )

    @pytest.mark.asyncio
    async def test_test_notification_button_press_error(
        self, mock_coordinator, mock_hass
    ):
        """Test notification button press with service error."""
        button = PawControlTestNotificationButton(
            mock_coordinator, "test_dog", "Test Dog"
        )
        button.hass = mock_hass

        mock_hass.services.async_call.side_effect = Exception("Service failed")

        with pytest.raises(HomeAssistantError, match="Failed to send notification"):
            await button.async_press()

    def test_reset_daily_stats_button(self, mock_coordinator):
        """Test reset daily stats button initialization."""
        button = PawControlResetDailyStatsButton(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert button._button_type == "reset_daily_stats"
        assert button._attr_device_class == ButtonDeviceClass.RESTART
        assert button._attr_icon == "mdi:refresh"

    @pytest.mark.asyncio
    async def test_reset_daily_stats_button_press(self, mock_coordinator, mock_hass):
        """Test reset daily stats button press."""
        button = PawControlResetDailyStatsButton(
            mock_coordinator, "test_dog", "Test Dog"
        )
        button.hass = mock_hass

        # Mock the data manager
        data_manager = AsyncMock()
        mock_hass.data[DOMAIN]["test_entry"]["data"] = data_manager

        # Mock coordinator refresh
        mock_coordinator.async_request_selective_refresh = AsyncMock()

        await button.async_press()

        # Should reset stats and refresh coordinator
        data_manager.async_reset_dog_daily_stats.assert_called_once_with("test_dog")
        mock_coordinator.async_request_selective_refresh.assert_called_once_with(
            ["test_dog"], priority=8
        )

    @pytest.mark.asyncio
    async def test_reset_daily_stats_button_press_no_data_manager(
        self, mock_coordinator, mock_hass
    ):
        """Test reset daily stats button press without data manager."""
        button = PawControlResetDailyStatsButton(
            mock_coordinator, "test_dog", "Test Dog"
        )
        button.hass = mock_hass

        # No data manager available
        mock_hass.data[DOMAIN]["test_entry"]["data"] = None

        with pytest.raises(HomeAssistantError, match="Data manager not available"):
            await button.async_press()

    def test_toggle_visitor_mode_button(self, mock_coordinator):
        """Test toggle visitor mode button initialization."""
        button = PawControlToggleVisitorModeButton(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert button._button_type == "toggle_visitor_mode"
        assert button._attr_icon == "mdi:account-switch"

    @pytest.mark.asyncio
    async def test_toggle_visitor_mode_button_press(self, mock_coordinator, mock_hass):
        """Test toggle visitor mode button press."""
        button = PawControlToggleVisitorModeButton(
            mock_coordinator, "test_dog", "Test Dog"
        )
        button.hass = mock_hass

        await button.async_press()

        # Should call set_visitor_mode service
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            "set_visitor_mode",
            {
                ATTR_DOG_ID: "test_dog",
                "enabled": True,  # Current mode is False, so should toggle to True
                "visitor_name": "Manual Toggle",
            },
            blocking=False,
        )

    def test_mark_fed_button(self, mock_coordinator):
        """Test mark fed button initialization."""
        button = PawControlMarkFedButton(mock_coordinator, "test_dog", "Test Dog")

        assert button._button_type == "mark_fed"
        assert button._attr_icon == "mdi:food-drumstick"

    @pytest.mark.asyncio
    async def test_mark_fed_button_press_morning(self, mock_coordinator, mock_hass):
        """Test mark fed button press in morning."""
        button = PawControlMarkFedButton(mock_coordinator, "test_dog", "Test Dog")
        button.hass = mock_hass

        # Mock time to morning
        with patch("custom_components.pawcontrol.button.dt_util.now") as mock_now:
            mock_now.return_value = datetime(2023, 1, 1, 8, 0)  # 8 AM

            await button.async_press()

        # Should call feed service with breakfast
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            SERVICE_FEED_DOG,
            {
                ATTR_DOG_ID: "test_dog",
                "meal_type": "breakfast",
                "portion_size": 0,
            },
            blocking=False,
        )

    @pytest.mark.asyncio
    async def test_mark_fed_button_press_evening(self, mock_coordinator, mock_hass):
        """Test mark fed button press in evening."""
        button = PawControlMarkFedButton(mock_coordinator, "test_dog", "Test Dog")
        button.hass = mock_hass

        # Mock time to evening
        with patch("custom_components.pawcontrol.button.dt_util.now") as mock_now:
            mock_now.return_value = datetime(2023, 1, 1, 18, 0)  # 6 PM

            await button.async_press()

        # Should call feed service with dinner
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            SERVICE_FEED_DOG,
            {
                ATTR_DOG_ID: "test_dog",
                "meal_type": "dinner",
                "portion_size": 0,
            },
            blocking=False,
        )

    def test_feed_meal_button(self, mock_coordinator):
        """Test feed meal button initialization."""
        button = PawControlFeedMealButton(
            mock_coordinator, "test_dog", "Test Dog", "breakfast"
        )

        assert button._button_type == "feed_breakfast"
        assert button._meal_type == "breakfast"
        assert button._attr_name == "Test Dog Feed Breakfast"

    @pytest.mark.asyncio
    async def test_feed_meal_button_press(self, mock_coordinator, mock_hass):
        """Test feed meal button press."""
        button = PawControlFeedMealButton(
            mock_coordinator, "test_dog", "Test Dog", "lunch"
        )
        button.hass = mock_hass

        await button.async_press()

        # Should call feed service with specific meal type
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            SERVICE_FEED_DOG,
            {
                ATTR_DOG_ID: "test_dog",
                "meal_type": "lunch",
                "portion_size": 0,
            },
            blocking=False,
        )

    def test_start_walk_button(self, mock_coordinator):
        """Test start walk button initialization."""
        button = PawControlStartWalkButton(mock_coordinator, "test_dog", "Test Dog")

        assert button._button_type == "start_walk"
        assert button._attr_icon == "mdi:walk"

    def test_start_walk_button_availability(self, mock_coordinator):
        """Test start walk button availability."""
        button = PawControlStartWalkButton(mock_coordinator, "test_dog", "Test Dog")

        # Should be available when no walk in progress
        assert button.available is True

        # Should be unavailable when walk in progress
        mock_coordinator.get_dog_data.return_value = {
            "walk": {"walk_in_progress": True}
        }
        button._dog_data_cache.clear()  # Clear cache
        assert button.available is False

    @pytest.mark.asyncio
    async def test_start_walk_button_press(self, mock_coordinator, mock_hass):
        """Test start walk button press."""
        button = PawControlStartWalkButton(mock_coordinator, "test_dog", "Test Dog")
        button.hass = mock_hass

        await button.async_press()

        # Should call start walk service
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            SERVICE_START_WALK,
            {
                ATTR_DOG_ID: "test_dog",
                "label": "Manual walk",
            },
            blocking=False,
        )

    @pytest.mark.asyncio
    async def test_start_walk_button_press_already_in_progress(
        self, mock_coordinator, mock_hass
    ):
        """Test start walk button press when walk already in progress."""
        # Mock walk in progress
        mock_coordinator.get_dog_data.return_value = {
            "walk": {
                "walk_in_progress": True,
                "current_walk_id": "walk_123",
                "current_walk_start": "2023-01-01T10:00:00",
            }
        }

        button = PawControlStartWalkButton(mock_coordinator, "test_dog", "Test Dog")
        button.hass = mock_hass

        with pytest.raises(HomeAssistantError):
            await button.async_press()

    def test_end_walk_button(self, mock_coordinator):
        """Test end walk button initialization."""
        button = PawControlEndWalkButton(mock_coordinator, "test_dog", "Test Dog")

        assert button._button_type == "end_walk"
        assert button._attr_icon == "mdi:stop"

    def test_end_walk_button_availability(self, mock_coordinator):
        """Test end walk button availability."""
        button = PawControlEndWalkButton(mock_coordinator, "test_dog", "Test Dog")

        # Should be unavailable when no walk in progress
        assert button.available is False

        # Should be available when walk in progress
        mock_coordinator.get_dog_data.return_value = {
            "walk": {"walk_in_progress": True}
        }
        button._dog_data_cache.clear()  # Clear cache
        assert button.available is True

    @pytest.mark.asyncio
    async def test_end_walk_button_press(self, mock_coordinator, mock_hass):
        """Test end walk button press."""
        # Mock walk in progress
        mock_coordinator.get_dog_data.return_value = {
            "walk": {"walk_in_progress": True}
        }

        button = PawControlEndWalkButton(mock_coordinator, "test_dog", "Test Dog")
        button.hass = mock_hass

        await button.async_press()

        # Should call end walk service
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            SERVICE_END_WALK,
            {ATTR_DOG_ID: "test_dog"},
            blocking=False,
        )

    @pytest.mark.asyncio
    async def test_end_walk_button_press_no_walk_in_progress(
        self, mock_coordinator, mock_hass
    ):
        """Test end walk button press when no walk in progress."""
        button = PawControlEndWalkButton(mock_coordinator, "test_dog", "Test Dog")
        button.hass = mock_hass

        with pytest.raises(HomeAssistantError):
            await button.async_press()

    @pytest.mark.asyncio
    async def test_quick_walk_button_press(self, mock_coordinator, mock_hass):
        """Test quick walk button press."""
        button = PawControlQuickWalkButton(mock_coordinator, "test_dog", "Test Dog")
        button.hass = mock_hass

        await button.async_press()

        # Should call both start and end walk services
        assert mock_hass.services.async_call.call_count == 2

        # Check first call (start walk)
        start_call = mock_hass.services.async_call.call_args_list[0]
        assert start_call[0] == (DOMAIN, SERVICE_START_WALK)
        assert start_call[1]["data"][ATTR_DOG_ID] == "test_dog"
        assert start_call[1]["blocking"] is True

        # Check second call (end walk)
        end_call = mock_hass.services.async_call.call_args_list[1]
        assert end_call[0] == (DOMAIN, SERVICE_END_WALK)
        assert end_call[1]["data"]["duration"] == 10
        assert end_call[1]["data"]["distance"] == 800

    def test_refresh_location_button(self, mock_coordinator):
        """Test refresh location button initialization."""
        button = PawControlRefreshLocationButton(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert button._button_type == "refresh_location"
        assert button._attr_device_class == ButtonDeviceClass.UPDATE
        assert button._attr_icon == "mdi:crosshairs-gps"

    @pytest.mark.asyncio
    async def test_refresh_location_button_press(self, mock_coordinator):
        """Test refresh location button press."""
        button = PawControlRefreshLocationButton(
            mock_coordinator, "test_dog", "Test Dog"
        )

        mock_coordinator.async_request_selective_refresh = AsyncMock()

        await button.async_press()

        # Should request selective refresh
        mock_coordinator.async_request_selective_refresh.assert_called_once_with(
            ["test_dog"], priority=9
        )

    @pytest.mark.asyncio
    async def test_call_dog_button_press(self, mock_coordinator):
        """Test call dog button press."""
        button = PawControlCallDogButton(mock_coordinator, "test_dog", "Test Dog")

        await button.async_press()
        # Should complete without error when GPS tracker available

    @pytest.mark.asyncio
    async def test_call_dog_button_press_no_gps(self, mock_coordinator):
        """Test call dog button press without GPS tracker."""
        # Mock no GPS data
        mock_coordinator.get_dog_data.return_value = {"gps": {"source": "none"}}

        button = PawControlCallDogButton(mock_coordinator, "test_dog", "Test Dog")

        with pytest.raises(HomeAssistantError, match="GPS tracker not available"):
            await button.async_press()

    @pytest.mark.asyncio
    async def test_log_weight_button_press(self, mock_coordinator, mock_hass):
        """Test log weight button press."""
        button = PawControlLogWeightButton(mock_coordinator, "test_dog", "Test Dog")
        button.hass = mock_hass

        await button.async_press()

        # Should call log health service
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            SERVICE_LOG_HEALTH,
            {
                ATTR_DOG_ID: "test_dog",
                "note": "Weight logged via button",
            },
            blocking=False,
        )

    @pytest.mark.asyncio
    async def test_start_grooming_button_press(self, mock_coordinator, mock_hass):
        """Test start grooming button press."""
        button = PawControlStartGroomingButton(mock_coordinator, "test_dog", "Test Dog")
        button.hass = mock_hass

        await button.async_press()

        # Should call start grooming service
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            SERVICE_START_GROOMING,
            {
                ATTR_DOG_ID: "test_dog",
                "type": "general",
                "notes": "Started via button",
            },
            blocking=False,
        )


class TestButtonProfiles:
    """Test button profile configurations."""

    def test_profile_button_limits_exist(self):
        """Test that all profile button limits are defined."""
        expected_profiles = [
            "basic",
            "standard",
            "advanced",
            "gps_focus",
            "health_focus",
        ]

        for profile in expected_profiles:
            assert profile in PROFILE_BUTTON_LIMITS
            assert PROFILE_BUTTON_LIMITS[profile] > 0

    def test_profile_button_limits_progression(self):
        """Test that profile limits show logical progression."""
        basic_limit = PROFILE_BUTTON_LIMITS["basic"]
        standard_limit = PROFILE_BUTTON_LIMITS["standard"]
        advanced_limit = PROFILE_BUTTON_LIMITS["advanced"]

        # Should show progression: basic < standard < advanced
        assert basic_limit < standard_limit < advanced_limit

        # Limits should be reasonable
        assert 1 <= basic_limit <= 5
        assert 4 <= standard_limit <= 10
        assert 8 <= advanced_limit <= 20

    def test_button_priorities_exist(self):
        """Test that button priorities are defined for all button types."""
        # Core buttons should have priority 1
        assert BUTTON_PRIORITIES["test_notification"] == 1
        assert BUTTON_PRIORITIES["reset_daily_stats"] == 1

        # Essential buttons should have priority 2
        assert BUTTON_PRIORITIES["mark_fed"] == 2
        assert BUTTON_PRIORITIES["start_walk"] == 2

        # All priority values should be in range 1-4
        for priority in BUTTON_PRIORITIES.values():
            assert 1 <= priority <= 4

    def test_button_priorities_completeness(self):
        """Test that priorities exist for all expected button types."""
        expected_button_types = [
            "test_notification",
            "reset_daily_stats",
            "mark_fed",
            "start_walk",
            "end_walk",
            "refresh_location",
            "log_weight",
            "feed_breakfast",
            "feed_dinner",
            "quick_walk",
            "log_medication",
        ]

        for button_type in expected_button_types:
            assert button_type in BUTTON_PRIORITIES


class TestButtonErrorHandling:
    """Test button error handling and edge cases."""

    @pytest.fixture
    def mock_coordinator_unavailable(self):
        """Create an unavailable coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = False
        coordinator.get_dog_data = Mock(return_value=None)
        return coordinator

    def test_button_unavailable_coordinator(self, mock_coordinator_unavailable):
        """Test button behavior with unavailable coordinator."""
        button = PawControlTestNotificationButton(
            mock_coordinator_unavailable, "test_dog", "Test Dog"
        )

        # Should be unavailable
        assert button.available is False

    @pytest.mark.asyncio
    async def test_button_service_call_error_handling(self, mock_coordinator):
        """Test button service call error handling."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock(side_effect=Exception("Service error"))

        button = PawControlTestNotificationButton(
            mock_coordinator, "test_dog", "Test Dog"
        )
        button.hass = hass

        with pytest.raises(HomeAssistantError):
            await button.async_press()

    def test_button_missing_dog_data(self, mock_coordinator):
        """Test button behavior when dog data is missing."""
        mock_coordinator.get_dog_data.return_value = None

        button = PawControlMarkFedButton(mock_coordinator, "test_dog", "Test Dog")

        # Should handle missing data gracefully
        module_data = button._get_module_data("feeding")
        assert module_data is None

    @pytest.mark.asyncio
    async def test_button_service_validation_error(self, mock_coordinator):
        """Test button handling of service validation errors."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock(
            side_effect=ServiceValidationError("Invalid service call")
        )

        button = PawControlStartWalkButton(mock_coordinator, "test_dog", "Test Dog")
        button.hass = hass

        with pytest.raises(HomeAssistantError):
            await button.async_press()

    def test_button_cache_edge_cases(self, mock_coordinator):
        """Test button caching edge cases."""
        button = PawControlMarkFedButton(mock_coordinator, "test_dog", "Test Dog")

        # Test cache with empty data
        mock_coordinator.get_dog_data.return_value = {}
        data = button._get_dog_data_cached()
        assert data == {}

        # Test cache with None data
        mock_coordinator.get_dog_data.return_value = None
        button._dog_data_cache.clear()
        data = button._get_dog_data_cached()
        assert data is None


class TestButtonIntegration:
    """Test button integration with other components."""

    @pytest.fixture
    def mock_hass_with_full_data(self):
        """Create a mock Home Assistant instance with full data."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock()

        # Mock data manager
        data_manager = AsyncMock()
        data_manager.async_reset_dog_daily_stats = AsyncMock()

        hass.data = {
            DOMAIN: {
                "test_entry": {
                    "data": data_manager,
                    "coordinator": Mock(),
                }
            }
        }
        return hass

    @pytest.mark.asyncio
    async def test_button_coordinator_integration(self, mock_coordinator):
        """Test button integration with coordinator."""
        mock_coordinator.async_request_selective_refresh = AsyncMock()

        button = PawControlRefreshLocationButton(
            mock_coordinator, "test_dog", "Test Dog"
        )

        await button.async_press()

        # Should request refresh from coordinator
        mock_coordinator.async_request_selective_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_button_data_manager_integration(
        self, mock_coordinator, mock_hass_with_full_data
    ):
        """Test button integration with data manager."""
        button = PawControlResetDailyStatsButton(
            mock_coordinator, "test_dog", "Test Dog"
        )
        button.hass = mock_hass_with_full_data

        # Mock coordinator refresh
        mock_coordinator.async_request_selective_refresh = AsyncMock()

        await button.async_press()

        # Should call data manager
        data_manager = mock_hass_with_full_data.data[DOMAIN]["test_entry"]["data"]
        data_manager.async_reset_dog_daily_stats.assert_called_once_with("test_dog")
