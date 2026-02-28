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


@pytest.mark.asyncio
async def test_async_setup_platforms_skips_optional_helpers_and_scripts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional setup should be skipped when explicitly disabled in options."""
    from custom_components.pawcontrol.setup import platform_setup

    forward = AsyncMock()
    helpers = AsyncMock()
    scripts = AsyncMock()

    monkeypatch.setattr(platform_setup, "_async_forward_platforms", forward)
    monkeypatch.setattr(platform_setup, "_async_setup_helpers", helpers)
    monkeypatch.setattr(platform_setup, "_async_setup_scripts", scripts)

    hass = SimpleNamespace()
    entry = SimpleNamespace()
    runtime_data = SimpleNamespace(
        config_entry_options={"skip_optional_setup": True},
    )

    await platform_setup.async_setup_platforms(hass, entry, runtime_data)

    forward.assert_awaited_once_with(hass, entry)
    helpers.assert_not_awaited()
    scripts.assert_not_awaited()


def test_resolve_enabled_modules_normalises_mapping_and_collection_inputs() -> None:
    """Enabled modules should be normalized for both dict and list option shapes."""
    from custom_components.pawcontrol.setup import platform_setup

    mapped = platform_setup._resolve_enabled_modules(
        {"enabled_modules": {"gps": 1, "feeding": 0}},
    )
    listed = platform_setup._resolve_enabled_modules(
        {"enabled_modules": ["gps", 99]},
    )
    invalid = platform_setup._resolve_enabled_modules(
        {"enabled_modules": "gps"},
    )

    assert mapped == {"gps": True, "feeding": False}
    assert listed == frozenset({"gps", "99"})
    assert invalid == frozenset()


@pytest.mark.asyncio
async def test_async_forward_platforms_accepts_non_awaitable_forward_result() -> None:
    """Platform forwarding should succeed when HA returns a non-awaitable result."""
    from custom_components.pawcontrol.setup import platform_setup

    forward = MagicMock(return_value=None)
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_forward_entry_setups=forward),
    )

    await platform_setup._async_forward_platforms(hass, SimpleNamespace(entry_id="e1"))

    forward.assert_called_once()


@pytest.mark.asyncio
async def test_optional_setup_managers_skip_notifications_when_no_items_created() -> None:
    """Helper/script notifications should be skipped for empty generation payloads."""
    from custom_components.pawcontrol.setup import platform_setup

    helper_create = AsyncMock(return_value={"buddy": []})
    script_create = AsyncMock(return_value={"buddy": [], "__entry__": []})
    notify = AsyncMock()

    runtime_data = SimpleNamespace(
        helper_manager=SimpleNamespace(async_create_helpers_for_dogs=helper_create),
        script_manager=SimpleNamespace(async_generate_scripts_for_dogs=script_create),
        dogs=[{"dog_id": "buddy"}],
        config_entry_options={"enabled_modules": ["gps"]},
        notification_manager=SimpleNamespace(async_send_notification=notify),
    )

    await platform_setup._async_setup_helpers(
        SimpleNamespace(),
        SimpleNamespace(),
        runtime_data,
    )
    await platform_setup._async_setup_scripts(
        SimpleNamespace(),
        SimpleNamespace(),
        runtime_data,
    )

    helper_create.assert_awaited_once()
    script_create.assert_awaited_once()
    notify.assert_not_awaited()
