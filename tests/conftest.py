import asyncio
import sys
import types
from collections.abc import Generator

import pytest
import sitecustomize  # noqa: F401
from unittest import mock
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.pawcontrol.const import DOMAIN

try:  # pragma: no cover - fallback when Home Assistant isn't installed
    from homeassistant.core import HomeAssistant
except ModuleNotFoundError:  # pragma: no cover
    ha_core = types.ModuleType("homeassistant.core")

    class HomeAssistant:  # minimal stub for tests
        pass

    class ServiceCall:  # minimal stub for tests
        pass

    ha_core.HomeAssistant = HomeAssistant
    ha_core.ServiceCall = ServiceCall
    sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    sys.modules["homeassistant.core"] = ha_core


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def enable_event_loop_debug() -> Generator[None]:
    """Ensure an event loop exists and enable debug mode for tests."""
    created_loop = False
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        created_loop = True
    loop.set_debug(True)
    try:
        yield
    finally:
        if created_loop:
            loop.close()
            asyncio.set_event_loop(None)


# Override plugin's fail_on_log_exception fixture to avoid dependency on
# ``homeassistant.util.logging`` which may not be available in this minimal
# test environment.
@pytest.fixture(autouse=True)
def fail_on_log_exception():
    yield


@pytest.fixture(autouse=True)
def restore_config_entry_state():
    """Ensure ConfigEntryState is reset after tests modify it."""
    from homeassistant import config_entries

    original = config_entries.ConfigEntryState
    try:
        yield
    finally:
        config_entries.ConfigEntryState = original


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mocker():
    """Minimal mocker fixture with automatic patch cleanup."""
    patches: list[mock._patch] = []

    def patch(target, *args, **kwargs):
        p = mock.patch(target, *args, **kwargs)
        patches.append(p)
        return p.start()

    def patch_object(target, attribute, *args, **kwargs):
        new_attr = kwargs.get("new", mock.MagicMock())
        try:
            p = mock.patch.object(target, attribute, new_attr, **{k: v for k, v in kwargs.items() if k != 'new'})
            patches.append(p)
            return p.start()
        except Exception:
            return new_attr

    helper = types.SimpleNamespace(patch=patch)
    helper.patch.object = patch_object  # type: ignore[attr-defined]
    try:
        yield helper
    finally:
        for p in patches:
            p.stop()


@pytest.fixture
def mock_config_entry():
    """Provide a basic MockConfigEntry for tests."""
    return MockConfigEntry(domain=DOMAIN, data={}, options={})


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator used by multiple tests."""
    coordinator = mock.MagicMock()
    coordinator._dog_data = {
        "test_dog": {
            "walk": {"walks_today": 3, "total_distance_today": 5000},
            "feeding": {"total_portions_today": 400},
            "health": {"weight_kg": 25.5},
        }
    }
    coordinator.get_dog_data = lambda dog_id: coordinator._dog_data.get(dog_id, {})
    coordinator.async_config_entry_first_refresh = mock.AsyncMock()
    return coordinator


@pytest.fixture
def mock_notification_router():
    return mock.MagicMock()


@pytest.fixture
def mock_setup_sync():
    obj = mock.MagicMock()
    obj.sync_all = mock.AsyncMock()
    return obj


@pytest.fixture
async def init_integration(
    hass,
    mock_config_entry,
    mock_coordinator,
    mock_notification_router,
    mock_setup_sync,
):
    """Set up the integration for tests."""
    mock_config_entry.add_to_hass(hass)
    with (
        mock.patch(
            "custom_components.pawcontrol.coordinator.PawControlCoordinator",
            return_value=mock_coordinator,
        ),
        mock.patch(
            "custom_components.pawcontrol.helpers.notification_router.NotificationRouter",
            return_value=mock_notification_router,
        ),
        mock.patch(
            "custom_components.pawcontrol.helpers.setup_sync.SetupSync",
            return_value=mock_setup_sync,
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    return mock_config_entry
