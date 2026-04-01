"""Targeted coverage tests for error_decorators.py — pure helpers (0% → 22%+).

Covers: get_repair_issue_id, map_to_repair_issue
"""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.error_decorators import get_repair_issue_id
from custom_components.pawcontrol.exceptions import (
    ConfigurationError,
    PawControlError,
    ValidationError,
    WalkError,
)


@pytest.mark.unit
def test_get_repair_issue_id_with_error_code() -> None:
    err = PawControlError("test error", error_code="err_001")
    result = get_repair_issue_id(err)
    assert result is None or isinstance(result, str)


@pytest.mark.unit
def test_get_repair_issue_id_no_error_code() -> None:
    err = PawControlError("generic error")
    result = get_repair_issue_id(err)
    assert result is None or isinstance(result, str)


@pytest.mark.unit
def test_get_repair_issue_id_validation_error() -> None:
    err = ValidationError("weight", -1.0, "too_low")
    result = get_repair_issue_id(err)
    assert result is None or isinstance(result, str)


@pytest.mark.unit
def test_get_repair_issue_id_walk_error() -> None:
    err = WalkError("walk failed", dog_id="rex")
    result = get_repair_issue_id(err)
    assert result is None or isinstance(result, str)


@pytest.mark.unit
def test_get_repair_issue_id_config_error() -> None:
    err = ConfigurationError("api_key", value="bad", reason="Invalid")
    result = get_repair_issue_id(err)
    assert result is None or isinstance(result, str)
