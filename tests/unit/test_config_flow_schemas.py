"""Unit tests for config_flow_schemas module.

Validates that schema constants, DOG_SCHEMA, MODULES_SCHEMA, and the
MODULE_SELECTION_KEYS tuple are all properly defined and usable.
"""

import pytest
import voluptuous as vol

from custom_components.pawcontrol.config_flow_schemas import (
    DOG_SCHEMA,
    MODULE_SELECTION_KEYS,
    MODULES_SCHEMA,
)
from custom_components.pawcontrol.const import (
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)


@pytest.mark.unit
def test_dog_schema_accepts_minimal_valid_payload() -> None:
    """DOG_SCHEMA should accept a payload with required fields filled."""
    data = {
        "dog_id": "buddy",
        "dog_name": "Buddy",
    }
    result = DOG_SCHEMA(data)
    assert result["dog_id"] == "buddy"
    assert result["dog_name"] == "Buddy"


@pytest.mark.unit
def test_dog_schema_applies_defaults() -> None:
    """Optional fields should receive their defaults when omitted."""
    data = {
        "dog_id": "max",
        "dog_name": "Max",
    }
    result = DOG_SCHEMA(data)
    assert result.get("dog_breed") == ""
    assert result.get("dog_age") == 3
    assert result.get("dog_weight") == 20.0
    assert result.get("dog_size") == "medium"


@pytest.mark.unit
def test_dog_schema_accepts_full_payload() -> None:
    """DOG_SCHEMA should accept and preserve a fully specified payload."""
    data = {
        "dog_id": "luna",
        "dog_name": "Luna",
        "dog_breed": "Labrador",
        "dog_age": 5,
        "dog_weight": 30.0,
        "dog_size": "large",
    }
    result = DOG_SCHEMA(data)
    assert result["dog_breed"] == "Labrador"
    assert result["dog_age"] == 5
    assert result["dog_weight"] == 30.0
    assert result["dog_size"] == "large"


@pytest.mark.unit
def test_dog_schema_rejects_missing_required_fields() -> None:
    """DOG_SCHEMA should raise vol.error.Invalid when required fields are absent."""
    with pytest.raises(vol.Invalid):
        DOG_SCHEMA({"dog_id": "solo"})  # missing dog_name

    with pytest.raises(vol.Invalid):
        DOG_SCHEMA({"dog_name": "Solo"})  # missing dog_id


@pytest.mark.unit
def test_modules_schema_accepts_all_defaults() -> None:
    """MODULES_SCHEMA should work with an empty dict by applying defaults."""
    result = MODULES_SCHEMA({})
    assert result[MODULE_FEEDING] is True
    assert result[MODULE_WALK] is True
    assert result[MODULE_HEALTH] is True
    assert result[MODULE_GPS] is False
    assert result[MODULE_NOTIFICATIONS] is True


@pytest.mark.unit
def test_modules_schema_accepts_explicit_overrides() -> None:
    """MODULES_SCHEMA should accept explicit boolean overrides."""
    data = {
        MODULE_GPS: True,
        MODULE_FEEDING: False,
    }
    result = MODULES_SCHEMA(data)
    assert result[MODULE_GPS] is True
    assert result[MODULE_FEEDING] is False
    assert result[MODULE_WALK] is True  # default preserved


@pytest.mark.unit
def test_module_selection_keys_contains_expected_modules() -> None:
    """MODULE_SELECTION_KEYS should include all core module constants."""
    expected = {MODULE_FEEDING, MODULE_WALK, MODULE_HEALTH, MODULE_GPS, MODULE_NOTIFICATIONS}
    assert set(MODULE_SELECTION_KEYS) == expected


@pytest.mark.unit
def test_module_selection_keys_is_tuple_of_strings() -> None:
    """MODULE_SELECTION_KEYS must be a tuple of non-empty strings."""
    assert isinstance(MODULE_SELECTION_KEYS, tuple)
    for key in MODULE_SELECTION_KEYS:
        assert isinstance(key, str) and key


@pytest.mark.unit
def test_dog_schema_is_voluptuous_schema() -> None:
    """DOG_SCHEMA must be a voluptuous Schema object."""
    assert isinstance(DOG_SCHEMA, vol.Schema)


@pytest.mark.unit
def test_modules_schema_is_voluptuous_schema() -> None:
    """MODULES_SCHEMA must be a voluptuous Schema object."""
    assert isinstance(MODULES_SCHEMA, vol.Schema)
