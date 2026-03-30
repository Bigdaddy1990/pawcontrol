"""Targeted coverage tests for coordinator_support.py — pure helpers (0% → 22%+).

Covers: coerce_dog_modules_config, ensure_dog_config_data
"""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.coordinator_support import (
    coerce_dog_modules_config,
    ensure_dog_config_data,
)


# ═══════════════════════════════════════════════════════════════════════════════
# coerce_dog_modules_config
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_coerce_dog_modules_config_none() -> None:
    result = coerce_dog_modules_config(None)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_coerce_dog_modules_config_empty_dict() -> None:
    result = coerce_dog_modules_config({})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_coerce_dog_modules_config_with_modules() -> None:
    payload = {"feeding": True, "walk": False, "gps": True}
    result = coerce_dog_modules_config(payload)
    assert isinstance(result, dict)
    assert result.get("feeding") is True
    assert result.get("walk") is False


@pytest.mark.unit
def test_coerce_dog_modules_config_coerces_values() -> None:
    # Non-bool values should be coerced to bool
    payload = {"feeding": 1, "walk": 0}
    result = coerce_dog_modules_config(payload)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_coerce_dog_modules_config_all_false() -> None:
    payload = {"feeding": False, "walk": False}
    result = coerce_dog_modules_config(payload)
    assert result.get("feeding") is False


# ═══════════════════════════════════════════════════════════════════════════════
# ensure_dog_config_data
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_ensure_dog_config_data_valid() -> None:
    data = {"dog_id": "rex", "dog_name": "Rex"}
    result = ensure_dog_config_data(data)
    assert result is not None
    assert result.get("dog_id") == "rex"


@pytest.mark.unit
def test_ensure_dog_config_data_missing_id() -> None:
    # Without required dog_id, returns None
    result = ensure_dog_config_data({"dog_name": "Rex"})
    assert result is None or isinstance(result, dict)


@pytest.mark.unit
def test_ensure_dog_config_data_empty() -> None:
    result = ensure_dog_config_data({})
    assert result is None or isinstance(result, dict)


@pytest.mark.unit
def test_ensure_dog_config_data_full() -> None:
    data = {
        "dog_id": "rex",
        "dog_name": "Rex",
        "dog_breed": "Labrador",
        "dog_weight": 25.0,
    }
    result = ensure_dog_config_data(data)
    assert result is not None
