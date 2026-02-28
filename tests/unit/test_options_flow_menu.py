"""Tests for the options flow main menu mixin."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.pawcontrol.options_flow_menu import MenuOptionsMixin


class _MenuHost(MenuOptionsMixin):
    """Test host implementing the menu API expected by the mixin."""

    def __init__(self) -> None:
        self.last_call: dict[str, Any] | None = None

    def async_show_menu(
        self, *, step_id: str, menu_options: list[str]
    ) -> dict[str, Any]:
        """Record call arguments and return a fake Home Assistant flow result."""
        self.last_call = {"step_id": step_id, "menu_options": menu_options}
        return {"type": "menu", "step_id": step_id, "menu_options": menu_options}


@pytest.mark.asyncio
async def test_async_step_init_returns_expected_menu_options() -> None:
    """The mixin should expose the complete init menu in the expected order."""
    host = _MenuHost()

    result = await host.async_step_init()

    assert host.last_call is not None
    assert host.last_call["step_id"] == "init"
    assert host.last_call["menu_options"] == [
        "entity_profiles",
        "manage_dogs",
        "performance_settings",
        "gps_settings",
        "push_settings",
        "geofence_settings",
        "weather_settings",
        "notifications",
        "feeding_settings",
        "health_settings",
        "system_settings",
        "dashboard_settings",
        "advanced_settings",
        "import_export",
    ]
    assert result == {
        "type": "menu",
        "step_id": "init",
        "menu_options": host.last_call["menu_options"],
    }
