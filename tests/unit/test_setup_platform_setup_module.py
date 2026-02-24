"""Unit tests for setup.platform_setup helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import ConfigEntryNotReady
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
