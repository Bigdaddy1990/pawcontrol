from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
    MODULE_WALK,
)
from custom_components.pawcontrol.coordinator_tasks import default_rejection_metrics
from custom_components.pawcontrol.dashboard_cards import (
    ModuleCardGenerator,
    StatisticsCardGenerator,
    WeatherCardGenerator,
    _coerce_map_options,
)
from custom_components.pawcontrol.dashboard_templates import (
    DEFAULT_MAP_HOURS_TO_SHOW,
    DEFAULT_MAP_ZOOM,
    DashboardTemplates,
)
from custom_components.pawcontrol.types import (
    DogConfigData,
    ensure_dog_modules_config,
)
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


@pytest.mark.asyncio
async def test_dog_status_template_accepts_typed_modules(
    hass: HomeAssistant,
) -> None:
    """Dog status template should accept ``DogModulesConfig`` payloads."""

    templates = DashboardTemplates(hass)
    modules = ensure_dog_modules_config(
        {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_HEALTH: False,
        }
    )

    assert modules[MODULE_FEEDING] is True

    card = await templates.get_dog_status_card_template(
        "alpha", "Alpha", modules, theme="minimal"
    )

    assert card["type"] == "entities"
    assert any(entity == "sensor.alpha_last_fed" for entity in card["entities"])
    assert any(
        entity == "binary_sensor.alpha_is_walking" for entity in card["entities"]
    )


def test_statistics_summary_template_counts_modules(hass: HomeAssistant) -> None:
    """Summary card should count enabled modules across dogs."""

    templates = DashboardTemplates(hass)
    raw_dogs = [
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

    card = templates.get_statistics_summary_template(raw_dogs, theme="dark")

    content = card["content"]
    assert "**Dogs managed:** 2" in content
    assert "Feeding: 1" in content
    assert "Notifications: 1" in content


@pytest.mark.asyncio
async def test_map_card_template_normalises_options(hass: HomeAssistant) -> None:
    """Map card helper should coerce raw option payloads."""

    templates = DashboardTemplates(hass)
    card = await templates.get_map_card_template(
        "alpha",
        {"zoom": "12", "hours_to_show": "4", "dark_mode": "true"},
        theme="dark",
    )

    assert card["default_zoom"] == 12
    assert card["zoom"] == 12
    assert card["hours_to_show"] == 4
    assert card["dark_mode"] is True


@pytest.mark.asyncio
async def test_map_card_template_clamps_and_accepts_default_zoom(
    hass: HomeAssistant,
) -> None:
    """Legacy ``default_zoom`` keys should be recognised and values clamped."""

    templates = DashboardTemplates(hass)
    card = await templates.get_map_card_template(
        "alpha",
        {"default_zoom": "25", "hours_to_show": "-6", "dark_mode": 0},
        theme="modern",
    )

    assert card["default_zoom"] == 20
    assert card["zoom"] == 20
    assert card["hours_to_show"] == 1
    assert card["dark_mode"] is False


@pytest.mark.asyncio
async def test_map_card_template_applies_default_zoom_when_missing(
    hass: HomeAssistant,
) -> None:
    """Missing zoom options should fall back to ``DEFAULT_MAP_ZOOM``."""

    templates = DashboardTemplates(hass)
    card = await templates.get_map_card_template(
        "alpha",
        {"dark_mode": True},
        theme="modern",
    )

    assert card["default_zoom"] == DEFAULT_MAP_ZOOM
    assert card["zoom"] == DEFAULT_MAP_ZOOM
    assert card["hours_to_show"] == DEFAULT_MAP_HOURS_TO_SHOW
    assert card["dark_mode"] is True


def test_coerce_map_options_reuses_normaliser() -> None:
    """The card generator should rely on the shared map option normaliser."""

    options = {"default_zoom": "1", "hours_to_show": 200, "dark_mode": "yes"}

    result = _coerce_map_options(options)

    assert result == {
        "zoom": 1,
        "default_zoom": 1,
        "dark_mode": True,
        "hours_to_show": 168,
    }


def test_coerce_map_options_applies_defaults_when_not_provided() -> None:
    """Map option normaliser should emit defaults when values are missing."""

    result = _coerce_map_options({"dark_mode": False})

    assert result is not None
    assert result["zoom"] == DEFAULT_MAP_ZOOM
    assert result["default_zoom"] == DEFAULT_MAP_ZOOM
    assert result["hours_to_show"] == DEFAULT_MAP_HOURS_TO_SHOW


def test_coerce_map_options_defaults_when_no_payload() -> None:
    """Passing an empty payload should still include typed defaults."""

    result = _coerce_map_options({})

    assert result is not None
    assert result["zoom"] == DEFAULT_MAP_ZOOM
    assert result["default_zoom"] == DEFAULT_MAP_ZOOM
    assert result["hours_to_show"] == DEFAULT_MAP_HOURS_TO_SHOW


def test_coerce_map_options_defaults_when_none() -> None:
    """None payloads should be normalised to typed defaults."""

    result = _coerce_map_options(None)

    assert result["zoom"] == DEFAULT_MAP_ZOOM
    assert result["default_zoom"] == DEFAULT_MAP_ZOOM
    assert result["hours_to_show"] == DEFAULT_MAP_HOURS_TO_SHOW


def test_coerce_map_options_iterable_pairs() -> None:
    """Iterable payloads of string-keyed pairs should be supported."""

    result = _coerce_map_options(
        [("zoom", "6"), ("hours_to_show", 12.7), ("dark_mode", "ON")]
    )

    assert result["zoom"] == 6
    assert result["default_zoom"] == 6
    assert result["hours_to_show"] == 12
    assert result["dark_mode"] is True


def test_coerce_map_options_nested_mapping_payload() -> None:
    """Nested map option payloads should be unwrapped before normalisation."""

    result = _coerce_map_options(
        {
            "map_options": {"zoom": 5, "dark_mode": "off"},
            "show_activity_graph": False,
        }
    )

    assert result["zoom"] == 5
    assert result["default_zoom"] == 5
    assert result.get("dark_mode") is False


def test_coerce_map_options_map_key_alias() -> None:
    """`map` aliases should be treated as map options input."""

    result = _coerce_map_options({"map": {"default_zoom": 8}})

    assert result["zoom"] == 8
    assert result["default_zoom"] == 8


def test_coerce_map_options_merges_nested_and_top_level() -> None:
    """Nested payloads should augment top-level overrides instead of replacing them."""

    result = _coerce_map_options(
        {"zoom": 9, "map_options": {"hours_to_show": 48, "dark_mode": True}}
    )

    assert result["zoom"] == 9
    assert result["default_zoom"] == 9
    assert result["hours_to_show"] == 48
    assert result.get("dark_mode") is True


def test_coerce_map_options_prefers_top_level_over_nested() -> None:
    """Top-level overrides should take precedence over nested aliases."""

    result = _coerce_map_options(
        {"zoom": 12, "map_options": {"zoom": 3, "default_zoom": 4}}
    )

    assert result["zoom"] == 12
    assert result["default_zoom"] == 4


def test_coerce_map_options_ignores_invalid_iterables(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unsupported iterable entries should be skipped with defaults preserved."""

    caplog.set_level(
        logging.DEBUG, logger="custom_components.pawcontrol.dashboard_templates"
    )

    result = _coerce_map_options(
        [
            (123, 4),  # invalid key type
            ("zoom", "3"),
            "zoom",  # unsupported entry
            {"hours_to_show": "72"},
        ]
    )

    assert result["zoom"] == 3
    assert result["default_zoom"] == 3
    assert result["hours_to_show"] == 72
    assert "Skipping map option entry" in caplog.text


def test_coerce_map_options_ignores_unsupported_mapping_entries(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Mappings with unsupported keys should be filtered while keeping defaults."""

    caplog.set_level(
        logging.DEBUG, logger="custom_components.pawcontrol.dashboard_templates"
    )

    result = _coerce_map_options(
        {
            "zoom": 7,
            "unsupported": "value",
            123: "bad",  # type: ignore[dict-item]
        }
    )

    assert result["zoom"] == 7
    assert result["default_zoom"] == 7
    assert result["hours_to_show"] == DEFAULT_MAP_HOURS_TO_SHOW
    assert "unsupported map option key" in caplog.text


def test_coerce_map_options_rejects_bool_numeric_values() -> None:
    """Boolean values should not coerce into zoom or history integers."""

    result = _coerce_map_options({"zoom": True, "hours_to_show": False})

    assert result["zoom"] == DEFAULT_MAP_ZOOM
    assert result["default_zoom"] == DEFAULT_MAP_ZOOM
    assert result["hours_to_show"] == DEFAULT_MAP_HOURS_TO_SHOW


def test_coerce_map_options_respects_separate_zoom_and_default() -> None:
    """Explicit zoom and default zoom values should remain distinct when valid."""

    result = _coerce_map_options({"zoom": 14, "default_zoom": 9})

    assert result["zoom"] == 14
    assert result["default_zoom"] == 9


def test_coerce_map_options_mirrors_default_when_zoom_missing() -> None:
    """Providing only default zoom should update both zoom fields."""

    result = _coerce_map_options({"default_zoom": 11})

    assert result["zoom"] == 11
    assert result["default_zoom"] == 11


@pytest.mark.asyncio
async def test_map_card_template_respects_dark_mode_override(
    hass: HomeAssistant,
) -> None:
    """Explicit dark-mode overrides should take precedence over theme defaults."""

    templates = DashboardTemplates(hass)

    card = await templates.get_map_card_template(
        "alpha",
        options={"dark_mode": False},
        theme="dark",
    )

    assert card["dark_mode"] is False


@pytest.mark.asyncio
async def test_map_card_template_accepts_dark_mode_enable_override(
    hass: HomeAssistant,
) -> None:
    """Explicitly enabling dark mode should apply even when theme is light."""

    templates = DashboardTemplates(hass)

    card = await templates.get_map_card_template(
        "beta",
        options={"dark_mode": True},
        theme="modern",
    )

    assert card["dark_mode"] is True


@pytest.mark.asyncio
async def test_statistics_generator_normalises_raw_dog_configs(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Statistics generator should normalise raw payloads before rendering."""

    templates = DashboardTemplates(hass)
    generator = StatisticsCardGenerator(hass, templates)

    async def _fake_validate(
        entities: Sequence[str], use_cache: bool = True
    ) -> list[str]:
        return list(entities)

    graphs: list[tuple[str, list[str]]] = []
    summary_payload: dict[str, object] | None = None

    async def _fake_graph(
        title: str,
        entities: Sequence[str],
        stat_types: Sequence[str],
        *,
        days_to_show: int,
        theme: str = "modern",
    ) -> dict[str, object]:
        graphs.append((title, list(entities)))
        return {
            "type": "statistics-graph",
            "title": title,
            "entities": list(entities),
            "stat_types": list(stat_types),
            "days_to_show": days_to_show,
            "theme": theme,
        }

    def _fake_summary(
        dogs: Sequence[DogConfigData],
        theme: str = "modern",
        *,
        coordinator_statistics: dict[str, object] | None = None,
    ) -> dict[str, object]:
        nonlocal summary_payload
        summary_payload = {
            "dogs": list(dogs),
            "theme": theme,
            "coordinator_statistics": coordinator_statistics,
        }
        return {"type": "markdown", "content": "summary"}

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)
    monkeypatch.setattr(templates, "get_statistics_graph_template", _fake_graph)
    monkeypatch.setattr(templates, "get_statistics_summary_template", _fake_summary)

    cards = await generator.generate_statistics_cards(
        [
            {"dog_name": "Missing ID"},
            {
                CONF_DOG_ID: "fido",
                CONF_DOG_NAME: "Fido",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_HEALTH: True,
                    MODULE_GPS: True,
                    MODULE_NOTIFICATIONS: True,
                },
            },
        ],
        {"theme": "classic"},
    )

    assert len(cards) == 5
    assert summary_payload is not None


def test_statistics_summary_template_includes_rejection_metrics(
    hass: HomeAssistant,
) -> None:
    """The summary markdown should embed rejection metrics when provided."""

    templates = DashboardTemplates(hass)
    last_rejection = 1_700_000_000.0
    card = templates.get_statistics_summary_template(
        [
            {
                CONF_DOG_ID: "fido",
                CONF_DOG_NAME: "Fido",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: False,
                    MODULE_HEALTH: True,
                    MODULE_NOTIFICATIONS: True,
                    MODULE_GPS: False,
                },
            }
        ],
        coordinator_statistics={
            "rejection_metrics": {
                **default_rejection_metrics(),
                "rejected_call_count": 3,
                "rejection_breaker_count": 2,
                "rejection_rate": 0.125,
                "last_rejection_time": last_rejection,
                "last_rejection_breaker_name": "api",
                "open_breaker_count": 1,
                "open_breaker_ids": ["api"],
                "rejection_breaker_ids": ["api"],
                "rejection_breakers": ["api"],
            }
        },
    )

    content = card["content"]
    assert "Resilience metrics" in content
    assert "- Rejected calls: 3" in content
    assert "- Rejecting breakers: 2" in content
    assert "- Rejection rate: 12.50%" in content
    iso_timestamp = datetime.fromtimestamp(last_rejection, UTC).isoformat()
    assert f"- Last rejection: {iso_timestamp}" in content
    assert "- Last rejecting breaker: api" in content


@pytest.mark.asyncio
async def test_statistics_generator_ignores_untyped_dogs(
    hass: HomeAssistant,
) -> None:
    """Statistics generator should skip payloads without typed configs."""

    templates = DashboardTemplates(hass)
    generator = StatisticsCardGenerator(hass, templates)

    cards = await generator.generate_statistics_cards(
        [{"dog_name": "No identifier"}],
        {"theme": "modern"},
    )

    assert cards == []


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
async def test_weather_recommendations_template_includes_overflow(
    hass: HomeAssistant,
) -> None:
    """Weather recommendations template should embed overflow notes."""

    templates = DashboardTemplates(hass)

    card = await templates.get_weather_recommendations_card_template(
        "fido",
        "Fido",
        recommendations=["Stay hydrated", "Avoid midday sun"],
        overflow_recommendations=2,
    )

    markdown = card["content"]
    assert "• Stay hydrated" in markdown
    assert "• Avoid midday sun" in markdown
    assert "*... and 2 more recommendations*" in markdown


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


@pytest.mark.asyncio
async def test_generate_visitor_cards_requires_enabled_module(
    hass: HomeAssistant,
) -> None:
    """Visitor cards should be skipped when the module is disabled."""

    templates = DashboardTemplates(hass)
    generator = ModuleCardGenerator(hass, templates)

    dog_config: DogConfigData = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_VISITOR: False},
    }

    cards = await generator.generate_visitor_cards(dog_config, {})

    assert cards == []


@pytest.mark.asyncio
async def test_generate_visitor_cards_includes_entities_and_markdown(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Visitor cards should render an entities card and markdown summary."""

    templates = DashboardTemplates(hass)
    generator = ModuleCardGenerator(hass, templates)

    validated_entities = [
        "switch.fido_visitor_mode",
        "binary_sensor.fido_visitor_mode",
    ]

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:
        assert entities == validated_entities
        return validated_entities

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)

    dog_config: DogConfigData = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_VISITOR: True},
    }

    cards = await generator.generate_visitor_cards(dog_config, {})

    assert len(cards) == 2
    entities_card, markdown_card = cards

    assert entities_card["type"] == "entities"
    assert entities_card["entities"] == validated_entities

    assert markdown_card["type"] == "markdown"
    assert markdown_card["title"] == "Fido visitor insights"
    content = markdown_card["content"]
    assert "Visitor mode status" in content
    assert "binary_sensor.fido_visitor_mode" in content


@pytest.mark.asyncio
async def test_generate_visitor_cards_only_outputs_markdown_when_entities_missing(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Visitor cards should fall back to markdown when no entities validate."""

    templates = DashboardTemplates(hass)
    generator = ModuleCardGenerator(hass, templates)

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:
        assert entities == [
            "switch.fido_visitor_mode",
            "binary_sensor.fido_visitor_mode",
        ]
        return []

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)

    dog_config: DogConfigData = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_VISITOR: True},
    }

    cards = await generator.generate_visitor_cards(dog_config, {})

    assert len(cards) == 1
    markdown_card = cards[0]
    assert markdown_card["type"] == "markdown"
    assert markdown_card["title"] == "Fido visitor insights"
