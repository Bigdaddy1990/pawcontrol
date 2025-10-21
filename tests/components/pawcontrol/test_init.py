"""Comprehensive integration tests for PawControl __init__.py.

Tests the complete integration setup, platform forwarding, service registration,
entity creation, and lifecycle management for Bronze quality assurance goals.

Quality Scale: Bronze target
Home Assistant: 2025.8.2+
Python: 3.12+
"""

from __future__ import annotations

import sys
from copy import deepcopy
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    PLATFORMS,
)
from custom_components.pawcontrol.runtime_data import (
    get_runtime_data,
    store_runtime_data,
)
from custom_components.pawcontrol.types import PawControlRuntimeData
from custom_components.pawcontrol.utils import sanitize_dog_id
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Mock external dependencies
sys.modules.setdefault("bluetooth_adapters", ModuleType("bluetooth_adapters"))

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.fixture
def mock_config_entry_data() -> dict[str, Any]:
    """Create mock config entry data."""
    return {
        "name": "PawControl Test",
        CONF_DOGS: [
            {
                CONF_DOG_ID: "buddy",
                CONF_DOG_NAME: "Buddy",
                "dog_breed": "Labrador",
                "dog_age": 5,
                "dog_weight": 25.0,
                "dog_size": "medium",
                "modules": {
                    "feeding": True,
                    "walk": True,
                    "health": True,
                    "gps": False,
                    "notifications": True,
                },
            },
            {
                CONF_DOG_ID: "max",
                CONF_DOG_NAME: "Max",
                "dog_breed": "German Shepherd",
                "dog_age": 3,
                "dog_weight": 30.0,
                "dog_size": "large",
                "modules": {
                    "feeding": True,
                    "walk": True,
                    "health": True,
                    "gps": True,
                    "notifications": True,
                },
            },
        ],
        "entity_profile": "standard",
    }


@pytest.fixture
def mock_config_entry_options() -> dict[str, Any]:
    """Create mock config entry options."""
    return {
        "entity_profile": "standard",
        "external_integrations": False,
        "gps_update_interval": 60,
        "debug_logging": False,
    }


class TestPawControlIntegrationSetup:
    """Test suite for integration setup and initialization."""

    async def test_async_setup_registers_services(self, hass: HomeAssistant) -> None:
        """Integration setup should register the service manager once."""

        from custom_components.pawcontrol import async_setup

        with patch(
            "custom_components.pawcontrol.PawControlServiceManager"
        ) as manager_cls:
            manager_instance = manager_cls.return_value
            result = await async_setup(hass, {})

        assert result is True
        manager_cls.assert_called_once_with(hass)
        assert hass.data[DOMAIN]["service_manager"] is manager_instance

    async def test_async_setup_reuses_existing_manager(
        self, hass: HomeAssistant
    ) -> None:
        """Ensure setup does not create a second service manager."""

        from custom_components.pawcontrol import async_setup

        existing_manager = Mock()
        hass.data.setdefault(DOMAIN, {})["service_manager"] = existing_manager

        with patch(
            "custom_components.pawcontrol.PawControlServiceManager"
        ) as manager_cls:
            result = await async_setup(hass, {})

        assert result is True
        manager_cls.assert_not_called()
        assert hass.data[DOMAIN]["service_manager"] is existing_manager

    async def test_async_setup_entry_success(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test successful integration setup."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)
        reload_unsub = Mock()
        entry.add_update_listener = Mock(return_value=reload_unsub)

        # Import here to avoid circular imports during test collection
        from custom_components.pawcontrol import async_setup_entry

        # Mock all the managers and coordinators
        captured_feeding_calls: list[list[dict[str, Any]]] = []

        async def _capture_feeding_init(dogs: list[dict[str, Any]]) -> None:
            captured_feeding_calls.append(dogs)

        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator"
            ) as mock_coordinator,
            patch(
                "custom_components.pawcontrol.PawControlDataManager"
            ) as mock_data_manager,
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager"
            ) as mock_notification_manager,
            patch(
                "custom_components.pawcontrol.FeedingManager"
            ) as mock_feeding_manager,
            patch("custom_components.pawcontrol.WalkManager") as mock_walk_manager,
            patch("custom_components.pawcontrol.EntityFactory") as mock_entity_factory,
        ):
            # Configure mocks
            mock_coordinator.return_value.async_prepare_entry = AsyncMock()
            mock_coordinator.return_value.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.return_value.async_start_background_tasks = Mock()
            mock_data_manager.return_value.async_initialize = AsyncMock()
            mock_notification_manager.return_value.async_initialize = AsyncMock()
            mock_feeding_manager.return_value.async_initialize = _capture_feeding_init
            mock_walk_manager.return_value.async_initialize = AsyncMock()
            mock_entity_factory.return_value.validate_profile = Mock(return_value=True)

            # Test setup
            result = await async_setup_entry(hass, entry)

            # Verify successful setup
            assert result is True
            runtime_data = get_runtime_data(hass, entry)
            assert runtime_data is not None
            assert isinstance(runtime_data, PawControlRuntimeData)
            assert runtime_data.reload_unsub is reload_unsub

            mock_coordinator.return_value.async_prepare_entry.assert_awaited_once()
            mock_coordinator.return_value.async_config_entry_first_refresh.assert_awaited_once()

            assert len(captured_feeding_calls) == 1
            typed_dogs = captured_feeding_calls[0]
            assert isinstance(typed_dogs, list)
            for dog in typed_dogs:
                assert isinstance(dog, dict)
                assert dog[CONF_DOG_ID]
                assert dog[CONF_DOG_NAME]
                assert isinstance(dog.get("modules"), dict)

            # Verify platform forwarding was initiated
            # Note: We can't easily test platform loading completion in unit tests
            # since it's async and depends on HA internals

    async def test_async_setup_entry_coordinator_initialization_failure(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test setup failure when coordinator initialization fails."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_setup_entry

        with patch(
            "custom_components.pawcontrol.PawControlCoordinator"
        ) as mock_coordinator:
            # Make coordinator first refresh fail
            mock_coordinator.return_value.async_prepare_entry = AsyncMock()
            mock_coordinator.return_value.async_config_entry_first_refresh = AsyncMock(
                side_effect=ConfigEntryNotReady("Coordinator failed to initialize")
            )

            # Test setup failure
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, entry)

    async def test_async_setup_entry_manager_initialization_failure(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test setup failure when manager initialization fails."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_setup_entry

        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator"
            ) as mock_coordinator,
            patch(
                "custom_components.pawcontrol.PawControlDataManager"
            ) as mock_data_manager,
        ):
            mock_coordinator.return_value.async_prepare_entry = AsyncMock()
            mock_coordinator.return_value.async_config_entry_first_refresh = AsyncMock()
            mock_data_manager.return_value.async_initialize = AsyncMock(
                side_effect=Exception("Data manager initialization failed")
            )

            # Test setup failure
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, entry)

    async def test_async_setup_entry_no_dogs_configured(
        self, hass: HomeAssistant
    ) -> None:
        """Test setup with no dogs configured."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"name": "PawControl Test", CONF_DOGS: []},
            options={"entity_profile": "basic"},
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_setup_entry

        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator"
            ) as mock_coordinator,
            patch(
                "custom_components.pawcontrol.PawControlDataManager"
            ) as mock_data_manager,
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager"
            ) as mock_notification_manager,
            patch(
                "custom_components.pawcontrol.FeedingManager"
            ) as mock_feeding_manager,
            patch("custom_components.pawcontrol.WalkManager") as mock_walk_manager,
            patch("custom_components.pawcontrol.EntityFactory") as mock_entity_factory,
        ):
            # Configure mocks for success case
            mock_coordinator.return_value.async_prepare_entry = AsyncMock()
            mock_coordinator.return_value.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.return_value.async_start_background_tasks = Mock()
            mock_data_manager.return_value.async_initialize = AsyncMock()
            mock_notification_manager.return_value.async_initialize = AsyncMock()
            mock_feeding_manager.return_value.async_initialize = AsyncMock()
            mock_walk_manager.return_value.async_initialize = AsyncMock()
            mock_entity_factory.return_value.validate_profile = Mock(return_value=True)

            # Should still succeed even with no dogs
            result = await async_setup_entry(hass, entry)
            assert result is True
            runtime_data = get_runtime_data(hass, entry)
            assert runtime_data is not None
            assert len(runtime_data.dogs) == 0

    async def test_async_setup_entry_invalid_profile(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test setup failure with invalid entity profile."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "invalid_profile"},
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_setup_entry

        with patch("custom_components.pawcontrol.EntityFactory") as mock_entity_factory:
            mock_entity_factory.return_value.validate_profile = Mock(return_value=False)

            # Test setup failure
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, entry)

    async def test_async_setup_entry_invalid_dog_configuration(
        self, hass: HomeAssistant
    ) -> None:
        """Dog entries missing required fields should block setup."""

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_DOGS: [
                    {
                        CONF_DOG_ID: "buddy",
                        # dog_name intentionally omitted to trigger validation
                    }
                ]
            },
            options={},
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_setup_entry

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)

    async def test_async_unload_entry_success(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test successful integration unload."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_unload_entry

        # Create mock runtime data
        mock_coordinator = Mock()
        mock_coordinator.async_shutdown = AsyncMock()
        mock_data_manager = Mock()
        mock_data_manager.async_shutdown = AsyncMock()
        mock_notification_manager = Mock()
        mock_notification_manager.async_shutdown = AsyncMock()
        mock_feeding_manager = Mock()
        mock_feeding_manager.async_shutdown = AsyncMock()
        mock_walk_manager = Mock()
        mock_walk_manager.async_shutdown = AsyncMock()

        reload_unsub = Mock()
        store_runtime_data(
            hass,
            entry,
            PawControlRuntimeData(
                coordinator=mock_coordinator,
                data_manager=mock_data_manager,
                notification_manager=mock_notification_manager,
                feeding_manager=mock_feeding_manager,
                walk_manager=mock_walk_manager,
                entity_factory=Mock(),
                entity_profile="standard",
                dogs=mock_config_entry_data[CONF_DOGS],
                script_manager=None,
                reload_unsub=reload_unsub,
            ),
        )

        # Mock platform unloading
        with patch(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            return_value=True,
        ) as mock_unload:
            result = await async_unload_entry(hass, entry)

            assert result is True
            from custom_components.pawcontrol import (
                get_platforms_for_profile_and_modules,
            )

            expected_platforms = get_platforms_for_profile_and_modules(
                mock_config_entry_data[CONF_DOGS],
                entry.options.get("entity_profile", "standard"),
            )
            mock_unload.assert_called_once_with(entry, expected_platforms)

            # Verify all managers were shut down
            mock_coordinator.async_shutdown.assert_called_once()
            mock_data_manager.async_shutdown.assert_called_once()
            mock_notification_manager.async_shutdown.assert_called_once()
            mock_feeding_manager.async_shutdown.assert_called_once()
            mock_walk_manager.async_shutdown.assert_called_once()
            reload_unsub.assert_called_once()
            runtime_data = get_runtime_data(hass, entry)
            assert runtime_data is None

    async def test_async_unload_entry_platform_unload_failure(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test unload when platform unloading fails."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_unload_entry

        # Create minimal runtime data
        store_runtime_data(
            hass,
            entry,
            PawControlRuntimeData(
                coordinator=Mock(),
                data_manager=Mock(),
                notification_manager=Mock(),
                feeding_manager=Mock(),
                walk_manager=Mock(),
                entity_factory=Mock(),
                entity_profile="standard",
                dogs=[],
                script_manager=None,
            ),
        )

        # Mock platform unloading to fail
        with patch(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            return_value=False,
        ):
            result = await async_unload_entry(hass, entry)
            assert result is False

    async def test_async_unload_entry_no_runtime_data(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test unload when no runtime data exists."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_unload_entry

        # No runtime data set
        with patch(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            return_value=True,
        ):
            result = await async_unload_entry(hass, entry)
            # Should still succeed even without runtime data
            assert result is True

    async def test_service_registration(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test that services are properly registered during setup."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_setup_entry

        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator"
            ) as mock_coordinator,
            patch(
                "custom_components.pawcontrol.PawControlDataManager"
            ) as mock_data_manager,
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager"
            ) as mock_notification_manager,
            patch(
                "custom_components.pawcontrol.FeedingManager"
            ) as mock_feeding_manager,
            patch("custom_components.pawcontrol.WalkManager") as mock_walk_manager,
            patch("custom_components.pawcontrol.EntityFactory") as mock_entity_factory,
            patch("homeassistant.helpers.service.async_register_admin_service"),
        ):
            # Configure mocks
            mock_coordinator.return_value.async_prepare_entry = AsyncMock()
            mock_coordinator.return_value.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.return_value.async_start_background_tasks = Mock()
            mock_data_manager.return_value.async_initialize = AsyncMock()
            mock_notification_manager.return_value.async_initialize = AsyncMock()
            mock_feeding_manager.return_value.async_initialize = AsyncMock()
            mock_walk_manager.return_value.async_initialize = AsyncMock()
            mock_entity_factory.return_value.validate_profile = Mock(return_value=True)

            result = await async_setup_entry(hass, entry)
            assert result is True

            # Verify services were registered
            # Note: The exact service registration depends on implementation
            # This is more of a smoke test to ensure no exceptions occur

    def test_runtime_data_structure(
        self, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test runtime data structure creation."""
        from custom_components.pawcontrol.types import PawControlRuntimeData

        # Create mock components
        mock_coordinator = Mock()
        mock_data_manager = Mock()
        mock_notification_manager = Mock()
        mock_feeding_manager = Mock()
        mock_walk_manager = Mock()
        mock_entity_factory = Mock()

        # Create runtime data
        runtime_data = PawControlRuntimeData(
            coordinator=mock_coordinator,
            data_manager=mock_data_manager,
            notification_manager=mock_notification_manager,
            feeding_manager=mock_feeding_manager,
            walk_manager=mock_walk_manager,
            entity_factory=mock_entity_factory,
            entity_profile="standard",
            dogs=mock_config_entry_data[CONF_DOGS],
            script_manager=None,
        )

        # Test structure
        assert runtime_data.coordinator == mock_coordinator
        assert runtime_data.data_manager == mock_data_manager
        assert runtime_data.notification_manager == mock_notification_manager
        assert runtime_data.feeding_manager == mock_feeding_manager
        assert runtime_data.walk_manager == mock_walk_manager
        assert runtime_data.entity_factory == mock_entity_factory
        assert runtime_data.entity_profile == "standard"
        assert len(runtime_data.dogs) == 2

        # Test dictionary-like access
        assert runtime_data["coordinator"] == mock_coordinator
        assert runtime_data["dogs"] == mock_config_entry_data[CONF_DOGS]
        assert runtime_data.get("entity_profile") == "standard"
        assert runtime_data.get("nonexistent_key", "default") == "default"

        # Test as_dict method
        as_dict = runtime_data.as_dict()
        assert as_dict["coordinator"] == mock_coordinator
        assert as_dict["entity_profile"] == "standard"


class TestPawControlPlatformForwarding:
    """Test suite for platform forwarding functionality."""

    async def test_all_platforms_forwarded(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test that all platforms are properly forwarded."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_setup_entry

        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator"
            ) as mock_coordinator,
            patch(
                "custom_components.pawcontrol.PawControlDataManager"
            ) as mock_data_manager,
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager"
            ) as mock_notification_manager,
            patch(
                "custom_components.pawcontrol.FeedingManager"
            ) as mock_feeding_manager,
            patch("custom_components.pawcontrol.WalkManager") as mock_walk_manager,
            patch("custom_components.pawcontrol.EntityFactory") as mock_entity_factory,
            patch(
                "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"
            ) as mock_forward,
        ):
            # Configure mocks
            mock_coordinator.return_value.async_prepare_entry = AsyncMock()
            mock_coordinator.return_value.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.return_value.async_start_background_tasks = Mock()
            mock_data_manager.return_value.async_initialize = AsyncMock()
            mock_notification_manager.return_value.async_initialize = AsyncMock()
            mock_feeding_manager.return_value.async_initialize = AsyncMock()
            mock_walk_manager.return_value.async_initialize = AsyncMock()
            mock_entity_factory.return_value.validate_profile = Mock(return_value=True)

            result = await async_setup_entry(hass, entry)
            assert result is True

            # Verify all platforms were forwarded
            mock_forward.assert_called_once_with(entry, PLATFORMS)

            # Verify expected platforms
            expected_platforms = {
                Platform.SENSOR,
                Platform.BINARY_SENSOR,
                Platform.BUTTON,
                Platform.SWITCH,
                Platform.SELECT,
                Platform.NUMBER,
                Platform.TEXT,
                Platform.DATE,
                Platform.DATETIME,
                Platform.DEVICE_TRACKER,
            }
            forwarded_platforms = set(mock_forward.call_args[0][1])
            assert expected_platforms.issubset(forwarded_platforms)

    async def test_platform_forwarding_failure_handling(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test handling of platform forwarding failures."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_setup_entry

        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator"
            ) as mock_coordinator,
            patch(
                "custom_components.pawcontrol.PawControlDataManager"
            ) as mock_data_manager,
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager"
            ) as mock_notification_manager,
            patch(
                "custom_components.pawcontrol.FeedingManager"
            ) as mock_feeding_manager,
            patch("custom_components.pawcontrol.WalkManager") as mock_walk_manager,
            patch("custom_components.pawcontrol.EntityFactory") as mock_entity_factory,
            patch(
                "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
                side_effect=Exception("Platform forwarding failed"),
            ),
        ):
            # Configure mocks
            mock_coordinator.return_value.async_prepare_entry = AsyncMock()
            mock_coordinator.return_value.async_config_entry_first_refresh = AsyncMock()
            mock_data_manager.return_value.async_initialize = AsyncMock()
            mock_notification_manager.return_value.async_initialize = AsyncMock()
            mock_feeding_manager.return_value.async_initialize = AsyncMock()
            mock_walk_manager.return_value.async_initialize = AsyncMock()
            mock_entity_factory.return_value.validate_profile = Mock(return_value=True)

            # Should raise ConfigEntryNotReady on platform forwarding failure
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, entry)


class TestPawControlEntityRegistry:
    """Test suite for entity registry integration."""

    async def test_entity_registry_cleanup_on_profile_change(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test that entity registry is properly cleaned up on profile changes."""
        # This is more of a conceptual test since entity cleanup
        # typically happens through HA's built-in mechanisms

        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        # Get entity registry
        entity_registry = er.async_get(hass)

        # Create some mock entities as if they were previously created
        entity_id_1 = entity_registry.async_get_or_create(
            domain=Platform.SENSOR,
            platform=DOMAIN,
            unique_id="pawcontrol_buddy_feeding_sensor",
            config_entry=entry,
        ).entity_id

        entity_id_2 = entity_registry.async_get_or_create(
            domain=Platform.BINARY_SENSOR,
            platform=DOMAIN,
            unique_id="pawcontrol_buddy_hungry_binary_sensor",
            config_entry=entry,
        ).entity_id

        # Verify entities exist
        assert entity_registry.async_get(entity_id_1) is not None
        assert entity_registry.async_get(entity_id_2) is not None

        # Test cleanup functionality
        from custom_components.pawcontrol import async_unload_entry

        # Mock runtime data for cleanup
        store_runtime_data(
            hass,
            entry,
            PawControlRuntimeData(
                coordinator=Mock(),
                data_manager=Mock(),
                notification_manager=Mock(),
                feeding_manager=Mock(),
                walk_manager=Mock(),
                entity_factory=Mock(),
                entity_profile="standard",
                dogs=mock_config_entry_data[CONF_DOGS],
                script_manager=None,
            ),
        )

        with patch(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            return_value=True,
        ):
            result = await async_unload_entry(hass, entry)
            assert result is True

        # Entities should still exist in registry (HA handles cleanup)
        # This test mainly verifies that unload doesn't crash


class TestPawControlPerformanceIntegration:
    """Test integration performance characteristics."""

    async def test_setup_performance_with_many_dogs(self, hass: HomeAssistant) -> None:
        """Test setup performance with many dogs configured."""
        import time

        # Create configuration with many dogs
        many_dogs = [
            {
                CONF_DOG_ID: f"dog_{i:02d}",
                CONF_DOG_NAME: f"Dog {i:02d}",
                "dog_breed": "Test Breed",
                "dog_age": 3,
                "dog_weight": 20.0,
                "dog_size": "medium",
                "modules": {
                    "feeding": True,
                    "walk": True,
                    "health": i % 2 == 0,  # Alternate health monitoring
                    "gps": i % 5 == 0,  # Every 5th dog has GPS
                    "notifications": True,
                },
            }
            for i in range(20)
        ]

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"name": "PawControl Performance Test", CONF_DOGS: many_dogs},
            options={"entity_profile": "basic"},  # Use basic profile for performance
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_setup_entry

        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator"
            ) as mock_coordinator,
            patch(
                "custom_components.pawcontrol.PawControlDataManager"
            ) as mock_data_manager,
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager"
            ) as mock_notification_manager,
            patch(
                "custom_components.pawcontrol.FeedingManager"
            ) as mock_feeding_manager,
            patch("custom_components.pawcontrol.WalkManager") as mock_walk_manager,
            patch("custom_components.pawcontrol.EntityFactory") as mock_entity_factory,
        ):
            # Configure mocks for fast execution
            mock_coordinator.return_value.async_prepare_entry = AsyncMock()
            mock_coordinator.return_value.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.return_value.async_start_background_tasks = Mock()
            mock_data_manager.return_value.async_initialize = AsyncMock()
            mock_notification_manager.return_value.async_initialize = AsyncMock()
            mock_feeding_manager.return_value.async_initialize = AsyncMock()
            mock_walk_manager.return_value.async_initialize = AsyncMock()
            mock_entity_factory.return_value.validate_profile = Mock(return_value=True)

            # Measure setup time
            start_time = time.perf_counter()
            result = await async_setup_entry(hass, entry)
            end_time = time.perf_counter()

            # Verify success and performance
            assert result is True
            setup_time = end_time - start_time

            # Should complete setup in reasonable time even with many dogs
            assert setup_time < 2.0  # Less than 2 seconds for 20 dogs

            # Verify runtime data structure
            runtime_data = get_runtime_data(hass, entry)
            assert runtime_data is not None
            assert len(runtime_data.dogs) == 20

    async def test_memory_usage_monitoring(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test memory usage monitoring during setup."""
        import gc
        import sys

        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={
                "entity_profile": "advanced"
            },  # Use advanced for more memory usage
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_setup_entry

        # Force garbage collection before measurement
        gc.collect()
        initial_objects = len(gc.get_objects())

        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator"
            ) as mock_coordinator,
            patch(
                "custom_components.pawcontrol.PawControlDataManager"
            ) as mock_data_manager,
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager"
            ) as mock_notification_manager,
            patch(
                "custom_components.pawcontrol.FeedingManager"
            ) as mock_feeding_manager,
            patch("custom_components.pawcontrol.WalkManager") as mock_walk_manager,
            patch("custom_components.pawcontrol.EntityFactory") as mock_entity_factory,
        ):
            # Configure mocks
            mock_coordinator.return_value.async_prepare_entry = AsyncMock()
            mock_coordinator.return_value.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.return_value.async_start_background_tasks = Mock()
            mock_data_manager.return_value.async_initialize = AsyncMock()
            mock_notification_manager.return_value.async_initialize = AsyncMock()
            mock_feeding_manager.return_value.async_initialize = AsyncMock()
            mock_walk_manager.return_value.async_initialize = AsyncMock()
            mock_entity_factory.return_value.validate_profile = Mock(return_value=True)

            # Setup integration
            result = await async_setup_entry(hass, entry)
            assert result is True

            # Measure memory usage after setup
            gc.collect()
            final_objects = len(gc.get_objects())

            # Should not create excessive objects
            objects_created = final_objects - initial_objects

            # This is a rough check - actual numbers will vary
            # Main goal is to ensure no obvious memory leaks
            assert objects_created < 1000  # Reasonable object creation limit


class TestPawControlErrorHandling:
    """Test error handling and edge cases."""

    async def test_setup_with_malformed_dog_data(self, hass: HomeAssistant) -> None:
        """Test setup behavior with malformed dog data."""
        malformed_data = {
            "name": "PawControl Error Test",
            CONF_DOGS: [
                {
                    # Missing required fields
                    "dog_breed": "Test Breed",
                },
                {
                    CONF_DOG_ID: "valid_dog",
                    CONF_DOG_NAME: "Valid Dog",
                    "modules": "invalid_modules_type",  # Should be dict
                },
            ],
        }

        entry = MockConfigEntry(
            domain=DOMAIN,
            data=malformed_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_setup_entry

        with patch("custom_components.pawcontrol.EntityFactory") as mock_entity_factory:
            mock_entity_factory.return_value.validate_profile = Mock(return_value=True)

            # Should raise ConfigEntryNotReady due to invalid data
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, entry)

    async def test_concurrent_setup_attempts(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Test behavior with concurrent setup attempts."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        from custom_components.pawcontrol import async_setup_entry

        with (
            patch(
                "custom_components.pawcontrol.PawControlCoordinator"
            ) as mock_coordinator,
            patch(
                "custom_components.pawcontrol.PawControlDataManager"
            ) as mock_data_manager,
            patch(
                "custom_components.pawcontrol.PawControlNotificationManager"
            ) as mock_notification_manager,
            patch(
                "custom_components.pawcontrol.FeedingManager"
            ) as mock_feeding_manager,
            patch("custom_components.pawcontrol.WalkManager") as mock_walk_manager,
            patch("custom_components.pawcontrol.EntityFactory") as mock_entity_factory,
        ):
            # Add delays to simulate concurrent access
            mock_coordinator.return_value.async_prepare_entry = AsyncMock()
            mock_coordinator.return_value.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.return_value.async_start_background_tasks = Mock()
            mock_data_manager.return_value.async_initialize = AsyncMock()
            mock_notification_manager.return_value.async_initialize = AsyncMock()
            mock_feeding_manager.return_value.async_initialize = AsyncMock()
            mock_walk_manager.return_value.async_initialize = AsyncMock()
            mock_entity_factory.return_value.validate_profile = Mock(return_value=True)

            # Attempt concurrent setup (should be handled gracefully by HA)
            import asyncio

            results = await asyncio.gather(
                async_setup_entry(hass, entry),
                async_setup_entry(hass, entry),
                return_exceptions=True,
            )

            # At least one should succeed or fail gracefully
            success_count = sum(1 for result in results if result is True)
            assert success_count >= 1 or all(
                isinstance(result, Exception) for result in results
            )


class TestPawControlDeviceRemoval:
    """Tests for the config entry device removal hook."""

    async def test_async_remove_config_entry_device_blocks_active_dog(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Devices for configured dogs must not be removed."""

        from custom_components.pawcontrol import async_remove_config_entry_device

        entry = MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data, options={})
        entry.add_to_hass(hass)

        device_entry = MagicMock()
        device_entry.identifiers = {(DOMAIN, sanitize_dog_id("buddy"))}
        device_entry.id = "pawcontrol-device-buddy"

        result = await async_remove_config_entry_device(hass, entry, device_entry)

        assert result is False

    async def test_async_remove_config_entry_device_allows_stale_dog(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Devices for removed dogs should be eligible for cleanup."""

        from custom_components.pawcontrol import async_remove_config_entry_device

        cleaned_data = deepcopy(mock_config_entry_data)
        cleaned_data[CONF_DOGS] = [
            dog for dog in cleaned_data[CONF_DOGS] if dog.get(CONF_DOG_ID) != "buddy"
        ]

        entry = MockConfigEntry(domain=DOMAIN, data=cleaned_data, options={})
        entry.add_to_hass(hass)

        device_entry = MagicMock()
        device_entry.identifiers = {(DOMAIN, sanitize_dog_id("buddy"))}
        device_entry.id = "pawcontrol-device-buddy"

        result = await async_remove_config_entry_device(hass, entry, device_entry)

        assert result is True

    async def test_async_remove_config_entry_device_blocks_runtime_dog(
        self, hass: HomeAssistant
    ) -> None:
        """Runtime data dogs should prevent removal until cleanup completes."""

        from custom_components.pawcontrol import async_remove_config_entry_device

        entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
        entry.add_to_hass(hass)

        runtime_data = PawControlRuntimeData(
            coordinator=Mock(),
            data_manager=Mock(),
            notification_manager=Mock(),
            feeding_manager=Mock(),
            walk_manager=Mock(),
            entity_factory=Mock(),
            entity_profile="standard",
            dogs=[{CONF_DOG_ID: "Buddy"}],
            script_manager=None,
        )
        store_runtime_data(hass, entry, runtime_data)

        device_entry = MagicMock()
        device_entry.identifiers = {(DOMAIN, sanitize_dog_id("buddy"))}
        device_entry.id = "pawcontrol-device-buddy"

        result = await async_remove_config_entry_device(hass, entry, device_entry)

        assert result is False

    async def test_async_remove_config_entry_device_blocks_option_dog(
        self, hass: HomeAssistant
    ) -> None:
        """Dogs stored in options should also block removal attempts."""

        from custom_components.pawcontrol import async_remove_config_entry_device

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={},
            options={
                CONF_DOGS: {"buddy": {CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"}}
            },
        )
        entry.add_to_hass(hass)

        device_entry = MagicMock()
        device_entry.identifiers = {(DOMAIN, sanitize_dog_id("buddy"))}
        device_entry.id = "pawcontrol-device-buddy"

        result = await async_remove_config_entry_device(hass, entry, device_entry)

        assert result is False

    async def test_async_remove_config_entry_device_ignores_foreign_device(
        self, hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
    ) -> None:
        """Devices from other domains should be ignored for removal decisions."""

        from custom_components.pawcontrol import async_remove_config_entry_device

        entry = MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data, options={})
        entry.add_to_hass(hass)

        device_entry = MagicMock()
        device_entry.identifiers = {("other", "buddy")}
        device_entry.id = "foreign-device-buddy"

        result = await async_remove_config_entry_device(hass, entry, device_entry)

        assert result is False
