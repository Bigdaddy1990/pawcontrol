"""Tests for Paw Control Dashboard Generator.

Tests the comprehensive dashboard creation, card generation, and Lovelace
integration functionality with full async operation and error handling coverage.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.dashboard_generator import (
    DASHBOARD_STORAGE_VERSION,
    DEFAULT_DASHBOARD_TITLE,
    DEFAULT_DASHBOARD_URL,
    DiscoveredDevice,
    PawControlDashboardGenerator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry for testing."""
    return MagicMock(spec=ConfigEntry, entry_id="test_entry_123")


@pytest.fixture
def sample_dogs_config():
    """Sample dogs configuration for testing."""
    return [
        {
            CONF_DOG_ID: "max",
            CONF_DOG_NAME: "Max",
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_HEALTH: True,
                MODULE_GPS: False,
            },
        },
        {
            CONF_DOG_ID: "bella",
            CONF_DOG_NAME: "Bella",
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: False,
                MODULE_HEALTH: True,
                MODULE_GPS: True,
            },
        },
    ]


@pytest.fixture
async def dashboard_generator(hass: HomeAssistant, mock_config_entry):
    """Create a dashboard generator for testing."""
    generator = PawControlDashboardGenerator(hass, mock_config_entry)

    # Mock the store to avoid file operations in tests
    with patch.object(generator, "_store") as mock_store:
        mock_store.async_load.return_value = None
        mock_store.async_save = AsyncMock()
        mock_store.async_remove = AsyncMock()

        await generator.async_initialize()
        yield generator


class TestPawControlDashboardGenerator:
    """Test the PawControlDashboardGenerator class."""

    async def test_initialization(self, hass: HomeAssistant, mock_config_entry):
        """Test dashboard generator initialization."""
        generator = PawControlDashboardGenerator(hass, mock_config_entry)

        assert not generator._initialized
        assert generator.hass == hass
        assert generator.entry == mock_config_entry
        assert generator._dashboards == {}

        # Test initialization with mocked store
        with patch.object(generator, "_store") as mock_store:
            mock_store.async_load.return_value = {
                "dashboards": {"test": {"title": "Test Dashboard"}}
            }

            await generator.async_initialize()

            assert generator._initialized
            assert "test" in generator._dashboards
            mock_store.async_load.assert_called_once()

    async def test_initialization_error_handling(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test initialization error handling."""
        generator = PawControlDashboardGenerator(hass, mock_config_entry)

        with patch.object(generator, "_store") as mock_store:
            mock_store.async_load.side_effect = Exception("Storage error")

            # Should not raise, should initialize with empty dashboards
            await generator.async_initialize()

            assert generator._initialized
            assert generator._dashboards == {}

    async def test_double_initialization(self, dashboard_generator):
        """Test that double initialization is handled properly."""
        # Generator should already be initialized from fixture
        assert dashboard_generator._initialized

        # Second initialization should be no-op
        with patch.object(dashboard_generator, "_store") as mock_store:
            await dashboard_generator.async_initialize()
            mock_store.async_load.assert_not_called()

    async def test_create_main_dashboard(self, dashboard_generator, sample_dogs_config):
        """Test main dashboard creation."""
        options = {
            "title": "My Dogs Dashboard",
            "url": "my-dogs",
            "show_statistics": True,
            "show_settings": True,
        }

        with patch.object(
            dashboard_generator, "_create_lovelace_dashboard"
        ) as mock_create:
            mock_create.return_value = "/path/to/dashboard"

            dashboard_url = await dashboard_generator.async_create_dashboard(
                sample_dogs_config, options
            )

            assert dashboard_url.startswith("/my-dogs")
            mock_create.assert_called_once()

            # Verify dashboard was stored
            stored_dashboards = dashboard_generator._dashboards
            assert len(stored_dashboards) == 1

            dashboard_info = list(stored_dashboards.values())[0]
            assert dashboard_info["title"] == "My Dogs Dashboard"
            assert dashboard_info["type"] == "main"
            assert dashboard_info["dogs"] == ["max", "bella"]

    async def test_create_main_dashboard_with_defaults(
        self, dashboard_generator, sample_dogs_config
    ):
        """Test main dashboard creation with default options."""
        with patch.object(
            dashboard_generator, "_create_lovelace_dashboard"
        ) as mock_create:
            mock_create.return_value = "/path/to/dashboard"

            dashboard_url = await dashboard_generator.async_create_dashboard(
                sample_dogs_config
            )

            assert dashboard_url.startswith(f"/{DEFAULT_DASHBOARD_URL}")

            dashboard_info = list(dashboard_generator._dashboards.values())[0]
            assert dashboard_info["title"] == DEFAULT_DASHBOARD_TITLE

    async def test_create_main_dashboard_empty_dogs_config(self, dashboard_generator):
        """Test main dashboard creation with empty dogs config."""
        with pytest.raises(
            ValueError, match="At least one dog configuration is required"
        ):
            await dashboard_generator.async_create_dashboard([])

    async def test_create_dog_dashboard(self, dashboard_generator):
        """Test individual dog dashboard creation."""
        dog_config = {
            CONF_DOG_ID: "rex",
            CONF_DOG_NAME: "Rex",
            "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
        }

        with patch.object(
            dashboard_generator, "_create_lovelace_dashboard"
        ) as mock_create:
            mock_create.return_value = "/path/to/dog-dashboard"

            dashboard_url = await dashboard_generator.async_create_dog_dashboard(
                dog_config
            )

            assert dashboard_url == "/paw-rex"
            mock_create.assert_called_once()

            dashboard_info = list(dashboard_generator._dashboards.values())[0]
            assert dashboard_info["title"] == "🐕 Rex"
            assert dashboard_info["type"] == "dog"
            assert dashboard_info["dog_id"] == "rex"

    async def test_create_dog_dashboard_invalid_config(self, dashboard_generator):
        """Test dog dashboard creation with invalid config."""
        # Missing dog_id
        with pytest.raises(ValueError, match="Dog ID is required"):
            await dashboard_generator.async_create_dog_dashboard(
                {CONF_DOG_NAME: "Test"}
            )

        # Missing dog_name
        with pytest.raises(ValueError, match="Dog name is required"):
            await dashboard_generator.async_create_dog_dashboard({CONF_DOG_ID: "test"})

    async def test_update_dashboard(self, dashboard_generator, sample_dogs_config):
        """Test dashboard update functionality."""
        # First create a dashboard
        with patch.object(
            dashboard_generator, "_create_lovelace_dashboard"
        ) as mock_create:
            mock_create.return_value = "/path/to/dashboard"
            dashboard_url = await dashboard_generator.async_create_dashboard(
                sample_dogs_config
            )

        # Now update it
        new_options = {"title": "Updated Title"}

        with patch.object(
            dashboard_generator, "_update_lovelace_dashboard"
        ) as mock_update:
            result = await dashboard_generator.async_update_dashboard(
                dashboard_url.lstrip("/"), sample_dogs_config, new_options
            )

            assert result is True
            mock_update.assert_called_once()

            # Verify options were updated
            dashboard_info = list(dashboard_generator._dashboards.values())[0]
            assert dashboard_info["options"] == new_options

    async def test_update_nonexistent_dashboard(
        self, dashboard_generator, sample_dogs_config
    ):
        """Test updating a dashboard that doesn't exist."""
        result = await dashboard_generator.async_update_dashboard(
            "nonexistent", sample_dogs_config
        )
        assert result is False

    async def test_delete_dashboard(self, dashboard_generator, sample_dogs_config):
        """Test dashboard deletion."""
        # First create a dashboard
        with patch.object(
            dashboard_generator, "_create_lovelace_dashboard"
        ) as mock_create:
            mock_create.return_value = "/path/to/dashboard"
            dashboard_url = await dashboard_generator.async_create_dashboard(
                sample_dogs_config
            )

        # Now delete it
        dashboard_key = dashboard_url.lstrip("/")

        with patch.object(
            dashboard_generator, "_delete_lovelace_dashboard"
        ) as mock_delete:
            result = await dashboard_generator.async_delete_dashboard(dashboard_key)

            assert result is True
            mock_delete.assert_called_once()
            assert dashboard_key not in dashboard_generator._dashboards

    async def test_delete_nonexistent_dashboard(self, dashboard_generator):
        """Test deleting a dashboard that doesn't exist."""
        result = await dashboard_generator.async_delete_dashboard("nonexistent")
        assert result is False

    async def test_cleanup(self, dashboard_generator, sample_dogs_config):
        """Test dashboard cleanup functionality."""
        # Create multiple dashboards
        with patch.object(
            dashboard_generator, "_create_lovelace_dashboard"
        ) as mock_create:
            mock_create.return_value = "/path/to/dashboard"

            await dashboard_generator.async_create_dashboard(sample_dogs_config)
            await dashboard_generator.async_create_dog_dashboard(sample_dogs_config[0])

        assert len(dashboard_generator._dashboards) == 2

        # Cleanup
        with patch.object(
            dashboard_generator, "_delete_lovelace_dashboard"
        ) as mock_delete:
            await dashboard_generator.async_cleanup()

            assert len(dashboard_generator._dashboards) == 0
            assert mock_delete.call_count == 2

    async def test_generate_overview_cards(
        self, dashboard_generator, sample_dogs_config
    ):
        """Test overview cards generation."""
        options = {"title": "Test Dashboard", "show_activity_summary": True}

        cards = await dashboard_generator._generate_overview_cards(
            sample_dogs_config, options
        )

        assert len(cards) >= 3  # Welcome, dog grid, actions, activity
        assert any("Test Dashboard" in str(card) for card in cards)
        assert any("grid" in card.get("type", "") for card in cards)

    async def test_generate_dog_cards(self, dashboard_generator):
        """Test individual dog cards generation."""
        dog_config = {
            CONF_DOG_ID: "test_dog",
            CONF_DOG_NAME: "Test Dog",
            "modules": {MODULE_FEEDING: True, MODULE_WALK: True, MODULE_HEALTH: True},
        }
        theme = {"primary": "#4CAF50", "accent": "#8BC34A"}
        options = {"show_activity_graph": True}

        cards = await dashboard_generator._generate_dog_cards(
            dog_config, theme, options
        )

        assert len(cards) >= 4  # Header, status, actions, activity graph

        # Check for expected card types
        card_types = [card.get("type") for card in cards]
        assert "picture-entity" in card_types
        assert "entities" in card_types
        assert "history-graph" in card_types

    async def test_generate_feeding_cards(self, dashboard_generator):
        """Test feeding-specific cards generation."""
        dog_config = {CONF_DOG_ID: "test_dog", CONF_DOG_NAME: "Test Dog"}

        cards = await dashboard_generator._generate_feeding_cards(dog_config, {})

        assert len(cards) >= 3  # Schedule, controls, history

        # Verify feeding entities are included
        entities_cards = [card for card in cards if card.get("type") == "entities"]
        assert len(entities_cards) >= 1

        # Check for feeding control buttons
        button_cards = [
            card
            for card in cards
            if card.get("type") == "horizontal-stack" and "cards" in card
        ]
        assert len(button_cards) >= 1

    async def test_generate_walk_cards(self, dashboard_generator):
        """Test walk-specific cards generation."""
        dog_config = {CONF_DOG_ID: "test_dog", CONF_DOG_NAME: "Test Dog"}

        cards = await dashboard_generator._generate_walk_cards(dog_config, {})

        assert len(cards) >= 3  # Status, controls (conditional), history

        # Check for conditional cards (start/end walk buttons)
        conditional_cards = [
            card for card in cards if card.get("type") == "conditional"
        ]
        assert len(conditional_cards) >= 2  # Start and end walk buttons

    async def test_generate_health_cards(self, dashboard_generator):
        """Test health-specific cards generation."""
        dog_config = {CONF_DOG_ID: "test_dog", CONF_DOG_NAME: "Test Dog"}

        cards = await dashboard_generator._generate_health_cards(dog_config, {})

        assert len(cards) >= 4  # Metrics, buttons, weight graph, schedule

        # Check for health entities
        entities_cards = [card for card in cards if card.get("type") == "entities"]
        assert len(entities_cards) >= 2  # Metrics and schedule

        # Check for weight tracking graph
        history_cards = [card for card in cards if card.get("type") == "history-graph"]
        assert len(history_cards) >= 1

    async def test_generate_gps_cards(self, dashboard_generator):
        """Test GPS-specific cards generation."""
        dog_config = {CONF_DOG_ID: "test_dog", CONF_DOG_NAME: "Test Dog"}
        options = {"dark_mode": True}

        cards = await dashboard_generator._generate_gps_cards(dog_config, options)

        assert len(cards) >= 4  # Map, status, geofence, history

        # Check for map card
        map_cards = [card for card in cards if card.get("type") == "map"]
        assert len(map_cards) >= 1
        assert map_cards[0]["dark_mode"] is True

    async def test_generate_statistics_cards(
        self, dashboard_generator, sample_dogs_config
    ):
        """Test statistics cards generation."""
        cards = await dashboard_generator._generate_statistics_cards(
            sample_dogs_config, {}
        )

        assert len(cards) >= 2  # Activity stats, summary at minimum

        # Check for statistics graphs
        stats_cards = [card for card in cards if card.get("type") == "statistics-graph"]
        assert len(stats_cards) >= 1

        # Check for summary markdown
        markdown_cards = [card for card in cards if card.get("type") == "markdown"]
        assert len(markdown_cards) >= 1

    async def test_generate_settings_cards(
        self, dashboard_generator, sample_dogs_config
    ):
        """Test settings cards generation."""
        cards = await dashboard_generator._generate_settings_cards(
            sample_dogs_config, {}
        )

        assert len(cards) >= 3  # Integration settings, per-dog settings, maintenance

        # Check for maintenance buttons
        button_cards = [
            card for card in cards if card.get("type") == "horizontal-stack"
        ]
        assert len(button_cards) >= 1

    async def test_create_lovelace_dashboard_file_operations(
        self, dashboard_generator, tmp_path
    ):
        """Test Lovelace dashboard file creation."""
        # Mock hass.config.path to return test directory
        with patch.object(dashboard_generator.hass.config, "path") as mock_path:
            storage_dir = tmp_path / ".storage"
            storage_dir.mkdir()
            mock_path.return_value = str(storage_dir)

            config = {"views": [{"title": "Test"}]}

            # Use aiofiles mock since we're in test environment
            with patch("aiofiles.open", create=True) as mock_open:
                mock_file = AsyncMock()
                mock_open.return_value.__aenter__.return_value = mock_file

                result = await dashboard_generator._create_lovelace_dashboard(
                    "test-dashboard", "Test Dashboard", config, "mdi:test", True
                )

                assert "test-dashboard" in result
                mock_file.write.assert_called_once()

                # Verify the written content structure
                written_content = mock_file.write.call_args[0][0]
                dashboard_data = json.loads(written_content)

                assert dashboard_data["data"]["config"] == config
                assert dashboard_data["data"]["title"] == "Test Dashboard"
                assert dashboard_data["data"]["icon"] == "mdi:test"

    async def test_dashboard_file_operations_error_handling(self, dashboard_generator):
        """Test error handling in dashboard file operations."""
        config = {"views": []}

        with patch("aiofiles.open", side_effect=Exception("File error")):
            with pytest.raises(
                HomeAssistantError, match="Dashboard file creation failed"
            ):
                await dashboard_generator._create_lovelace_dashboard(
                    "test", "Test", config, "mdi:test", True
                )

    async def test_callback_methods(self, dashboard_generator, sample_dogs_config):
        """Test callback methods for dashboard info retrieval."""
        # Create a dashboard first
        with patch.object(
            dashboard_generator, "_create_lovelace_dashboard"
        ) as mock_create:
            mock_create.return_value = "/path/to/dashboard"
            dashboard_url = await dashboard_generator.async_create_dashboard(
                sample_dogs_config
            )

        dashboard_key = dashboard_url.lstrip("/")

        # Test get_dashboard_info
        info = dashboard_generator.get_dashboard_info(dashboard_key)
        assert info is not None
        assert info["type"] == "main"

        # Test get_all_dashboards
        all_dashboards = dashboard_generator.get_all_dashboards()
        assert len(all_dashboards) == 1
        assert dashboard_key in all_dashboards

        # Test is_initialized
        assert dashboard_generator.is_initialized() is True

    async def test_validate_stored_dashboards(self, dashboard_generator, tmp_path):
        """Test stored dashboard validation and cleanup."""
        # Add some test dashboards with different validity states
        dashboard_generator._dashboards = {
            "valid": {
                "title": "Valid Dashboard",
                "created": "2023-01-01T00:00:00",
                "type": "main",
                "path": str(tmp_path / "valid.json"),
            },
            "invalid_missing_fields": {
                "title": "Invalid Dashboard",
                # Missing required fields
            },
            "invalid_missing_file": {
                "title": "Invalid Dashboard",
                "created": "2023-01-01T00:00:00",
                "type": "main",
                "path": "/nonexistent/path.json",
            },
        }

        # Create the valid dashboard file
        (tmp_path / "valid.json").touch()

        with patch.object(dashboard_generator, "_save_dashboards") as mock_save:
            await dashboard_generator._validate_stored_dashboards()

            # Should only have the valid dashboard left
            assert "valid" in dashboard_generator._dashboards
            assert "invalid_missing_fields" not in dashboard_generator._dashboards
            assert "invalid_missing_file" not in dashboard_generator._dashboards

            mock_save.assert_called_once()

    async def test_concurrent_operations(self, dashboard_generator, sample_dogs_config):
        """Test concurrent dashboard operations with proper locking."""
        with patch.object(
            dashboard_generator, "_create_lovelace_dashboard"
        ) as mock_create:
            mock_create.return_value = "/path/to/dashboard"

            # Run multiple dashboard creations concurrently
            tasks = [
                dashboard_generator.async_create_dashboard(
                    sample_dogs_config, {"url": f"test-{i}"}
                )
                for i in range(3)
            ]

            results = await asyncio.gather(*tasks)

            assert len(results) == 3
            assert all(url.startswith("/test-") for url in results)
            assert len(dashboard_generator._dashboards) == 3


class TestDashboardGeneratorErrorHandling:
    """Test error handling scenarios in dashboard generator."""

    async def test_storage_errors(self, hass: HomeAssistant, mock_config_entry):
        """Test handling of storage errors."""
        generator = PawControlDashboardGenerator(hass, mock_config_entry)

        with patch.object(generator, "_store") as mock_store:
            mock_store.async_save.side_effect = Exception("Storage error")

            await generator.async_initialize()

            # Should handle save errors gracefully
            with pytest.raises(
                HomeAssistantError, match="Dashboard storage save failed"
            ):
                await generator._save_dashboards()

    async def test_lovelace_creation_errors(
        self, dashboard_generator, sample_dogs_config
    ):
        """Test handling of Lovelace creation errors."""
        with patch.object(
            dashboard_generator, "_create_lovelace_dashboard"
        ) as mock_create:
            mock_create.side_effect = Exception("Lovelace error")

            with pytest.raises(HomeAssistantError, match="Dashboard creation failed"):
                await dashboard_generator.async_create_dashboard(sample_dogs_config)

    async def test_update_errors(self, dashboard_generator, sample_dogs_config):
        """Test handling of dashboard update errors."""
        # Create a dashboard first
        with patch.object(
            dashboard_generator, "_create_lovelace_dashboard"
        ) as mock_create:
            mock_create.return_value = "/path/to/dashboard"
            dashboard_url = await dashboard_generator.async_create_dashboard(
                sample_dogs_config
            )

        # Now test update error
        with patch.object(
            dashboard_generator, "_update_lovelace_dashboard"
        ) as mock_update:
            mock_update.side_effect = Exception("Update error")

            result = await dashboard_generator.async_update_dashboard(
                dashboard_url.lstrip("/"), sample_dogs_config
            )

            assert result is False

    async def test_cleanup_with_errors(self, dashboard_generator, sample_dogs_config):
        """Test cleanup when some operations fail."""
        # Create a dashboard
        with patch.object(
            dashboard_generator, "_create_lovelace_dashboard"
        ) as mock_create:
            mock_create.return_value = "/path/to/dashboard"
            await dashboard_generator.async_create_dashboard(sample_dogs_config)

        # Test cleanup with partial failures
        with patch.object(
            dashboard_generator, "_delete_lovelace_dashboard"
        ) as mock_delete:
            mock_delete.side_effect = Exception("Delete error")

            # Should not raise, should continue cleanup
            await dashboard_generator.async_cleanup()

            # Storage should still be cleared
            assert len(dashboard_generator._dashboards) == 0
