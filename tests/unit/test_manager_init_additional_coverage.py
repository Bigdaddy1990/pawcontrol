"""Additional coverage tests for setup.manager_init."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.exceptions import ConfigEntryAuthFailed
from custom_components.pawcontrol.setup import manager_init


@pytest.mark.asyncio
async def test_initialize_manager_with_timeout_logs_and_reraises_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generic manager failures should be logged before bubbling up."""
    fake_logger = MagicMock()
    monkeypatch.setattr(manager_init, "_LOGGER", fake_logger)

    async def _raise_runtime_error() -> None:
        raise RuntimeError("broken")

    with pytest.raises(RuntimeError, match="broken"):
        await manager_init._async_initialize_manager_with_timeout(
            "demo",
            _raise_runtime_error(),
            timeout=1,
        )

    fake_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_initialize_all_managers_prioritizes_auth_failures() -> None:
    """Auth failures should be re-raised before non-auth initialization errors."""

    class _Manager:
        def __init__(self, side_effect: Exception | None = None) -> None:
            self._side_effect = side_effect

        async def async_initialize(self, *_args, **_kwargs) -> None:
            if self._side_effect is not None:
                raise self._side_effect

    auth_error = ConfigEntryAuthFailed("reauth")
    core_managers = {
        "dog_ids": ["dog-1"],
        "data_manager": _Manager(ValueError("generic")),
        "notification_manager": _Manager(),
        "feeding_manager": _Manager(auth_error),
        "walk_manager": _Manager(),
    }

    with pytest.raises(ConfigEntryAuthFailed, match="reauth"):
        await manager_init._async_initialize_all_managers(
            core_managers,
            optional_managers={},
            dogs_config=[{"dog_id": "dog-1"}],
            entry=SimpleNamespace(options={}),
        )


def test_register_runtime_monitors_noop_without_method() -> None:
    """Monitor registration should be skipped when manager lacks hook."""
    runtime_data = SimpleNamespace(data_manager=object())

    # Should not raise when the hook does not exist.
    manager_init._register_runtime_monitors(runtime_data)


def test_register_runtime_monitors_calls_hook_when_present() -> None:
    """Monitor registration should delegate to the data manager hook when present."""
    data_manager = SimpleNamespace(register_runtime_cache_monitors=MagicMock())
    runtime_data = SimpleNamespace(data_manager=data_manager)

    manager_init._register_runtime_monitors(runtime_data)

    data_manager.register_runtime_cache_monitors.assert_called_once_with(runtime_data)
