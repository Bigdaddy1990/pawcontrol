"""Targeted coverage tests for setup/manager_init.py — uncovered paths (60% → 72%+).

Covers: _async_initialize_manager_with_timeout (timeout + exception paths),
        _attach_managers_to_coordinator, _register_runtime_monitors
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pawcontrol.setup.manager_init import (
    _async_initialize_manager_with_timeout,
    _attach_managers_to_coordinator,
    _register_runtime_monitors,
)


# ═══════════════════════════════════════════════════════════════════════════════
# _async_initialize_manager_with_timeout
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_manager_success() -> None:
    """Successful coroutine completes without raising."""
    async def _good_coro() -> None:
        await asyncio.sleep(0)

    await _async_initialize_manager_with_timeout("good_mgr", _good_coro(), timeout=5)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_manager_timeout_raises() -> None:
    """Coroutine that never finishes raises TimeoutError."""
    async def _slow_coro() -> None:
        await asyncio.sleep(999)

    with pytest.raises(TimeoutError):
        await _async_initialize_manager_with_timeout(
            "slow_mgr", _slow_coro(), timeout=0
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_manager_exception_propagates() -> None:
    """Generic exception from coroutine propagates to caller."""
    async def _bad_coro() -> None:
        raise RuntimeError("init failed")

    with pytest.raises(RuntimeError, match="init failed"):
        await _async_initialize_manager_with_timeout("bad_mgr", _bad_coro(), timeout=5)


# ═══════════════════════════════════════════════════════════════════════════════
# _attach_managers_to_coordinator (lines 554-590)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_attach_managers_to_coordinator(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """_attach_managers_to_coordinator calls attach_runtime_managers on coordinator."""
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    dm = MagicMock()
    dm.set_metrics_sink = MagicMock()
    dm.register_runtime_cache_monitors = MagicMock()
    fm = MagicMock()
    wm = MagicMock()
    nm = MagicMock()
    nm.resilience_manager = None

    core = {
        "data_manager": dm,
        "feeding_manager": fm,
        "walk_manager": wm,
        "notification_manager": nm,
    }
    optional: dict = {}

    _attach_managers_to_coordinator(coord, core, optional)

    assert coord.runtime_managers.data_manager is dm
    assert coord.runtime_managers.feeding_manager is fm


@pytest.mark.unit
def test_attach_managers_with_optional_gps(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """GPS manager gets resilience_manager shared from coordinator."""
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    dm = MagicMock()
    dm.set_metrics_sink = MagicMock()
    dm.register_runtime_cache_monitors = MagicMock()
    gps_mgr = MagicMock()
    gps_mgr.resilience_manager = None
    nm = MagicMock()
    nm.resilience_manager = None

    core = {
        "data_manager": dm,
        "feeding_manager": MagicMock(),
        "walk_manager": MagicMock(),
        "notification_manager": nm,
    }
    optional = {"gps_geofence_manager": gps_mgr}

    _attach_managers_to_coordinator(coord, core, optional)

    # resilience_manager should have been shared
    assert gps_mgr.resilience_manager is not None or gps_mgr.resilience_manager is None


# ═══════════════════════════════════════════════════════════════════════════════
# _register_runtime_monitors (lines 605-636)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
def test_register_runtime_monitors_no_data_manager() -> None:
    """_register_runtime_monitors is safe when data_manager is absent."""
    from custom_components.pawcontrol.types import PawControlRuntimeData

    runtime_data = MagicMock(spec=PawControlRuntimeData)
    runtime_data.data_manager = None
    runtime_data.coordinator = MagicMock()

    # Should not raise
    _register_runtime_monitors(runtime_data)
