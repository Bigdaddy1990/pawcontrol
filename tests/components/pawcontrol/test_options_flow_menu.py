"""Tests for the options flow menu mixin."""

from collections.abc import Sequence
from typing import Any

from custom_components.pawcontrol.options_flow_menu import MenuOptionsMixin
from custom_components.pawcontrol.types import OptionsMainMenuAction


class _FakeMenuFlow(MenuOptionsMixin):
    """Minimal host implementation for ``MenuOptionsMixin`` tests."""

    def __init__(self) -> None:
        self.step_id: str | None = None
        self.menu_options: list[OptionsMainMenuAction] | None = None

    def async_show_menu(
        self,
        *,
        step_id: str,
        menu_options: list[OptionsMainMenuAction],
    ) -> dict[str, Any]:
        """Capture menu arguments and return a flow-like payload."""
        self.step_id = step_id
        self.menu_options = menu_options
        return {
            "type": "menu",
            "step_id": step_id,
            "menu_options": menu_options,
        }


async def test_async_step_init_exposes_expected_menu_options() -> None:
    """The init step should expose all supported options in canonical order."""
    flow = _FakeMenuFlow()

    result = await flow.async_step_init()

    assert result["type"] == "menu"
    assert result["step_id"] == "init"
    assert flow.step_id == "init"

    assert flow.menu_options is not None
    expected_menu_options: Sequence[OptionsMainMenuAction] = [
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
    assert flow.menu_options == list(expected_menu_options)
    assert result["menu_options"] == list(expected_menu_options)
