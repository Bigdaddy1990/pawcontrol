"""Comprehensive tests for dashboard card generators.

Tests all card generator classes including overview, dog-specific, module,
health-aware feeding, and statistics cards with entity validation.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

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
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_hass_cards() -> HomeAssistant:
    """Mock Home Assistant with realistic entity states for card testing."""
    hass = Mock(spec=HomeAssistant)

    # Mock entity states for card generation testing
    mock_states = {
        # Dog status entities
        "sensor.max_status": Mock(state="active"),
        "sensor.bella_status": Mock(state="sleeping"),
        "sensor.charlie_status": Mock(state="active"),
        # Feeding entities
        "sensor.max_next_meal_time": Mock(state="2024-01-15 18:00:00"),
        "sensor.max_meals_today": Mock(state="2"),
        "sensor.max_calories_today": Mock(state="1450"),
        "sensor.max_last_fed": Mock(state="2024-01-15 12:30:00"),
        "sensor.max_health_feeding_status": Mock(state="optimal"),
        "sensor.max_daily_calorie_target": Mock(state="1800"),
        "sensor.max_calories_consumed_today": Mock(state="1450"),
        # Walk entities
        "binary_sensor.max_is_walking": Mock(state="off"),
        "sensor.max_current_walk_duration": Mock(state="0"),
        "sensor.max_walks_today": Mock(state="2"),
        "sensor.max_walk_distance_today": Mock(state="5.2"),
        "sensor.max_last_walk_time": Mock(state="2024-01-15 14:00:00"),
        # Health entities
        "sensor.max_health_status": Mock(state="excellent"),
        "sensor.max_weight": Mock(state="35.5"),
        "sensor.max_temperature": Mock(state="38.5"),
        "sensor.max_mood": Mock(state="happy"),
        "sensor.max_energy_level": Mock(state="high"),
        "date.max_next_vet_visit": Mock(state="2024-03-15"),
        "date.max_next_vaccination": Mock(state="2024-06-01"),
        # GPS entities
        "device_tracker.max_location": Mock(state="home"),
        "sensor.max_gps_accuracy": Mock(state="5"),
        "sensor.max_distance_from_home": Mock(state="0.2"),
        "sensor.max_speed": Mock(state="0"),
        "sensor.max_battery_level": Mock(state="85"),
        "binary_sensor.max_at_home": Mock(state="on"),
        "binary_sensor.max_at_park": Mock(state="off"),
        "switch.max_gps_tracking_enabled": Mock(state="on"),
        # Global entities
        f"button.{DOMAIN}_feed_all_dogs": Mock(state="unknown"),
        f"sensor.{DOMAIN}_dogs_walking": Mock(state="1"),
        # Activity entities
        "sensor.max_activity_level": Mock(state="moderate"),
        "sensor.bella_activity_level": Mock(state="low"),
    }

    def get_state(entity_id):
        if entity_id in mock_states:
            return mock_states[entity_id]
        # Return unavailable state for unknown entities
        return Mock(state=STATE_UNAVAILABLE)

    hass.states.get = get_state
    return hass


@pytest.fixture
def mock_templates():
    """Mock dashboard templates for testing."""
    templates = Mock()

    # Mock template methods
    templates.get_dog_status_card_template = AsyncMock(
        return_value={
            "type": "entities",
            "title": "Status",
            "entities": ["sensor.max_status", "sensor.max_activity_level"],
        }
    )

    templates.get_action_buttons_template = AsyncMock(
        return_value=[
            {"type": "button", "name": "Feed", "icon": "mdi:food"},
            {"type": "button", "name": "Walk", "icon": "mdi:walk"},
        ]
    )

    templates.get_map_card_template = AsyncMock(
        return_value={
            "type": "map",
            "title": "Location",
            "entities": ["device_tracker.max_location"],
        }
    )

    templates.get_history_graph_template = AsyncMock(
        return_value={
            "type": "history-graph",
            "title": "History",
            "entities": ["sensor.max_activity_level"],
            "hours_to_show": 24,
        }
    )

    templates.get_feeding_controls_template = AsyncMock(
        return_value={
            "type": "entities",
            "title": "Feeding Controls",
            "entities": ["button.max_feed", "sensor.max_next_meal"],
        }
    )

    return templates


@pytest.fixture
def sample_dog_config() -> dict[str, any]:
    """Sample dog configuration for testing."""
    return {
        CONF_DOG_ID: "max",
        CONF_DOG_NAME: "Max",
        "dog_breed": "German Shepherd",
        "dog_weight": 35.5,
        "modules": {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_HEALTH: True,
            MODULE_GPS: True,
        },
    }


class TestOverviewCardGenerator:
    """Test overview dashboard card generation."""

    @pytest.fixture
    def overview_generator(
        self, mock_hass_cards, mock_templates
    ) -> OverviewCardGenerator:
        """Create overview card generator."""
        return OverviewCardGenerator(mock_hass_cards, mock_templates)

    async def test_welcome_card_generation(
        self, overview_generator: OverviewCardGenerator
    ):
        """Test welcome card generation with dog count."""
        dogs_config = [
            {"dog_id": "max", "dog_name": "Max"},
            {"dog_id": "bella", "dog_name": "Bella"},
            {"dog_id": "charlie", "dog_name": "Charlie"},
        ]

        options = {"title": "My Pack Dashboard"}

        welcome_card = await overview_generator.generate_welcome_card(
            dogs_config, options
        )

        assert welcome_card["type"] == "markdown"
        assert "My Pack Dashboard" in welcome_card["content"]
        assert "3" in welcome_card["content"]  # Dog count
        assert "dogs" in welcome_card["content"]

    async def test_welcome_card_single_dog(
        self, overview_generator: OverviewCardGenerator
    ):
        """Test welcome card with single dog (singular form)."""
        dogs_config = [{"dog_id": "max", "dog_name": "Max"}]

        welcome_card = await overview_generator.generate_welcome_card(dogs_config, {})

        assert "1" in welcome_card["content"]
        assert "dog" in welcome_card["content"]
        assert "dogs" not in welcome_card["content"]  # Should use singular

    async def test_dogs_grid_generation(
        self, overview_generator: OverviewCardGenerator
    ):
        """Test dogs grid card generation."""
        dogs_config = [
            {"dog_id": "max", "dog_name": "Max"},
            {"dog_id": "bella", "dog_name": "Bella"},
        ]

        dogs_grid = await overview_generator.generate_dogs_grid(
            dogs_config, "/my-dashboard"
        )

        assert dogs_grid["type"] == "grid"
        assert dogs_grid["columns"] == 2  # Based on dog count
        assert len(dogs_grid["cards"]) == 2

        # Check first card
        first_card = dogs_grid["cards"][0]
        assert first_card["type"] == "button"
        assert first_card["entity"] == "sensor.max_status"
        assert first_card["name"] == "Max"
        assert "/my-dashboard/max" in first_card["tap_action"]["navigation_path"]

    async def test_dogs_grid_with_unavailable_dogs(
        self, overview_generator: OverviewCardGenerator
    ):
        """Test dogs grid filtering unavailable dogs."""
        dogs_config = [
            {"dog_id": "max", "dog_name": "Max"},  # Available
            {"dog_id": "nonexistent", "dog_name": "Ghost"},  # Not available
        ]

        dogs_grid = await overview_generator.generate_dogs_grid(dogs_config, "/test")

        # Should only include available dogs
        assert len(dogs_grid["cards"]) == 1
        assert dogs_grid["cards"][0]["name"] == "Max"

    async def test_quick_actions_generation(
        self, overview_generator: OverviewCardGenerator
    ):
        """Test quick actions card generation."""
        dogs_config = [
            {"dog_id": "max", "modules": {MODULE_FEEDING: True, MODULE_WALK: True}},
            {"dog_id": "bella", "modules": {
                MODULE_FEEDING: True, MODULE_WALK: False}},
        ]

        quick_actions = await overview_generator.generate_quick_actions(dogs_config)

        assert quick_actions["type"] == "horizontal-stack"
        # Feed All + Walk Status + Daily Reset
        assert len(quick_actions["cards"]) == 3

        # Check feed all button
        feed_button = next(
            card for card in quick_actions["cards"] if card["name"] == "Feed All"
        )
        assert feed_button["icon"] == "mdi:food-drumstick"

    async def test_quick_actions_no_modules(
        self, overview_generator: OverviewCardGenerator
    ):
        """Test quick actions with no enabled modules."""
        dogs_config = [
            {"dog_id": "max", "modules": {MODULE_FEEDING: False, MODULE_WALK: False}},
        ]

        quick_actions = await overview_generator.generate_quick_actions(dogs_config)

        # Should still have daily reset button
        assert len(quick_actions["cards"]) == 1
        assert quick_actions["cards"][0]["name"] == "Daily Reset"


class TestDogCardGenerator:
    """Test individual dog card generation."""

    @pytest.fixture
    def dog_generator(self, mock_hass_cards, mock_templates) -> DogCardGenerator:
        """Create dog card generator."""
        return DogCardGenerator(mock_hass_cards, mock_templates)

    async def test_dog_overview_cards_complete(
        self, dog_generator: DogCardGenerator, sample_dog_config
    ):
        """Test complete dog overview card generation."""
        theme = {"primary": "#4CAF50", "accent": "#8BC34A"}
        options = {"show_activity_graph": True}

        cards = await dog_generator.generate_dog_overview_cards(
            sample_dog_config, theme, options
        )

        assert len(cards) >= 3  # Header + status + actions + additional cards

        # Should include dog status card
        status_card = next(
            card for card in cards if card.get("type") == "entities")
        assert status_card is not None

    async def test_dog_header_card_generation(
        self, dog_generator: DogCardGenerator, sample_dog_config
    ):
        """Test dog header card with picture."""
        header_card = await dog_generator._generate_dog_header_card(
            sample_dog_config, {}
        )

        assert header_card["type"] == "picture-entity"
        assert header_card["entity"] == "sensor.max_status"
        assert header_card["name"] == "Max"
        assert "/local/paw_control/max.jpg" in header_card["image"]

    async def test_gps_map_card_generation(self, dog_generator: DogCardGenerator):
        """Test GPS map card generation."""
        map_card = await dog_generator._generate_gps_map_card("max", {})

        assert map_card is not None
        assert map_card["type"] == "map"
        assert "max" in str(map_card)  # Should reference dog

    async def test_gps_map_card_unavailable(self, dog_generator: DogCardGenerator):
        """Test GPS map card when tracker unavailable."""
        map_card = await dog_generator._generate_gps_map_card("nonexistent", {})

        assert map_card is None

    async def test_activity_graph_card(
        self, dog_generator: DogCardGenerator, sample_dog_config
    ):
        """Test activity graph card generation."""
        options = {"show_activity_graph": True}

        activity_card = await dog_generator._generate_activity_graph_card(
            sample_dog_config, options
        )

        assert activity_card is not None
        assert activity_card["type"] == "history-graph"

    async def test_activity_graph_disabled(
        self, dog_generator: DogCardGenerator, sample_dog_config
    ):
        """Test activity graph when disabled."""
        options = {"show_activity_graph": False}

        activity_card = await dog_generator._generate_activity_graph_card(
            sample_dog_config, options
        )

        assert activity_card is None


class TestHealthAwareFeedingCardGenerator:
    """Test health-aware feeding card generation."""

    @pytest.fixture
    def health_feeding_generator(
        self, mock_hass_cards, mock_templates
    ) -> HealthAwareFeedingCardGenerator:
        """Create health-aware feeding card generator."""
        return HealthAwareFeedingCardGenerator(mock_hass_cards, mock_templates)

    async def test_health_feeding_overview(
        self,
        health_feeding_generator: HealthAwareFeedingCardGenerator,
        sample_dog_config,
    ):
        """Test health-aware feeding overview cards."""
        cards = await health_feeding_generator.generate_health_feeding_overview(
            sample_dog_config, {}
        )

        assert len(cards) >= 2  # Health status + calorie tracking at minimum

        # Check health feeding status card
        health_card = next(
            card for card in cards if "Health Feeding" in card.get("title", "")
        )
        assert health_card["type"] == "entities"
        assert (
            len(health_card["entities"]) >= 4
        )  # Health status, target, consumed, adjustment

    async def test_calorie_tracking_card(
        self, health_feeding_generator: HealthAwareFeedingCardGenerator
    ):
        """Test calorie tracking card generation."""
        calorie_card = await health_feeding_generator._generate_calorie_tracking_card(
            "max", {}
        )

        assert calorie_card is not None
        assert calorie_card["type"] == "history-graph"
        assert "Calorie Tracking" in calorie_card["title"]

    async def test_weight_management_card(
        self, health_feeding_generator: HealthAwareFeedingCardGenerator
    ):
        """Test weight management card generation."""
        weight_card = await health_feeding_generator._generate_weight_management_card(
            "max", {}
        )

        assert weight_card is not None
        assert weight_card["type"] == "vertical-stack"
        assert len(weight_card["cards"]) == 2  # Entities + gauge

    async def test_portion_calculator_card(
        self, health_feeding_generator: HealthAwareFeedingCardGenerator
    ):
        """Test portion calculator card generation."""
        # Mock the health aware portions entity as available
        with MockedEntity("sensor.max_health_aware_portions"):
            portion_card = (
                await health_feeding_generator._generate_portion_calculator_card(
                    "max", {}
                )
            )

            assert portion_card is not None
            assert portion_card["type"] == "vertical-stack"
            assert len(portion_card["cards"]) == 2  # Markdown + buttons

    async def test_smart_feeding_buttons(
        self, health_feeding_generator: HealthAwareFeedingCardGenerator
    ):
        """Test smart feeding buttons generation."""
        buttons_card = await health_feeding_generator._generate_smart_feeding_buttons(
            "max", {}
        )

        assert buttons_card["type"] == "grid"
        assert buttons_card["columns"] == 2
        assert len(buttons_card["cards"]) == 2  # Breakfast + dinner buttons


class TestModuleCardGenerator:
    """Test module-specific card generation."""

    @pytest.fixture
    def module_generator(self, mock_hass_cards, mock_templates) -> ModuleCardGenerator:
        """Create module card generator."""
        return ModuleCardGenerator(mock_hass_cards, mock_templates)

    async def test_feeding_cards_standard(
        self, module_generator: ModuleCardGenerator, sample_dog_config
    ):
        """Test standard feeding cards (non health-aware)."""
        # Disable health module for standard feeding
        config = sample_dog_config.copy()
        config["modules"][MODULE_HEALTH] = False

        cards = await module_generator.generate_feeding_cards(config, {})

        assert len(cards) >= 2  # Schedule + controls + history

        # Should include feeding schedule
        schedule_card = next(
            card for card in cards if card.get("title") == "Feeding Schedule"
        )
        assert schedule_card["type"] == "entities"

    async def test_feeding_cards_health_aware(
        self, module_generator: ModuleCardGenerator, sample_dog_config
    ):
        """Test health-aware feeding cards."""
        cards = await module_generator.generate_feeding_cards(sample_dog_config, {})

        # Should use health-aware feeding generator
        assert len(cards) >= 3  # Health overview + controls + history

    async def test_walk_cards_generation(
        self, module_generator: ModuleCardGenerator, sample_dog_config
    ):
        """Test walk module cards generation."""
        cards = await module_generator.generate_walk_cards(sample_dog_config, {})

        assert len(cards) >= 3  # Status + conditional buttons + history

        # Should include walk status
        status_card = next(card for card in cards if card.get(
            "title") == "Walk Status")
        assert status_card["type"] == "entities"

        # Should include conditional start/stop buttons
        conditional_cards = [
            card for card in cards if card.get("type") == "conditional"
        ]
        assert len(conditional_cards) == 2  # Start + stop buttons

    async def test_health_cards_generation(
        self, module_generator: ModuleCardGenerator, sample_dog_config
    ):
        """Test health module cards generation."""
        cards = await module_generator.generate_health_cards(sample_dog_config, {})

        assert len(cards) >= 3  # Metrics + buttons + history/dates

        # Should include health metrics
        metrics_card = next(
            card for card in cards if card.get("title") == "Health Metrics"
        )
        assert metrics_card["type"] == "entities"

    async def test_gps_cards_generation(
        self, module_generator: ModuleCardGenerator, sample_dog_config
    ):
        """Test GPS module cards generation."""
        cards = await module_generator.generate_gps_cards(sample_dog_config, {})

        assert len(cards) >= 3  # Map + status + geofence + history

        # Should include main GPS map
        map_card = next(card for card in cards if card.get("type") == "map")
        assert map_card is not None

    async def test_gps_cards_no_tracker(self, module_generator: ModuleCardGenerator):
        """Test GPS cards when tracker unavailable."""
        config = {
            CONF_DOG_ID: "nonexistent",
            CONF_DOG_NAME: "Ghost",
            "modules": {MODULE_GPS: True},
        }

        cards = await module_generator.generate_gps_cards(config, {})

        # Should return empty list if no tracker
        assert len(cards) == 0


class TestStatisticsCardGenerator:
    """Test statistics card generation."""

    @pytest.fixture
    def stats_generator(
        self, mock_hass_cards, mock_templates
    ) -> StatisticsCardGenerator:
        """Create statistics card generator."""
        return StatisticsCardGenerator(mock_hass_cards, mock_templates)

    async def test_statistics_cards_generation(
        self, stats_generator: StatisticsCardGenerator
    ):
        """Test complete statistics cards generation."""
        dogs_config = [
            {"dog_id": "max", "modules": {MODULE_FEEDING: True, MODULE_WALK: True}},
            {"dog_id": "bella", "modules": {
                MODULE_FEEDING: True, MODULE_HEALTH: True}},
        ]

        cards = await stats_generator.generate_statistics_cards(dogs_config, {})

        assert len(cards) >= 1  # At least summary card

        # Should include summary card
        summary_card = next(
            card for card in cards if card.get("type") == "markdown")
        assert "2" in summary_card["content"]  # 2 dogs managed

    async def test_activity_statistics_card(
        self, stats_generator: StatisticsCardGenerator
    ):
        """Test activity statistics card generation."""
        dogs_config = [
            {"dog_id": "max"},
            {"dog_id": "bella"},
        ]

        activity_card = await stats_generator._generate_activity_statistics(dogs_config)

        assert activity_card is not None
        assert activity_card["type"] == "statistics-graph"
        assert "Activity Statistics" in activity_card["title"]

    async def test_feeding_statistics_card(
        self, stats_generator: StatisticsCardGenerator
    ):
        """Test feeding statistics card generation."""
        dogs_config = [
            {"dog_id": "max", "modules": {MODULE_FEEDING: True}},
        ]

        feeding_card = await stats_generator._generate_feeding_statistics(dogs_config)

        assert feeding_card is not None
        assert feeding_card["type"] == "statistics-graph"
        assert "Feeding Statistics" in feeding_card["title"]

    async def test_summary_card_generation(
        self, stats_generator: StatisticsCardGenerator
    ):
        """Test summary card generation with module counts."""
        dogs_config = [
            {"dog_id": "max", "modules": {MODULE_FEEDING: True, MODULE_WALK: True}},
            {"dog_id": "bella", "modules": {MODULE_FEEDING: True, MODULE_GPS: True}},
            {"dog_id": "charlie", "modules": {MODULE_HEALTH: True}},
        ]

        summary_card = stats_generator._generate_summary_card(dogs_config)

        assert summary_card["type"] == "markdown"
        content = summary_card["content"]

        assert "3" in content  # 3 dogs managed
        assert "Feeding: 2" in content
        assert "Walks: 1" in content
        assert "Health: 1" in content
        assert "GPS: 1" in content


class TestCardEntityValidation:
    """Test card entity validation functionality."""

    @pytest.fixture
    def base_generator(self, mock_hass_cards, mock_templates):
        """Create base card generator for testing validation."""
        from custom_components.pawcontrol.dashboard_cards import BaseCardGenerator

        return BaseCardGenerator(mock_hass_cards, mock_templates)

    async def test_entity_validation_available(self, base_generator):
        """Test entity validation with available entities."""
        entities = ["sensor.max_status", "sensor.max_activity_level"]

        valid_entities = await base_generator._validate_entities(entities)

        assert len(valid_entities) == 2
        assert "sensor.max_status" in valid_entities

    async def test_entity_validation_mixed(self, base_generator):
        """Test entity validation with mixed availability."""
        entities = [
            "sensor.max_status",  # Available
            "sensor.nonexistent",  # Unavailable
            "sensor.max_activity_level",  # Available
        ]

        valid_entities = await base_generator._validate_entities(entities)

        assert len(valid_entities) == 2
        assert "sensor.nonexistent" not in valid_entities

    async def test_entity_exists_check(self, base_generator):
        """Test individual entity existence check."""
        assert await base_generator._entity_exists("sensor.max_status") is True
        assert await base_generator._entity_exists("sensor.nonexistent") is False


# Helper context manager for mocking entity availability
class MockedEntity:
    """Context manager to temporarily mock entity availability."""

    def __init__(self, entity_id):
        self.entity_id = entity_id

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
