"""Comprehensive tests for PawControl config flow.

Tests all configuration flow paths including user setup, reauthentication,
reconfiguration, and error handling to achieve 95%+ coverage.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol
from custom_components.pawcontrol.config_flow import PawControlConfigFlow
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
)
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

# Test data
VALID_DOG_DATA = {
    CONF_DOG_ID: "buddy",
    CONF_DOG_NAME: "Buddy",
    CONF_DOG_BREED: "Golden Retriever",
    CONF_DOG_AGE: 3,
    CONF_DOG_WEIGHT: 30.5,
    CONF_DOG_SIZE: "large",
}

VALID_MODULES = {
    "feeding": True,
    "walk": True,
    "health": True,
    "gps": False,
    "notifications": True,
}


async def test_user_flow_single_dog(hass: HomeAssistant) -> None:
    """Test the full user flow with a single dog."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Step 1: Integration name
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "My Paw Control"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_dog"

    # Step 2: Add dog
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        VALID_DOG_DATA,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dog_modules"

    # Step 3: Configure modules
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        VALID_MODULES,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_another"

    # Step 4: Don't add another dog
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"add_another": False},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "entity_profile"

    # Step 5: Select entity profile
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"entity_profile": "standard"},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "My Paw Control (Standard)"
    assert len(result["data"][CONF_DOGS]) == 1
    assert result["data"][CONF_DOGS][0][CONF_DOG_ID] == "buddy"


async def test_user_flow_multiple_dogs(hass: HomeAssistant) -> None:
    """Test the user flow with multiple dogs."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Step 1: Integration name
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Multi Dog Control"},
    )

    # Step 2: Add first dog
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        VALID_DOG_DATA,
    )

    # Step 3: Configure modules for first dog
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        VALID_MODULES,
    )

    # Step 4: Add another dog
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"add_another": True},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_dog"

    # Step 5: Add second dog
    second_dog_data = VALID_DOG_DATA.copy()
    second_dog_data[CONF_DOG_ID] = "max"
    second_dog_data[CONF_DOG_NAME] = "Max"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        second_dog_data,
    )

    # Step 6: Configure modules for second dog
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        VALID_MODULES,
    )

    # Step 7: Don't add another dog
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"add_another": False},
    )

    # Step 8: Select entity profile
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"entity_profile": "advanced"},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert len(result["data"][CONF_DOGS]) == 2


async def test_user_flow_validation_errors(hass: HomeAssistant) -> None:
    """Test validation errors in the user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Test empty integration name
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: ""},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_NAME: "Name required"}

    # Test too long integration name
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "a" * 51},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_NAME: "Name too long"}

    # Valid name to proceed
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Test Integration"},
    )

    # Test invalid dog ID format
    invalid_dog_data = VALID_DOG_DATA.copy()
    invalid_dog_data[CONF_DOG_ID] = "Invalid ID!"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        invalid_dog_data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_DOG_ID: "Invalid ID format"}

    # Test duplicate dog ID
    valid_dog = VALID_DOG_DATA.copy()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        valid_dog,
    )

    # Configure modules
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        VALID_MODULES,
    )

    # Try to add another dog with same ID
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"add_another": True},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        valid_dog,  # Same ID as before
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_DOG_ID: "ID already exists"}


async def test_user_flow_dog_name_validation(hass: HomeAssistant) -> None:
    """Test dog name validation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Test"},
    )

    # Test too short name
    invalid_dog = VALID_DOG_DATA.copy()
    invalid_dog[CONF_DOG_NAME] = ""

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        invalid_dog,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_DOG_NAME: "Name too short"}

    # Test too long name
    invalid_dog[CONF_DOG_NAME] = "a" * 31

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        invalid_dog,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_DOG_NAME: "Name too long"}


async def test_already_configured(hass: HomeAssistant) -> None:
    """Test we abort if already configured."""
    # Create an existing entry
    existing_entry = config_entries.ConfigEntry(
        version=1,
        minor_version=2,
        domain=DOMAIN,
        title="Existing Paw Control",
        data={CONF_NAME: "Existing"},
        source=config_entries.SOURCE_USER,
        unique_id="existing_paw_control",
    )
    existing_entry.add_to_hass(hass)

    # Try to add another with same unique ID
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Existing Paw Control"},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauthentication_flow(hass: HomeAssistant) -> None:
    """Test reauthentication flow."""
    # Create an existing entry
    existing_entry = config_entries.ConfigEntry(
        version=1,
        minor_version=2,
        domain=DOMAIN,
        title="Test Paw Control",
        data={
            CONF_NAME: "Test",
            CONF_DOGS: [VALID_DOG_DATA],
        },
        source=config_entries.SOURCE_USER,
        unique_id="test_paw_control",
    )
    existing_entry.add_to_hass(hass)

    # Start reauth flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": existing_entry.entry_id,
        },
        data=existing_entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    # Confirm reauthentication
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"confirm": True},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reauthentication_flow_declined(hass: HomeAssistant) -> None:
    """Test declining reauthentication."""
    existing_entry = config_entries.ConfigEntry(
        version=1,
        minor_version=2,
        domain=DOMAIN,
        title="Test Paw Control",
        data={
            CONF_NAME: "Test",
            CONF_DOGS: [VALID_DOG_DATA],
        },
        source=config_entries.SOURCE_USER,
        unique_id="test_paw_control",
    )
    existing_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": existing_entry.entry_id,
        },
        data=existing_entry.data,
    )

    # Decline reauthentication
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"confirm": False},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "reauth_unsuccessful"}


async def test_reconfigure_flow(hass: HomeAssistant) -> None:
    """Test reconfiguration flow."""
    existing_entry = config_entries.ConfigEntry(
        version=1,
        minor_version=2,
        domain=DOMAIN,
        title="Test Paw Control",
        data={
            CONF_NAME: "Test",
            CONF_DOGS: [VALID_DOG_DATA],
        },
        options={"entity_profile": "standard"},
        source=config_entries.SOURCE_USER,
        unique_id="test_paw_control",
    )
    existing_entry.add_to_hass(hass)

    # Start reconfigure flow
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_get_entry",
        return_value=existing_entry,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": "reconfigure",
                "entry_id": existing_entry.entry_id,
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reconfigure"

        # Change entity profile
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"entity_profile": "advanced"},
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"


async def test_reconfigure_flow_no_entry(hass: HomeAssistant) -> None:
    """Test reconfiguration flow with missing entry."""
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_get_entry",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": "reconfigure",
                "entry_id": "nonexistent",
            },
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reconfigure_failed"


async def test_profile_selection(hass: HomeAssistant) -> None:
    """Test different entity profile selections."""
    profiles = ["basic", "standard", "advanced", "gps_focus", "health_focus"]

    for profile in profiles:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: f"Test {profile}"},
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            VALID_DOG_DATA,
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            VALID_MODULES,
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"add_another": False},
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"entity_profile": profile},
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["options"]["entity_profile"] == profile


async def test_max_dogs_limit(hass: HomeAssistant) -> None:
    """Test that we can't add more than 10 dogs."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Many Dogs"},
    )

    # Add 10 dogs (maximum)
    for i in range(10):
        dog_data = VALID_DOG_DATA.copy()
        dog_data[CONF_DOG_ID] = f"dog_{i}"
        dog_data[CONF_DOG_NAME] = f"Dog {i}"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            dog_data,
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            VALID_MODULES,
        )

        if i < 9:
            # Add another dog
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {"add_another": True},
            )

    # After 10 dogs, should proceed to entity profile
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"add_another": True},  # Try to add another
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "entity_profile"  # Should proceed, not allow more dogs


async def test_flow_with_invalid_modules(hass: HomeAssistant) -> None:
    """Test flow with invalid module selection."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Test"},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        VALID_DOG_DATA,
    )

    # Try invalid modules data
    with patch(
        "custom_components.pawcontrol.config_flow.MODULES_SCHEMA",
        side_effect=vol.Invalid("Invalid selection"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"invalid": "data"},
        )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_selection"}


async def test_abort_no_dogs_configured(hass: HomeAssistant) -> None:
    """Test abort when no dogs are configured."""
    flow = PawControlConfigFlow()
    flow.hass = hass
    flow._dogs = []  # No dogs configured

    result = await flow.async_step_final_setup()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_dogs_configured"


async def test_abort_invalid_dog_config(hass: HomeAssistant) -> None:
    """Test abort when dog configuration is invalid."""
    flow = PawControlConfigFlow()
    flow.hass = hass
    flow._dogs = [{"name": "No ID"}]  # Invalid - missing dog_id
    flow._integration_name = "Test"
    flow._entity_profile = "standard"

    result = await flow.async_step_final_setup()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "invalid_dog_config"


async def test_unique_id_configuration(hass: HomeAssistant) -> None:
    """Test unique ID handling in configuration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Configure with specific name
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Test Unique"},
    )

    # Continue through flow
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        VALID_DOG_DATA,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        VALID_MODULES,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"add_another": False},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"entity_profile": "standard"},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Try to create another with same unique ID
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Test Unique"},  # Same name -> same unique ID
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
