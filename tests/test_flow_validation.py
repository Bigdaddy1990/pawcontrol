"""Tests for config/options flow validation helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import ensure_package, install_homeassistant_stubs, load_module

PROJECT_ROOT = Path(__file__).resolve().parents[1]


install_homeassistant_stubs()
ensure_package("custom_components", PROJECT_ROOT / "custom_components")
ensure_package(
    "custom_components.pawcontrol",
    PROJECT_ROOT / "custom_components" / "pawcontrol",
)

flow_validation = load_module(
    "custom_components.pawcontrol.flow_validation",
    PROJECT_ROOT / "custom_components" / "pawcontrol" / "flow_validation.py",
)
const = load_module(
    "custom_components.pawcontrol.const",
    PROJECT_ROOT / "custom_components" / "pawcontrol" / "const.py",
)
exceptions = load_module(
    "custom_components.pawcontrol.exceptions",
    PROJECT_ROOT / "custom_components" / "pawcontrol" / "exceptions.py",
)

validate_dog_setup_input = flow_validation.validate_dog_setup_input
validate_dog_update_input = flow_validation.validate_dog_update_input
FlowValidationError = exceptions.FlowValidationError


def test_validate_dog_setup_rejects_duplicate_names() -> None:
    user_input = {
        const.CONF_DOG_ID: "buddy",
        const.CONF_DOG_NAME: "Buddy",
        const.CONF_DOG_WEIGHT: 18.5,
        const.CONF_DOG_SIZE: "medium",
        const.CONF_DOG_AGE: 4,
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            user_input,
            existing_ids=set(),
            existing_names={"buddy"},
            current_dog_count=0,
            max_dogs=3,
        )

    assert err.value.field_errors[const.CONF_DOG_NAME] == "dog_name_already_exists"


def test_validate_dog_setup_rejects_invalid_breed() -> None:
    user_input = {
        const.CONF_DOG_ID: "luna",
        const.CONF_DOG_NAME: "Luna",
        const.CONF_DOG_WEIGHT: 21.0,
        const.CONF_DOG_SIZE: "medium",
        const.CONF_DOG_AGE: 5,
        const.CONF_DOG_BREED: "Husky!",
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            user_input,
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=0,
            max_dogs=3,
        )

    assert err.value.field_errors[const.CONF_DOG_BREED] == "invalid_dog_breed"


def test_validate_dog_update_rejects_duplicate_name() -> None:
    current_dog = {
        const.CONF_DOG_NAME: "Rex",
        const.CONF_DOG_WEIGHT: 12.0,
        const.CONF_DOG_SIZE: "small",
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            current_dog,
            {const.CONF_DOG_NAME: "Buddy"},
            existing_names={"buddy"},
        )

    assert err.value.field_errors[const.CONF_DOG_NAME] == "dog_name_already_exists"
