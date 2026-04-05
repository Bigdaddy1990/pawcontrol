"""Focused branch coverage tests for setup.manager_init."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import ConfigEntryNotReady
import pytest

from custom_components.pawcontrol.setup import manager_init


@pytest.mark.asyncio
async def test_async_initialize_coordinator_logs_refresh_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful refresh should emit the completion debug log."""
    logger = MagicMock()
    coordinator = SimpleNamespace(
        async_prepare_entry=AsyncMock(),
        async_config_entry_first_refresh=AsyncMock(),
    )
    monkeypatch.setattr(manager_init, "_LOGGER", logger)

    await manager_init._async_initialize_coordinator(
        coordinator,
        skip_optional_setup=False,
    )

    assert any(
        call.args and call.args[0] == "Coordinator refresh completed in %.2f seconds"
        for call in logger.debug.call_args_list
    )


@pytest.mark.asyncio
async def test_async_initialize_coordinator_refresh_timeout_uses_not_ready_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeouts during refresh should be wrapped with init timeout context."""
    wait_for = manager_init.asyncio.wait_for

    async def _prepare_entry() -> None:
        return None

    async def _refresh() -> None:
        return None

    async def _wait_for_with_refresh_timeout(awaitable, *, timeout):  # type: ignore[no-untyped-def]
        if timeout == manager_init._COORDINATOR_REFRESH_TIMEOUT:
            raise TimeoutError
        return await wait_for(awaitable, timeout=timeout)

    coordinator = SimpleNamespace(
        async_prepare_entry=_prepare_entry,
        async_config_entry_first_refresh=_refresh,
    )
    monkeypatch.setattr(
        manager_init.asyncio,
        "wait_for",
        _wait_for_with_refresh_timeout,
    )

    with pytest.raises(ConfigEntryNotReady, match="initialization timeout"):
        await manager_init._async_initialize_coordinator(
            coordinator,
            skip_optional_setup=False,
        )


@pytest.mark.asyncio
async def test_async_create_optional_managers_skip_path_returns_empty_managers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skipping optional setup should return the all-None manager payload."""
    logger = MagicMock()
    monkeypatch.setattr(manager_init, "_LOGGER", logger)

    result = await manager_init._async_create_optional_managers(
        hass=SimpleNamespace(),
        entry=SimpleNamespace(entry_id="entry-1"),
        dogs_config=[],
        core_managers={"notification_manager": object()},
        skip_optional_setup=True,
    )

    assert all(value is None for value in result.values())
    logger.debug.assert_called_once_with("Skipping optional manager creation")
