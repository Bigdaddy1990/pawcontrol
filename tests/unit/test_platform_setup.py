"""Coverage tests for setup platform helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
import pytest

from custom_components.pawcontrol.setup import platform_setup


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        (None, frozenset()),
        (
            {"enabled_modules": {"weather": 1, "feeding": 0}},
            {"weather": True, "feeding": False},
        ),
        (
            {"enabled_modules": ["weather", "feeding"]},
            frozenset({"weather", "feeding"}),
        ),
        ({"enabled_modules": "not-a-collection"}, frozenset()),
    ],
)
def test_resolve_enabled_modules(options: object | None, expected: object) -> None:
    """Normalise enabled module options across supported input shapes."""
    assert platform_setup._resolve_enabled_modules(options) == expected


@pytest.mark.asyncio
async def test_async_forward_platforms_retries_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeouts should retry and eventually raise ConfigEntryNotReady."""
    monkeypatch.setattr(platform_setup.asyncio, "sleep", AsyncMock())

    async def _raise_timeout(*_args, **_kwargs) -> None:
        raise TimeoutError

    forward_calls = 0

    def _forward(*_args, **_kwargs):
        nonlocal forward_calls
        forward_calls += 1
        return _raise_timeout()

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_forward_entry_setups=_forward),
    )

    with pytest.raises(ConfigEntryNotReady, match="Platform setup timeout"):
        await platform_setup._async_forward_platforms(hass, SimpleNamespace())

    assert forward_calls == 3


@pytest.mark.asyncio
async def test_async_forward_platforms_retries_generic_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generic exceptions should retry before succeeding."""
    monkeypatch.setattr(platform_setup.asyncio, "sleep", AsyncMock())

    forward = AsyncMock(side_effect=[RuntimeError("boom"), None])
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_forward_entry_setups=forward),
    )

    await platform_setup._async_forward_platforms(hass, SimpleNamespace())

    assert forward.call_count == 2


@pytest.mark.asyncio
async def test_async_setup_scripts_logs_skipped_on_homeassistant_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """HomeAssistantError should be logged as a skipped non-critical failure."""
    script_manager = SimpleNamespace(
        async_generate_scripts_for_dogs=AsyncMock(
            side_effect=HomeAssistantError("blocked")
        ),
    )
    runtime_data = SimpleNamespace(
        script_manager=script_manager,
        dogs={"dog-1": {}},
        config_entry_options={"enabled_modules": ["weather"]},
        notification_manager=None,
    )

    await platform_setup._async_setup_scripts(
        SimpleNamespace(), SimpleNamespace(), runtime_data
    )

    assert "Script creation skipped" in caplog.text


@pytest.mark.asyncio
async def test_async_setup_scripts_notifies_with_entry_scripts() -> None:
    """Script setup should notify when any scripts were generated."""
    script_manager = SimpleNamespace(
        async_generate_scripts_for_dogs=AsyncMock(
            return_value={"dog-1": ["walk"], "__entry__": ["escalation"]}
        ),
    )
    notification_manager = SimpleNamespace(async_send_notification=AsyncMock())
    runtime_data = SimpleNamespace(
        script_manager=script_manager,
        dogs={"dog-1": {}},
        config_entry_options={"enabled_modules": ["weather"]},
        notification_manager=notification_manager,
    )

    await platform_setup._async_setup_scripts(
        SimpleNamespace(), SimpleNamespace(), runtime_data
    )

    notification_manager.async_send_notification.assert_awaited_once()
