"""Tests for config/options flow validation helpers."""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.const import CONF_DOG_AGE
from custom_components.pawcontrol.const import CONF_DOG_BREED
from custom_components.pawcontrol.const import CONF_DOG_ID
from custom_components.pawcontrol.const import CONF_DOG_NAME
from custom_components.pawcontrol.const import CONF_DOG_SIZE
from custom_components.pawcontrol.const import CONF_DOG_WEIGHT
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.flow_validation import validate_dog_setup_input
from custom_components.pawcontrol.flow_validation import validate_dog_update_input


def test_validate_dog_setup_input_success() -> None:
    user_input = {
        CONF_DOG_ID: 'buddy',
        CONF_DOG_NAME: 'Buddy',
        CONF_DOG_WEIGHT: 20.5,
        CONF_DOG_SIZE: 'medium',
        CONF_DOG_AGE: 4,
        CONF_DOG_BREED: 'Golden Retriever',
    }

    result = validate_dog_setup_input(
        user_input,
        existing_ids=set(),
        existing_names=set(),
        current_dog_count=0,
        max_dogs=3,
    )

    assert result[CONF_DOG_ID] == 'buddy'
    assert result[CONF_DOG_NAME] == 'Buddy'
    assert result[CONF_DOG_WEIGHT] == pytest.approx(20.5)
    assert result[CONF_DOG_SIZE] == 'medium'
    assert result[CONF_DOG_AGE] == 4
    assert result[CONF_DOG_BREED] == 'Golden Retriever'


def test_validate_dog_setup_input_reports_field_and_base_errors() -> None:
    user_input = {
        CONF_DOG_ID: '1',
        CONF_DOG_NAME: '',
        CONF_DOG_WEIGHT: 'bad',
        CONF_DOG_SIZE: 'unknown',
        CONF_DOG_AGE: 'bad',
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            user_input,
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=3,
            max_dogs=3,
        )

    assert err.value.field_errors[CONF_DOG_ID] == 'dog_id_too_short'
    assert err.value.field_errors[CONF_DOG_NAME] == 'dog_name_required'
    assert err.value.field_errors[CONF_DOG_WEIGHT] == 'invalid_weight_format'
    assert err.value.field_errors[CONF_DOG_SIZE] == 'invalid_dog_size'
    assert err.value.field_errors[CONF_DOG_AGE] == 'invalid_age_format'
    assert 'max_dogs_reached' in err.value.base_errors


def test_validate_dog_setup_rejects_duplicate_name() -> None:
    user_input = {
        CONF_DOG_ID: 'luna',
        CONF_DOG_NAME: 'Buddy',
        CONF_DOG_WEIGHT: 18.5,
        CONF_DOG_SIZE: 'medium',
        CONF_DOG_AGE: 4,
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            user_input,
            existing_ids=set(),
            existing_names={'buddy'},
            current_dog_count=0,
            max_dogs=3,
        )

    assert err.value.field_errors[CONF_DOG_NAME] == 'dog_name_already_exists'


def test_validate_dog_setup_rejects_invalid_breed() -> None:
    user_input = {
        CONF_DOG_ID: 'luna',
        CONF_DOG_NAME: 'Luna',
        CONF_DOG_WEIGHT: 21.0,
        CONF_DOG_SIZE: 'medium',
        CONF_DOG_AGE: 5,
        CONF_DOG_BREED: 'Husky!',
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            user_input,
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=0,
            max_dogs=3,
        )

    assert err.value.field_errors[CONF_DOG_BREED] == 'invalid_dog_breed'


def test_validate_dog_setup_rejects_weight_size_mismatch() -> None:
    user_input = {
        CONF_DOG_ID: 'tiny',
        CONF_DOG_NAME: 'Tiny',
        CONF_DOG_WEIGHT: 50.0,
        CONF_DOG_SIZE: 'toy',
        CONF_DOG_AGE: 3,
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_setup_input(
            user_input,
            existing_ids=set(),
            existing_names=set(),
            current_dog_count=0,
            max_dogs=3,
        )

    assert err.value.field_errors[CONF_DOG_WEIGHT] == 'weight_size_mismatch'


def test_validate_dog_update_rejects_duplicate_name() -> None:
    current_dog = {
        CONF_DOG_NAME: 'Rex',
        CONF_DOG_WEIGHT: 12.0,
        CONF_DOG_SIZE: 'small',
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            current_dog,
            {CONF_DOG_NAME: 'Buddy'},
            existing_names={'buddy'},
        )

    assert err.value.field_errors[CONF_DOG_NAME] == 'dog_name_already_exists'


def test_validate_dog_update_rejects_invalid_breed() -> None:
    current_dog = {
        CONF_DOG_NAME: 'Luna',
        CONF_DOG_WEIGHT: 20.0,
        CONF_DOG_SIZE: 'medium',
    }

    with pytest.raises(FlowValidationError) as err:
        validate_dog_update_input(
            current_dog,
            {CONF_DOG_BREED: 'Husky!'},
        )

    assert err.value.field_errors[CONF_DOG_BREED] == 'invalid_dog_breed'


def test_validate_dog_update_allows_removing_optional_fields() -> None:
    current_dog = {
        CONF_DOG_NAME: 'Luna',
        CONF_DOG_WEIGHT: 20.0,
        CONF_DOG_SIZE: 'medium',
        CONF_DOG_AGE: 5,
        CONF_DOG_BREED: 'Beagle',
    }

    updated = validate_dog_update_input(
        current_dog,
        {
            CONF_DOG_AGE: None,
            CONF_DOG_BREED: None,
        },
    )

    assert CONF_DOG_AGE not in updated
    assert CONF_DOG_BREED not in updated
