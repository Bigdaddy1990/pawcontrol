"""Tests for the options flow main menu mixin."""

from homeassistant.data_entry_flow import FlowResultType

from custom_components.pawcontrol.options_flow_menu import MenuOptionsMixin
from custom_components.pawcontrol.types import PUSH_SETTINGS_MENU_ACTION


class _MenuFlow(MenuOptionsMixin):
    """Minimal host implementation for menu mixin tests."""

    def async_show_menu(self, *, step_id: str, menu_options: list[str]):
        return {
            "type": FlowResultType.MENU,
            "step_id": step_id,
            "menu_options": menu_options,
        }


async def test_async_step_init_exposes_expected_menu_order() -> None:
    """The init step should expose every expected options section in order."""
    flow = _MenuFlow()

    result = await flow.async_step_init()

    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"
    assert result["menu_options"] == [
        "entity_profiles",
        "manage_dogs",
        "performance_settings",
        "gps_settings",
        PUSH_SETTINGS_MENU_ACTION,
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
