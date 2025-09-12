"""Advanced scenario tests for PawControl config_flow_dogs multi-dog configurations.

This module provides comprehensive testing for complex multi-dog setup scenarios,
advanced configuration workflows, diet validation, health integration, and
performance testing for large-scale deployments.

Test Focus Areas:
- Multi-dog setup workflows with complex configurations
- Advanced health and feeding integration scenarios
- Comprehensive diet validation and conflict detection
- GPS configuration across multiple devices and dogs
- Performance testing with large numbers of dogs
- Error recovery and partial failure scenarios
- Cross-dog validation and consistency checking
- Complex medication and health condition interactions

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+
"""
from __future__ import annotations

import asyncio
import copy
import time
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import call
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.pawcontrol.config_flow_base import DOG_ID_PATTERN
from custom_components.pawcontrol.config_flow_base import MAX_DOGS_PER_ENTRY
from custom_components.pawcontrol.config_flow_base import VALIDATION_SEMAPHORE
from custom_components.pawcontrol.config_flow_dogs import DIET_COMPATIBILITY_RULES
from custom_components.pawcontrol.config_flow_dogs import DogManagementMixin
from custom_components.pawcontrol.const import CONF_BREAKFAST_TIME
from custom_components.pawcontrol.const import CONF_DAILY_FOOD_AMOUNT
from custom_components.pawcontrol.const import CONF_DINNER_TIME
from custom_components.pawcontrol.const import CONF_DOG_AGE
from custom_components.pawcontrol.const import CONF_DOG_BREED
from custom_components.pawcontrol.const import CONF_DOG_ID
from custom_components.pawcontrol.const import CONF_DOG_NAME
from custom_components.pawcontrol.const import CONF_DOG_SIZE
from custom_components.pawcontrol.const import CONF_DOG_WEIGHT
from custom_components.pawcontrol.const import CONF_FOOD_TYPE
from custom_components.pawcontrol.const import CONF_GPS_SOURCE
from custom_components.pawcontrol.const import CONF_LUNCH_TIME
from custom_components.pawcontrol.const import CONF_MEALS_PER_DAY
from custom_components.pawcontrol.const import CONF_MODULES
from custom_components.pawcontrol.const import CONF_SNACK_TIMES
from custom_components.pawcontrol.const import MAX_DOG_AGE
from custom_components.pawcontrol.const import MAX_DOG_NAME_LENGTH
from custom_components.pawcontrol.const import MAX_DOG_WEIGHT
from custom_components.pawcontrol.const import MIN_DOG_AGE
from custom_components.pawcontrol.const import MIN_DOG_NAME_LENGTH
from custom_components.pawcontrol.const import MIN_DOG_WEIGHT
from custom_components.pawcontrol.const import MODULE_DASHBOARD
from custom_components.pawcontrol.const import MODULE_FEEDING
from custom_components.pawcontrol.const import MODULE_GPS
from custom_components.pawcontrol.const import MODULE_GROOMING
from custom_components.pawcontrol.const import MODULE_HEALTH
from custom_components.pawcontrol.const import MODULE_MEDICATION
from custom_components.pawcontrol.const import MODULE_NOTIFICATIONS
from custom_components.pawcontrol.const import MODULE_TRAINING
from custom_components.pawcontrol.const import MODULE_VISITOR
from custom_components.pawcontrol.const import MODULE_WALK
from custom_components.pawcontrol.const import SPECIAL_DIET_OPTIONS


class MockDogConfigFlow(DogManagementMixin):
    """Mock config flow with dog management functionality for testing."""

    def __init__(self, hass: HomeAssistant):
        """Initialize mock config flow."""
        self.hass = hass
        self._dogs: list[dict[str, Any]] = []
        self._errors: dict[str, str] = {}
        self._validation_cache: dict[str, Any] = {}
        self._current_dog_config: dict[str, Any] | None = None
        self._global_modules: dict[str, Any] = {}

    def async_show_form(self, **kwargs) -> ConfigFlowResult:
        """Mock form display."""
        return {
            "type": FlowResultType.FORM,
            "step_id": kwargs.get("step_id"),
            "data_schema": kwargs.get("data_schema"),
            "errors": kwargs.get("errors", {}),
            "description_placeholders": kwargs.get("description_placeholders", {}),
        }

    async def async_step_entity_profile(self) -> ConfigFlowResult:
        """Mock entity profile step."""
        return {
            "type": FlowResultType.FORM,
            "step_id": "entity_profile",
        }

    def _format_dogs_list(self) -> str:
        """Format dogs list for display."""
        if not self._dogs:
            return "No dogs configured yet"
        return "\n".join(
            f"• {dog.get(CONF_DOG_NAME, 'Unknown')} ({dog.get(CONF_DOG_ID, 'unknown')})"
            for dog in self._dogs
        )

    def _is_weight_size_compatible(self, weight: float, size: str) -> bool:
        """Check if weight is compatible with size category."""
        size_ranges = {
            "toy": (1.0, 6.0),
            "small": (6.0, 12.0),
            "medium": (12.0, 27.0),
            "large": (27.0, 45.0),
            "giant": (45.0, 90.0),
        }
        min_weight, max_weight = size_ranges.get(size, (0, 200))
        return min_weight <= weight <= max_weight

    async def _generate_smart_dog_id_suggestion(
        self, user_input: dict[str, Any] | None
    ) -> str:
        """Generate smart dog ID suggestion."""
        if user_input and user_input.get(CONF_DOG_NAME):
            base_name = user_input[CONF_DOG_NAME].lower().replace(" ", "_")
            return base_name[:20]
        return f"dog_{len(self._dogs) + 1}"

    async def _suggest_dog_breed(self, user_input: dict[str, Any] | None) -> str:
        """Suggest dog breed based on input."""
        return ""

    def _get_available_device_trackers(self) -> dict[str, str]:
        """Get available device trackers."""
        return {
            "device_tracker.phone_1": "Phone 1",
            "device_tracker.phone_2": "Phone 2",
            "device_tracker.car": "Family Car",
        }

    def _get_available_person_entities(self) -> dict[str, str]:
        """Get available person entities."""
        return {
            "person.owner": "Owner",
            "person.family_member": "Family Member",
        }


@pytest.fixture
def mock_hass():
    """Create mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    hass.data = {"entity_registry": MagicMock()}
    return hass


@pytest.fixture
def mock_config_flow(mock_hass):
    """Create mock config flow for testing."""
    return MockDogConfigFlow(mock_hass)


@pytest.fixture
def sample_dog_configs():
    """Create sample dog configurations for testing."""
    return [
        {
            CONF_DOG_ID: "max_large_dog",
            CONF_DOG_NAME: "Max",
            CONF_DOG_BREED: "German Shepherd",
            CONF_DOG_AGE: 5,
            CONF_DOG_WEIGHT: 35.0,
            CONF_DOG_SIZE: "large",
        },
        {
            CONF_DOG_ID: "luna_small_dog",
            CONF_DOG_NAME: "Luna",
            CONF_DOG_BREED: "Yorkshire Terrier",
            CONF_DOG_AGE: 3,
            CONF_DOG_WEIGHT: 4.5,
            CONF_DOG_SIZE: "small",
        },
        {
            CONF_DOG_ID: "rocky_medium_dog",
            CONF_DOG_NAME: "Rocky",
            CONF_DOG_BREED: "Border Collie",
            CONF_DOG_AGE: 7,
            CONF_DOG_WEIGHT: 22.0,
            CONF_DOG_SIZE: "medium",
        },
    ]


class TestMultiDogSetupWorkflows:
    """Test complex multi-dog setup workflows."""

    @pytest.mark.asyncio
    async def test_sequential_multi_dog_setup_workflow(
        self, mock_config_flow, sample_dog_configs
    ):
        """Test setting up multiple dogs sequentially with full configuration."""
        # Setup first dog
        result1 = await mock_config_flow.async_step_add_dog(sample_dog_configs[0])
        assert result1["type"] == FlowResultType.FORM
        assert result1["step_id"] == "dog_modules"

        # Configure modules for first dog
        modules_config1 = {
            "enable_feeding": True,
            "enable_walk": True,
            "enable_health": True,
            "enable_gps": True,
            "enable_notifications": True,
            "enable_dashboard": True,
        }

        result2 = await mock_config_flow.async_step_dog_modules(modules_config1)
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "dog_gps"

        # Configure GPS for first dog
        gps_config1 = {
            CONF_GPS_SOURCE: "device_tracker.phone_1",
            "gps_update_interval": 60,
            "gps_accuracy_filter": 20,
            "enable_geofencing": True,
            "home_zone_radius": 100,
        }

        result3 = await mock_config_flow.async_step_dog_gps(gps_config1)
        assert result3["type"] == FlowResultType.FORM
        assert result3["step_id"] == "dog_feeding"

        # Configure feeding for first dog
        feeding_config1 = {
            CONF_MEALS_PER_DAY: 2,
            CONF_DAILY_FOOD_AMOUNT: 800,
            CONF_FOOD_TYPE: "dry_food",
            "feeding_schedule": "strict",
            "breakfast_enabled": True,
            CONF_BREAKFAST_TIME: "07:00:00",
            "dinner_enabled": True,
            CONF_DINNER_TIME: "18:00:00",
        }

        result4 = await mock_config_flow.async_step_dog_feeding(feeding_config1)
        assert result4["type"] == FlowResultType.FORM
        assert result4["step_id"] == "dog_health"

        # Configure health for first dog
        health_config1 = {
            "vet_name": "Dr. Smith",
            "weight_tracking": True,
            "ideal_weight": 35.0,
            "activity_level": "high",
            "spayed_neutered": True,
            "has_arthritis": False,
            "joint_support": True,  # Special diet for large breed
        }

        result5 = await mock_config_flow.async_step_dog_health(health_config1)
        assert result5["type"] == FlowResultType.FORM
        assert result5["step_id"] == "add_another_dog"

        # Verify first dog was added
        assert len(mock_config_flow._dogs) == 1
        first_dog = mock_config_flow._dogs[0]
        assert first_dog[CONF_DOG_NAME] == "Max"
        assert first_dog[CONF_MODULES][MODULE_GPS] is True
        assert "gps_config" in first_dog
        assert "feeding_config" in first_dog
        assert "health_config" in first_dog

        # Choose to add another dog
        result6 = await mock_config_flow.async_step_add_another_dog(
            {"add_another": True}
        )
        assert result6["type"] == FlowResultType.FORM
        assert result6["step_id"] == "add_dog"

        # Setup second dog with different configuration
        result7 = await mock_config_flow.async_step_add_dog(sample_dog_configs[1])
        assert result7["type"] == FlowResultType.FORM
        assert result7["step_id"] == "dog_modules"

        # Configure modules for second dog (different from first)
        modules_config2 = {
            "enable_feeding": True,
            "enable_walk": False,  # Different from first dog
            "enable_health": True,
            "enable_gps": False,  # No GPS for small dog
            "enable_notifications": True,
            "enable_medication": True,  # Add medication module
        }

        result8 = await mock_config_flow.async_step_dog_modules(modules_config2)
        # Should skip GPS and go directly to feeding
        assert result8["type"] == FlowResultType.FORM
        assert result8["step_id"] == "dog_feeding"

        # Configure feeding for small dog
        feeding_config2 = {
            CONF_MEALS_PER_DAY: 3,  # More meals for small dog
            CONF_DAILY_FOOD_AMOUNT: 150,  # Much less food
            CONF_FOOD_TYPE: "wet_food",
            "feeding_schedule": "flexible",
        }

        result9 = await mock_config_flow.async_step_dog_feeding(feeding_config2)
        assert result9["type"] == FlowResultType.FORM
        assert result9["step_id"] == "dog_health"

        # Configure health with medication for second dog
        health_config2 = {
            "vet_name": "Dr. Johnson",
            "weight_tracking": True,
            "ideal_weight": 4.5,
            "activity_level": "moderate",
            "spayed_neutered": True,
            "medication_1_name": "Heart Medication",
            "medication_1_dosage": "5mg",
            "medication_1_frequency": "daily",
            "medication_1_time": "08:00:00",
            "medication_1_with_meals": True,
        }

        result10 = await mock_config_flow.async_step_dog_health(health_config2)
        assert result10["type"] == FlowResultType.FORM
        assert result10["step_id"] == "add_another_dog"

        # Verify second dog was added
        assert len(mock_config_flow._dogs) == 2
        second_dog = mock_config_flow._dogs[1]
        assert second_dog[CONF_DOG_NAME] == "Luna"
        assert second_dog[CONF_MODULES][MODULE_GPS] is False
        assert "gps_config" not in second_dog
        assert "health_config" in second_dog
        assert "medications" in second_dog["health_config"]

        # Choose not to add more dogs
        result11 = await mock_config_flow.async_step_add_another_dog(
            {"add_another": False}
        )
        assert result11["type"] == FlowResultType.FORM
        assert result11["step_id"] == "configure_modules"

    @pytest.mark.asyncio
    async def test_complex_multi_dog_health_integration_workflow(
        self, mock_config_flow
    ):
        """Test complex health integration across multiple dogs."""
        # Dog 1: Senior dog with multiple health conditions
        senior_dog = {
            CONF_DOG_ID: "senior_dog",
            CONF_DOG_NAME: "Senior Dog",
            CONF_DOG_AGE: 12,
            CONF_DOG_WEIGHT: 30.0,
            CONF_DOG_SIZE: "large",
        }

        result1 = await mock_config_flow.async_step_add_dog(senior_dog)
        assert result1["type"] == FlowResultType.FORM

        # Enable health and medication modules
        modules_config = {
            "enable_feeding": True,
            "enable_health": True,
            "enable_medication": True,
            "enable_gps": False,
        }

        result2 = await mock_config_flow.async_step_dog_modules(modules_config)
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "dog_feeding"

        # Configure feeding with health awareness
        feeding_config = {
            CONF_MEALS_PER_DAY: 2,
            CONF_DAILY_FOOD_AMOUNT: 600,
            CONF_FOOD_TYPE: "wet_food",
            "health_aware_portions": True,
        }

        result3 = await mock_config_flow.async_step_dog_feeding(feeding_config)
        assert result3["type"] == FlowResultType.FORM
        assert result3["step_id"] == "dog_health"

        # Complex health configuration with multiple conditions
        complex_health_config = {
            "vet_name": "Senior Pet Clinic",
            "weight_tracking": True,
            "ideal_weight": 28.0,  # Weight loss goal
            "body_condition_score": 6,  # Slightly overweight
            "activity_level": "low",
            "weight_goal": "lose",
            "spayed_neutered": True,
            # Health conditions
            "has_arthritis": True,
            "has_heart_disease": True,
            "has_kidney_disease": False,
            "has_diabetes": False,
            # Special diets for senior dog with conditions
            "senior_formula": True,
            "joint_support": True,
            "weight_control": True,
            "low_fat": True,  # For heart condition
            "prescription": True,  # Veterinary diet
            # Multiple medications
            "medication_1_name": "Arthritis Relief",
            "medication_1_dosage": "75mg",
            "medication_1_frequency": "twice_daily",
            "medication_1_time": "08:00:00",
            "medication_1_with_meals": True,
            "medication_2_name": "Heart Medication",
            "medication_2_dosage": "10mg",
            "medication_2_frequency": "daily",
            "medication_2_time": "18:00:00",
            "medication_2_with_meals": False,
        }

        result4 = await mock_config_flow.async_step_dog_health(complex_health_config)
        assert result4["type"] == FlowResultType.FORM
        assert result4["step_id"] == "add_another_dog"

        # Verify complex health configuration was stored
        assert len(mock_config_flow._dogs) == 1
        senior_dog_config = mock_config_flow._dogs[0]
        health_config = senior_dog_config["health_config"]

        assert health_config["weight_goal"] == "lose"
        assert health_config["body_condition_score"] == 6
        assert "arthritis" in health_config["health_conditions"]
        assert "heart_disease" in health_config["health_conditions"]
        assert len(health_config["medications"]) == 2
        assert any(
            med["name"] == "Arthritis Relief" for med in health_config["medications"]
        )

        # Verify diet validation was performed
        feeding_config = senior_dog_config["feeding_config"]
        assert feeding_config["health_aware_portions"] is True
        assert feeding_config["weight_goal"] == "lose"
        assert "diet_validation" in feeding_config

    @pytest.mark.asyncio
    async def test_multi_dog_gps_configuration_workflow(self, mock_config_flow):
        """Test GPS configuration across multiple dogs with different devices."""
        gps_configs = [
            {
                "dog": {
                    CONF_DOG_ID: "outdoor_dog",
                    CONF_DOG_NAME: "Outdoor Dog",
                    CONF_DOG_SIZE: "large",
                },
                "gps": {
                    CONF_GPS_SOURCE: "tractive",
                    "gps_update_interval": 30,
                    "gps_accuracy_filter": 10,
                    "enable_geofencing": True,
                    "home_zone_radius": 200,
                },
            },
            {
                "dog": {
                    CONF_DOG_ID: "indoor_dog",
                    CONF_DOG_NAME: "Indoor Dog",
                    CONF_DOG_SIZE: "small",
                },
                "gps": {
                    CONF_GPS_SOURCE: "manual",
                    "gps_update_interval": 120,
                    "gps_accuracy_filter": 50,
                    "enable_geofencing": False,
                },
            },
            {
                "dog": {
                    CONF_DOG_ID: "family_dog",
                    CONF_DOG_NAME: "Family Dog",
                    CONF_DOG_SIZE: "medium",
                },
                "gps": {
                    CONF_GPS_SOURCE: "person.owner",
                    "gps_update_interval": 60,
                    "gps_accuracy_filter": 25,
                    "enable_geofencing": True,
                    "home_zone_radius": 100,
                },
            },
        ]

        for i, config in enumerate(gps_configs):
            # Add dog
            result1 = await mock_config_flow.async_step_add_dog(config["dog"])
            assert result1["type"] == FlowResultType.FORM

            # Configure modules with GPS enabled
            modules_config = {
                "enable_gps": True,
                "enable_feeding": False,  # Skip other steps for GPS focus
                "enable_health": False,
            }

            result2 = await mock_config_flow.async_step_dog_modules(modules_config)
            assert result2["type"] == FlowResultType.FORM
            assert result2["step_id"] == "dog_gps"

            # Configure GPS
            result3 = await mock_config_flow.async_step_dog_gps(config["gps"])
            assert result3["type"] == FlowResultType.FORM
            assert result3["step_id"] == "add_another_dog"

            # Verify GPS configuration
            dog_config = mock_config_flow._dogs[i]
            assert "gps_config" in dog_config
            assert (
                dog_config["gps_config"][CONF_GPS_SOURCE]
                == config["gps"][CONF_GPS_SOURCE]
            )

            # Add another dog if not the last one
            if i < len(gps_configs) - 1:
                result4 = await mock_config_flow.async_step_add_another_dog(
                    {"add_another": True}
                )
                assert result4["type"] == FlowResultType.FORM
                assert result4["step_id"] == "add_dog"

        # Verify all dogs were configured with different GPS sources
        assert len(mock_config_flow._dogs) == 3
        gps_sources = [
            dog["gps_config"][CONF_GPS_SOURCE] for dog in mock_config_flow._dogs
        ]
        assert "tractive" in gps_sources
        assert "manual" in gps_sources
        assert "person.owner" in gps_sources

    @pytest.mark.asyncio
    async def test_maximum_dogs_workflow(self, mock_config_flow):
        """Test workflow when approaching maximum number of dogs."""
        # Add dogs up to near the limit
        dogs_to_add = min(MAX_DOGS_PER_ENTRY - 1, 8)  # Leave room for one more

        for i in range(dogs_to_add):
            dog_config = {
                CONF_DOG_ID: f"dog_{i + 1}",
                CONF_DOG_NAME: f"Dog {i + 1}",
                CONF_DOG_SIZE: "medium",
                CONF_DOG_WEIGHT: 20.0 + i,
                CONF_DOG_AGE: 3 + (i % 5),
            }

            result1 = await mock_config_flow.async_step_add_dog(dog_config)
            assert result1["type"] == FlowResultType.FORM

            # Minimal module configuration to speed up test
            modules_config = {
                "enable_feeding": i % 2 == 0,  # Alternate feeding
                "enable_health": i % 3 == 0,  # Every third dog
                "enable_gps": i % 4 == 0,  # Every fourth dog
            }

            result2 = await mock_config_flow.async_step_dog_modules(modules_config)

            # Handle different next steps based on modules
            if modules_config["enable_gps"]:
                assert result2["step_id"] == "dog_gps"
                # Configure minimal GPS
                gps_config = {CONF_GPS_SOURCE: "manual"}
                result3 = await mock_config_flow.async_step_dog_gps(gps_config)
                if modules_config["enable_feeding"]:
                    assert result3["step_id"] == "dog_feeding"
                    feeding_config = {
                        CONF_MEALS_PER_DAY: 2,
                        CONF_DAILY_FOOD_AMOUNT: 400,
                    }
                    result4 = await mock_config_flow.async_step_dog_feeding(
                        feeding_config
                    )
                    if modules_config["enable_health"]:
                        assert result4["step_id"] == "dog_health"
                        health_config = {"weight_tracking": True}
                        result5 = await mock_config_flow.async_step_dog_health(
                            health_config
                        )
                        assert result5["step_id"] == "add_another_dog"
                    else:
                        assert result4["step_id"] == "add_another_dog"
                else:
                    assert result3["step_id"] == "add_another_dog"
            elif modules_config["enable_feeding"]:
                assert result2["step_id"] == "dog_feeding"
                feeding_config = {CONF_MEALS_PER_DAY: 2, CONF_DAILY_FOOD_AMOUNT: 400}
                result3 = await mock_config_flow.async_step_dog_feeding(feeding_config)
                if modules_config["enable_health"]:
                    assert result3["step_id"] == "dog_health"
                    health_config = {"weight_tracking": True}
                    result4 = await mock_config_flow.async_step_dog_health(
                        health_config
                    )
                    assert result4["step_id"] == "add_another_dog"
                else:
                    assert result3["step_id"] == "add_another_dog"
            elif modules_config["enable_health"]:
                assert result2["step_id"] == "dog_health"
                health_config = {"weight_tracking": True}
                result3 = await mock_config_flow.async_step_dog_health(health_config)
                assert result3["step_id"] == "add_another_dog"
            else:
                assert result2["step_id"] == "add_another_dog"

            # Add another dog if not the last one
            if i < dogs_to_add - 1:
                await mock_config_flow.async_step_add_another_dog({"add_another": True})

        # Verify we have the expected number of dogs
        assert len(mock_config_flow._dogs) == dogs_to_add

        # Test adding one more dog to reach the limit
        last_dog_config = {
            CONF_DOG_ID: "final_dog",
            CONF_DOG_NAME: "Final Dog",
            CONF_DOG_SIZE: "large",
        }

        await mock_config_flow.async_step_add_dog(last_dog_config)
        await mock_config_flow.async_step_dog_modules({"enable_feeding": False})

        # Should now be at or near the limit
        assert len(mock_config_flow._dogs) == dogs_to_add + 1

        # Test the "add another dog" step when at/near limit
        result_limit = await mock_config_flow.async_step_add_another_dog(None)
        placeholders = result_limit["description_placeholders"]

        # Should show limit information
        assert "at_limit" in placeholders
        assert str(len(mock_config_flow._dogs)) in placeholders["dog_count"]


class TestAdvancedDietValidationScenarios:
    """Test comprehensive diet validation and conflict detection."""

    @pytest.mark.asyncio
    async def test_diet_conflict_detection_workflow(self, mock_config_flow):
        """Test detection of conflicting diet combinations."""
        # Add dog with conflicting diet requirements
        dog_config = {
            CONF_DOG_ID: "conflict_dog",
            CONF_DOG_NAME: "Conflict Dog",
            CONF_DOG_AGE: 2,  # Young adult
            CONF_DOG_SIZE: "medium",
        }

        await mock_config_flow.async_step_add_dog(dog_config)
        await mock_config_flow.async_step_dog_modules({"enable_health": True})
        result3 = await mock_config_flow.async_step_dog_health(
            {
                # Conflicting age-specific diets
                "puppy_formula": True,
                "senior_formula": True,  # CONFLICT: Both age formulas
                # Multiple prescription diets
                "prescription": True,
                "diabetic": True,  # WARNING: Multiple prescription
                "kidney_support": True,  # WARNING: Multiple prescription
                # Raw diet with medical conditions
                "raw_diet": True,
                "sensitive_stomach": True,  # WARNING: Raw + sensitive stomach
            }
        )

        # Should complete but log conflicts
        assert result3["type"] == FlowResultType.FORM

        # Verify diet validation was performed
        dog = mock_config_flow._dogs[0]
        health_config = dog["health_config"]
        diet_requirements = health_config["special_diet_requirements"]

        # Check that all selected diets were recorded
        assert "puppy_formula" in diet_requirements
        assert "senior_formula" in diet_requirements
        assert "prescription" in diet_requirements
        assert "diabetic" in diet_requirements
        assert "kidney_support" in diet_requirements
        assert "raw_diet" in diet_requirements
        assert "sensitive_stomach" in diet_requirements

        # If feeding config exists, check diet validation
        if "feeding_config" in dog:
            diet_validation = dog["feeding_config"].get("diet_validation", {})
            assert diet_validation.get("recommended_vet_consultation") is True

    @pytest.mark.asyncio
    async def test_age_appropriate_diet_suggestions(self, mock_config_flow):
        """Test age-appropriate diet suggestions."""
        test_cases = [
            {
                "age": 1,  # Puppy
                "expected_defaults": {"puppy_formula": True, "senior_formula": False},
                "name": "Puppy Test",
            },
            {
                "age": 8,  # Senior
                "expected_defaults": {"puppy_formula": False, "senior_formula": True},
                "name": "Senior Test",
            },
            {
                "age": 4,  # Adult
                "expected_defaults": {"puppy_formula": False, "senior_formula": False},
                "name": "Adult Test",
            },
        ]

        for case in test_cases:
            dog_config = {
                CONF_DOG_ID: f"age_test_dog_{case['age']}",
                CONF_DOG_NAME: case["name"],
                CONF_DOG_AGE: case["age"],
                CONF_DOG_SIZE: "medium",
            }

            await mock_config_flow.async_step_add_dog(dog_config)
            await mock_config_flow.async_step_dog_modules({"enable_health": True})

            # Check if the health form shows appropriate defaults
            result3 = await mock_config_flow.async_step_dog_health(None)
            assert result3["type"] == FlowResultType.FORM
            assert result3["step_id"] == "dog_health"

            # Verify the schema has the expected defaults
            schema = result3["data_schema"]
            assert schema is not None

            # Test with defaults that should be applied based on age
            health_config = {}
            for diet, expected in case["expected_defaults"].items():
                health_config[diet] = expected

            result4 = await mock_config_flow.async_step_dog_health(health_config)
            assert result4["type"] == FlowResultType.FORM

            # Verify the diet was properly set
            dog = mock_config_flow._dogs[-1]  # Last added dog
            diet_requirements = dog["health_config"]["special_diet_requirements"]

            for diet, expected in case["expected_defaults"].items():
                if expected:
                    assert diet in diet_requirements
                else:
                    assert diet not in diet_requirements

    @pytest.mark.asyncio
    async def test_comprehensive_special_diet_coverage(self, mock_config_flow):
        """Test that all special diet options from const.py are properly handled."""
        dog_config = {
            CONF_DOG_ID: "comprehensive_diet_dog",
            CONF_DOG_NAME: "Comprehensive Diet Dog",
            CONF_DOG_SIZE: "large",
            CONF_DOG_AGE: 6,
        }

        await mock_config_flow.async_step_add_dog(dog_config)
        await mock_config_flow.async_step_dog_modules({"enable_health": True})

        # Test all special diet options from SPECIAL_DIET_OPTIONS
        all_diet_config = {}
        for diet_option in SPECIAL_DIET_OPTIONS:
            all_diet_config[diet_option] = True

        # Should handle all diet options without errors
        result3 = await mock_config_flow.async_step_dog_health(all_diet_config)
        assert result3["type"] == FlowResultType.FORM

        # Verify all diets were recorded
        dog = mock_config_flow._dogs[0]
        diet_requirements = dog["health_config"]["special_diet_requirements"]

        # All SPECIAL_DIET_OPTIONS should be present
        for diet_option in SPECIAL_DIET_OPTIONS:
            assert diet_option in diet_requirements

        # Should have validation warnings/conflicts for this many diets
        if "feeding_config" in dog:
            diet_validation = dog["feeding_config"].get("diet_validation", {})
            assert diet_validation.get("total_diets") == len(SPECIAL_DIET_OPTIONS)

    def test_diet_compatibility_rules_validation(self, mock_config_flow):
        """Test the diet compatibility rules validation logic."""
        # Test each compatibility rule defined in DIET_COMPATIBILITY_RULES
        test_cases = [
            {
                "name": "age_exclusive_conflict",
                "diets": ["puppy_formula", "senior_formula"],
                "expected_conflicts": 1,
                "expected_warnings": 0,
            },
            {
                "name": "multiple_prescription_warning",
                "diets": ["prescription", "diabetic", "kidney_support"],
                "expected_conflicts": 0,
                "expected_warnings": 1,
            },
            {
                "name": "raw_medical_warning",
                "diets": ["raw_diet", "prescription", "sensitive_stomach"],
                "expected_conflicts": 0,
                "expected_warnings": 2,  # Raw + medical conditions warning + multiple prescription
            },
            {
                "name": "hypoallergenic_warning",
                "diets": ["hypoallergenic", "organic", "raw_diet"],
                "expected_conflicts": 0,
                "expected_warnings": 2,  # Hypoallergenic + others, raw + medical
            },
        ]

        for case in test_cases:
            validation_result = mock_config_flow._validate_diet_combinations(
                case["diets"]
            )

            assert len(validation_result["conflicts"]) == case["expected_conflicts"], (
                f"Case {case['name']}: Expected {case['expected_conflicts']} conflicts, "
                f"got {len(validation_result['conflicts'])}"
            )

            assert len(validation_result["warnings"]) >= case["expected_warnings"], (
                f"Case {case['name']}: Expected at least {case['expected_warnings']} warnings, "
                f"got {len(validation_result['warnings'])}"
            )

            # Should recommend vet consultation if there are any conflicts or warnings
            if case["expected_conflicts"] > 0 or case["expected_warnings"] > 0:
                assert validation_result["recommended_vet_consultation"] is True


class TestPerformanceAndStressScenarios:
    """Test performance under stress conditions and large configurations."""

    @pytest.mark.asyncio
    async def test_validation_rate_limiting(self, mock_config_flow):
        """Test that validation rate limiting prevents flooding."""
        # Create multiple validation requests rapidly
        validation_tasks = []

        for i in range(10):
            dog_config = {
                CONF_DOG_ID: f"rapid_dog_{i}",
                CONF_DOG_NAME: f"Rapid Dog {i}",
                CONF_DOG_SIZE: "medium",
            }
            # Each validation should respect the semaphore
            task = mock_config_flow._async_validate_dog_config(dog_config)
            validation_tasks.append(task)

        # Run validations concurrently
        start_time = time.time()
        results = await asyncio.gather(*validation_tasks, return_exceptions=True)
        end_time = time.time()

        # All should complete successfully
        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"Task {i} failed: {result}"
            assert result["valid"] is True

        # Should take some time due to rate limiting
        total_time = end_time - start_time
        assert total_time > 0.05  # At least 50ms for rate limiting

    @pytest.mark.asyncio
    async def test_large_scale_dog_configuration_performance(self, mock_config_flow):
        """Test performance with large numbers of dogs."""
        # Create configurations for many dogs
        large_dog_count = min(
            MAX_DOGS_PER_ENTRY // 2, 15
        )  # Don't exceed reasonable limits

        start_time = time.time()

        for i in range(large_dog_count):
            dog_config = {
                CONF_DOG_ID: f"perf_dog_{i:03d}",
                CONF_DOG_NAME: f"Performance Dog {i:03d}",
                CONF_DOG_BREED: f"Breed {i % 10}",
                CONF_DOG_AGE: 2 + (i % 12),
                CONF_DOG_WEIGHT: 10.0 + (i % 30),
                CONF_DOG_SIZE: ["toy", "small", "medium", "large", "giant"][i % 5],
            }

            # Add dog with minimal configuration to test performance
            result1 = await mock_config_flow.async_step_add_dog(dog_config)
            assert result1["type"] == FlowResultType.FORM

            # Simple module configuration
            modules_config = {
                "enable_feeding": i % 2 == 0,
                "enable_health": i % 3 == 0,
                "enable_gps": i % 5 == 0,
            }

            result2 = await mock_config_flow.async_step_dog_modules(modules_config)

            # Skip detailed configuration for performance test
            if result2["step_id"] != "add_another_dog":
                # If not going directly to add_another_dog, configure minimally
                if result2["step_id"] == "dog_gps":
                    await mock_config_flow.async_step_dog_gps(
                        {CONF_GPS_SOURCE: "manual"}
                    )
                elif result2["step_id"] == "dog_feeding":
                    await mock_config_flow.async_step_dog_feeding(
                        {CONF_MEALS_PER_DAY: 2, CONF_DAILY_FOOD_AMOUNT: 400}
                    )
                elif result2["step_id"] == "dog_health":
                    await mock_config_flow.async_step_dog_health(
                        {"weight_tracking": True}
                    )

        end_time = time.time()
        total_time = end_time - start_time

        # Verify all dogs were added
        assert len(mock_config_flow._dogs) == large_dog_count

        # Performance should be reasonable (less than 2 seconds per dog on average)
        average_time_per_dog = total_time / large_dog_count
        assert average_time_per_dog < 2.0, (
            f"Performance too slow: {average_time_per_dog:.2f}s per dog"
        )

        # Verify no memory leaks in validation cache
        assert len(mock_config_flow._validation_cache) <= large_dog_count * 2

    @pytest.mark.asyncio
    async def test_complex_configuration_memory_usage(self, mock_config_flow):
        """Test memory usage with complex dog configurations."""
        # Create dogs with very complex configurations
        complex_dogs_count = 5

        for i in range(complex_dogs_count):
            dog_config = {
                CONF_DOG_ID: f"complex_dog_{i}",
                CONF_DOG_NAME: f"Complex Dog {i}",
                CONF_DOG_SIZE: "large",
                CONF_DOG_BREED: "Complex Breed with Very Long Name That Tests Memory",
            }

            await mock_config_flow.async_step_add_dog(dog_config)

            # Enable all modules
            all_modules = {
                "enable_feeding": True,
                "enable_walk": True,
                "enable_health": True,
                "enable_gps": True,
                "enable_notifications": True,
                "enable_dashboard": True,
                "enable_visitor": True,
                "enable_grooming": True,
                "enable_medication": True,
                "enable_training": True,
            }

            await mock_config_flow.async_step_dog_modules(all_modules)

            # Complex GPS configuration
            complex_gps = {
                CONF_GPS_SOURCE: "tractive",
                "gps_update_interval": 15,
                "gps_accuracy_filter": 5,
                "enable_geofencing": True,
                "home_zone_radius": 150,
            }

            await mock_config_flow.async_step_dog_gps(complex_gps)

            # Complex feeding configuration
            complex_feeding = {
                CONF_MEALS_PER_DAY: 4,
                CONF_DAILY_FOOD_AMOUNT: 1000,
                CONF_FOOD_TYPE: "mixed",
                "feeding_schedule": "custom",
                "breakfast_enabled": True,
                CONF_BREAKFAST_TIME: "06:30:00",
                "lunch_enabled": True,
                CONF_LUNCH_TIME: "12:00:00",
                "dinner_enabled": True,
                CONF_DINNER_TIME: "17:30:00",
                "snacks_enabled": True,
                "enable_reminders": True,
                "reminder_minutes_before": 10,
            }

            await mock_config_flow.async_step_dog_feeding(complex_feeding)

            # Very complex health configuration
            complex_health = {
                "vet_name": f"Complex Veterinary Clinic for Dog {i}",
                "vet_phone": f"+1-555-{i:03d}-{i * 123:04d}",
                "weight_tracking": True,
                "health_aware_portions": True,
                "ideal_weight": 35.0 + i,
                "body_condition_score": 5,
                "activity_level": "high",
                "weight_goal": "maintain",
                "spayed_neutered": True,
                # Multiple health conditions
                "has_arthritis": i % 2 == 0,
                "has_allergies": i % 3 == 0,
                "has_digestive_issues": i % 4 == 0,
                # Complex diet requirements
                "joint_support": True,
                "organic": True,
                "grain_free": i % 2 == 0,
                "hypoallergenic": i % 3 == 0,
                # Multiple medications
                "medication_1_name": f"Medication A for Dog {i}",
                "medication_1_dosage": f"{10 + i}mg",
                "medication_1_frequency": "daily",
                "medication_1_time": "08:00:00",
                "medication_1_with_meals": True,
                "medication_1_notes": f"Special instructions for dog {i} medication A",
                "medication_2_name": f"Medication B for Dog {i}",
                "medication_2_dosage": f"{5 + i}ml",
                "medication_2_frequency": "twice_daily",
                "medication_2_time": "20:00:00",
                "medication_2_with_meals": False,
                "medication_2_notes": f"Special instructions for dog {i} medication B",
            }

            result5 = await mock_config_flow.async_step_dog_health(complex_health)
            assert result5["type"] == FlowResultType.FORM

        # Verify all complex configurations were stored
        assert len(mock_config_flow._dogs) == complex_dogs_count

        # Verify complex data integrity
        for i, dog in enumerate(mock_config_flow._dogs):
            assert dog[CONF_DOG_NAME] == f"Complex Dog {i}"
            assert "gps_config" in dog
            assert "feeding_config" in dog
            assert "health_config" in dog
            assert len(dog["health_config"]["medications"]) == 2

    @pytest.mark.asyncio
    async def test_concurrent_dog_additions(self, mock_config_flow):
        """Test handling of concurrent dog addition attempts."""
        # This test simulates what might happen if someone rapidly clicked
        # through the interface or if there were race conditions

        # Create multiple add_dog tasks that might run concurrently
        concurrent_dogs = [
            {
                CONF_DOG_ID: f"concurrent_dog_{i}",
                CONF_DOG_NAME: f"Concurrent Dog {i}",
                CONF_DOG_SIZE: "medium",
            }
            for i in range(5)
        ]

        # Start multiple add_dog operations
        add_tasks = []
        for dog_config in concurrent_dogs:
            task = mock_config_flow.async_step_add_dog(dog_config)
            add_tasks.append(task)

        # Wait for all to complete
        results = await asyncio.gather(*add_tasks, return_exceptions=True)

        # At least some should succeed (the first one definitely should)
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) >= 1

        # The validation cache should handle concurrent access
        assert isinstance(mock_config_flow._validation_cache, dict)


class TestErrorRecoveryAndEdgeCases:
    """Test error recovery and edge case handling."""

    @pytest.mark.asyncio
    async def test_validation_timeout_recovery(self, mock_config_flow):
        """Test recovery from validation timeouts."""
        # Mock a validation that times out
        with patch.object(
            mock_config_flow, "_async_validate_dog_config"
        ) as mock_validate:
            mock_validate.side_effect = TimeoutError()

            dog_config = {
                CONF_DOG_ID: "timeout_dog",
                CONF_DOG_NAME: "Timeout Dog",
                CONF_DOG_SIZE: "medium",
            }

            result = await mock_config_flow.async_step_add_dog(dog_config)

            # Should show form with timeout error
            assert result["type"] == FlowResultType.FORM
            assert result["step_id"] == "add_dog"
            assert "validation_timeout" in result["errors"]["base"]

    @pytest.mark.asyncio
    async def test_partial_configuration_failure_recovery(self, mock_config_flow):
        """Test recovery from partial configuration failures."""
        # Start adding a dog successfully
        dog_config = {
            CONF_DOG_ID: "partial_fail_dog",
            CONF_DOG_NAME: "Partial Fail Dog",
            CONF_DOG_SIZE: "medium",
        }

        result1 = await mock_config_flow.async_step_add_dog(dog_config)
        assert result1["type"] == FlowResultType.FORM
        assert result1["step_id"] == "dog_modules"

        # Configure modules successfully
        modules_config = {"enable_health": True}
        result2 = await mock_config_flow.async_step_dog_modules(modules_config)
        assert result2["step_id"] == "dog_health"

        # Simulate failure during health configuration
        with patch.object(
            mock_config_flow, "_collect_health_conditions"
        ) as mock_collect:
            mock_collect.side_effect = ValueError("Health data parsing failed")

            health_config = {"weight_tracking": True}

            # Should handle the error gracefully
            try:
                result3 = await mock_config_flow.async_step_dog_health(health_config)
                # If it doesn't raise an exception, it should show an error form
                assert result3["type"] == FlowResultType.FORM
            except ValueError:
                # If it does raise, that's also acceptable - depends on implementation
                pass

    @pytest.mark.asyncio
    async def test_invalid_dog_data_edge_cases(self, mock_config_flow):
        """Test handling of various invalid dog data edge cases."""
        invalid_configs = [
            {
                "name": "empty_dog_id",
                "config": {CONF_DOG_ID: "", CONF_DOG_NAME: "Valid Name"},
                "expected_error": CONF_DOG_ID,
            },
            {
                "name": "invalid_characters_dog_id",
                "config": {CONF_DOG_ID: "dog@#$%", CONF_DOG_NAME: "Valid Name"},
                "expected_error": CONF_DOG_ID,
            },
            {
                "name": "too_long_dog_id",
                "config": {CONF_DOG_ID: "a" * 50, CONF_DOG_NAME: "Valid Name"},
                "expected_error": CONF_DOG_ID,
            },
            {
                "name": "empty_dog_name",
                "config": {CONF_DOG_ID: "valid_id", CONF_DOG_NAME: ""},
                "expected_error": CONF_DOG_NAME,
            },
            {
                "name": "too_short_dog_name",
                "config": {CONF_DOG_ID: "valid_id", CONF_DOG_NAME: "A"},
                "expected_error": CONF_DOG_NAME,
            },
            {
                "name": "too_long_dog_name",
                "config": {CONF_DOG_ID: "valid_id", CONF_DOG_NAME: "A" * 100},
                "expected_error": CONF_DOG_NAME,
            },
            {
                "name": "negative_weight",
                "config": {
                    CONF_DOG_ID: "valid_id",
                    CONF_DOG_NAME: "Valid Name",
                    CONF_DOG_WEIGHT: -5.0,
                },
                "expected_error": CONF_DOG_WEIGHT,
            },
            {
                "name": "excessive_weight",
                "config": {
                    CONF_DOG_ID: "valid_id",
                    CONF_DOG_NAME: "Valid Name",
                    CONF_DOG_WEIGHT: 200.0,
                },
                "expected_error": CONF_DOG_WEIGHT,
            },
            {
                "name": "negative_age",
                "config": {
                    CONF_DOG_ID: "valid_id",
                    CONF_DOG_NAME: "Valid Name",
                    CONF_DOG_AGE: -1,
                },
                "expected_error": CONF_DOG_AGE,
            },
            {
                "name": "excessive_age",
                "config": {
                    CONF_DOG_ID: "valid_id",
                    CONF_DOG_NAME: "Valid Name",
                    CONF_DOG_AGE: 50,
                },
                "expected_error": CONF_DOG_AGE,
            },
            {
                "name": "weight_size_mismatch",
                "config": {
                    CONF_DOG_ID: "valid_id",
                    CONF_DOG_NAME: "Valid Name",
                    CONF_DOG_WEIGHT: 80.0,  # Giant dog weight
                    CONF_DOG_SIZE: "toy",  # But toy size
                },
                "expected_error": CONF_DOG_WEIGHT,
            },
        ]

        for case in invalid_configs:
            result = await mock_config_flow.async_step_add_dog(case["config"])

            # Should show form with appropriate error
            assert result["type"] == FlowResultType.FORM
            assert result["step_id"] == "add_dog"
            assert case["expected_error"] in result["errors"], (
                f"Case {case['name']}: Expected error for {case['expected_error']}, "
                f"got errors: {result['errors']}"
            )

    @pytest.mark.asyncio
    async def test_duplicate_dog_detection(self, mock_config_flow):
        """Test detection and handling of duplicate dogs."""
        # Add first dog successfully
        first_dog = {
            CONF_DOG_ID: "unique_dog",
            CONF_DOG_NAME: "Unique Dog",
            CONF_DOG_SIZE: "medium",
        }

        result1 = await mock_config_flow.async_step_add_dog(first_dog)
        assert result1["type"] == FlowResultType.FORM
        await mock_config_flow.async_step_dog_modules({"enable_feeding": False})

        # Try to add dog with same ID
        duplicate_id_dog = {
            CONF_DOG_ID: "unique_dog",  # Same ID
            CONF_DOG_NAME: "Different Name",
            CONF_DOG_SIZE: "large",
        }

        result2 = await mock_config_flow.async_step_add_dog(duplicate_id_dog)
        assert result2["type"] == FlowResultType.FORM
        assert CONF_DOG_ID in result2["errors"]
        assert "already_exists" in result2["errors"][CONF_DOG_ID]

        # Try to add dog with same name (case insensitive)
        duplicate_name_dog = {
            CONF_DOG_ID: "different_id",
            CONF_DOG_NAME: "UNIQUE DOG",  # Same name, different case
            CONF_DOG_SIZE: "small",
        }

        result3 = await mock_config_flow.async_step_add_dog(duplicate_name_dog)
        assert result3["type"] == FlowResultType.FORM
        assert CONF_DOG_NAME in result3["errors"]
        assert "already_exists" in result3["errors"][CONF_DOG_NAME]

    @pytest.mark.asyncio
    async def test_gps_configuration_edge_cases(self, mock_config_flow):
        """Test edge cases in GPS configuration."""
        # Setup dog first
        dog_config = {CONF_DOG_ID: "gps_test_dog", CONF_DOG_NAME: "GPS Test Dog"}
        await mock_config_flow.async_step_add_dog(dog_config)
        await mock_config_flow.async_step_dog_modules({"enable_gps": True})

        # Test extreme GPS configuration values
        extreme_gps_configs = [
            {
                "name": "minimal_update_interval",
                "config": {
                    CONF_GPS_SOURCE: "manual",
                    "gps_update_interval": 30,  # Minimum allowed
                    "gps_accuracy_filter": 5,  # Minimum allowed
                    "home_zone_radius": 10,  # Minimum allowed
                },
            },
            {
                "name": "maximum_update_interval",
                "config": {
                    CONF_GPS_SOURCE: "webhook",
                    "gps_update_interval": 600,  # Maximum allowed
                    "gps_accuracy_filter": 500,  # Maximum allowed
                    "home_zone_radius": 500,  # Maximum allowed
                },
            },
            {
                "name": "nonexistent_device_tracker",
                "config": {
                    CONF_GPS_SOURCE: "device_tracker.nonexistent",
                    "gps_update_interval": 60,
                },
            },
            {
                "name": "complex_source_name",
                "config": {
                    CONF_GPS_SOURCE: "device_tracker.very_long_device_name_with_special_chars_123",
                    "gps_update_interval": 120,
                },
            },
        ]

        for case in extreme_gps_configs:
            # Should handle all configurations gracefully
            result = await mock_config_flow.async_step_dog_gps(case["config"])
            assert result["type"] == FlowResultType.FORM, f"Case {case['name']} failed"

            # Verify GPS config was stored
            if mock_config_flow._current_dog_config:
                gps_config = mock_config_flow._current_dog_config.get("gps_config", {})
                assert CONF_GPS_SOURCE in gps_config
                assert gps_config[CONF_GPS_SOURCE] == case["config"][CONF_GPS_SOURCE]


class TestCrossValidationAndConsistency:
    """Test cross-validation and consistency checks across dogs."""

    @pytest.mark.asyncio
    async def test_feeding_consistency_across_dogs(self, mock_config_flow):
        """Test feeding consistency validation across multiple dogs."""
        # Add dogs with varying feeding configurations
        feeding_variations = [
            {
                "dog": {
                    CONF_DOG_ID: "big_eater",
                    CONF_DOG_NAME: "Big Eater",
                    CONF_DOG_SIZE: "giant",
                    CONF_DOG_WEIGHT: 70.0,
                },
                "feeding": {
                    CONF_MEALS_PER_DAY: 2,
                    CONF_DAILY_FOOD_AMOUNT: 1200,
                    CONF_FOOD_TYPE: "dry_food",
                },
            },
            {
                "dog": {
                    CONF_DOG_ID: "small_eater",
                    CONF_DOG_NAME: "Small Eater",
                    CONF_DOG_SIZE: "toy",
                    CONF_DOG_WEIGHT: 3.0,
                },
                "feeding": {
                    CONF_MEALS_PER_DAY: 4,
                    CONF_DAILY_FOOD_AMOUNT: 120,
                    CONF_FOOD_TYPE: "wet_food",
                },
            },
            {
                "dog": {
                    CONF_DOG_ID: "medium_eater",
                    CONF_DOG_NAME: "Medium Eater",
                    CONF_DOG_SIZE: "medium",
                    CONF_DOG_WEIGHT: 25.0,
                },
                "feeding": {
                    CONF_MEALS_PER_DAY: 2,
                    CONF_DAILY_FOOD_AMOUNT: 500,
                    CONF_FOOD_TYPE: "mixed",
                },
            },
        ]

        for variation in feeding_variations:
            # Add dog
            await mock_config_flow.async_step_add_dog(variation["dog"])
            await mock_config_flow.async_step_dog_modules({"enable_feeding": True})
            result3 = await mock_config_flow.async_step_dog_feeding(
                variation["feeding"]
            )

            # Should complete successfully
            assert result3["type"] == FlowResultType.FORM

        # Verify feeding configurations make sense relative to dog sizes
        for _i, dog in enumerate(mock_config_flow._dogs):
            feeding_config = dog["feeding_config"]
            dog_weight = dog[CONF_DOG_WEIGHT]
            daily_amount = feeding_config[CONF_DAILY_FOOD_AMOUNT]

            # Basic sanity check: food amount should roughly correlate with weight
            amount_per_kg = daily_amount / dog_weight

            # Should be between 10-50g per kg (reasonable range)
            assert 10 <= amount_per_kg <= 50, (
                f"Dog {dog[CONF_DOG_NAME]} has unreasonable food ratio: "
                f"{amount_per_kg:.1f}g per kg"
            )

    @pytest.mark.asyncio
    async def test_health_condition_consistency_validation(self, mock_config_flow):
        """Test consistency of health conditions across related configurations."""
        # Add dog with health conditions that should affect feeding
        health_aware_dog = {
            CONF_DOG_ID: "health_aware_dog",
            CONF_DOG_NAME: "Health Aware Dog",
            CONF_DOG_SIZE: "large",
            CONF_DOG_WEIGHT: 40.0,
            CONF_DOG_AGE: 8,  # Senior
        }

        await mock_config_flow.async_step_add_dog(health_aware_dog)
        await mock_config_flow.async_step_dog_modules(
            {
                "enable_feeding": True,
                "enable_health": True,
                "enable_medication": True,
            }
        )

        # Configure feeding first
        feeding_config = {
            CONF_MEALS_PER_DAY: 2,
            CONF_DAILY_FOOD_AMOUNT: 700,
            CONF_FOOD_TYPE: "wet_food",
            "health_aware_portions": True,
        }

        await mock_config_flow.async_step_dog_feeding(feeding_config)

        # Configure health with conditions that should be reflected in feeding
        health_config = {
            "weight_tracking": True,
            "ideal_weight": 35.0,  # Weight loss goal
            "body_condition_score": 7,  # Overweight
            "activity_level": "low",  # Low activity
            "weight_goal": "lose",
            "has_diabetes": True,
            "has_kidney_disease": True,
            # Corresponding special diets
            "diabetic": True,
            "kidney_support": True,
            "weight_control": True,
            "senior_formula": True,
            # Medication with meals
            "medication_1_name": "Diabetes Medication",
            "medication_1_with_meals": True,
            "medication_1_time": "08:00:00",
        }

        result4 = await mock_config_flow.async_step_dog_health(health_config)
        assert result4["type"] == FlowResultType.FORM

        # Verify health-feeding integration
        dog = mock_config_flow._dogs[0]
        dog["health_config"]
        feeding_data = dog["feeding_config"]

        # Check that health conditions are reflected in feeding config
        assert feeding_data["health_aware_portions"] is True
        assert feeding_data["weight_goal"] == "lose"
        assert feeding_data["ideal_weight"] == 35.0
        assert "diabetes" in feeding_data["health_conditions"]
        assert "kidney_disease" in feeding_data["health_conditions"]
        assert feeding_data["medication_with_meals"] is True

        # Verify special diet requirements are captured
        assert "diabetic" in feeding_data["special_diet"]
        assert "kidney_support" in feeding_data["special_diet"]
        assert "weight_control" in feeding_data["special_diet"]

    @pytest.mark.asyncio
    async def test_module_dependency_validation(self, mock_config_flow):
        """Test validation of module dependencies across configurations."""
        # Test scenarios where certain modules depend on others
        dependency_scenarios = [
            {
                "name": "medication_requires_health",
                "modules": {"enable_medication": True, "enable_health": False},
                "should_work": True,  # medication can work without health module
            },
            {
                "name": "gps_with_feeding_notifications",
                "modules": {
                    "enable_gps": True,
                    "enable_feeding": True,
                    "enable_notifications": True,
                },
                "should_work": True,
            },
            {
                "name": "all_modules_enabled",
                "modules": {
                    "enable_feeding": True,
                    "enable_walk": True,
                    "enable_health": True,
                    "enable_gps": True,
                    "enable_notifications": True,
                    "enable_dashboard": True,
                    "enable_visitor": True,
                    "enable_grooming": True,
                    "enable_medication": True,
                    "enable_training": True,
                },
                "should_work": True,
            },
            {
                "name": "minimal_modules",
                "modules": {
                    "enable_feeding": False,
                    "enable_health": False,
                    "enable_gps": False,
                },
                "should_work": True,  # Should work with minimal modules
            },
        ]

        for i, scenario in enumerate(dependency_scenarios):
            dog_config = {
                CONF_DOG_ID: f"dependency_dog_{i}",
                CONF_DOG_NAME: f"Dependency Dog {i}",
                CONF_DOG_SIZE: "medium",
            }

            await mock_config_flow.async_step_add_dog(dog_config)
            result2 = await mock_config_flow.async_step_dog_modules(scenario["modules"])

            if scenario["should_work"]:
                # Should proceed to next step or add_another_dog
                assert result2["type"] == FlowResultType.FORM
                next_step = result2["step_id"]
                assert next_step in [
                    "dog_gps",
                    "dog_feeding",
                    "dog_health",
                    "add_another_dog",
                ]

                # Verify modules were stored correctly
                current_modules = mock_config_flow._current_dog_config[CONF_MODULES]
                for module, expected in scenario["modules"].items():
                    module_name = module.replace("enable_", "")
                    # Convert enable_x to MODULE_X constants
                    if module_name == "feeding":
                        assert current_modules[MODULE_FEEDING] == expected
                    elif module_name == "health":
                        assert current_modules[MODULE_HEALTH] == expected
                    elif module_name == "gps":
                        assert current_modules[MODULE_GPS] == expected
                    # Add other module checks as needed
            else:
                # Should show error or handle gracefully
                assert result2["type"] == FlowResultType.FORM
                # May show errors or redirect appropriately


if __name__ == "__main__":
    pytest.main([__file__])
