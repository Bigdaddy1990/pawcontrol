"""Additional setup-layer coverage regression tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_async_initialize_managers_orchestrates_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manager initialization should execute orchestration steps in order."""
    from custom_components.pawcontrol.setup import manager_init

    session = object()
    coordinator = SimpleNamespace(api_client=object())
    core_managers = {"data_manager": object()}
    optional_managers = {"helper_manager": object()}
    runtime_data = SimpleNamespace(runtime=True)

    initialize_coordinator = AsyncMock()
    create_core = AsyncMock(return_value=core_managers)
    create_optional = AsyncMock(return_value=optional_managers)
    initialize_all = AsyncMock()
    attach = MagicMock()
    create_runtime = MagicMock(return_value=runtime_data)
    register_monitors = MagicMock()

    monkeypatch.setattr(manager_init, "async_get_clientsession", lambda _h: session)
    monkeypatch.setattr(manager_init, "PawControlCoordinator", lambda *_: coordinator)
    monkeypatch.setattr(
        manager_init, "_async_initialize_coordinator", initialize_coordinator
    )
    monkeypatch.setattr(manager_init, "_async_create_core_managers", create_core)
    monkeypatch.setattr(
        manager_init, "_async_create_optional_managers", create_optional
    )
    monkeypatch.setattr(manager_init, "_async_initialize_all_managers", initialize_all)
    monkeypatch.setattr(manager_init, "_attach_managers_to_coordinator", attach)
    monkeypatch.setattr(manager_init, "_create_runtime_data", create_runtime)
    monkeypatch.setattr(manager_init, "_register_runtime_monitors", register_monitors)

    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry-1")
    dogs = [{"dog_id": "buddy", "dog_name": "Buddy"}]

    result = await manager_init.async_initialize_managers(
        hass,
        entry,
        dogs,
        "standard",
        skip_optional_setup=True,
    )

    assert result is runtime_data
    initialize_coordinator.assert_awaited_once_with(coordinator, True)
    create_core.assert_awaited_once_with(hass, entry, coordinator, dogs, session)
    create_optional.assert_awaited_once_with(hass, entry, dogs, core_managers, True)
    initialize_all.assert_awaited_once_with(
        core_managers, optional_managers, dogs, entry
    )
    attach.assert_called_once_with(coordinator, core_managers, optional_managers)
    create_runtime.assert_called_once_with(
        entry,
        coordinator,
        core_managers,
        optional_managers,
        dogs,
        "standard",
    )
    register_monitors.assert_called_once_with(runtime_data)


@pytest.mark.asyncio
async def test_async_setup_platforms_runs_optional_helpers_and_scripts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Platform setup should run helper/script setup when not skipped."""
    from custom_components.pawcontrol.setup import platform_setup

    forward = AsyncMock()
    helpers = AsyncMock()
    scripts = AsyncMock()

    monkeypatch.setattr(platform_setup, "_async_forward_platforms", forward)
    monkeypatch.setattr(platform_setup, "_async_setup_helpers", helpers)
    monkeypatch.setattr(platform_setup, "_async_setup_scripts", scripts)

    hass = SimpleNamespace()
    entry = SimpleNamespace()
    runtime_data = SimpleNamespace(config_entry_options={})

    await platform_setup.async_setup_platforms(hass, entry, runtime_data)

    forward.assert_awaited_once_with(hass, entry)
    helpers.assert_awaited_once_with(hass, entry, runtime_data)
    scripts.assert_awaited_once_with(hass, entry, runtime_data)
