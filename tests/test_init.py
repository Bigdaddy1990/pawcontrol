"""Tests for the Paw Control integration __init__ module."""

import asyncio
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
from custom_components.pawcontrol import (
    PawControlSetupError,
    async_reload_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.pawcontrol.const import (
    ATTR_DOG_ID,
    ATTR_MEAL_TYPE,
    ATTR_PORTION_SIZE,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    EVENT_FEEDING_LOGGED,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
    PLATFORMS,
    SERVICE_DAILY_RESET,
    SERVICE_END_WALK,
    SERVICE_FEED_DOG,
    SERVICE_LOG_HEALTH,
    SERVICE_START_WALK,
)
from custom_components.pawcontrol.exceptions import (
    ConfigurationError,
    DogNotFoundError,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError


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

    @pytest.mark.asyncio
    async def test_setup_entry_success(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator,
        mock_data_manager,
        mock_notification_manager,
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
            patch.object(
                hass.config_entries, "async_forward_entry_setups", return_value=True
            ) as mock_forward,
        ):
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            mock_data_manager.async_initialize.assert_called_once()
            mock_notification_manager.async_initialize.assert_called_once()
            mock_coordinator.async_config_entry_first_refresh.assert_called_once()
            mock_forward.assert_called_once_with(mock_config_entry, PLATFORMS)

    @pytest.mark.asyncio
    async def test_setup_entry_no_dogs_configured(self, hass: HomeAssistant):
        """Test setup with no dogs configured."""
        entry = Mock()
        entry.data = {CONF_DOGS: []}
        entry.entry_id = "test_entry"

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)

    @pytest.mark.asyncio
    async def test_setup_entry_invalid_dog_config(self, hass: HomeAssistant):
        """Test setup with invalid dog configuration."""
        entry = Mock()
        entry.data = {
            CONF_DOGS: [
                {CONF_DOG_ID: "", CONF_DOG_NAME: "Test Dog"}  # Invalid: empty dog_id
            ]
        }
        entry.entry_id = "test_entry"

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)

    @pytest.mark.asyncio
    async def test_setup_entry_platform_setup_failure(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator,
        mock_data_manager,
        mock_notification_manager,
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

            # Check legacy data storage
            assert DOMAIN in hass.data
            assert mock_config_entry.entry_id in hass.data[DOMAIN]


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
        ) as mock_unload:
            result = await async_unload_entry(hass, mock_config_entry)

            assert result is True
            mock_unload.assert_called_once_with(mock_config_entry, PLATFORMS)
            mock_coordinator.async_shutdown.assert_called_once()
            mock_data_manager.async_shutdown.assert_called_once()
            mock_notification_manager.async_shutdown.assert_called_once()

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


class TestServiceHandlers:
    """Test service handler functions."""

    @pytest.fixture
    def mock_service_call(self):
        """Return a mock service call."""
        call = Mock(spec=ServiceCall)
        call.data = {
            ATTR_DOG_ID: "test_dog",
            ATTR_MEAL_TYPE: "breakfast",
            ATTR_PORTION_SIZE: 200.0,
        }
        return call

    @pytest.fixture
    def mock_runtime_data(
        self, mock_coordinator, mock_data_manager, mock_notification_manager
    ):
        """Return mock runtime data."""
        return {
            "coordinator": mock_coordinator,
            "data_manager": mock_data_manager,
            "notification_manager": mock_notification_manager,
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
            mock_runtime_data["data_manager"].async_log_feeding.assert_called_once()

            # Verify event was fired
            assert len(bus_events) == 1
            assert bus_events[0][0] == EVENT_FEEDING_LOGGED

    @pytest.mark.asyncio
    async def test_feed_dog_service_dog_not_found(self, hass: HomeAssistant):
        """Test feed_dog service with non-existent dog."""
        with (
            patch(
                "custom_components.pawcontrol._get_runtime_data_for_dog",
                return_value=None,
            ),
            patch(
                "custom_components.pawcontrol._get_available_dog_ids", return_value=[]
            ),
        ):
            from custom_components.pawcontrol import _async_register_services

            # Mock service registration to capture handler
            service_handler = None

            def capture_handler(domain, service, handler, schema=None):
                nonlocal service_handler
                if service == SERVICE_FEED_DOG:
                    service_handler = handler

            with (
                patch.object(
                    hass.services, "async_register", side_effect=capture_handler
                ),
                patch.object(hass.services, "has_service", return_value=False),
            ):
                await _async_register_services(hass)

            call = Mock()
            call.data = {ATTR_DOG_ID: "nonexistent_dog"}

            with pytest.raises(ServiceValidationError):
                await service_handler(call)

    @pytest.mark.asyncio
    async def test_start_walk_service_success(
        self, hass: HomeAssistant, mock_runtime_data
    ):
        """Test successful start_walk service call."""
        with (
            patch(
                "custom_components.pawcontrol._get_runtime_data_for_dog",
                return_value=mock_runtime_data,
            ),
            patch.object(hass.services, "has_service", return_value=False),
        ):
            from custom_components.pawcontrol import _async_register_services

            service_handler = None

            def capture_handler(domain, service, handler, schema=None):
                nonlocal service_handler
                if service == SERVICE_START_WALK:
                    service_handler = handler

            with patch.object(
                hass.services, "async_register", side_effect=capture_handler
            ):
                await _async_register_services(hass)

            # Mock return value for start_walk
            mock_runtime_data["data_manager"].async_start_walk.return_value = "walk_123"

            call = Mock()
            call.data = {
                ATTR_DOG_ID: "test_dog",
                "label": "Morning walk",
                "walk_type": "regular",
            }

            bus_events = []

            def capture_event(event_type, event_data):
                bus_events.append((event_type, event_data))

            with patch.object(hass.bus, "async_fire", side_effect=capture_event):
                await service_handler(call)

            mock_runtime_data["data_manager"].async_start_walk.assert_called_once()
            assert len(bus_events) == 1
            assert bus_events[0][0] == EVENT_WALK_STARTED

    @pytest.mark.asyncio
    async def test_end_walk_service_success(
        self, hass: HomeAssistant, mock_runtime_data
    ):
        """Test successful end_walk service call."""
        with (
            patch(
                "custom_components.pawcontrol._get_runtime_data_for_dog",
                return_value=mock_runtime_data,
            ),
            patch.object(hass.services, "has_service", return_value=False),
        ):
            from custom_components.pawcontrol import _async_register_services

            service_handler = None

            def capture_handler(domain, service, handler, schema=None):
                nonlocal service_handler
                if service == SERVICE_END_WALK:
                    service_handler = handler

            with patch.object(
                hass.services, "async_register", side_effect=capture_handler
            ):
                await _async_register_services(hass)

            call = Mock()
            call.data = {
                ATTR_DOG_ID: "test_dog",
                "distance": 2000.0,
                "duration": 30,
            }

            bus_events = []

            def capture_event(event_type, event_data):
                bus_events.append((event_type, event_data))

            with patch.object(hass.bus, "async_fire", side_effect=capture_event):
                await service_handler(call)

            mock_runtime_data["data_manager"].async_end_walk.assert_called_once()
            assert len(bus_events) == 1
            assert bus_events[0][0] == EVENT_WALK_ENDED

    @pytest.mark.asyncio
    async def test_daily_reset_service_success(
        self, hass: HomeAssistant, mock_runtime_data
    ):
        """Test successful daily_reset service call."""
        # Setup multiple dogs
        hass.data[DOMAIN] = {"entry1": mock_runtime_data}

        with (
            patch(
                "custom_components.pawcontrol._get_available_dog_ids",
                return_value=["test_dog"],
            ),
            patch(
                "custom_components.pawcontrol._get_runtime_data_for_dog",
                return_value=mock_runtime_data,
            ),
            patch.object(hass.services, "has_service", return_value=False),
        ):
            from custom_components.pawcontrol import _async_register_services

            service_handler = None

            def capture_handler(domain, service, handler, schema=None):
                nonlocal service_handler
                if service == SERVICE_DAILY_RESET:
                    service_handler = handler

            with patch.object(
                hass.services, "async_register", side_effect=capture_handler
            ):
                await _async_register_services(hass)

            call = Mock()
            call.data = {}

            await service_handler(call)

            # Verify reset was called
            mock_runtime_data[
                "data_manager"
            ].async_reset_dog_daily_stats.assert_called_once_with("test_dog")


class TestHelperFunctions:
    """Test helper functions."""

    @pytest.mark.asyncio
    async def test_get_runtime_data_for_dog_found(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test finding runtime data for existing dog."""
        runtime_data = {"dogs": [{"dog_id": "test_dog", "dog_name": "Test Dog"}]}
        mock_config_entry.runtime_data = runtime_data

        with patch.object(
            hass.config_entries, "async_entries", return_value=[mock_config_entry]
        ):
            from custom_components.pawcontrol import _get_runtime_data_for_dog

            result = _get_runtime_data_for_dog(hass, "test_dog")

        assert result == runtime_data

    @pytest.mark.asyncio
    async def test_get_runtime_data_for_dog_not_found(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test runtime data when dog not found."""
        runtime_data = {"dogs": [{"dog_id": "other_dog", "dog_name": "Other Dog"}]}
        mock_config_entry.runtime_data = runtime_data

        with patch.object(
            hass.config_entries, "async_entries", return_value=[mock_config_entry]
        ):
            from custom_components.pawcontrol import _get_runtime_data_for_dog

            result = _get_runtime_data_for_dog(hass, "test_dog")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_runtime_data_legacy_fallback(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test fallback to legacy data storage."""
        # No runtime_data, use legacy
        mock_config_entry.runtime_data = None
        mock_coordinator = Mock()
        mock_coordinator.config_entry = mock_config_entry

        legacy_data = {
            "coordinator": mock_coordinator,
            "data": Mock(),
            "notifications": Mock(),
        }

        mock_config_entry.data = {
            CONF_DOGS: [{"dog_id": "test_dog", "dog_name": "Test Dog"}]
        }

        hass.data[DOMAIN] = {mock_config_entry.entry_id: legacy_data}

        with patch.object(
            hass.config_entries, "async_entries", return_value=[mock_config_entry]
        ):
            from custom_components.pawcontrol import _get_runtime_data_for_dog

            result = _get_runtime_data_for_dog(hass, "test_dog")

        assert result is not None
        assert "coordinator" in result
        assert "data_manager" in result

    def test_get_available_dog_ids(self, hass: HomeAssistant, mock_config_entry):
        """Test getting list of available dog IDs."""
        runtime_data = {
            "dogs": [
                {"dog_id": "dog1", "dog_name": "Dog 1"},
                {"dog_id": "dog2", "dog_name": "Dog 2"},
            ]
        }
        mock_config_entry.runtime_data = runtime_data

        with patch.object(
            hass.config_entries, "async_entries", return_value=[mock_config_entry]
        ):
            from custom_components.pawcontrol import _get_available_dog_ids

            result = _get_available_dog_ids(hass)

        assert result == ["dog1", "dog2"]


class TestDailyResetScheduler:
    """Test daily reset scheduler."""

    @pytest.mark.asyncio
    async def test_setup_daily_reset_scheduler(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test setting up daily reset scheduler."""
        mock_config_entry.options = {"reset_time": "23:59:00"}
        hass.data[DOMAIN] = {}

        with patch(
            "custom_components.pawcontrol.async_track_time_change"
        ) as mock_track:
            from custom_components.pawcontrol import _async_setup_daily_reset_scheduler

            await _async_setup_daily_reset_scheduler(hass, mock_config_entry)

            mock_track.assert_called_once()
            assert hass.data[DOMAIN].get("_daily_reset_scheduled") is True

    @pytest.mark.asyncio
    async def test_setup_daily_reset_scheduler_already_configured(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test scheduler when already configured."""
        hass.data[DOMAIN] = {"_daily_reset_scheduled": True}

        with patch(
            "custom_components.pawcontrol.async_track_time_change"
        ) as mock_track:
            from custom_components.pawcontrol import _async_setup_daily_reset_scheduler

            await _async_setup_daily_reset_scheduler(hass, mock_config_entry)

            mock_track.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_daily_reset_scheduler_invalid_time(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test scheduler with invalid time format."""
        mock_config_entry.options = {"reset_time": "invalid_time"}
        hass.data[DOMAIN] = {}

        with patch(
            "custom_components.pawcontrol.async_track_time_change"
        ) as mock_track:
            from custom_components.pawcontrol import _async_setup_daily_reset_scheduler

            await _async_setup_daily_reset_scheduler(hass, mock_config_entry)

            # Should fall back to default time
            mock_track.assert_called_once()
            args, kwargs = mock_track.call_args
            assert kwargs["hour"] == 23  # Default time hour
            assert kwargs["minute"] == 59  # Default time minute


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

    @pytest.mark.asyncio
    async def test_validate_dogs_configuration_duplicate_dog_id(self):
        """Test validation with duplicate dog IDs."""
        dogs_config = [
            {"dog_id": "test_dog", "dog_name": "Test Dog 1"},
            {"dog_id": "test_dog", "dog_name": "Test Dog 2"},  # Duplicate ID
        ]

        from custom_components.pawcontrol import _async_validate_dogs_configuration

        with pytest.raises(ConfigurationError):
            await _async_validate_dogs_configuration(dogs_config)

    @pytest.mark.asyncio
    async def test_validate_dogs_configuration_invalid_weight(self):
        """Test validation with invalid weight."""
        dogs_config = [
            {
                "dog_id": "test_dog",
                "dog_name": "Test Dog",
                "dog_weight": 300.0,  # Invalid: too heavy
                "dog_size": "toy",  # Inconsistent with weight
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

    @pytest.mark.asyncio
    async def test_setup_with_component_cleanup_on_error(
        self,
        hass: HomeAssistant,
        mock_config_entry,
    ):
        """Test cleanup when component initialization fails."""
        with patch(
            "custom_components.pawcontrol.PawControlCoordinator",
            side_effect=Exception("Coordinator failed"),
        ):
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_cleanup_runtime_data_with_errors(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test cleanup when components raise errors during shutdown."""
        mock_coordinator = Mock()
        mock_coordinator.async_shutdown = AsyncMock(
            side_effect=Exception("Shutdown error")
        )

        runtime_data = {"coordinator": mock_coordinator}

        from custom_components.pawcontrol import _async_cleanup_runtime_data

        # Should not raise exception even if component shutdown fails
        await _async_cleanup_runtime_data(hass, mock_config_entry, runtime_data)


class TestServiceRegistration:
    """Test service registration functionality."""

    @pytest.mark.asyncio
    async def test_register_services_success(self, hass: HomeAssistant):
        """Test successful service registration."""
        with (
            patch.object(hass.services, "has_service", return_value=False),
            patch.object(hass.services, "async_register") as mock_register,
        ):
            from custom_components.pawcontrol import _async_register_services

            await _async_register_services(hass)

            # Verify all services were registered
            expected_services = [
                SERVICE_FEED_DOG,
                SERVICE_START_WALK,
                SERVICE_END_WALK,
                SERVICE_LOG_HEALTH,
                "log_medication",
                "start_grooming",
                SERVICE_DAILY_RESET,
                "notify_test",
            ]

            assert mock_register.call_count == len(expected_services)

    @pytest.mark.asyncio
    async def test_register_services_already_registered(self, hass: HomeAssistant):
        """Test service registration when services already exist."""
        with (
            patch.object(hass.services, "has_service", return_value=True),
            patch.object(hass.services, "async_register") as mock_register,
        ):
            from custom_components.pawcontrol import _async_register_services

            await _async_register_services(hass)

            # Should not register anything
            mock_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_services_failure(self, hass: HomeAssistant):
        """Test service registration failure."""
        with (
            patch.object(hass.services, "has_service", return_value=False),
            patch.object(
                hass.services,
                "async_register",
                side_effect=Exception("Registration failed"),
            ),
        ):
            from custom_components.pawcontrol import _async_register_services

            with pytest.raises(PawControlSetupError):
                await _async_register_services(hass)


class TestPerformanceMonitoring:
    """Test performance monitoring decorator."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_timeout_handling(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test that setup entry handles timeouts gracefully."""
        with (
            patch("custom_components.pawcontrol.PawControlCoordinator"),
            patch("custom_components.pawcontrol.PawControlDataManager"),
            patch("custom_components.pawcontrol.PawControlNotificationManager"),
            patch("asyncio.timeout") as mock_timeout,
        ):
            # Setup timeout context manager
            timeout_cm = MagicMock()
            timeout_cm.__aenter__ = AsyncMock()
            timeout_cm.__aexit__ = AsyncMock()
            mock_timeout.return_value = timeout_cm

            with patch.object(
                hass.config_entries, "async_forward_entry_setups", return_value=True
            ):
                result = await async_setup_entry(hass, mock_config_entry)
                assert result is True
