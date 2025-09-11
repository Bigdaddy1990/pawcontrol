"""Tests for the Paw Control integration __init__ module."""
from __future__ import annotations

import asyncio
from datetime import datetime
from datetime import time
from unittest.mock import AsyncMock
from unittest.mock import call
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.exceptions import ServiceValidationError

from custom_components.pawcontrol import async_reload_entry
from custom_components.pawcontrol import async_setup
from custom_components.pawcontrol import async_setup_entry
from custom_components.pawcontrol import async_unload_entry
from custom_components.pawcontrol import get_platforms_for_profile_and_modules
from custom_components.pawcontrol import PawControlSetupError
from custom_components.pawcontrol.const import ATTR_DOG_ID
from custom_components.pawcontrol.const import ATTR_MEAL_TYPE
from custom_components.pawcontrol.const import ATTR_PORTION_SIZE
from custom_components.pawcontrol.const import CONF_DOG_ID
from custom_components.pawcontrol.const import CONF_DOG_NAME
from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.const import EVENT_FEEDING_LOGGED
from custom_components.pawcontrol.const import EVENT_WALK_ENDED
from custom_components.pawcontrol.const import EVENT_WALK_STARTED
from custom_components.pawcontrol.const import MODULE_DASHBOARD
from custom_components.pawcontrol.const import MODULE_FEEDING
from custom_components.pawcontrol.const import MODULE_GPS
from custom_components.pawcontrol.const import MODULE_HEALTH
from custom_components.pawcontrol.const import MODULE_NOTIFICATIONS
from custom_components.pawcontrol.const import MODULE_VISITOR
from custom_components.pawcontrol.const import MODULE_WALK
from custom_components.pawcontrol.const import PLATFORMS
from custom_components.pawcontrol.const import SERVICE_DAILY_RESET
from custom_components.pawcontrol.const import SERVICE_END_WALK
from custom_components.pawcontrol.const import SERVICE_FEED_DOG
from custom_components.pawcontrol.const import SERVICE_LOG_HEALTH
from custom_components.pawcontrol.const import SERVICE_START_WALK
from custom_components.pawcontrol.entity_factory import ENTITY_PROFILES
from custom_components.pawcontrol.exceptions import ConfigurationError
from custom_components.pawcontrol.exceptions import DogNotFoundError


class TestAsync_Setup:
    """Test the async_setup function."""

    @pytest.mark.asyncio
    async def test_async_setup_success(self, hass: HomeAssistant):
        """Test successful setup."""
        result = await async_setup(hass, {})

        assert result is True
        assert DOMAIN in hass.data
        assert hass.data[DOMAIN] == {}

    @pytest.mark.asyncio
    async def test_async_setup_with_config(self, hass: HomeAssistant):
        """Test setup with configuration."""
        config = {"some_config": "value"}
        result = await async_setup(hass, config)

        assert result is True
        assert DOMAIN in hass.data


class TestAsyncSetupEntry:
    """Test the async_setup_entry function."""

    @pytest.fixture
    def mock_coordinator(self):
        """Return a mock coordinator."""
        coordinator = Mock()
        coordinator.async_config_entry_first_refresh = AsyncMock()
        coordinator.async_shutdown = AsyncMock()
        coordinator.set_managers = Mock()
        coordinator.async_start_background_tasks = AsyncMock()
        return coordinator

    @pytest.fixture
    def mock_data_manager(self):
        """Return a mock data manager."""
        data_manager = AsyncMock()
        data_manager.async_initialize = AsyncMock()
        data_manager.async_shutdown = AsyncMock()
        return data_manager

    @pytest.fixture
    def mock_notification_manager(self):
        """Return a mock notification manager."""
        notification_manager = AsyncMock()
        notification_manager.async_initialize = AsyncMock()
        notification_manager.async_shutdown = AsyncMock()
        return notification_manager

    @pytest.fixture
    def mock_entity_factory(self):
        """Return a mock entity factory."""
        factory = Mock()
        factory.estimate_entity_count = Mock(return_value=12)
        factory.create_entities_for_dog = Mock(return_value=[])
        return factory

    @pytest.mark.asyncio
    async def test_setup_entry_success(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator,
        mock_data_manager,
        mock_notification_manager,
        mock_entity_factory,
    ):
        """Test successful entry setup."""
        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator",
                return_value=mock_coordinator,
            ),
            patch(
                "custom_components.pawcontrol.PawControlDataManager",
                return_value=mock_data_manager,
            ),
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager",
                return_value=mock_notification_manager,
            ),
            patch(
                "custom_components.pawcontrol.EntityFactory",
                return_value=mock_entity_factory,
            ),
            patch(
                "custom_components.pawcontrol.get_platforms_for_profile_and_modules",
                return_value=[Platform.SENSOR, Platform.BUTTON],
            ),
            patch.object(
                hass.config_entries, "async_forward_entry_setups", return_value=True
            ) as mock_forward,
        ):
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            mock_data_manager.async_initialize.assert_called_once()
            mock_notification_manager.async_initialize.assert_called_once()
            mock_coordinator.async_config_entry_first_refresh.assert_called_once()
            mock_forward.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_entry_profile_integration(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator,
        mock_data_manager,
        mock_notification_manager,
        mock_entity_factory,
    ):
        """Test setup entry with profile system integration."""
        # Set profile in options
        mock_config_entry.options = {"entity_profile": "basic"}

        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator",
                return_value=mock_coordinator,
            ),
            patch(
                "custom_components.pawcontrol.PawControlDataManager",
                return_value=mock_data_manager,
            ),
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager",
                return_value=mock_notification_manager,
            ),
            patch(
                "custom_components.pawcontrol.EntityFactory",
                return_value=mock_entity_factory,
            ),
            patch(
                "custom_components.pawcontrol.get_platforms_for_profile_and_modules",
                return_value=[Platform.SENSOR, Platform.BUTTON],
            ) as mock_get_platforms,
            patch.object(
                hass.config_entries, "async_forward_entry_setups", return_value=True
            ),
        ):
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True

            # Verify profile was passed to platform determination
            mock_get_platforms.assert_called_once()
            call_args = mock_get_platforms.call_args
            assert call_args[1] == "basic"  # entity_profile parameter

            # Verify runtime data includes profile
            assert hasattr(mock_config_entry, "runtime_data")
            assert mock_config_entry.runtime_data["entity_profile"] == "basic"

    @pytest.mark.asyncio
    async def test_setup_entry_no_dogs_configured(self, hass: HomeAssistant):
        """Test setup with no dogs configured."""
        entry = Mock()
        entry.data = {CONF_DOGS: []}
        entry.entry_id = "test_entry"
        entry.options = {}

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)

    @pytest.mark.asyncio
    async def test_setup_entry_invalid_dog_config(self, hass: HomeAssistant):
        """Test setup with invalid dog configuration."""
        entry = Mock()
        entry.data = {
            CONF_DOGS: [
                # Invalid: empty dog_id
                {CONF_DOG_ID: "", CONF_DOG_NAME: "Test Dog"}
            ]
        }
        entry.entry_id = "test_entry"
        entry.options = {}

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)

    @pytest.mark.asyncio
    async def test_setup_entry_unknown_profile_fallback(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator,
        mock_data_manager,
        mock_notification_manager,
        mock_entity_factory,
    ):
        """Test setup with unknown profile falls back to standard."""
        # Set unknown profile
        mock_config_entry.options = {"entity_profile": "unknown_profile"}

        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator",
                return_value=mock_coordinator,
            ),
            patch(
                "custom_components.pawcontrol.PawControlDataManager",
                return_value=mock_data_manager,
            ),
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager",
                return_value=mock_notification_manager,
            ),
            patch(
                "custom_components.pawcontrol.EntityFactory",
                return_value=mock_entity_factory,
            ),
            patch(
                "custom_components.pawcontrol.get_platforms_for_profile_and_modules",
                return_value=[Platform.SENSOR],
            ),
            patch.object(
                hass.config_entries, "async_forward_entry_setups", return_value=True
            ),
        ):
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            # Should fall back to 'standard' profile
            assert mock_config_entry.runtime_data["entity_profile"] == "standard"

    @pytest.mark.asyncio
    async def test_setup_entry_platform_setup_failure(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator,
        mock_data_manager,
        mock_notification_manager,
        mock_entity_factory,
    ):
        """Test setup when platform setup fails."""
        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator",
                return_value=mock_coordinator,
            ),
            patch(
                "custom_components.pawcontrol.PawControlDataManager",
                return_value=mock_data_manager,
            ),
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager",
                return_value=mock_notification_manager,
            ),
            patch(
                "custom_components.pawcontrol.EntityFactory",
                return_value=mock_entity_factory,
            ),
            patch(
                "custom_components.pawcontrol.get_platforms_for_profile_and_modules",
                return_value=[Platform.SENSOR],
            ),
            patch.object(
                hass.config_entries,
                "async_forward_entry_setups",
                side_effect=Exception("Platform setup failed"),
            ),
        ):
            with pytest.raises(ConfigEntryNotReady, match="Platform setup failed"):
                await async_setup_entry(hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_setup_entry_coordinator_refresh_timeout(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator,
        mock_data_manager,
        mock_notification_manager,
        mock_entity_factory,
    ):
        """Test setup when coordinator refresh times out."""
        mock_coordinator.async_config_entry_first_refresh.side_effect = (
            asyncio.TimeoutError()
        )

        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator",
                return_value=mock_coordinator,
            ),
            patch(
                "custom_components.pawcontrol.PawControlDataManager",
                return_value=mock_data_manager,
            ),
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager",
                return_value=mock_notification_manager,
            ),
            patch(
                "custom_components.pawcontrol.EntityFactory",
                return_value=mock_entity_factory,
            ),
            patch(
                "custom_components.pawcontrol.get_platforms_for_profile_and_modules",
                return_value=[Platform.SENSOR],
            ),
            patch.object(
                hass.config_entries, "async_forward_entry_setups", return_value=True
            ),
        ):
            # Should succeed despite timeout (graceful degradation)
            result = await async_setup_entry(hass, mock_config_entry)
            assert result is True

    @pytest.mark.asyncio
    async def test_setup_entry_data_storage(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator,
        mock_data_manager,
        mock_notification_manager,
        mock_entity_factory,
    ):
        """Test that runtime data is properly stored."""
        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator",
                return_value=mock_coordinator,
            ),
            patch(
                "custom_components.pawcontrol.PawControlDataManager",
                return_value=mock_data_manager,
            ),
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager",
                return_value=mock_notification_manager,
            ),
            patch(
                "custom_components.pawcontrol.EntityFactory",
                return_value=mock_entity_factory,
            ),
            patch(
                "custom_components.pawcontrol.get_platforms_for_profile_and_modules",
                return_value=[Platform.SENSOR],
            ),
            patch.object(
                hass.config_entries, "async_forward_entry_setups", return_value=True
            ),
        ):
            await async_setup_entry(hass, mock_config_entry)

            # Check runtime data
            assert hasattr(mock_config_entry, "runtime_data")
            runtime_data = mock_config_entry.runtime_data
            assert "coordinator" in runtime_data
            assert "data_manager" in runtime_data
            assert "notification_manager" in runtime_data
            assert "entity_factory" in runtime_data
            assert "entity_profile" in runtime_data

            # Check legacy data storage
            assert DOMAIN in hass.data
            assert mock_config_entry.entry_id in hass.data[DOMAIN]


class TestProfileBasedPlatformSelection:
    """Test profile-based platform selection functionality."""

    def test_get_platforms_for_profile_basic(self):
        """Test platform selection for basic profile."""
        dogs = [
            {
                "dog_id": "test_dog",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: False,
                    MODULE_HEALTH: False,
                },
            }
        ]

        platforms = get_platforms_for_profile_and_modules(dogs, "basic")

        # Basic profile should have minimal platforms
        expected_platforms = {Platform.SENSOR,
                              Platform.BUTTON, Platform.BINARY_SENSOR}
        assert set(platforms).issubset(expected_platforms)
        assert Platform.SENSOR in platforms  # Always required
        assert Platform.BUTTON in platforms  # Always required

    def test_get_platforms_for_profile_standard(self):
        """Test platform selection for standard profile."""
        dogs = [
            {
                "dog_id": "test_dog",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                },
            }
        ]

        platforms = get_platforms_for_profile_and_modules(dogs, "standard")

        # Standard profile should have moderate platforms
        assert Platform.SENSOR in platforms
        assert Platform.BUTTON in platforms
        assert Platform.BINARY_SENSOR in platforms
        assert Platform.SELECT in platforms
        assert Platform.SWITCH in platforms

    def test_get_platforms_for_profile_advanced(self):
        """Test platform selection for advanced profile."""
        dogs = [
            {
                "dog_id": "test_dog",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                },
            }
        ]

        platforms = get_platforms_for_profile_and_modules(dogs, "advanced")

        # Advanced profile should have all platforms
        assert len(platforms) >= 6  # Should have many platforms
        assert Platform.SENSOR in platforms
        assert Platform.DEVICE_TRACKER in platforms
        assert Platform.DATE in platforms

    def test_get_platforms_for_profile_gps_focus(self):
        """Test platform selection for GPS-focused profile."""
        dogs = [
            {
                "dog_id": "test_dog",
                "modules": {
                    MODULE_FEEDING: False,
                    MODULE_WALK: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: False,
                },
            }
        ]

        platforms = get_platforms_for_profile_and_modules(dogs, "gps_focus")

        # GPS focus should prioritize location tracking
        assert Platform.DEVICE_TRACKER in platforms
        assert Platform.SENSOR in platforms
        assert Platform.NUMBER in platforms  # GPS settings

    def test_get_platforms_for_profile_health_focus(self):
        """Test platform selection for health-focused profile."""
        dogs = [
            {
                "dog_id": "test_dog",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: False,
                    MODULE_GPS: False,
                    MODULE_HEALTH: True,
                },
            }
        ]

        platforms = get_platforms_for_profile_and_modules(dogs, "health_focus")

        # Health focus should prioritize health monitoring
        assert Platform.DATE in platforms  # Health dates
        assert Platform.NUMBER in platforms  # Health metrics
        assert Platform.TEXT in platforms  # Health notes

    def test_get_platforms_for_profile_no_dogs(self):
        """Test platform selection with empty dogs list."""
        platforms = get_platforms_for_profile_and_modules([], "standard")

        # Should have core platforms at minimum
        assert Platform.SENSOR in platforms
        assert Platform.BUTTON in platforms

    def test_get_platforms_for_profile_multiple_dogs(self):
        """Test platform selection with multiple dogs."""
        dogs = [
            {"dog_id": "dog1", "modules": {MODULE_GPS: True, MODULE_FEEDING: True}},
            {"dog_id": "dog2", "modules": {MODULE_HEALTH: True, MODULE_WALK: True}},
        ]

        platforms = get_platforms_for_profile_and_modules(dogs, "standard")

        # Should include platforms for all enabled modules across dogs
        assert Platform.DEVICE_TRACKER in platforms  # GPS from dog1
        assert Platform.DATE in platforms  # Health from dog2

    def test_get_platforms_optimization_metrics(self):
        """Test that platform optimization shows performance improvement."""
        dogs = [
            {
                "dog_id": "test_dog",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                },
            }
        ]

        basic_platforms = get_platforms_for_profile_and_modules(dogs, "basic")
        advanced_platforms = get_platforms_for_profile_and_modules(
            dogs, "advanced")

        # Advanced should have more platforms than basic
        assert len(advanced_platforms) > len(basic_platforms)

        # But both should be less than all possible platforms
        assert len(basic_platforms) < len(PLATFORMS)
        assert len(advanced_platforms) <= len(PLATFORMS)


class TestProfileBasedSetupOptimization:
    """Test profile-based setup optimization features."""

    @pytest.fixture
    def mock_entity_factory(self):
        """Mock entity factory with realistic estimate_entity_count."""
        factory = Mock()
        factory.estimate_entity_count = Mock(
            side_effect=self._estimate_entities)
        return factory

    def _estimate_entities(self, profile, modules):
        """Realistic entity count estimation for testing."""
        base_counts = {
            "basic": 8,
            "standard": 12,
            "advanced": 18,
            "gps_focus": 10,
            "health_focus": 10,
        }

        base = base_counts.get(profile, 12)
        enabled_modules = sum(1 for enabled in modules.values() if enabled)
        return min(base, base + enabled_modules)

    @pytest.mark.asyncio
    async def test_setup_performance_optimization_basic(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_entity_factory,
    ):
        """Test setup performance with basic profile."""
        mock_config_entry.options = {"entity_profile": "basic"}
        mock_config_entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "test_dog",
                    CONF_DOG_NAME: "Test Dog",
                    "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
                }
            ]
        }

        with (
            patch("custom_components.pawcontrol.PawControlCoordinator"),
            patch("custom_components.pawcontrol.PawControlDataManager"),
            patch("custom_components.pawcontrol.PawControlNotificationManager"),
            patch("custom_components.pawcontrol.DogDataManager"),
            patch("custom_components.pawcontrol.WalkManager"),
            patch("custom_components.pawcontrol.FeedingManager"),
            patch("custom_components.pawcontrol.HealthCalculator"),
            patch(
                "custom_components.pawcontrol.EntityFactory",
                return_value=mock_entity_factory,
            ),
            patch.object(
                hass.config_entries, "async_forward_entry_setups", return_value=True
            ),
            patch("custom_components.pawcontrol.PawControlServiceManager"),
            patch("custom_components.pawcontrol.async_setup_daily_reset_scheduler"),
        ):
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True

            # Verify entity count estimation was called
            mock_entity_factory.estimate_entity_count.assert_called()

            # Verify basic profile was used
            runtime_data = mock_config_entry.runtime_data
            assert runtime_data["entity_profile"] == "basic"

    @pytest.mark.asyncio
    async def test_setup_performance_optimization_multiple_dogs(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_entity_factory,
    ):
        """Test setup performance with multiple dogs."""
        mock_config_entry.options = {"entity_profile": "standard"}
        mock_config_entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "dog1",
                    CONF_DOG_NAME: "Dog 1",
                    "modules": {MODULE_FEEDING: True, MODULE_GPS: True},
                },
                {
                    CONF_DOG_ID: "dog2",
                    CONF_DOG_NAME: "Dog 2",
                    "modules": {MODULE_HEALTH: True, MODULE_WALK: True},
                },
            ]
        }

        with (
            patch("custom_components.pawcontrol.PawControlCoordinator"),
            patch("custom_components.pawcontrol.PawControlDataManager"),
            patch("custom_components.pawcontrol.PawControlNotificationManager"),
            patch("custom_components.pawcontrol.DogDataManager"),
            patch("custom_components.pawcontrol.WalkManager"),
            patch("custom_components.pawcontrol.FeedingManager"),
            patch("custom_components.pawcontrol.HealthCalculator"),
            patch(
                "custom_components.pawcontrol.EntityFactory",
                return_value=mock_entity_factory,
            ),
            patch.object(
                hass.config_entries, "async_forward_entry_setups", return_value=True
            ),
            patch("custom_components.pawcontrol.PawControlServiceManager"),
            patch("custom_components.pawcontrol.async_setup_daily_reset_scheduler"),
        ):
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True

            # Should estimate entities for each dog
            assert mock_entity_factory.estimate_entity_count.call_count == 2

    @pytest.mark.asyncio
    async def test_setup_batch_optimization_many_dogs(
        self,
        hass: HomeAssistant,
        mock_entity_factory,
    ):
        """Test batched setup optimization for many dogs."""
        # Create entry with many dogs to trigger batch optimization
        many_dogs = [
            {
                CONF_DOG_ID: f"dog_{i}",
                CONF_DOG_NAME: f"Dog {i}",
                "modules": {MODULE_FEEDING: True},
            }
            for i in range(5)  # More than 3 dogs
        ]

        entry = Mock()
        entry.entry_id = "test_entry"
        entry.options = {"entity_profile": "standard"}
        entry.data = {CONF_DOGS: many_dogs}

        with (
            patch("custom_components.pawcontrol.PawControlCoordinator"),
            patch("custom_components.pawcontrol.PawControlDataManager"),
            patch("custom_components.pawcontrol.PawControlNotificationManager"),
            patch("custom_components.pawcontrol.DogDataManager"),
            patch("custom_components.pawcontrol.WalkManager"),
            patch("custom_components.pawcontrol.FeedingManager"),
            patch("custom_components.pawcontrol.HealthCalculator"),
            patch(
                "custom_components.pawcontrol.EntityFactory",
                return_value=mock_entity_factory,
            ),
            patch.object(
                hass.config_entries, "async_forward_entry_setups", return_value=True
            ),
            patch("custom_components.pawcontrol.PawControlServiceManager"),
            patch("custom_components.pawcontrol.async_setup_daily_reset_scheduler"),
            patch("asyncio.gather") as mock_gather,
        ):
            result = await async_setup_entry(hass, entry)

            assert result is True

            # Should use batch-based parallel loading for many dogs
            mock_gather.assert_called()


class TestAsyncUnloadEntry:
    """Test the async_unload_entry function."""

    @pytest.mark.asyncio
    async def test_unload_entry_success(self, hass: HomeAssistant, mock_config_entry):
        """Test successful entry unload."""
        # Setup runtime data
        mock_coordinator = Mock()
        mock_coordinator.async_shutdown = AsyncMock()
        mock_data_manager = Mock()
        mock_data_manager.async_shutdown = AsyncMock()
        mock_notification_manager = Mock()
        mock_notification_manager.async_shutdown = AsyncMock()

        mock_config_entry.runtime_data = {
            "coordinator": mock_coordinator,
            "data_manager": mock_data_manager,
            "notification_manager": mock_notification_manager,
        }

        hass.data[DOMAIN] = {mock_config_entry.entry_id: {}}

        with patch.object(
            hass.config_entries, "async_unload_platforms", return_value=True
        ):
            result = await async_unload_entry(hass, mock_config_entry)

            assert result is True
            mock_coordinator.async_shutdown.assert_called_once()
            mock_data_manager.async_shutdown.assert_called_once()
            mock_notification_manager.async_shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_unload_entry_profile_aware_platforms(self, hass: HomeAssistant):
        """Test unload uses profile-aware platform determination."""
        entry = Mock()
        entry.entry_id = "test_entry"
        entry.options = {"entity_profile": "basic"}
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "test_dog",
                    CONF_DOG_NAME: "Test Dog",
                    "modules": {MODULE_FEEDING: True},
                }
            ]
        }
        entry.runtime_data = None

        hass.data[DOMAIN] = {}

        with (
            patch(
                "custom_components.pawcontrol.get_platforms_for_profile_and_modules",
                return_value=[Platform.SENSOR, Platform.BUTTON],
            ) as mock_get_platforms,
            patch.object(
                hass.config_entries, "async_unload_platforms", return_value=True
            ) as mock_unload,
        ):
            result = await async_unload_entry(hass, entry)

            assert result is True
            mock_get_platforms.assert_called_once()
            mock_unload.assert_called_once_with(
                entry, [Platform.SENSOR, Platform.BUTTON]
            )

    @pytest.mark.asyncio
    async def test_unload_entry_platform_failure(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test unload when platform unload fails."""
        hass.data[DOMAIN] = {mock_config_entry.entry_id: {}}

        with patch.object(
            hass.config_entries, "async_unload_platforms", return_value=False
        ):
            result = await async_unload_entry(hass, mock_config_entry)
            assert result is False

    @pytest.mark.asyncio
    async def test_unload_entry_timeout(self, hass: HomeAssistant, mock_config_entry):
        """Test unload with timeout."""
        hass.data[DOMAIN] = {mock_config_entry.entry_id: {}}

        with patch.object(
            hass.config_entries,
            "async_unload_platforms",
            side_effect=asyncio.TimeoutError(),
        ):
            result = await async_unload_entry(hass, mock_config_entry)
            assert result is False


class TestAsyncReloadEntry:
    """Test the async_reload_entry function."""

    @pytest.mark.asyncio
    async def test_reload_entry_success(self, hass: HomeAssistant, mock_config_entry):
        """Test successful entry reload."""
        mock_config_entry.options = {"entity_profile": "advanced"}

        with (
            patch(
                "custom_components.pawcontrol.async_unload_entry", return_value=True
            ) as mock_unload,
            patch(
                "custom_components.pawcontrol.async_setup_entry", return_value=True
            ) as mock_setup,
        ):
            await async_reload_entry(hass, mock_config_entry)

            mock_unload.assert_called_once_with(hass, mock_config_entry)
            mock_setup.assert_called_once_with(hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_reload_entry_failure(self, hass: HomeAssistant, mock_config_entry):
        """Test reload when unload or setup fails."""
        with patch(
            "custom_components.pawcontrol.async_unload_entry",
            side_effect=Exception("Unload failed"),
        ):
            with pytest.raises(Exception, match="Unload failed"):
                await async_reload_entry(hass, mock_config_entry)


class TestProfileSystemValidation:
    """Test profile system validation."""

    def test_all_profiles_exist(self):
        """Test that all expected profiles are defined."""
        expected_profiles = [
            "basic",
            "standard",
            "advanced",
            "gps_focus",
            "health_focus",
        ]
        assert set(ENTITY_PROFILES.keys()) == set(expected_profiles)

    def test_profile_configuration_validity(self):
        """Test that all profiles have valid configuration."""
        for profile_name, profile_config in ENTITY_PROFILES.items():
            assert "max_entities" in profile_config
            assert "description" in profile_config
            assert "modules" in profile_config

            assert isinstance(profile_config["max_entities"], int)
            assert profile_config["max_entities"] > 0
            assert isinstance(profile_config["description"], str)
            assert len(profile_config["description"]) > 0
            assert isinstance(profile_config["modules"], dict)

    def test_profile_entity_limits_progression(self):
        """Test that profile entity limits show logical progression."""
        basic_limit = ENTITY_PROFILES["basic"]["max_entities"]
        standard_limit = ENTITY_PROFILES["standard"]["max_entities"]
        advanced_limit = ENTITY_PROFILES["advanced"]["max_entities"]

        # Should show progression: basic < standard < advanced
        assert basic_limit < standard_limit < advanced_limit

        # Limits should be reasonable
        assert 5 <= basic_limit <= 10
        assert 10 <= standard_limit <= 15
        assert 15 <= advanced_limit <= 25

    def test_focused_profiles_have_appropriate_modules(self):
        """Test that focused profiles enable appropriate modules."""
        gps_profile = ENTITY_PROFILES["gps_focus"]
        health_profile = ENTITY_PROFILES["health_focus"]

        # GPS focus should enable GPS and related modules
        assert gps_profile["modules"][MODULE_GPS] is True

        # Health focus should enable health and feeding
        assert health_profile["modules"][MODULE_HEALTH] is True
        assert health_profile["modules"][MODULE_FEEDING] is True


class TestEntityFactoryIntegration:
    """Test EntityFactory integration in setup process."""

    @pytest.fixture
    def mock_entity_factory_with_methods(self):
        """Mock entity factory with all required methods."""
        factory = Mock()
        factory.estimate_entity_count = Mock(return_value=12)
        factory.create_entities_for_dog = Mock(
            return_value=[Mock(), Mock(), Mock()])
        factory.get_profile_info = Mock(
            return_value={"description": "Test profile", "max_entities": 12}
        )
        return factory

    @pytest.mark.asyncio
    async def test_entity_factory_integration_in_setup(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_entity_factory_with_methods,
    ):
        """Test that EntityFactory is properly integrated in setup."""
        mock_config_entry.options = {"entity_profile": "standard"}

        with (
            patch("custom_components.pawcontrol.PawControlCoordinator"),
            patch("custom_components.pawcontrol.PawControlDataManager"),
            patch("custom_components.pawcontrol.PawControlNotificationManager"),
            patch("custom_components.pawcontrol.DogDataManager"),
            patch("custom_components.pawcontrol.WalkManager"),
            patch("custom_components.pawcontrol.FeedingManager"),
            patch("custom_components.pawcontrol.HealthCalculator"),
            patch(
                "custom_components.pawcontrol.EntityFactory",
                return_value=mock_entity_factory_with_methods,
            ),
            patch.object(
                hass.config_entries, "async_forward_entry_setups", return_value=True
            ),
            patch("custom_components.pawcontrol.PawControlServiceManager"),
            patch("custom_components.pawcontrol.async_setup_daily_reset_scheduler"),
        ):
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True

            # Verify EntityFactory was created and used
            assert "entity_factory" in mock_config_entry.runtime_data

            # Verify entity count estimation was called for each dog
            mock_entity_factory_with_methods.estimate_entity_count.assert_called()

    @pytest.mark.asyncio
    async def test_entity_factory_stored_in_runtime_data(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_entity_factory_with_methods,
    ):
        """Test that EntityFactory is stored in runtime data."""
        with (
            patch("custom_components.pawcontrol.PawControlCoordinator"),
            patch("custom_components.pawcontrol.PawControlDataManager"),
            patch("custom_components.pawcontrol.PawControlNotificationManager"),
            patch("custom_components.pawcontrol.DogDataManager"),
            patch("custom_components.pawcontrol.WalkManager"),
            patch("custom_components.pawcontrol.FeedingManager"),
            patch("custom_components.pawcontrol.HealthCalculator"),
            patch(
                "custom_components.pawcontrol.EntityFactory",
                return_value=mock_entity_factory_with_methods,
            ),
            patch.object(
                hass.config_entries, "async_forward_entry_setups", return_value=True
            ),
            patch("custom_components.pawcontrol.PawControlServiceManager"),
            patch("custom_components.pawcontrol.async_setup_daily_reset_scheduler"),
        ):
            await async_setup_entry(hass, mock_config_entry)

            # Check both runtime_data and legacy storage
            assert "entity_factory" in mock_config_entry.runtime_data
            assert "entity_factory" in hass.data[DOMAIN][mock_config_entry.entry_id]

            # Verify they're the same object
            assert (
                mock_config_entry.runtime_data["entity_factory"]
                == hass.data[DOMAIN][mock_config_entry.entry_id]["entity_factory"]
            )


class TestPerformanceMetrics:
    """Test performance metrics and optimization."""

    def test_platform_reduction_metrics(self):
        """Test platform reduction provides significant optimization."""
        all_dogs_all_modules = [
            {
                "dog_id": "test_dog",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                    MODULE_NOTIFICATIONS: True,
                    MODULE_DASHBOARD: True,
                    MODULE_VISITOR: True,
                },
            }
        ]

        basic_platforms = get_platforms_for_profile_and_modules(
            all_dogs_all_modules, "basic"
        )
        advanced_platforms = get_platforms_for_profile_and_modules(
            all_dogs_all_modules, "advanced"
        )

        total_platforms = len(PLATFORMS)
        basic_reduction = (total_platforms -
                           len(basic_platforms)) / total_platforms
        advanced_reduction = (
            total_platforms - len(advanced_platforms)
        ) / total_platforms

        # Basic should have significant reduction (at least 30%)
        assert basic_reduction >= 0.3

        # Advanced should have some reduction but less than basic
        assert 0 <= advanced_reduction < basic_reduction

    def test_entity_count_optimization_estimation(self):
        """Test entity count optimization through profiles."""
        # This would be more detailed with actual EntityFactory, but tests the principle
        profile_limits = {
            "basic": ENTITY_PROFILES["basic"]["max_entities"],
            "standard": ENTITY_PROFILES["standard"]["max_entities"],
            "advanced": ENTITY_PROFILES["advanced"]["max_entities"],
        }

        # Calculate theoretical reduction vs legacy (assume 54 entities was legacy)
        legacy_count = 54

        for profile, limit in profile_limits.items():
            reduction = (legacy_count - limit) / legacy_count

            if profile == "basic":
                assert reduction >= 0.7  # At least 70% reduction
            elif profile == "standard":
                assert reduction >= 0.6  # At least 60% reduction
            elif profile == "advanced":
                assert reduction >= 0.4  # At least 40% reduction


# Add missing service and helper tests from original
class TestServiceHandlers:
    """Test service handler functions."""

    @pytest.fixture
    def mock_service_call(self):
        """Return a mock service call."""
        call = Mock(spec=ServiceCall)  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            ATTR_MEAL_TYPE: "breakfast",
            ATTR_PORTION_SIZE: 200.0,
        }
        return call

    @pytest.fixture
    def mock_runtime_data(self):
        """Return mock runtime data."""
        coordinator = Mock()
        data_manager = AsyncMock()
        notification_manager = AsyncMock()

        return {
            "coordinator": coordinator,
            "data_manager": data_manager,
            "notification_manager": notification_manager,
            "dogs": [{"dog_id": "test_dog", "dog_name": "Test Dog"}],
        }

    @pytest.mark.asyncio
    async def test_feed_dog_service_success(
        self, hass: HomeAssistant, mock_config_entry, mock_runtime_data
    ):
        """Test successful feed_dog service call."""
        # Setup data
        mock_config_entry.runtime_data = mock_runtime_data
        hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_runtime_data}

        # Mock the service registration
        service_handler = None

        def capture_service_handler(domain, service, handler, schema=None):
            nonlocal service_handler
            if service == SERVICE_FEED_DOG:
                service_handler = handler

        with (
            patch.object(
                hass.services, "async_register", side_effect=capture_service_handler
            ),
            patch.object(hass.services, "has_service", return_value=False),
            patch(
                "custom_components.pawcontrol._get_runtime_data_for_dog",
                return_value=mock_runtime_data,
            ),
        ):
            # Register services
            from custom_components.pawcontrol import _async_register_services

            await _async_register_services(hass)

            # Call the service
            call = Mock()
            call.data = {
                ATTR_DOG_ID: "test_dog",
                ATTR_MEAL_TYPE: "breakfast",
                ATTR_PORTION_SIZE: 200.0,
            }

            bus_events = []

            def capture_event(event_type, event_data):
                bus_events.append((event_type, event_data))

            with patch.object(hass.bus, "async_fire", side_effect=capture_event):
                await service_handler(call)

            # Verify data manager was called
            mock_runtime_data["data_manager"].async_log_feeding.assert_called_once(
            )

            # Verify event was fired
            assert len(bus_events) == 1
            assert bus_events[0][0] == EVENT_FEEDING_LOGGED


class TestHelperFunctions:
    """Test helper functions."""

    @pytest.mark.asyncio
    async def test_get_runtime_data_for_dog_found(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test finding runtime data for existing dog."""
        runtime_data = {
            "dogs": [{"dog_id": "test_dog", "dog_name": "Test Dog"}]}
        mock_config_entry.runtime_data = runtime_data

        with patch.object(
            hass.config_entries, "async_entries", return_value=[mock_config_entry]
        ):
            from custom_components.pawcontrol import _get_runtime_data_for_dog

            result = _get_runtime_data_for_dog(hass, "test_dog")

        assert result == runtime_data


class TestValidationFunctions:
    """Test configuration validation functions."""

    @pytest.mark.asyncio
    async def test_validate_dogs_configuration_valid(self):
        """Test validation with valid dogs configuration."""
        dogs_config = [
            {
                "dog_id": "test_dog",
                "dog_name": "Test Dog",
                "dog_age": 5,
                "dog_weight": 25.0,
                "dog_size": "medium",
            }
        ]

        from custom_components.pawcontrol import _async_validate_dogs_configuration

        # Should not raise any exception
        await _async_validate_dogs_configuration(dogs_config)

    @pytest.mark.asyncio
    async def test_validate_dogs_configuration_invalid_dog_id(self):
        """Test validation with invalid dog ID."""
        dogs_config = [
            {
                "dog_id": "",  # Invalid: empty
                "dog_name": "Test Dog",
            }
        ]

        from custom_components.pawcontrol import _async_validate_dogs_configuration

        with pytest.raises(ConfigurationError):
            await _async_validate_dogs_configuration(dogs_config)


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_pawcontrol_setup_error(self):
        """Test PawControlSetupError exception."""
        error = PawControlSetupError("Test error", "test_code")
        assert str(error) == "Test error"
        assert error.error_code == "test_code"

        # Test default error code
        error_default = PawControlSetupError("Test error")
        assert error_default.error_code == "setup_failed"
