"""Targeted coverage tests for error_recovery.py — (0% → 28%+).

Covers: ErrorRecoveryCoordinator init, handle_error_with_recovery,
        get_error_recovery_coordinator
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.error_recovery import (
    ErrorRecoveryCoordinator,
    handle_error_with_recovery,
)


def _make_hass():
    hass = MagicMock()
    hass.data = {}
    return hass


@pytest.mark.unit
def test_error_recovery_coordinator_init() -> None:
    coord = ErrorRecoveryCoordinator(_make_hass(), domain="pawcontrol")
    assert coord is not None


@pytest.mark.unit
def test_error_recovery_coordinator_default_domain() -> None:
    coord = ErrorRecoveryCoordinator(_make_hass())
    assert coord is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_error_with_recovery_basic() -> None:
    hass = _make_hass()
    err = RuntimeError("something broke")
    result = await handle_error_with_recovery(hass, err)
    assert isinstance(result, dict)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_error_with_recovery_with_context() -> None:
    hass = _make_hass()
    err = ValueError("bad value")
    result = await handle_error_with_recovery(hass, err, context={"dog_id": "rex"})
    assert isinstance(result, dict)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_error_with_recovery_fallback() -> None:
    hass = _make_hass()
    err = TimeoutError("timeout")
    result = await handle_error_with_recovery(hass, err, fallback_value="default")
    assert isinstance(result, dict)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_error_with_recovery_connection_error() -> None:
    hass = _make_hass()
    err = ConnectionError("network down")
    result = await handle_error_with_recovery(hass, err)
    assert isinstance(result, dict)
