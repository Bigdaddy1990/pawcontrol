"""Test Paw Control config flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.pawcontrol.const import DOMAIN


async def test_form_single_dog(hass: HomeAssistant) -> None:
    """Test we get the form for a single dog setup."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    # Step 1: Number of dogs
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"num_dogs": 1},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dog_config"

    # Step 2: Dog configuration
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "dog_id": "rex",
            "name": "Rex",
            "breed": "German Shepherd",
            "age": 3,
            "weight": 30,
            "size": "large",
            "module_walk": True,
            "module_feeding": True,
            "module_health": True,
            "module_gps": False,
            "module_notifications": True,
            "module_dashboard": True,
            "module_grooming": True,
            "module_medication": False,
            "module_training": False,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "sources"

    # Step 3: Data sources
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "door_sensor": "binary_sensor.front_door",
            "person_entities": ["person.owner"],
            "device_trackers": [],
            "calendar": None,
            "weather": None,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "notifications"

    # Step 4: Notifications
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "notify_fallback": "notify.mobile_app",
            "quiet_hours_start": "22:00:00",
            "quiet_hours_end": "07:00:00",
            "reminder_repeat_min": 30,
            "snooze_min": 15,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "system"

    # Step 5: System settings
    with patch(
        "custom_components.pawcontrol.async_setup_entry",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "reset_time": "23:59:00",
                "export_path": "/config/pawcontrol",
                "export_format": "csv",
                "visitor_mode": False,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Paw Control"
    assert result["options"]["dogs"][0]["dog_id"] == "rex"
    assert result["options"]["dogs"][0]["name"] == "Rex"


async def test_form_num_dogs_float(hass: HomeAssistant) -> None:
    """Test number of dogs input accepts floats."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"num_dogs": 2.0},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dog_config"


async def test_form_multiple_dogs(hass: HomeAssistant) -> None:
    """Test configuration with multiple dogs."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Step 1: Number of dogs
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"num_dogs": 2},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dog_config"

    # Step 2a: First dog configuration
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "dog_id": "rex",
            "name": "Rex",
            "breed": "German Shepherd",
            "age": 3,
            "weight": 30,
            "size": "large",
            "module_walk": True,
            "module_feeding": True,
            "module_health": True,
            "module_gps": False,
            "module_notifications": True,
            "module_dashboard": True,
            "module_grooming": True,
            "module_medication": False,
            "module_training": False,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dog_config"

    # Step 2b: Second dog configuration
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "dog_id": "buddy",
            "name": "Buddy",
            "breed": "Labrador",
            "age": 5,
            "weight": 25,
            "size": "large",
            "module_walk": True,
            "module_feeding": True,
            "module_health": False,
            "module_gps": False,
            "module_notifications": True,
            "module_dashboard": True,
            "module_grooming": False,
            "module_medication": False,
            "module_training": False,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "sources"


async def test_form_duplicate_dog_id(hass: HomeAssistant) -> None:
    """Test error when using duplicate dog IDs."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"num_dogs": 2},
    )

    # First dog
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "dog_id": "rex",
            "name": "Rex",
            "breed": "German Shepherd",
            "age": 3,
            "weight": 30,
            "size": "large",
            "module_walk": True,
            "module_feeding": True,
            "module_health": True,
            "module_gps": False,
            "module_notifications": True,
            "module_dashboard": True,
            "module_grooming": True,
            "module_medication": False,
            "module_training": False,
        },
    )

    # Second dog with same ID
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "dog_id": "rex",  # Duplicate ID
            "name": "Rex 2",
            "breed": "Labrador",
            "age": 5,
            "weight": 25,
            "size": "large",
            "module_walk": True,
            "module_feeding": True,
            "module_health": False,
            "module_gps": False,
            "module_notifications": True,
            "module_dashboard": True,
            "module_grooming": False,
            "module_medication": False,
            "module_training": False,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dog_config"
    assert result["errors"]["base"] == "duplicate_dog_id"


async def test_single_instance_allowed(hass: HomeAssistant) -> None:
    """Test that only a single instance is allowed."""
    # Create first instance
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    # Try to create second instance
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
