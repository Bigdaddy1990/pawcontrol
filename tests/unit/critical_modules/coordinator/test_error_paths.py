"""Gate-oriented unit tests for ``coordinator.py`` decision paths."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.pawcontrol.coordinator import (
    CoordinatorUpdateFailed,
    PawControlCoordinator,
)
from custom_components.pawcontrol.exceptions import (
    ConfigEntryAuthFailed,
    UpdateFailed,
    ValidationError,
)

# Validation cluster


def test_initial_update_interval_falls_back_on_validation_error() -> None:
    """Invalid option payloads should trigger the balanced fallback interval."""
    fake_coordinator = SimpleNamespace(
        registry=SimpleNamespace(
            calculate_update_interval=MagicMock(
                side_effect=ValidationError("update_interval", "bad", "invalid")
            )
        )
    )

    interval = PawControlCoordinator._initial_update_interval(
        fake_coordinator,
        SimpleNamespace(options={}),
    )

    assert interval == 120


# Error-path cluster


@pytest.mark.asyncio
async def test_async_update_data_wraps_unexpected_cycle_errors() -> None:
    """Unexpected runtime failures must be wrapped as ``CoordinatorUpdateFailed``."""

    class _Registry:
        def __len__(self) -> int:
            return 1

        def ids(self) -> list[str]:
            return ["buddy"]

    fake_coordinator = SimpleNamespace(
        registry=_Registry(),
        async_prepare_entry=AsyncMock(),
        _execute_cycle=AsyncMock(side_effect=RuntimeError("boom")),
        _synchronize_module_states=AsyncMock(),
        _data={"buddy": {}},
    )

    with pytest.raises(CoordinatorUpdateFailed, match="Coordinator update failed"):
        await PawControlCoordinator._async_update_data(fake_coordinator)


@pytest.mark.asyncio
async def test_async_update_data_propagates_known_update_failures() -> None:
    """Known UpdateFailed errors should propagate unchanged."""

    class _Registry:
        def __len__(self) -> int:
            return 1

        def ids(self) -> list[str]:
            return ["buddy"]

    fake_coordinator = SimpleNamespace(
        registry=_Registry(),
        async_prepare_entry=AsyncMock(),
        _execute_cycle=AsyncMock(side_effect=UpdateFailed("upstream")),
        _synchronize_module_states=AsyncMock(),
        _data={"buddy": {}},
    )

    with pytest.raises(UpdateFailed, match="upstream"):
        await PawControlCoordinator._async_update_data(fake_coordinator)


@pytest.mark.asyncio
async def test_async_update_data_propagates_auth_failures() -> None:
    """Authentication failures must bubble up to trigger reauth flows."""

    class _Registry:
        def __len__(self) -> int:
            return 1

        def ids(self) -> list[str]:
            return ["buddy"]

    fake_coordinator = SimpleNamespace(
        registry=_Registry(),
        async_prepare_entry=AsyncMock(),
        _execute_cycle=AsyncMock(side_effect=ConfigEntryAuthFailed("auth")),
        _synchronize_module_states=AsyncMock(),
        _data={"buddy": {}},
    )

    with pytest.raises(ConfigEntryAuthFailed, match="auth"):
        await PawControlCoordinator._async_update_data(fake_coordinator)


# Recovery cluster


@pytest.mark.asyncio
async def test_async_update_data_recovers_when_state_sync_fails() -> None:
    """State sync warnings should not abort successful cycle payload updates."""

    class _Registry:
        def __len__(self) -> int:
            return 1

        def ids(self) -> list[str]:
            return ["buddy"]

    payload = {"buddy": {"gps": {"enabled": True}}}
    fake_coordinator = SimpleNamespace(
        registry=_Registry(),
        async_prepare_entry=AsyncMock(),
        _execute_cycle=AsyncMock(return_value=(payload, object())),
        _synchronize_module_states=AsyncMock(side_effect=RuntimeError("sync")),
        _data={"buddy": {}},
    )

    result = await PawControlCoordinator._async_update_data(fake_coordinator)

    assert result == payload


# Result-persistence cluster


@pytest.mark.asyncio
async def test_async_update_data_returns_empty_payload_for_empty_registry() -> None:
    """No-dog setups should return a stable empty payload."""

    class _Registry:
        def __len__(self) -> int:
            return 0

    fake_coordinator = SimpleNamespace(registry=_Registry())

    assert await PawControlCoordinator._async_update_data(fake_coordinator) == {}
