from __future__ import annotations

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from custom_components.pawcontrol.dashboard_cards import (
    ModuleCardGenerator,
    WeatherCardGenerator,
)
from custom_components.pawcontrol.dashboard_templates import DashboardTemplates
from custom_components.pawcontrol.types import DogConfigData
from homeassistant.core import HomeAssistant


@pytest.mark.asyncio
async def test_statistics_graph_template_returns_card(hass: HomeAssistant) -> None:
    """The statistics graph helper should return a typed card."""

    templates = DashboardTemplates(hass)
    card = await templates.get_statistics_graph_template(
        "Activity",
        ["sensor.alpha_activity", "sensor.beta_activity"],
        ["mean", "max"],
        days_to_show=14,
        theme="playful",
    )

    assert card is not None
    assert card["type"] == "statistics-graph"
    assert card["entities"] == [
        "sensor.alpha_activity",
        "sensor.beta_activity",
    ]
    assert card["stat_types"] == ["mean", "max"]
    assert card["days_to_show"] == 14
    assert "card_mod" in card


def test_statistics_summary_template_counts_modules(hass: HomeAssistant) -> None:
    """Summary card should count enabled modules across dogs."""

    templates = DashboardTemplates(hass)
    dogs: list[DogConfigData] = [
        {
            CONF_DOG_ID: "alpha",
            CONF_DOG_NAME: "Alpha",
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_HEALTH: False,
                MODULE_GPS: True,
                MODULE_NOTIFICATIONS: False,
            },
        },
        {
            CONF_DOG_ID: "beta",
            CONF_DOG_NAME: "Beta",
            "modules": {
                MODULE_FEEDING: False,
                MODULE_WALK: True,
                MODULE_HEALTH: True,
                MODULE_GPS: False,
                MODULE_NOTIFICATIONS: True,
            },
        },
    ]

    card = templates.get_statistics_summary_template(dogs, theme="dark")

    content = card["content"]
    assert "**Dogs managed:** 2" in content
    assert "Feeding: 1" in content
    assert "Notifications: 1" in content


@pytest.mark.asyncio
async def test_notification_templates_handle_missing_metrics(
    hass: HomeAssistant,
) -> None:
    """Notification overview should degrade gracefully without sensor data."""

    templates = DashboardTemplates(hass)
    overview = await templates.get_notifications_overview_card_template(
        "alpha", "Alpha", theme="modern"
    )

    assert "No notifications recorded" in overview["content"]

    settings = await templates.get_notification_settings_card_template(
        "alpha", "Alpha", [], theme="modern"
    )
    assert settings is None


@pytest.mark.asyncio
async def test_weather_recommendations_card_parses_structured_data(
    hass: HomeAssistant,
) -> None:
    """Weather recommendations card should flatten structured data safely."""

    templates = DashboardTemplates(hass)
    generator = WeatherCardGenerator(hass, templates)

    hass.states.async_set(
        "sensor.fido_weather_recommendations",
        "Hydrate; Seek shade",
        {
            "recommendations": [
                "Check paws",
                {"text": "Limit midday walks"},
                ["Bring water", None],
            ]
        },
    )

    card = await generator._generate_weather_recommendations_card("fido", "Fido", {})
    assert card is not None
    markdown = card["cards"][1]["content"]
    assert "• Hydrate" in markdown
    assert "Limit midday walks" in markdown
    assert "Bring water" in markdown


@pytest.mark.asyncio
async def test_generate_notification_cards_uses_templates(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Notification cards should be composed through the typed templates."""

    templates = DashboardTemplates(hass)
    generator = ModuleCardGenerator(hass, templates)

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:
        return [entity for entity in entities if "select" not in entity]

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)

    dog_config: DogConfigData = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_NOTIFICATIONS: True},
    }

    cards = await generator.generate_notification_cards(dog_config, {"theme": "dark"})

    assert any(card["type"] == "entities" for card in cards)
    assert any(card["type"] == "markdown" for card in cards)
    assert any(card["type"] == "horizontal-stack" for card in cards)
