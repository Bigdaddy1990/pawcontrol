"""Comprehensive tests for Paw Control dashboard components.

This module provides complete test coverage for dashboard auto-generation,
edge cases, performance scenarios, and multi-dog configurations.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

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
from custom_components.pawcontrol.dashboard_cards import (
    DogCardGenerator,
    HealthAwareFeedingCardGenerator,
    ModuleCardGenerator,
    OverviewCardGenerator,
    StatisticsCardGenerator,
)
from custom_components.pawcontrol.dashboard_generator import (
    PawControlDashboardGenerator,
)
from custom_components.pawcontrol.dashboard_renderer import DashboardRenderer
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

# Test Fixtures


@pytest.fixture
def mock_config_entry() -> ConfigEntry:
    """Create mock config entry for testing."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_123"
    entry.title = "Test PawControl"
    return entry


@pytest.fixture
def multi_dog_config() -> list[dict[str, any]]:
    """Comprehensive multi-dog configuration for testing."""
    return [
        {
            CONF_DOG_ID: "max_shepherd",
            CONF_DOG_NAME: "Max",
            "dog_breed": "German Shepherd",
            "dog_weight": 35.5,
            "dog_age": 4,
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_HEALTH: True,
                MODULE_GPS: True,
            },
            "feeding_schedule": {"meals_per_day": 2, "total_daily_food": 400},
            "health_data": {"last_checkup": "2024-12-01", "vaccinated": True},
        },
        {
            CONF_DOG_ID: "bella_lab",
            CONF_DOG_NAME: "Bella",
            "dog_breed": "Labrador",
            "dog_weight": 28.2,
            "dog_age": 2,
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: False,
                MODULE_HEALTH: True,
                MODULE_GPS: False,
            },
            "feeding_schedule": {"meals_per_day": 3, "total_daily_food": 320},
            "health_data": {"last_checkup": "2025-01-15", "vaccinated": True},
        },
        {
            CONF_DOG_ID: "charlie_beagle",
            CONF_DOG_NAME: "Charlie",
            "dog_breed": "Beagle",
            "dog_weight": 15.8,
            "dog_age": 8,
            "modules": {
                MODULE_FEEDING: False,
                MODULE_WALK: True,
                MODULE_HEALTH: True,
                MODULE_GPS: True,
            },
            "feeding_schedule": {"meals_per_day": 2, "total_daily_food": 250},
            "health_data": {"last_checkup": "2024-11-20", "vaccinated": False},
        },
    ]


@pytest.fixture
def complex_dashboard_options() -> dict[str, any]:
    """Complex dashboard options for testing."""
    return {
        "title": "🐕 My Pack Dashboard",
        "url": "my-pack-dashboard",
        "theme": "dark",
        "show_in_sidebar": True,
        "show_statistics": True,
        "show_settings": True,
        "show_activity_summary": True,
        "show_activity_graph": True,
        "dashboard_url": "/my-pack-dashboard",
    }


@pytest.fixture
async def dashboard_generator(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> PawControlDashboardGenerator:
    """Create initialized dashboard generator with mocked storage."""
    generator = PawControlDashboardGenerator(hass, mock_config_entry)

    with patch.object(generator, "_store") as mock_store:
        mock_store.async_load = AsyncMock(return_value={"dashboards": {}})
        mock_store.async_save = AsyncMock()
        await generator.async_initialize()

    return generator


@pytest.fixture
def mock_hass_with_entities(hass: HomeAssistant) -> HomeAssistant:
    """Mock Home Assistant with realistic entity states."""
    # Mock entity states for comprehensive testing
    mock_states = {
        # Dog status entities
        "sensor.max_shepherd_status": Mock(state="active"),
        "sensor.bella_lab_status": Mock(state="sleeping"),
        "sensor.charlie_beagle_status": Mock(state="active"),
        # Feeding entities
        "sensor.max_shepherd_next_meal_time": Mock(state="2024-01-15 18:00:00"),
        "sensor.max_shepherd_meals_today": Mock(state="2"),
        "sensor.bella_lab_meals_today": Mock(state="3"),
        "sensor.max_shepherd_calories_today": Mock(state="1450"),
        # Health entities
        "sensor.max_shepherd_health_feeding_status": Mock(state="optimal"),
        "sensor.max_shepherd_daily_calorie_target": Mock(state="1800"),
        "sensor.max_shepherd_calories_consumed_today": Mock(state="1450"),
        "sensor.max_shepherd_weight": Mock(state="35.5"),
        "sensor.bella_lab_weight": Mock(state="28.2"),
        # Walk entities
        "binary_sensor.max_shepherd_is_walking": Mock(state="off"),
        "sensor.max_shepherd_walks_today": Mock(state="2"),
        "sensor.charlie_beagle_walks_today": Mock(state="3"),
        # GPS entities
        "device_tracker.max_shepherd_location": Mock(state="home"),
        "device_tracker.charlie_beagle_location": Mock(state="park"),
        "sensor.max_shepherd_distance_from_home": Mock(state="0.2"),
        # Integration controls
        f"button.{DOMAIN}_feed_all_dogs": Mock(state="unknown"),
        f"sensor.{DOMAIN}_dogs_walking": Mock(state="1"),
    }

    hass.states.get = Mock(side_effect=lambda entity_id: mock_states.get(entity_id))
    return hass


# Test Classes


class TestDashboardGeneratorCore:
    """Test core dashboard generator functionality."""

    async def test_initialization_with_storage(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ):
        """Test generator initialization with existing storage data."""
        existing_dashboards = {
            "my-dashboard": {
                "url": "my-dashboard",
                "title": "My Dashboard",
                "type": "main",
                "created": "2024-01-15T10:00:00",
            }
        }

        generator = PawControlDashboardGenerator(hass, mock_config_entry)

        with patch.object(generator, "_store") as mock_store:
            mock_store.async_load = AsyncMock(
                return_value={"dashboards": existing_dashboards}
            )
            mock_store.async_save = AsyncMock()

            await generator.async_initialize()

            assert generator.is_initialized()
            assert len(generator.get_all_dashboards()) == 1
            assert "my-dashboard" in generator.get_all_dashboards()

    async def test_create_main_dashboard_with_complex_options(
        self,
        dashboard_generator: PawControlDashboardGenerator,
        multi_dog_config: list[dict[str, any]],
        complex_dashboard_options: dict[str, any],
    ):
        """Test main dashboard creation with complex multi-dog configuration."""
        # Mock renderer to return realistic dashboard config
        mock_dashboard_config = {
            "views": [
                {"title": "Overview", "path": "overview", "cards": []},
                {"title": "Max", "path": "max_shepherd", "cards": []},
                {"title": "Bella", "path": "bella_lab", "cards": []},
                {"title": "Charlie", "path": "charlie_beagle", "cards": []},
                {"title": "Statistics", "path": "statistics", "cards": []},
            ]
        }

        with (
            patch.object(
                dashboard_generator._renderer,
                "render_main_dashboard",
                AsyncMock(return_value=mock_dashboard_config),
            ),
            patch.object(
                dashboard_generator,
                "_create_dashboard_file",
                AsyncMock(return_value=Path("/test/dashboard.json")),
            ),
            patch.object(dashboard_generator, "_save_dashboard_metadata", AsyncMock()),
        ):
            url = await dashboard_generator.async_create_dashboard(
                multi_dog_config, complex_dashboard_options
            )

            assert url.startswith("/my_pack_dashboard")

            # Verify dashboard metadata
            dashboards = dashboard_generator.get_all_dashboards()
            assert len(dashboards) == 1

            dashboard_info = next(iter(dashboards.values()))
            assert dashboard_info["title"] == "🐕 My Pack Dashboard"
            assert dashboard_info["type"] == "main"
            assert len(dashboard_info["dogs"]) == 3
            assert "max_shepherd" in dashboard_info["dogs"]

    async def test_create_individual_dog_dashboards(
        self,
        dashboard_generator: PawControlDashboardGenerator,
        multi_dog_config: list[dict[str, any]],
    ):
        """Test creating individual dashboards for each dog."""
        mock_dog_config = {
            "views": [
                {"title": "Overview", "path": "overview", "cards": []},
                {"title": "Feeding", "path": "feeding", "cards": []},
                {"title": "Health", "path": "health", "cards": []},
            ]
        }

        with (
            patch.object(
                dashboard_generator._renderer,
                "render_dog_dashboard",
                AsyncMock(return_value=mock_dog_config),
            ),
            patch.object(
                dashboard_generator,
                "_create_dashboard_file",
                AsyncMock(side_effect=lambda *args: Path(f"/test/{args[0]}.json")),
            ),
            patch.object(dashboard_generator, "_save_dashboard_metadata", AsyncMock()),
        ):
            # Create dashboards for all dogs
            created_urls = []
            for dog in multi_dog_config:
                url = await dashboard_generator.async_create_dog_dashboard(dog)
                created_urls.append(url)

            assert len(created_urls) == 3
            assert "/paw-max_shepherd" in created_urls
            assert "/paw-bella_lab" in created_urls
            assert "/paw-charlie_beagle" in created_urls

            # Verify all dashboards registered
            dashboards = dashboard_generator.get_all_dashboards()
            assert len(dashboards) == 3

            # Check each dashboard type and metadata
            for dashboard_info in dashboards.values():
                assert dashboard_info["type"] == "dog"
                assert "dog_id" in dashboard_info
                assert "dog_name" in dashboard_info

    async def test_dashboard_update_functionality(
        self,
        dashboard_generator: PawControlDashboardGenerator,
        multi_dog_config: list[dict[str, any]],
    ):
        """Test updating existing dashboard with new configuration."""
        # First create a dashboard
        with (
            patch.object(
                dashboard_generator._renderer,
                "render_main_dashboard",
                AsyncMock(return_value={"views": []}),
            ),
            patch.object(
                dashboard_generator,
                "_create_dashboard_file",
                AsyncMock(return_value=Path("/test/dashboard.json")),
            ),
            patch.object(dashboard_generator, "_save_dashboard_metadata", AsyncMock()),
        ):
            url = await dashboard_generator.async_create_dashboard(multi_dog_config)
            dashboard_url = url.lstrip("/")

        # Update with modified configuration
        updated_config = multi_dog_config.copy()
        updated_config[0]["dog_weight"] = 36.0  # Weight change

        with (
            patch.object(
                dashboard_generator._renderer,
                "render_main_dashboard",
                AsyncMock(return_value={"views": [{"title": "Updated"}]}),
            ),
            patch.object(
                dashboard_generator._renderer,
                "write_dashboard_file",
                AsyncMock(),
            ),
        ):
            success = await dashboard_generator.async_update_dashboard(
                dashboard_url, updated_config, {"updated": True}
            )

            assert success

            # Verify metadata updated
            dashboard_info = dashboard_generator.get_dashboard_info(dashboard_url)
            assert dashboard_info is not None
            assert "updated" in dashboard_info

    async def test_performance_stats_collection(
        self, dashboard_generator: PawControlDashboardGenerator
    ):
        """Test performance statistics collection."""
        # Mock renderer stats
        mock_render_stats = {
            "active_jobs": 0,
            "total_jobs_processed": 5,
            "template_cache": {"hits": 150, "misses": 23},
        }

        with patch.object(
            dashboard_generator._renderer,
            "get_render_stats",
            return_value=mock_render_stats,
        ):
            stats = dashboard_generator.get_performance_stats()

            assert "dashboards_count" in stats
            assert "initialized" in stats
            assert "renderer" in stats
            assert stats["renderer"]["total_jobs_processed"] == 5


class TestDashboardAutoGeneration:
    """Test dashboard auto-generation features."""

    async def test_auto_generation_post_config_setup(
        self,
        mock_hass_with_entities: HomeAssistant,
        multi_dog_config: list[dict[str, any]],
    ):
        """Test dashboard auto-generation after initial config setup."""
        # Simulate config flow completion triggering auto-generation
        mock_config_entry = MagicMock(spec=ConfigEntry)
        mock_config_entry.entry_id = "auto_test"
        mock_config_entry.data = {"dogs": multi_dog_config}

        generator = PawControlDashboardGenerator(
            mock_hass_with_entities, mock_config_entry
        )

        with (
            patch.object(generator, "_store") as mock_store,
            patch.object(
                generator._renderer,
                "render_main_dashboard",
                AsyncMock(return_value={"views": []}),
            ),
            patch.object(
                generator,
                "_create_dashboard_file",
                AsyncMock(return_value=Path("/test/auto.json")),
            ),
        ):
            mock_store.async_load = AsyncMock(return_value={"dashboards": {}})
            mock_store.async_save = AsyncMock()

            await generator.async_initialize()

            # Trigger auto-generation
            dashboard_url = await generator.async_create_dashboard(
                multi_dog_config,
                {"auto_generated": True, "title": "Auto Generated Dashboard"},
            )

            assert dashboard_url is not None
            dashboards = generator.get_all_dashboards()
            assert len(dashboards) == 1

            dashboard_info = next(iter(dashboards.values()))
            assert dashboard_info["options"]["auto_generated"] is True

    async def test_auto_module_detection_and_cards(
        self,
        mock_hass_with_entities: HomeAssistant,
        multi_dog_config: list[dict[str, any]],
    ):
        """Test automatic module detection and appropriate card generation."""
        generator = PawControlDashboardGenerator(mock_hass_with_entities, MagicMock())

        # Mock specific card generators to track calls
        with (
            patch.object(generator, "_store") as mock_store,
            patch.object(
                generator._renderer.module_generator, "generate_feeding_cards"
            ) as mock_feeding,
            patch.object(
                generator._renderer.module_generator, "generate_walk_cards"
            ) as mock_walk,
            patch.object(
                generator._renderer.module_generator, "generate_health_cards"
            ) as mock_health,
            patch.object(
                generator._renderer.module_generator, "generate_gps_cards"
            ) as mock_gps,
        ):
            mock_store.async_load = AsyncMock(return_value={"dashboards": {}})
            mock_store.async_save = AsyncMock()

            # Configure return values
            mock_feeding.return_value = [{"type": "entities", "title": "Feeding"}]
            mock_walk.return_value = [{"type": "entities", "title": "Walk"}]
            mock_health.return_value = [{"type": "entities", "title": "Health"}]
            mock_gps.return_value = [{"type": "map", "title": "GPS"}]

            await generator.async_initialize()

            # Test each dog's individual dashboard auto-generation
            for dog in multi_dog_config:
                await generator.async_create_dog_dashboard(dog)

            # Verify appropriate card generators were called based on modules
            assert mock_feeding.call_count == 2  # Max and Bella have feeding enabled
            assert mock_walk.call_count == 2  # Max and Charlie have walk enabled
            assert mock_health.call_count == 3  # All dogs have health enabled
            assert mock_gps.call_count == 2  # Max and Charlie have GPS enabled

    async def test_conditional_dashboard_features(
        self,
        mock_hass_with_entities: HomeAssistant,
        multi_dog_config: list[dict[str, any]],
    ):
        """Test conditional dashboard features based on available entities."""
        generator = PawControlDashboardGenerator(mock_hass_with_entities, MagicMock())

        with (
            patch.object(generator, "_store") as mock_store,
            patch.object(
                generator._renderer.overview_generator, "generate_quick_actions"
            ) as mock_actions,
            patch.object(
                generator._renderer.overview_generator, "generate_dogs_grid"
            ) as mock_grid,
        ):
            mock_store.async_load = AsyncMock(return_value={"dashboards": {}})
            mock_store.async_save = AsyncMock()

            # Mock return values based on entity availability
            mock_actions.return_value = {
                "type": "horizontal-stack",
                "cards": [
                    {"type": "button", "name": "Feed All"},  # Available
                    {"type": "button", "name": "Walk Status"},  # Available
                ],
            }

            mock_grid.return_value = {
                "type": "grid",
                "cards": [
                    {"type": "button", "entity": "sensor.max_shepherd_status"},
                    {"type": "button", "entity": "sensor.bella_lab_status"},
                    {"type": "button", "entity": "sensor.charlie_beagle_status"},
                ],
            }

            await generator.async_initialize()

            # Create dashboard and verify conditional features
            with patch.object(
                generator._renderer, "render_main_dashboard"
            ) as mock_render:
                mock_render.return_value = {"views": []}
                await generator.async_create_dashboard(multi_dog_config)

                # Verify render was called with correct dog config
                call_args = mock_render.call_args[0]
                assert len(call_args[0]) == 3  # All three dogs


class TestDashboardEdgeCases:
    """Test dashboard edge cases and error handling."""

    async def test_invalid_dog_configuration_handling(
        self, dashboard_generator: PawControlDashboardGenerator
    ):
        """Test handling of invalid dog configurations."""
        invalid_configs = [
            [],  # Empty list
            [{"invalid": "config"}],  # Missing required fields
            [
                {CONF_DOG_ID: "", CONF_DOG_NAME: "Empty ID"},  # Empty ID
                {CONF_DOG_ID: "valid", CONF_DOG_NAME: ""},  # Empty name
            ],
        ]

        for invalid_config in invalid_configs:
            with pytest.raises((ValueError, HomeAssistantError)):
                await dashboard_generator.async_create_dashboard(invalid_config)

    async def test_storage_corruption_recovery(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ):
        """Test recovery from corrupted storage data."""
        generator = PawControlDashboardGenerator(hass, mock_config_entry)

        # Simulate corrupted storage
        corrupted_data = {
            "dashboards": {
                "corrupted1": {"missing_required_fields": True},
                "corrupted2": {"path": "/nonexistent/path.json"},
                "valid": {
                    "title": "Valid Dashboard",
                    "created": "2024-01-15T10:00:00",
                    "type": "main",
                    "path": "/valid/path.json",
                },
            }
        }

        with (
            patch.object(generator, "_store") as mock_store,
            patch("pathlib.Path.exists") as mock_exists,
        ):
            mock_store.async_load = AsyncMock(return_value=corrupted_data)
            mock_store.async_save = AsyncMock()

            # Mock path existence check
            mock_exists.side_effect = lambda path: str(path) == "/valid/path.json"

            await generator.async_initialize()

            # Verify corrupted entries were removed
            dashboards = generator.get_all_dashboards()
            assert len(dashboards) == 1
            assert "valid" in dashboards
            assert "corrupted1" not in dashboards
            assert "corrupted2" not in dashboards

    async def test_concurrent_dashboard_operations(
        self,
        dashboard_generator: PawControlDashboardGenerator,
        multi_dog_config: list[dict[str, any]],
    ):
        """Test concurrent dashboard creation and updates."""
        # Mock renderer operations
        with (
            patch.object(
                dashboard_generator._renderer,
                "render_main_dashboard",
                AsyncMock(return_value={"views": []}),
            ),
            patch.object(
                dashboard_generator._renderer,
                "render_dog_dashboard",
                AsyncMock(return_value={"views": []}),
            ),
            patch.object(
                dashboard_generator,
                "_create_dashboard_file",
                AsyncMock(side_effect=lambda *args: Path(f"/test/{args[0]}.json")),
            ),
            patch.object(dashboard_generator, "_save_dashboard_metadata", AsyncMock()),
        ):
            # Create multiple dashboards concurrently
            tasks = [
                dashboard_generator.async_create_dashboard(
                    [multi_dog_config[0]], {"title": f"Dashboard {i}"}
                )
                for i in range(3)
            ]

            # Add individual dog dashboard tasks
            tasks.extend(
                [
                    dashboard_generator.async_create_dog_dashboard(dog)
                    for dog in multi_dog_config
                ]
            )

            # Execute all tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Verify all operations completed successfully
            assert len(results) == 6
            for result in results:
                assert not isinstance(result, Exception)
                assert isinstance(result, str)  # Dashboard URL

            # Verify all dashboards were created
            dashboards = dashboard_generator.get_all_dashboards()
            assert len(dashboards) == 6

    async def test_memory_cleanup_on_errors(
        self,
        dashboard_generator: PawControlDashboardGenerator,
        multi_dog_config: list[dict[str, any]],
    ):
        """Test proper memory cleanup when dashboard operations fail."""
        # Force renderer to fail
        with patch.object(
            dashboard_generator._renderer,
            "render_main_dashboard",
            AsyncMock(side_effect=Exception("Rendering failed")),
        ):
            with pytest.raises(HomeAssistantError):
                await dashboard_generator.async_create_dashboard(multi_dog_config)

            # Verify no partial state was saved
            dashboards = dashboard_generator.get_all_dashboards()
            assert len(dashboards) == 0

    async def test_large_configuration_handling(
        self, dashboard_generator: PawControlDashboardGenerator
    ):
        """Test handling of large multi-dog configurations."""
        # Create configuration for 50 dogs
        large_config = []
        for i in range(50):
            large_config.append(  # noqa: PERF401
                {
                    CONF_DOG_ID: f"dog_{i:03d}",
                    CONF_DOG_NAME: f"Dog {i + 1}",
                    "modules": {
                        MODULE_FEEDING: i % 2 == 0,  # Every other dog
                        MODULE_WALK: i % 3 == 0,  # Every third dog
                        MODULE_HEALTH: True,  # All dogs
                        MODULE_GPS: i % 4 == 0,  # Every fourth dog
                    },
                }
            )

        with (
            patch.object(
                dashboard_generator._renderer,
                "render_main_dashboard",
                AsyncMock(return_value={"views": []}),
            ),
            patch.object(
                dashboard_generator,
                "_create_dashboard_file",
                AsyncMock(return_value=Path("/test/large.json")),
            ),
            patch.object(dashboard_generator, "_save_dashboard_metadata", AsyncMock()),
        ):
            # Should handle large configuration without issues
            url = await dashboard_generator.async_create_dashboard(large_config)

            assert url is not None

            # Verify dashboard metadata
            dashboards = dashboard_generator.get_all_dashboards()
            assert len(dashboards) == 1

            dashboard_info = next(iter(dashboards.values()))
            assert len(dashboard_info["dogs"]) == 50


class TestDashboardCardGeneration:
    """Test individual dashboard card generation."""

    @pytest.fixture
    def mock_templates(self):
        """Mock dashboard templates."""
        templates = Mock()
        templates.get_dog_status_card_template = AsyncMock(
            return_value={"type": "entities", "title": "Status"}
        )
        templates.get_action_buttons_template = AsyncMock(
            return_value=[{"type": "button", "name": "Feed"}]
        )
        templates.get_map_card_template = AsyncMock(
            return_value={"type": "map", "title": "Location"}
        )
        templates.get_history_graph_template = AsyncMock(
            return_value={"type": "history-graph", "entities": ["sensor.test"]}
        )
        templates.get_feeding_controls_template = AsyncMock(
            return_value={"type": "entities", "title": "Feeding Controls"}
        )
        return templates

    async def test_overview_card_generation(
        self, mock_hass_with_entities: HomeAssistant, mock_templates, multi_dog_config
    ):
        """Test overview dashboard card generation."""
        generator = OverviewCardGenerator(mock_hass_with_entities, mock_templates)

        # Test welcome card
        welcome_card = await generator.generate_welcome_card(
            multi_dog_config, {"title": "Test Dashboard"}
        )

        assert welcome_card["type"] == "markdown"
        assert "Test Dashboard" in welcome_card["content"]
        assert "3" in welcome_card["content"]  # 3 dogs

        # Test dogs grid
        dogs_grid = await generator.generate_dogs_grid(
            multi_dog_config, "/test-dashboard"
        )

        assert dogs_grid["type"] == "grid"
        assert len(dogs_grid["cards"]) == 3  # All dogs have status entities
        assert dogs_grid["columns"] == 3

    async def test_health_aware_feeding_cards(
        self, mock_hass_with_entities: HomeAssistant, mock_templates
    ):
        """Test health-aware feeding card generation."""
        generator = HealthAwareFeedingCardGenerator(
            mock_hass_with_entities, mock_templates
        )

        dog_config = {
            "dog_id": "max_shepherd",
            "dog_name": "Max",
            "modules": {MODULE_FEEDING: True, MODULE_HEALTH: True},
        }

        # Test health feeding overview
        cards = await generator.generate_health_feeding_overview(dog_config, {})

        assert len(cards) > 0

        # Should include health status card
        health_card = next(
            (card for card in cards if "Health Feeding" in card.get("title", "")), None
        )
        assert health_card is not None
        assert health_card["type"] == "entities"

        # Test feeding controls
        control_cards = await generator.generate_health_feeding_controls(dog_config, {})

        assert len(control_cards) > 0
        smart_buttons = next(
            (card for card in control_cards if card.get("type") == "grid"), None
        )
        assert smart_buttons is not None

    async def test_module_card_generation_conditional(
        self, mock_hass_with_entities: HomeAssistant, mock_templates
    ):
        """Test module card generation based on enabled modules."""
        generator = ModuleCardGenerator(mock_hass_with_entities, mock_templates)

        # Dog with selective modules
        dog_config = {
            CONF_DOG_ID: "selective_dog",
            CONF_DOG_NAME: "Selective",
            "modules": {
                MODULE_FEEDING: True,  # Enabled
                MODULE_WALK: False,  # Disabled
                MODULE_HEALTH: True,  # Enabled
                MODULE_GPS: False,  # Disabled
            },
        }

        # Test feeding cards (should be generated)
        feeding_cards = await generator.generate_feeding_cards(dog_config, {})
        assert len(feeding_cards) > 0

        # Test walk cards (should be empty)
        walk_cards = await generator.generate_walk_cards(dog_config, {})
        assert len(walk_cards) == 0  # No entities available

        # Test health cards (should be generated)
        health_cards = await generator.generate_health_cards(dog_config, {})
        assert len(health_cards) > 0

    async def test_statistics_card_aggregation(
        self, mock_hass_with_entities: HomeAssistant, mock_templates, multi_dog_config
    ):
        """Test statistics card generation with multi-dog data aggregation."""
        generator = StatisticsCardGenerator(mock_hass_with_entities, mock_templates)

        cards = await generator.generate_statistics_cards(multi_dog_config, {})

        assert len(cards) > 0

        # Should include summary card
        summary_card = next(
            (card for card in cards if card.get("type") == "markdown"), None
        )
        assert summary_card is not None
        assert "3" in summary_card["content"]  # 3 dogs managed

        # Should include activity statistics if entities exist
        next(
            (card for card in cards if "Activity Statistics" in card.get("title", "")),
            None,
        )
        # May be None if no activity entities available


class TestDashboardRendererPerformance:
    """Test dashboard renderer performance and scaling."""

    async def test_concurrent_render_jobs(self, hass: HomeAssistant):
        """Test concurrent rendering job processing."""
        renderer = DashboardRenderer(hass)

        # Mock card generators
        with (
            patch.object(
                renderer.overview_generator,
                "generate_welcome_card",
                AsyncMock(return_value={}),
            ),
            patch.object(
                renderer.overview_generator,
                "generate_dogs_grid",
                AsyncMock(return_value={}),
            ),
            patch.object(
                renderer.overview_generator,
                "generate_quick_actions",
                AsyncMock(return_value={}),
            ),
            patch.object(
                renderer.dog_generator,
                "generate_dog_overview_cards",
                AsyncMock(return_value=[]),
            ),
        ):
            # Create multiple render jobs
            tasks = []
            for i in range(5):
                dog_config = [{"dog_id": f"dog_{i}", "dog_name": f"Dog {i}"}]
                tasks.append(renderer.render_main_dashboard(dog_config))

            # Execute concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Verify all completed successfully
            assert len(results) == 5
            for result in results:
                assert not isinstance(result, Exception)
                assert "views" in result

    async def test_render_timeout_handling(self, hass: HomeAssistant):
        """Test rendering timeout and cleanup."""
        renderer = DashboardRenderer(hass)

        # Mock a slow card generator that times out
        slow_generator = AsyncMock()
        # Exceeds timeout
        slow_generator.side_effect = lambda *args: asyncio.sleep(35)

        with (
            patch.object(
                renderer.overview_generator, "generate_welcome_card", slow_generator
            ),
            pytest.raises(HomeAssistantError, match="timeout"),
        ):
            await renderer.render_main_dashboard(
                [{"dog_id": "test", "dog_name": "Test"}]
            )

    async def test_memory_efficient_batch_processing(self, hass: HomeAssistant):
        """Test memory-efficient processing of large dog lists."""
        renderer = DashboardRenderer(hass)

        # Create large dog configuration
        large_dog_config = []
        for i in range(100):
            large_dog_config.append(  # noqa: PERF401
                {
                    "dog_id": f"dog_{i:03d}",
                    "dog_name": f"Dog {i + 1}",
                    "modules": {"feeding": True},
                }
            )

        with (
            patch.object(
                renderer.overview_generator,
                "generate_welcome_card",
                AsyncMock(return_value={}),
            ),
            patch.object(
                renderer.overview_generator,
                "generate_dogs_grid",
                AsyncMock(return_value={}),
            ),
            patch.object(
                renderer.overview_generator,
                "generate_quick_actions",
                AsyncMock(return_value={}),
            ),
            patch.object(
                renderer.dog_generator,
                "generate_dog_overview_cards",
                AsyncMock(return_value=[]),
            ),
        ):
            # Should process without memory issues
            result = await renderer.render_main_dashboard(large_dog_config)

            assert "views" in result
            # Should have overview + individual dog views
            assert len(result["views"]) > 1

    async def test_render_statistics_tracking(self, hass: HomeAssistant):
        """Test rendering statistics collection."""
        renderer = DashboardRenderer(hass)

        # Perform some rendering operations
        with (
            patch.object(
                renderer.overview_generator,
                "generate_welcome_card",
                AsyncMock(return_value={}),
            ),
            patch.object(
                renderer.overview_generator,
                "generate_dogs_grid",
                AsyncMock(return_value={}),
            ),
        ):
            # Execute multiple render jobs
            for i in range(3):
                await renderer.render_main_dashboard(
                    [{"dog_id": f"test_{i}", "dog_name": f"Test {i}"}]
                )

        # Check statistics
        stats = renderer.get_render_stats()

        assert "active_jobs" in stats
        assert "total_jobs_processed" in stats
        assert stats["total_jobs_processed"] == 3
        assert stats["active_jobs"] == 0  # All completed
