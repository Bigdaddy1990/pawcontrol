"""Tests for the Paw Control config flow."""

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.config_flow import (
    DOG_ID_PATTERN,
    MAX_DOGS_PER_ENTRY,
    PawControlConfigFlow,
    PawControlOptionsFlow,
)
from custom_components.pawcontrol.const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_DOGS,
    CONF_MODULES,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
    MODULE_WALK,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


class TestPawControlConfigFlow:
    """Test the Paw Control config flow."""

    @pytest.fixture
    def flow(self):
        """Create a config flow instance."""
        return PawControlConfigFlow()

    @pytest.mark.asyncio
    async def test_user_step_show_form(self, hass: HomeAssistant):
        """Test the user step shows the form."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        result = await flow.async_step_user()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"
        assert "integration_name" in result["description_placeholders"]

    @pytest.mark.asyncio
    async def test_user_step_valid_input(self, hass: HomeAssistant):
        """Test user step with valid input."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        user_input = {"name": "My Paw Control"}

        with (
            patch.object(flow, "_generate_unique_id", return_value="my_paw_control"),
            patch.object(flow, "async_set_unique_id"),
            patch.object(flow, "_abort_if_unique_id_configured"),
            patch.object(flow, "async_step_add_dog") as mock_add_dog,
        ):
            mock_add_dog.return_value = {"type": FlowResultType.FORM}

            await flow.async_step_user(user_input)

            assert flow._integration_name == "My Paw Control"
            mock_add_dog.assert_called_once()

    @pytest.mark.asyncio
    async def test_user_step_invalid_name(self, hass: HomeAssistant):
        """Test user step with invalid name."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        user_input = {"name": ""}  # Empty name

        result = await flow.async_step_user(user_input)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_user_step_reserved_name(self, hass: HomeAssistant):
        """Test user step with reserved integration name."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        user_input = {"name": "Home Assistant"}  # Reserved name

        result = await flow.async_step_user(user_input)

        assert result["type"] == FlowResultType.FORM
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_add_dog_step_show_form(self, hass: HomeAssistant):
        """Test the add dog step shows the form."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        result = await flow.async_step_add_dog()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "add_dog"

    @pytest.mark.asyncio
    async def test_add_dog_step_valid_input(self, hass: HomeAssistant):
        """Test add dog step with valid input."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        user_input = {
            CONF_DOG_ID: "test_dog",
            CONF_DOG_NAME: "Test Dog",
            CONF_DOG_BREED: "Golden Retriever",
            CONF_DOG_AGE: 5,
            CONF_DOG_WEIGHT: 25.0,
            CONF_DOG_SIZE: "medium",
        }

        with patch.object(flow, "async_step_add_another_dog") as mock_add_another:
            mock_add_another.return_value = {"type": FlowResultType.FORM}

            await flow.async_step_add_dog(user_input)

            assert len(flow._dogs) == 1
            assert flow._dogs[0][CONF_DOG_ID] == "test_dog"
            assert flow._dogs[0][CONF_DOG_NAME] == "Test Dog"
            mock_add_another.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_dog_step_invalid_dog_id(self, hass: HomeAssistant):
        """Test add dog step with invalid dog ID."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        user_input = {
            CONF_DOG_ID: "Invalid Dog ID!",  # Contains invalid characters
            CONF_DOG_NAME: "Test Dog",
        }

        result = await flow.async_step_add_dog(user_input)

        assert result["type"] == FlowResultType.FORM
        assert "errors" in result
        assert len(flow._dogs) == 0

    @pytest.mark.asyncio
    async def test_add_dog_step_duplicate_dog_id(self, hass: HomeAssistant):
        """Test add dog step with duplicate dog ID."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        # Add first dog
        flow._dogs = [{"dog_id": "test_dog", "dog_name": "First Dog"}]

        user_input = {
            CONF_DOG_ID: "test_dog",  # Duplicate
            CONF_DOG_NAME: "Second Dog",
        }

        result = await flow.async_step_add_dog(user_input)

        assert result["type"] == FlowResultType.FORM
        assert "errors" in result
        assert len(flow._dogs) == 1  # No new dog added

    @pytest.mark.asyncio
    async def test_add_dog_step_weight_size_mismatch(self, hass: HomeAssistant):
        """Test add dog step with weight/size mismatch."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        user_input = {
            CONF_DOG_ID: "test_dog",
            CONF_DOG_NAME: "Test Dog",
            CONF_DOG_WEIGHT: 50.0,  # Too heavy for toy
            CONF_DOG_SIZE: "toy",
        }

        result = await flow.async_step_add_dog(user_input)

        assert result["type"] == FlowResultType.FORM
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_add_another_dog_step_yes(self, hass: HomeAssistant):
        """Test add another dog step with yes."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._dogs = [{"dog_id": "test_dog", "dog_name": "Test Dog"}]

        user_input = {"add_another": True}

        with patch.object(flow, "async_step_add_dog") as mock_add_dog:
            mock_add_dog.return_value = {"type": FlowResultType.FORM}

            await flow.async_step_add_another_dog(user_input)

            mock_add_dog.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_another_dog_step_no(self, hass: HomeAssistant):
        """Test add another dog step with no."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._dogs = [{"dog_id": "test_dog", "dog_name": "Test Dog"}]

        user_input = {"add_another": False}

        with patch.object(flow, "async_step_configure_modules") as mock_configure:
            mock_configure.return_value = {"type": FlowResultType.FORM}

            await flow.async_step_add_another_dog(user_input)

            mock_configure.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_another_dog_at_limit(self, hass: HomeAssistant):
        """Test add another dog when at limit."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        # Fill up to limit
        flow._dogs = [
            {"dog_id": f"dog_{i}", "dog_name": f"Dog {i}"}
            for i in range(MAX_DOGS_PER_ENTRY)
        ]

        result = await flow.async_step_add_another_dog()

        assert result["type"] == FlowResultType.FORM
        assert "at_limit" in result["description_placeholders"]

    @pytest.mark.asyncio
    async def test_configure_modules_step(self, hass: HomeAssistant):
        """Test configure modules step."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._dogs = [
            {
                "dog_id": "large_dog",
                "dog_name": "Large Dog",
                "dog_size": "large",
                "dog_age": 5,
                "modules": {},
            }
        ]

        user_input = {
            "enable_gps": True,
            "enable_health": True,
            "enable_visitor_mode": True,
            "enable_advanced_features": True,
        }

        with patch.object(flow, "async_step_final_setup") as mock_final:
            mock_final.return_value = {"type": FlowResultType.CREATE_ENTRY}

            await flow.async_step_configure_modules(user_input)

            # Check that modules were configured
            dog_modules = flow._dogs[0][CONF_MODULES]
            assert dog_modules[MODULE_GPS] is True
            assert dog_modules[MODULE_HEALTH] is True
            assert dog_modules[MODULE_VISITOR] is True

            mock_final.assert_called_once()

    @pytest.mark.asyncio
    async def test_configure_modules_no_dogs(self, hass: HomeAssistant):
        """Test configure modules with no dogs."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._dogs = []

        with patch.object(flow, "async_step_final_setup") as mock_final:
            mock_final.return_value = {"type": FlowResultType.ABORT}

            await flow.async_step_configure_modules()

            mock_final.assert_called_once()

    @pytest.mark.asyncio
    async def test_final_setup_step_success(self, hass: HomeAssistant):
        """Test final setup step success."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._integration_name = "Test Integration"
        flow._dogs = [
            {
                "dog_id": "test_dog",
                "dog_name": "Test Dog",
                "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
            }
        ]

        with patch.object(flow, "async_create_entry") as mock_create:
            mock_create.return_value = {"type": FlowResultType.CREATE_ENTRY}

            await flow.async_step_final_setup()

            mock_create.assert_called_once()
            call_args = mock_create.call_args
            assert call_args[1]["title"] == "Test Integration"
            assert CONF_DOGS in call_args[1]["data"]

    @pytest.mark.asyncio
    async def test_final_setup_no_dogs(self, hass: HomeAssistant):
        """Test final setup with no dogs configured."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._dogs = []

        with patch.object(flow, "async_abort") as mock_abort:
            mock_abort.return_value = {"type": FlowResultType.ABORT}

            await flow.async_step_final_setup()

            mock_abort.assert_called_once_with(reason="no_dogs_configured")

    def test_generate_unique_id(self):
        """Test unique ID generation."""
        flow = PawControlConfigFlow()

        # Test normal name
        uid = flow._generate_unique_id("My Paw Control")
        assert uid == "my_paw_control"

        # Test name with special characters
        uid = flow._generate_unique_id("Test-Name With Spaces!")
        assert uid == "testname_with_spaces"

        # Test name starting with number
        uid = flow._generate_unique_id("123 Test")
        assert uid == "paw_control_123_test"

    def test_dog_id_pattern(self):
        """Test dog ID validation pattern."""
        valid_ids = ["dog1", "my_dog", "test_123", "a", "abc_def_123"]
        invalid_ids = ["Dog1", "my-dog", "test dog", "123dog", "_dog", ""]

        for dog_id in valid_ids:
            assert DOG_ID_PATTERN.match(dog_id), f"Expected {dog_id} to be valid"

        for dog_id in invalid_ids:
            assert not DOG_ID_PATTERN.match(dog_id), f"Expected {dog_id} to be invalid"

    @pytest.mark.asyncio
    async def test_validate_dog_config_caching(self, hass: HomeAssistant):
        """Test that validation caching works."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        user_input = {
            CONF_DOG_ID: "test_dog",
            CONF_DOG_NAME: "Test Dog",
        }

        # First call
        result1 = await flow._async_validate_dog_config(user_input)

        # Second call should use cache
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 0  # Same timestamp
            result2 = await flow._async_validate_dog_config(user_input)

        assert result1 == result2

    def test_is_weight_size_compatible(self):
        """Test weight and size compatibility checking."""
        flow = PawControlConfigFlow()

        # Test compatible combinations
        assert flow._is_weight_size_compatible(5.0, "toy")
        assert flow._is_weight_size_compatible(10.0, "small")
        assert flow._is_weight_size_compatible(20.0, "medium")
        assert flow._is_weight_size_compatible(35.0, "large")
        assert flow._is_weight_size_compatible(60.0, "giant")

        # Test incompatible combinations
        assert not flow._is_weight_size_compatible(50.0, "toy")
        assert not flow._is_weight_size_compatible(2.0, "giant")

    def test_get_feeding_defaults_by_size(self):
        """Test feeding defaults by dog size."""
        flow = PawControlConfigFlow()

        toy_defaults = flow._get_feeding_defaults_by_size("toy")
        assert toy_defaults["meals_per_day"] == 3
        assert toy_defaults["daily_amount"] == 0.5

        giant_defaults = flow._get_feeding_defaults_by_size("giant")
        assert giant_defaults["meals_per_day"] == 2
        assert giant_defaults["daily_amount"] == 4.5

        # Test unknown size falls back to medium
        unknown_defaults = flow._get_feeding_defaults_by_size("unknown")
        medium_defaults = flow._get_feeding_defaults_by_size("medium")
        assert unknown_defaults == medium_defaults

    @pytest.mark.asyncio
    async def test_generate_smart_dog_id_suggestion(self, hass: HomeAssistant):
        """Test smart dog ID suggestion generation."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        # Test single word name
        suggestion = await flow._generate_smart_dog_id_suggestion({"dog_name": "Buddy"})
        assert suggestion == "buddy"

        # Test multi-word name
        suggestion = await flow._generate_smart_dog_id_suggestion(
            {"dog_name": "Max Cooper"}
        )
        assert suggestion == "max_c"

        # Test name with special characters
        suggestion = await flow._generate_smart_dog_id_suggestion(
            {"dog_name": "Rex-123!"}
        )
        assert suggestion == "rex123"

        # Test empty or no name
        suggestion = await flow._generate_smart_dog_id_suggestion({})
        assert suggestion == ""

        suggestion = await flow._generate_smart_dog_id_suggestion({"dog_name": ""})
        assert suggestion == ""

    @pytest.mark.asyncio
    async def test_generate_smart_dog_id_suggestion_conflict_resolution(
        self, hass: HomeAssistant
    ):
        """Test dog ID suggestion conflict resolution."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        # Add existing dog
        flow._dogs = [{"dog_id": "buddy", "dog_name": "Existing Buddy"}]

        suggestion = await flow._generate_smart_dog_id_suggestion({"dog_name": "Buddy"})
        assert suggestion == "buddy_2"  # Should avoid conflict

    @pytest.mark.asyncio
    async def test_suggest_dog_breed(self, hass: HomeAssistant):
        """Test dog breed suggestion."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        # Test name-based suggestion
        suggestion = await flow._suggest_dog_breed({"dog_name": "Max"})
        assert suggestion == "German Shepherd"

        suggestion = await flow._suggest_dog_breed({"dog_name": "Bella"})
        assert suggestion == "Labrador"

        # Test unknown name
        suggestion = await flow._suggest_dog_breed({"dog_name": "Unknown"})
        assert suggestion == ""

        # Test no input
        suggestion = await flow._suggest_dog_breed(None)
        assert suggestion == ""

    def test_format_dogs_list(self):
        """Test dogs list formatting."""
        flow = PawControlConfigFlow()

        # Test empty list
        formatted = flow._format_dogs_list()
        assert "No dogs configured" in formatted

        # Test with dogs
        flow._dogs = [
            {
                "dog_name": "Buddy",
                "dog_id": "buddy",
                "dog_breed": "Golden Retriever",
                "dog_age": 5,
                "dog_weight": 25.0,
                "dog_size": "medium",
                "modules": {"feeding": True, "walk": True, "health": False},
            }
        ]

        formatted = flow._format_dogs_list()
        assert "Buddy" in formatted
        assert "buddy" in formatted
        assert "Golden Retriever" in formatted
        assert "2/3 modules enabled" in formatted

    def test_get_dogs_module_summary(self):
        """Test dogs module summary generation."""
        flow = PawControlConfigFlow()
        flow._dogs = [
            {
                "dog_name": "Large Dog",
                "dog_size": "large",
                "dog_age": 5,
            },
            {
                "dog_name": "Small Puppy",
                "dog_size": "small",
                "dog_age": 1,
            },
        ]

        summary = flow._get_dogs_module_summary()
        assert "Large Dog: GPS tracking" in summary
        assert "Small Puppy: Standard modules" in summary

    @pytest.mark.asyncio
    async def test_create_intelligent_options(self, hass: HomeAssistant):
        """Test intelligent options creation."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        config_data = {
            CONF_DOGS: [
                {
                    "dog_size": "large",
                    "modules": {"gps": True, "feeding": True},
                },
                {
                    "dog_size": "small",
                    "modules": {"gps": False, "feeding": True},
                },
            ]
        }

        options = await flow._create_intelligent_options(config_data)

        assert "reset_time" in options
        assert "notifications" in options
        assert "gps_update_interval" in options
        assert "dashboard_mode" in options
        assert options["dashboard_mode"] == "full"  # Multiple dogs


class TestPawControlOptionsFlow:
    """Test the Paw Control options flow."""

    @pytest.fixture
    def options_flow(self, mock_config_entry):
        """Create an options flow instance."""
        return PawControlOptionsFlow(mock_config_entry)

    @pytest.mark.asyncio
    async def test_init_step_show_menu(self, hass: HomeAssistant, options_flow):
        """Test the init step shows the menu."""
        result = await options_flow.async_step_init()

        assert result["type"] == FlowResultType.MENU
        assert result["step_id"] == "init"
        assert "manage_dogs" in result["menu_options"]
        assert "gps_settings" in result["menu_options"]
        assert "notifications" in result["menu_options"]

    @pytest.mark.asyncio
    async def test_import_export_step_redirect(self, hass: HomeAssistant, options_flow):
        """Test import/export step redirects to main menu."""
        result = await options_flow.async_step_import_export()

        # Should redirect back to init
        assert result is not None


class TestConfigFlowValidation:
    """Test configuration flow validation functions."""

    @pytest.mark.asyncio
    async def test_async_validate_integration_name(self, hass: HomeAssistant):
        """Test integration name validation."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        # Test valid name
        result = await flow._async_validate_integration_name("My Paw Control")
        assert result["valid"] is True
        assert len(result["errors"]) == 0

        # Test empty name
        result = await flow._async_validate_integration_name("")
        assert result["valid"] is False
        assert "integration_name_required" in result["errors"].values()

        # Test too long name
        result = await flow._async_validate_integration_name("x" * 60)
        assert result["valid"] is False
        assert "integration_name_too_long" in result["errors"].values()

        # Test reserved name
        result = await flow._async_validate_integration_name("Home Assistant")
        assert result["valid"] is False
        assert "reserved_integration_name" in result["errors"].values()

    @pytest.mark.asyncio
    async def test_async_validate_dog_config_all_fields(self, hass: HomeAssistant):
        """Test comprehensive dog configuration validation."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        # Test valid configuration
        valid_config = {
            CONF_DOG_ID: "test_dog",
            CONF_DOG_NAME: "Test Dog",
            CONF_DOG_BREED: "Golden Retriever",
            CONF_DOG_AGE: 5,
            CONF_DOG_WEIGHT: 25.0,
            CONF_DOG_SIZE: "medium",
        }

        result = await flow._async_validate_dog_config(valid_config)
        assert result["valid"] is True

        # Test invalid age
        invalid_config = valid_config.copy()
        invalid_config[CONF_DOG_AGE] = 35  # Too old
        result = await flow._async_validate_dog_config(invalid_config)
        assert result["valid"] is False

        # Test invalid breed length
        invalid_config = valid_config.copy()
        invalid_config[CONF_DOG_BREED] = "x" * 60  # Too long
        result = await flow._async_validate_dog_config(invalid_config)
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_create_dog_config_with_defaults(self, hass: HomeAssistant):
        """Test dog configuration creation with intelligent defaults."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        user_input = {
            CONF_DOG_ID: "test_dog",
            CONF_DOG_NAME: "Test Dog",
            CONF_DOG_SIZE: "large",
            CONF_DOG_AGE: 3,
        }

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 12345

            dog_config = await flow._create_dog_config(user_input)

        assert dog_config[CONF_DOG_ID] == "test_dog"
        assert dog_config[CONF_DOG_NAME] == "Test Dog"
        assert dog_config[CONF_DOG_SIZE] == "large"
        assert CONF_MODULES in dog_config
        assert "feeding_defaults" in dog_config
        assert "created_at" in dog_config

        # Large dogs should have GPS enabled by default
        assert dog_config[CONF_MODULES][MODULE_GPS] is True

    @pytest.mark.asyncio
    async def test_create_enhanced_dog_schema(self, hass: HomeAssistant):
        """Test enhanced dog schema creation."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        schema = await flow._create_enhanced_dog_schema(
            {"dog_name": "Test"}, "test_dog", "Golden Retriever"
        )

        assert schema is not None
        # Schema validation would be complex to test in detail
        # but we can verify it's created without errors

    def test_get_feature_summary(self):
        """Test feature summary generation."""
        flow = PawControlConfigFlow()

        summary = flow._get_feature_summary()
        assert "🐕 Multi-dog management" in summary
        assert "📍 GPS tracking" in summary
        assert "🍽️ Feeding schedules" in summary


class TestConfigFlowErrors:
    """Test error handling in config flow."""

    @pytest.mark.asyncio
    async def test_add_dog_validation_exception(self, hass: HomeAssistant):
        """Test handling of validation exceptions."""
        flow = PawControlConfigFlow()
        flow.hass = hass

        user_input = {
            CONF_DOG_ID: "test_dog",
            CONF_DOG_NAME: "Test Dog",
        }

        with patch.object(
            flow,
            "_async_validate_dog_config",
            side_effect=Exception("Validation error"),
        ):
            result = await flow.async_step_add_dog(user_input)

            assert result["type"] == FlowResultType.FORM
            assert "errors" in result
            assert "base" in result["errors"]

    @pytest.mark.asyncio
    async def test_final_setup_validation_exception(self, hass: HomeAssistant):
        """Test handling of final setup exceptions."""
        flow = PawControlConfigFlow()
        flow.hass = hass
        flow._integration_name = "Test"
        flow._dogs = [{"dog_id": "test", "dog_name": "Test"}]

        with patch(
            "custom_components.pawcontrol.config_flow.is_dog_config_valid",
            side_effect=Exception("Validation error"),
        ):
            result = await flow.async_step_final_setup()

            assert result["type"] == FlowResultType.ABORT
            assert result["reason"] == "setup_failed"
