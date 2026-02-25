"""Unit tests for setup.platform_setup helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
import pytest

from custom_components.pawcontrol.setup import platform_setup


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        (None, frozenset()),
        ({"enabled_modules": {"gps": 1, "walk": 0}}, {"gps": True, "walk": False}),
        ({"enabled_modules": ["gps", 7]}, frozenset({"gps", "7"})),
        ({"enabled_modules": "gps"}, frozenset()),
    ],
)
def test_resolve_enabled_modules(options: object | None, expected: object) -> None:
    """Enabled modules should be normalized for managers."""
    assert platform_setup._resolve_enabled_modules(options) == expected


@pytest.mark.asyncio
async def test_async_forward_platforms_retries_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forwarding should retry once when the first attempt times out."""
    attempts = 0

    async def _forward() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_forward_entry_setups=MagicMock(side_effect=lambda *_: _forward()),
        ),
    )
    entry = SimpleNamespace()
    sleep_mock = AsyncMock()
    monkeypatch.setattr(platform_setup.asyncio, "sleep", sleep_mock)

    await platform_setup._async_forward_platforms(hass, entry)

    assert attempts == 2
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_forward_platforms_import_error_raises_not_ready() -> None:
    """Import failures should be surfaced as ConfigEntryNotReady."""

    def _raise_import_error(*_: object) -> None:
        raise ImportError("missing dep")

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_forward_entry_setups=_raise_import_error),
    )
    entry = SimpleNamespace()

    with pytest.raises(ConfigEntryNotReady, match="missing dependency"):
        await platform_setup._async_forward_platforms(hass, entry)


@pytest.mark.asyncio
async def test_async_setup_platforms_skips_optional_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional helper/script setup should be skipped when configured."""
    forward_mock = AsyncMock()
    helpers_mock = AsyncMock()
    scripts_mock = AsyncMock()
    monkeypatch.setattr(platform_setup, "_async_forward_platforms", forward_mock)
    monkeypatch.setattr(platform_setup, "_async_setup_helpers", helpers_mock)
    monkeypatch.setattr(platform_setup, "_async_setup_scripts", scripts_mock)

    runtime_data = SimpleNamespace(config_entry_options={"skip_optional_setup": True})
    hass = SimpleNamespace()
    entry = SimpleNamespace()

    await platform_setup.async_setup_platforms(hass, entry, runtime_data)

    forward_mock.assert_awaited_once_with(hass, entry)
    helpers_mock.assert_not_called()
    scripts_mock.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_helpers_calls_manager_with_resolved_modules() -> None:
    """Helper manager should receive dogs and normalized module config."""
    create_helpers = AsyncMock(return_value={"buddy": ["a", "b"]})
    runtime_data = SimpleNamespace(
        helper_manager=SimpleNamespace(async_create_helpers_for_dogs=create_helpers),
        dogs=[{"dog_id": "buddy", "dog_name": "Buddy"}],
        config_entry_options={"enabled_modules": {"gps": 1}},
        notification_manager=None,
    )

    await platform_setup._async_setup_helpers(
        SimpleNamespace(), SimpleNamespace(), runtime_data
    )

    create_helpers.assert_awaited_once_with(
        runtime_data.dogs,
        {"gps": True},
    )


@pytest.mark.asyncio
async def test_async_setup_platforms_runs_optional_tasks() -> None:
    """Helpers and scripts should run when optional setup is enabled."""
    forward_mock = AsyncMock()
    helpers_mock = AsyncMock()
    scripts_mock = AsyncMock()
    runtime_data = SimpleNamespace(config_entry_options={})
    hass = SimpleNamespace()
    entry = SimpleNamespace()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(platform_setup, "_async_forward_platforms", forward_mock)
        mp.setattr(platform_setup, "_async_setup_helpers", helpers_mock)
        mp.setattr(platform_setup, "_async_setup_scripts", scripts_mock)
        await platform_setup.async_setup_platforms(hass, entry, runtime_data)

    forward_mock.assert_awaited_once_with(hass, entry)
    helpers_mock.assert_awaited_once_with(hass, entry, runtime_data)
    scripts_mock.assert_awaited_once_with(hass, entry, runtime_data)


@pytest.mark.asyncio
async def test_async_forward_platforms_wraps_timeout_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated timeout errors should raise ConfigEntryNotReady."""

    async def _always_timeout() -> None:
        raise TimeoutError

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_forward_entry_setups=lambda *_: _always_timeout(),
        ),
    )
    sleep_mock = AsyncMock()
    monkeypatch.setattr(platform_setup.asyncio, "sleep", sleep_mock)

    with pytest.raises(ConfigEntryNotReady, match="Platform setup timeout"):
        await platform_setup._async_forward_platforms(hass, SimpleNamespace())

    assert sleep_mock.await_count == 2


@pytest.mark.asyncio
async def test_async_forward_platforms_wraps_generic_exception_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generic platform errors should retry then raise not-ready."""

    async def _always_fail() -> None:
        raise RuntimeError("boom")

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_forward_entry_setups=lambda *_: _always_fail(),
        ),
    )
    sleep_mock = AsyncMock()
    monkeypatch.setattr(platform_setup.asyncio, "sleep", sleep_mock)

    with pytest.raises(ConfigEntryNotReady, match="RuntimeError"):
        await platform_setup._async_forward_platforms(hass, SimpleNamespace())

    assert sleep_mock.await_count == 2


@pytest.mark.asyncio
async def test_async_setup_helpers_handles_noncritical_failures() -> None:
    """Helper setup should tolerate timeout and generic errors."""
    create_helpers = AsyncMock(return_value={})
    runtime_data = SimpleNamespace(
        helper_manager=SimpleNamespace(async_create_helpers_for_dogs=create_helpers),
        dogs=[{"dog_id": "buddy", "dog_name": "Buddy"}],
        config_entry_options={"enabled_modules": ["gps"]},
        notification_manager=SimpleNamespace(async_send_notification=AsyncMock()),
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            platform_setup.asyncio,
            "wait_for",
            AsyncMock(side_effect=[TimeoutError, RuntimeError("broken")]),
        )
        await platform_setup._async_setup_helpers(
            SimpleNamespace(), SimpleNamespace(), runtime_data
        )
        await platform_setup._async_setup_helpers(
            SimpleNamespace(), SimpleNamespace(), runtime_data
        )


@pytest.mark.asyncio
async def test_async_setup_helpers_handles_notification_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Notification errors should be swallowed after helper creation."""
    create_helpers = AsyncMock(return_value={"buddy": ["a"]})
    notify = AsyncMock(side_effect=RuntimeError("notify failed"))
    runtime_data = SimpleNamespace(
        helper_manager=SimpleNamespace(async_create_helpers_for_dogs=create_helpers),
        dogs=[{"dog_id": "buddy", "dog_name": "Buddy"}],
        config_entry_options={"enabled_modules": ["gps"]},
        notification_manager=SimpleNamespace(async_send_notification=notify),
    )

    class _Priority:
        NORMAL = "normal"

    class _Type:
        SYSTEM_INFO = "system_info"

    monkeypatch.setitem(
        __import__("sys").modules,
        "custom_components.pawcontrol.notifications",
        SimpleNamespace(NotificationPriority=_Priority, NotificationType=_Type),
    )

    await platform_setup._async_setup_helpers(
        SimpleNamespace(), SimpleNamespace(), runtime_data
    )
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_setup_scripts_handles_success_and_noncritical_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Script setup should send notifications and absorb expected failures."""
    generate_scripts = AsyncMock(
        return_value={"buddy": ["script.one"], "__entry__": ["entry.escalation"]}
    )
    notify = AsyncMock()
    runtime_data = SimpleNamespace(
        script_manager=SimpleNamespace(
            async_generate_scripts_for_dogs=generate_scripts
        ),
        dogs=[{"dog_id": "buddy", "dog_name": "Buddy"}],
        config_entry_options={"enabled_modules": {"gps": True}},
        notification_manager=SimpleNamespace(async_send_notification=notify),
    )

    class _Priority:
        NORMAL = "normal"

    class _Type:
        SYSTEM_INFO = "system_info"

    monkeypatch.setitem(
        __import__("sys").modules,
        "custom_components.pawcontrol.notifications",
        SimpleNamespace(NotificationPriority=_Priority, NotificationType=_Type),
    )

    await platform_setup._async_setup_scripts(
        SimpleNamespace(), SimpleNamespace(), runtime_data
    )
    notify.assert_awaited_once()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            platform_setup.asyncio, "wait_for", AsyncMock(side_effect=TimeoutError)
        )
        await platform_setup._async_setup_scripts(
            SimpleNamespace(), SimpleNamespace(), runtime_data
        )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            platform_setup.asyncio,
            "wait_for",
            AsyncMock(side_effect=HomeAssistantError("skip")),
        )
        await platform_setup._async_setup_scripts(
            SimpleNamespace(), SimpleNamespace(), runtime_data
        )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            platform_setup.asyncio,
            "wait_for",
            AsyncMock(side_effect=RuntimeError("broken")),
        )
        await platform_setup._async_setup_scripts(
            SimpleNamespace(), SimpleNamespace(), runtime_data
        )


@pytest.mark.asyncio
async def test_setup_helpers_and_scripts_skip_without_managers() -> None:
    """No-op branches should execute when helper/script managers are missing."""
    runtime_data = SimpleNamespace(
        helper_manager=None,
        script_manager=None,
        dogs=[],
        config_entry_options={},
        notification_manager=None,
    )

    await platform_setup._async_setup_helpers(
        SimpleNamespace(), SimpleNamespace(), runtime_data
    )
    await platform_setup._async_setup_scripts(
        SimpleNamespace(), SimpleNamespace(), runtime_data
    )


@pytest.mark.asyncio
async def test_async_setup_scripts_swallows_notification_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Script notification failures should be non-critical."""
    generate_scripts = AsyncMock(return_value={"buddy": ["script.one"]})
    notify = AsyncMock(side_effect=RuntimeError("notify failed"))
    runtime_data = SimpleNamespace(
        script_manager=SimpleNamespace(
            async_generate_scripts_for_dogs=generate_scripts
        ),
        dogs=[{"dog_id": "buddy", "dog_name": "Buddy"}],
        config_entry_options={"enabled_modules": {"gps": True}},
        notification_manager=SimpleNamespace(async_send_notification=notify),
    )

    class _Priority:
        NORMAL = "normal"

    class _Type:
        SYSTEM_INFO = "system_info"

    monkeypatch.setitem(
        __import__("sys").modules,
        "custom_components.pawcontrol.notifications",
        SimpleNamespace(NotificationPriority=_Priority, NotificationType=_Type),
    )

    await platform_setup._async_setup_scripts(
        SimpleNamespace(), SimpleNamespace(), runtime_data
    )
    notify.assert_awaited_once()
