"""Simplified tests for the Paw Control dashboard generator."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import aiofiles
import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.pawcontrol.const import CONF_DOG_ID
from custom_components.pawcontrol.const import CONF_DOG_NAME
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.const import MODULE_FEEDING
from custom_components.pawcontrol.const import MODULE_GPS
from custom_components.pawcontrol.const import MODULE_HEALTH
from custom_components.pawcontrol.const import MODULE_WALK
from custom_components.pawcontrol.dashboard_generator import DASHBOARD_STORAGE_VERSION
from custom_components.pawcontrol.dashboard_generator import DEFAULT_DASHBOARD_TITLE
from custom_components.pawcontrol.dashboard_generator import DEFAULT_DASHBOARD_URL
from custom_components.pawcontrol.dashboard_generator import PawControlDashboardGenerator


@pytest.fixture
def mock_config_entry() -> ConfigEntry:
    """Create a minimal mock ConfigEntry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"
    return entry


@pytest.fixture
def sample_dogs_config() -> list[dict[str, any]]:
    """Return sample dog configurations."""
    return [
        {
            CONF_DOG_ID: "max",
            CONF_DOG_NAME: "Max",
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_HEALTH: True,
                MODULE_GPS: False,
            },
        },
        {
            CONF_DOG_ID: "bella",
            CONF_DOG_NAME: "Bella",
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: False,
                MODULE_HEALTH: True,
                MODULE_GPS: True,
            },
        },
    ]


@pytest.fixture
async def generator(hass: HomeAssistant, mock_config_entry: ConfigEntry):
    """Return an initialized dashboard generator with storage patched."""
    gen = PawControlDashboardGenerator(hass, mock_config_entry)
    with patch.object(gen, "_store") as mock_store:
        mock_store.async_load = AsyncMock(
            return_value={"dashboards": {},
                          "version": DASHBOARD_STORAGE_VERSION}
        )
        mock_store.async_save = AsyncMock()
        await gen.async_initialize()
        yield gen


class TestDashboardGenerator:
    """Tests for dashboard generator core functionality."""

    async def test_initialization(self, generator: PawControlDashboardGenerator):
        """Ensure initialization loads storage and sets state."""
        assert generator._initialized
        assert generator._dashboards == {}

    async def test_create_main_dashboard(
        self, generator: PawControlDashboardGenerator, sample_dogs_config
    ):
        """Test creating the main dashboard."""
        with (
            patch.object(
                generator._renderer,
                "render_main_dashboard",
                AsyncMock(return_value={}),
            ),
            patch.object(
                generator,
                "_create_dashboard_file",
                AsyncMock(return_value=Path("/path/to/dashboard")),
            ),
            patch.object(generator, "_save_dashboard_metadata", AsyncMock()),
        ):
            url = await generator.async_create_dashboard(
                sample_dogs_config, {
                    "title": "My Dogs Dashboard", "url": "my-dogs"}
            )
            assert url.startswith("/my_dogs")
            assert DEFAULT_DASHBOARD_TITLE not in url
            assert len(generator._dashboards) == 1

    async def test_create_dog_dashboard(self, generator: PawControlDashboardGenerator):
        """Test creating a dog specific dashboard."""
        dog_config = {
            CONF_DOG_ID: "rex",
            CONF_DOG_NAME: "Rex",
            "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
        }
        with (
            patch.object(
                generator._renderer,
                "render_dog_dashboard",
                AsyncMock(return_value={}),
            ),
            patch.object(
                generator,
                "_create_dashboard_file",
                AsyncMock(return_value=Path("/path/to/dog")),
            ),
            patch.object(generator, "_save_dashboard_metadata", AsyncMock()),
        ):
            url = await generator.async_create_dog_dashboard(dog_config)
            assert url == "/paw-rex"
            assert "rex" in generator._dashboards[url.lstrip("/")]["dog_id"]
