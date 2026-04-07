"""Focused error-path unit tests for ``coordinator.py``."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.pawcontrol.coordinator import (
    CoordinatorUpdateFailed,
    PawControlCoordinator,
)
from custom_components.pawcontrol.exceptions import ValidationError


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
