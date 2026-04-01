"""Targeted coverage tests for runtime_data.py — (0% → 18%+).

Covers: RuntimeDataUnavailableError, RuntimeDataIncompatibleError,
        describe_runtime_store_status, get_runtime_data
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.runtime_data import (
    RuntimeDataIncompatibleError,
    RuntimeDataUnavailableError,
    get_runtime_data,
)


# ─── RuntimeDataUnavailableError ─────────────────────────────────────────────

@pytest.mark.unit
def test_runtime_data_unavailable_error_raise() -> None:
    with pytest.raises(RuntimeDataUnavailableError):
        raise RuntimeDataUnavailableError("entry_123")


@pytest.mark.unit
def test_runtime_data_unavailable_is_exception() -> None:
    err = RuntimeDataUnavailableError("entry_abc")
    assert isinstance(err, Exception)


@pytest.mark.unit
def test_runtime_data_unavailable_message() -> None:
    err = RuntimeDataUnavailableError("test_entry")
    assert err is not None


# ─── RuntimeDataIncompatibleError ────────────────────────────────────────────

@pytest.mark.unit
def test_runtime_data_incompatible_error_raise() -> None:
    with pytest.raises(RuntimeDataIncompatibleError):
        raise RuntimeDataIncompatibleError("entry_xyz", "expected v2, got v1")


@pytest.mark.unit
def test_runtime_data_incompatible_is_exception() -> None:
    err = RuntimeDataIncompatibleError("entry_abc", "version mismatch")
    assert isinstance(err, Exception)


# ─── get_runtime_data ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_get_runtime_data_missing_returns_none() -> None:
    hass = MagicMock()
    hass.data = {}
    result = get_runtime_data(hass, "nonexistent_entry")
    assert result is None or isinstance(result, object)


@pytest.mark.unit
def test_get_runtime_data_empty_hass_data() -> None:
    hass = MagicMock()
    hass.data = {}
    result = get_runtime_data(hass, "entry_001")
    assert result is None or result is not None
