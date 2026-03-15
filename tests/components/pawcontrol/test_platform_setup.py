"""Tests for platform setup helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
import pytest

from custom_components.pawcontrol.setup import platform_setup


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        (None, frozenset()),
        ({"enabled_modules": {"gps": 1, "walk": 0}}, {"gps": True, "walk": False}),
        ({"enabled_modules": ["gps", "weather"]}, frozenset({"gps", "weather"})),
        ({"enabled_modules": "gps"}, frozenset()),
    ],
)
def test_resolve_enabled_modules(options: object | None, expected: object) -> None:
    """Enabled module extraction should normalize multiple payload shapes."""
    assert platform_setup._resolve_enabled_modules(options) == expected


@pytest.mark.asyncio
async def test_async_setup_platforms_skips_optional_managers() -> None:
    """Optional helper/script setup should be skipped when configured."""
    entry = Mock()
    hass = SimpleNamespace(config_entries=SimpleNamespace())
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
    runtime_data = SimpleNamespace(config_entry_options={"skip_optional_setup": True})

    await platform_setup.async_setup_platforms(hass, entry, runtime_data)

    hass.config_entries.async_forward_entry_setups.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_forward_platforms_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient platform setup errors should be retried."""
    entry = Mock()
    forward = AsyncMock(side_effect=[RuntimeError("boom"), None])
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_forward_entry_setups=forward)
    )
    sleep_mock = AsyncMock()
    monkeypatch.setattr(platform_setup.asyncio, "sleep", sleep_mock)

    await platform_setup._async_forward_platforms(hass, entry)

    assert forward.await_count == 2
    sleep_mock.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_async_forward_platforms_import_error_raises_not_ready() -> None:
    """Import failures should become ConfigEntryNotReady."""
    entry = Mock()
    hass = SimpleNamespace(config_entries=SimpleNamespace())
    hass.config_entries.async_forward_entry_setups = Mock(
        side_effect=ImportError("missing")
    )

    with pytest.raises(ConfigEntryNotReady, match="missing dependency"):
        await platform_setup._async_forward_platforms(hass, entry)


@pytest.mark.asyncio
async def test_async_setup_helpers_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Helper setup timeout should be logged and treated as non-critical."""
    helper_manager = SimpleNamespace(async_create_helpers_for_dogs=AsyncMock())
    runtime_data = SimpleNamespace(
        helper_manager=helper_manager,
        dogs=[{"dog_id": "dog-1"}],
        config_entry_options={"enabled_modules": {"gps": True}},
        notification_manager=None,
    )
    monkeypatch.setattr(
        platform_setup.asyncio, "wait_for", AsyncMock(side_effect=TimeoutError)
    )

    await platform_setup._async_setup_helpers(SimpleNamespace(), Mock(), runtime_data)


@pytest.mark.asyncio
async def test_async_setup_scripts_homeassistant_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Home Assistant errors should use the skipped warning path."""
    script_manager = SimpleNamespace(async_generate_scripts_for_dogs=AsyncMock())
    runtime_data = SimpleNamespace(
        script_manager=script_manager,
        dogs=[{"dog_id": "dog-1"}],
        config_entry_options={"enabled_modules": {"gps": True}},
        notification_manager=None,
    )
    monkeypatch.setattr(
        platform_setup.asyncio,
        "wait_for",
        AsyncMock(side_effect=HomeAssistantError("busy")),
    )

    await platform_setup._async_setup_scripts(SimpleNamespace(), Mock(), runtime_data)


@pytest.mark.asyncio
async def test_async_setup_scripts_sends_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Script setup should include entry scripts in totals and notify once."""
    script_manager = SimpleNamespace(async_generate_scripts_for_dogs=AsyncMock())
    notification_manager = SimpleNamespace(async_send_notification=AsyncMock())
    runtime_data = SimpleNamespace(
        script_manager=script_manager,
        dogs=[{"dog_id": "dog-1"}],
        config_entry_options={"enabled_modules": ["gps"]},
        notification_manager=notification_manager,
    )
    monkeypatch.setattr(
        platform_setup.asyncio,
        "wait_for",
        AsyncMock(return_value={"dog-1": ["a", "b"], "__entry__": ["fallback"]}),
    )

    await platform_setup._async_setup_scripts(SimpleNamespace(), Mock(), runtime_data)

    notification_manager.async_send_notification.assert_awaited_once()
