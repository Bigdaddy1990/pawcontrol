from collections.abc import Sequence
from datetime import UTC, datetime
import logging

from homeassistant.core import HomeAssistant
import pytest

from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
    MODULE_WALK,
)
from custom_components.pawcontrol.coordinator_tasks import default_rejection_metrics
from custom_components.pawcontrol.dashboard_cards import (
    HealthAwareFeedingCardGenerator,
    ModuleCardGenerator,
    OverviewCardGenerator,
    StatisticsCardGenerator,
    WeatherCardGenerator,
    _coerce_map_options,
)
from custom_components.pawcontrol.dashboard_templates import (
    DEFAULT_MAP_HOURS_TO_SHOW,
    DEFAULT_MAP_ZOOM,
    DashboardTemplates,
)
from custom_components.pawcontrol.types import DogConfigData, ensure_dog_modules_config


@pytest.mark.asyncio
async def test_statistics_graph_template_returns_card(hass: HomeAssistant) -> None:
    """The statistics graph helper should return a typed card."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    card = await templates.get_statistics_graph_template(  # noqa: E111
        "Activity",
        ["sensor.alpha_activity", "sensor.beta_activity"],
        ["mean", "max"],
        days_to_show=14,
        theme="playful",
    )

    assert card is not None  # noqa: E111
    assert card["type"] == "statistics-graph"  # noqa: E111
    assert card["entities"] == [  # noqa: E111
        "sensor.alpha_activity",
        "sensor.beta_activity",
    ]
    assert card["stat_types"] == ["mean", "max"]  # noqa: E111
    assert card["days_to_show"] == 14  # noqa: E111
    assert "card_mod" in card  # noqa: E111


@pytest.mark.asyncio
async def test_dog_status_template_accepts_typed_modules(
    hass: HomeAssistant,
) -> None:
    """Dog status template should accept ``DogModulesConfig`` payloads."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    modules = ensure_dog_modules_config({  # noqa: E111
        MODULE_FEEDING: True,
        MODULE_WALK: True,
        MODULE_HEALTH: False,
    })

    assert modules[MODULE_FEEDING] is True  # noqa: E111

    card = await templates.get_dog_status_card_template(  # noqa: E111
        "alpha", "Alpha", modules, theme="minimal"
    )

    assert card["type"] == "entities"  # noqa: E111
    assert any(entity == "sensor.alpha_last_fed" for entity in card["entities"])  # noqa: E111
    assert any(
        entity == "binary_sensor.alpha_is_walking" for entity in card["entities"]
    )  # noqa: E111


def test_statistics_summary_template_counts_modules(hass: HomeAssistant) -> None:
    """Summary card should count enabled modules across dogs."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    raw_dogs = [  # noqa: E111
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

    card = templates.get_statistics_summary_template(raw_dogs, theme="dark")  # noqa: E111

    content = card["content"]  # noqa: E111
    assert "**Dogs managed:** 2" in content  # noqa: E111
    assert "Feeding: 1" in content  # noqa: E111
    assert "Notifications: 1" in content  # noqa: E111


def test_statistics_summary_template_localises_general_sections(
    hass: HomeAssistant,
) -> None:
    """Summary card should localise header, counts, and title."""  # noqa: E111

    hass.config.language = "de"  # noqa: E111
    templates = DashboardTemplates(hass)  # noqa: E111
    raw_dogs = [  # noqa: E111
        {
            CONF_DOG_ID: "alpha",
            CONF_DOG_NAME: "Alpha",
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_HEALTH: True,
                MODULE_GPS: True,
                MODULE_NOTIFICATIONS: True,
            },
        }
    ]

    card = templates.get_statistics_summary_template(raw_dogs)  # noqa: E111

    content = card["content"]  # noqa: E111
    assert "## Paw Control Statistiken" in content  # noqa: E111
    assert "**Verwaltete Hunde:** 1" in content  # noqa: E111
    assert "**Aktive Module:**" in content  # noqa: E111
    assert "- Fütterung: 1" in content  # noqa: E111
    assert "- Spaziergänge: 1" in content  # noqa: E111
    assert "- Gesundheit: 1" in content  # noqa: E111
    assert "- GPS: 1" in content  # noqa: E111
    assert "- Benachrichtigungen: 1" in content  # noqa: E111
    assert "*Zuletzt aktualisiert:" in content  # noqa: E111
    assert card["title"] == "Zusammenfassung"  # noqa: E111


@pytest.mark.asyncio
async def test_map_card_template_normalises_options(hass: HomeAssistant) -> None:
    """Map card helper should coerce raw option payloads."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    card = await templates.get_map_card_template(  # noqa: E111
        "alpha",
        {"zoom": "12", "hours_to_show": "4", "dark_mode": "true"},
        theme="dark",
    )

    assert card["default_zoom"] == 12  # noqa: E111
    assert card["zoom"] == 12  # noqa: E111
    assert card["hours_to_show"] == 4  # noqa: E111
    assert card["dark_mode"] is True  # noqa: E111


@pytest.mark.asyncio
async def test_map_card_template_clamps_and_accepts_default_zoom(
    hass: HomeAssistant,
) -> None:
    """Legacy ``default_zoom`` keys should be recognised and values clamped."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    card = await templates.get_map_card_template(  # noqa: E111
        "alpha",
        {"default_zoom": "25", "hours_to_show": "-6", "dark_mode": 0},
        theme="modern",
    )

    assert card["default_zoom"] == 20  # noqa: E111
    assert card["zoom"] == 20  # noqa: E111
    assert card["hours_to_show"] == 1  # noqa: E111
    assert card["dark_mode"] is False  # noqa: E111


@pytest.mark.asyncio
async def test_map_card_template_applies_default_zoom_when_missing(
    hass: HomeAssistant,
) -> None:
    """Missing zoom options should fall back to ``DEFAULT_MAP_ZOOM``."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    card = await templates.get_map_card_template(  # noqa: E111
        "alpha",
        {"dark_mode": True},
        theme="modern",
    )

    assert card["default_zoom"] == DEFAULT_MAP_ZOOM  # noqa: E111
    assert card["zoom"] == DEFAULT_MAP_ZOOM  # noqa: E111
    assert card["hours_to_show"] == DEFAULT_MAP_HOURS_TO_SHOW  # noqa: E111
    assert card["dark_mode"] is True  # noqa: E111


def test_coerce_map_options_reuses_normaliser() -> None:
    """The card generator should rely on the shared map option normaliser."""  # noqa: E111

    options = {"default_zoom": "1", "hours_to_show": 200, "dark_mode": "yes"}  # noqa: E111

    result = _coerce_map_options(options)  # noqa: E111

    assert result == {  # noqa: E111
        "zoom": 1,
        "default_zoom": 1,
        "dark_mode": True,
        "hours_to_show": 168,
    }


def test_coerce_map_options_applies_defaults_when_not_provided() -> None:
    """Map option normaliser should emit defaults when values are missing."""  # noqa: E111

    result = _coerce_map_options({"dark_mode": False})  # noqa: E111

    assert result is not None  # noqa: E111
    assert result["zoom"] == DEFAULT_MAP_ZOOM  # noqa: E111
    assert result["default_zoom"] == DEFAULT_MAP_ZOOM  # noqa: E111
    assert result["hours_to_show"] == DEFAULT_MAP_HOURS_TO_SHOW  # noqa: E111


def test_coerce_map_options_defaults_when_no_payload() -> None:
    """Passing an empty payload should still include typed defaults."""  # noqa: E111

    result = _coerce_map_options({})  # noqa: E111

    assert result is not None  # noqa: E111
    assert result["zoom"] == DEFAULT_MAP_ZOOM  # noqa: E111
    assert result["default_zoom"] == DEFAULT_MAP_ZOOM  # noqa: E111
    assert result["hours_to_show"] == DEFAULT_MAP_HOURS_TO_SHOW  # noqa: E111


def test_coerce_map_options_defaults_when_none() -> None:
    """None payloads should be normalised to typed defaults."""  # noqa: E111

    result = _coerce_map_options(None)  # noqa: E111

    assert result["zoom"] == DEFAULT_MAP_ZOOM  # noqa: E111
    assert result["default_zoom"] == DEFAULT_MAP_ZOOM  # noqa: E111
    assert result["hours_to_show"] == DEFAULT_MAP_HOURS_TO_SHOW  # noqa: E111


def test_coerce_map_options_iterable_pairs() -> None:
    """Iterable payloads of string-keyed pairs should be supported."""  # noqa: E111

    result = _coerce_map_options([  # noqa: E111
        ("zoom", "6"),
        ("hours_to_show", 12.7),
        ("dark_mode", "ON"),
    ])

    assert result["zoom"] == 6  # noqa: E111
    assert result["default_zoom"] == 6  # noqa: E111
    assert result["hours_to_show"] == 12  # noqa: E111
    assert result["dark_mode"] is True  # noqa: E111


def test_coerce_map_options_nested_mapping_payload() -> None:
    """Nested map option payloads should be unwrapped before normalisation."""  # noqa: E111

    result = _coerce_map_options({  # noqa: E111
        "map_options": {"zoom": 5, "dark_mode": "off"},
        "show_activity_graph": False,
    })

    assert result["zoom"] == 5  # noqa: E111
    assert result["default_zoom"] == 5  # noqa: E111
    assert result.get("dark_mode") is False  # noqa: E111


def test_coerce_map_options_map_key_alias() -> None:
    """`map` aliases should be treated as map options input."""  # noqa: E111

    result = _coerce_map_options({"map": {"default_zoom": 8}})  # noqa: E111

    assert result["zoom"] == 8  # noqa: E111
    assert result["default_zoom"] == 8  # noqa: E111


def test_coerce_map_options_merges_nested_and_top_level() -> None:
    """Nested payloads should augment top-level overrides instead of replacing them."""  # noqa: E111

    result = _coerce_map_options({  # noqa: E111
        "zoom": 9,
        "map_options": {"hours_to_show": 48, "dark_mode": True},
    })

    assert result["zoom"] == 9  # noqa: E111
    assert result["default_zoom"] == 9  # noqa: E111
    assert result["hours_to_show"] == 48  # noqa: E111
    assert result.get("dark_mode") is True  # noqa: E111


def test_coerce_map_options_prefers_top_level_over_nested() -> None:
    """Top-level overrides should take precedence over nested aliases."""  # noqa: E111

    result = _coerce_map_options({  # noqa: E111
        "zoom": 12,
        "map_options": {"zoom": 3, "default_zoom": 4},
    })

    assert result["zoom"] == 12  # noqa: E111
    assert result["default_zoom"] == 4  # noqa: E111


def test_coerce_map_options_ignores_invalid_iterables(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unsupported iterable entries should be skipped with defaults preserved."""  # noqa: E111

    caplog.set_level(  # noqa: E111
        logging.DEBUG, logger="custom_components.pawcontrol.dashboard_templates"
    )

    result = _coerce_map_options([  # noqa: E111
        (123, 4),  # invalid key type
        ("zoom", "3"),
        "zoom",  # unsupported entry
        {"hours_to_show": "72"},
    ])

    assert result["zoom"] == 3  # noqa: E111
    assert result["default_zoom"] == 3  # noqa: E111
    assert result["hours_to_show"] == 72  # noqa: E111
    assert "Skipping map option entry" in caplog.text  # noqa: E111


def test_coerce_map_options_ignores_unsupported_mapping_entries(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Mappings with unsupported keys should be filtered while keeping defaults."""  # noqa: E111

    caplog.set_level(  # noqa: E111
        logging.DEBUG, logger="custom_components.pawcontrol.dashboard_templates"
    )

    result = _coerce_map_options({  # noqa: E111
        "zoom": 7,
        "unsupported": "value",
        123: "bad",  # type: ignore[dict-item]
    })

    assert result["zoom"] == 7  # noqa: E111
    assert result["default_zoom"] == 7  # noqa: E111
    assert result["hours_to_show"] == DEFAULT_MAP_HOURS_TO_SHOW  # noqa: E111
    assert "unsupported map option key" in caplog.text  # noqa: E111


def test_coerce_map_options_rejects_bool_numeric_values() -> None:
    """Boolean values should not coerce into zoom or history integers."""  # noqa: E111

    result = _coerce_map_options({"zoom": True, "hours_to_show": False})  # noqa: E111

    assert result["zoom"] == DEFAULT_MAP_ZOOM  # noqa: E111
    assert result["default_zoom"] == DEFAULT_MAP_ZOOM  # noqa: E111
    assert result["hours_to_show"] == DEFAULT_MAP_HOURS_TO_SHOW  # noqa: E111


def test_coerce_map_options_respects_separate_zoom_and_default() -> None:
    """Explicit zoom and default zoom values should remain distinct when valid."""  # noqa: E111

    result = _coerce_map_options({"zoom": 14, "default_zoom": 9})  # noqa: E111

    assert result["zoom"] == 14  # noqa: E111
    assert result["default_zoom"] == 9  # noqa: E111


def test_coerce_map_options_mirrors_default_when_zoom_missing() -> None:
    """Providing only default zoom should update both zoom fields."""  # noqa: E111

    result = _coerce_map_options({"default_zoom": 11})  # noqa: E111

    assert result["zoom"] == 11  # noqa: E111
    assert result["default_zoom"] == 11  # noqa: E111


@pytest.mark.asyncio
async def test_map_card_template_respects_dark_mode_override(
    hass: HomeAssistant,
) -> None:
    """Explicit dark-mode overrides should take precedence over theme defaults."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111

    card = await templates.get_map_card_template(  # noqa: E111
        "alpha",
        options={"dark_mode": False},
        theme="dark",
    )

    assert card["dark_mode"] is False  # noqa: E111


@pytest.mark.asyncio
async def test_map_card_template_accepts_dark_mode_enable_override(
    hass: HomeAssistant,
) -> None:
    """Explicitly enabling dark mode should apply even when theme is light."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111

    card = await templates.get_map_card_template(  # noqa: E111
        "beta",
        options={"dark_mode": True},
        theme="modern",
    )

    assert card["dark_mode"] is True  # noqa: E111


@pytest.mark.asyncio
async def test_statistics_generator_normalises_raw_dog_configs(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Statistics generator should normalise raw payloads before rendering."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    generator = StatisticsCardGenerator(hass, templates)  # noqa: E111

    async def _fake_validate(  # noqa: E111
        entities: Sequence[str], use_cache: bool = True
    ) -> list[str]:
        return list(entities)

    graphs: list[tuple[str, list[str]]] = []  # noqa: E111
    summary_payload: dict[str, object] | None = None  # noqa: E111

    async def _fake_graph(  # noqa: E111
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

    def _fake_summary(  # noqa: E111
        dogs: Sequence[DogConfigData],
        theme: str = "modern",
        *,
        coordinator_statistics: dict[str, object] | None = None,
        service_execution_metrics: dict[str, object] | None = None,
        service_guard_metrics: dict[str, object] | None = None,
    ) -> dict[str, object]:
        nonlocal summary_payload
        summary_payload = {
            "dogs": list(dogs),
            "theme": theme,
            "coordinator_statistics": coordinator_statistics,
            "service_execution_metrics": service_execution_metrics,
            "service_guard_metrics": service_guard_metrics,
        }
        return {"type": "markdown", "content": "summary"}

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)  # noqa: E111
    monkeypatch.setattr(templates, "get_statistics_graph_template", _fake_graph)  # noqa: E111
    monkeypatch.setattr(templates, "get_statistics_summary_template", _fake_summary)  # noqa: E111

    cards = await generator.generate_statistics_cards(  # noqa: E111
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

    assert len(cards) == 5  # noqa: E111
    assert summary_payload is not None  # noqa: E111


def test_statistics_summary_template_includes_rejection_metrics(
    hass: HomeAssistant,
) -> None:
    """The summary markdown should embed rejection metrics when provided."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    last_rejection = 1_700_000_000.0  # noqa: E111
    coordinator_metrics = {  # noqa: E111
        **default_rejection_metrics(),
        "rejected_call_count": 3,
        "rejection_breaker_count": 2,
        "rejection_rate": 0.125,
        "last_rejection_time": last_rejection,
        "last_rejection_breaker_name": "api",
        "open_breaker_count": 1,
        "open_breakers": ["api"],
        "open_breaker_ids": ["api"],
        "half_open_breaker_count": 1,
        "half_open_breakers": ["cache"],
        "half_open_breaker_ids": ["cache"],
        "unknown_breaker_count": 1,
        "unknown_breakers": ["legacy"],
        "unknown_breaker_ids": ["legacy"],
        "rejection_breaker_ids": ["api", "cache"],
        "rejection_breakers": ["api"],
    }
    service_metrics = {  # noqa: E111
        **default_rejection_metrics(),
        "rejected_call_count": 1,
        "rejection_breaker_count": 1,
        "rejection_rate": 0.05,
        "last_rejection_time": last_rejection - 3600,
        "last_rejection_breaker_id": "automation",
        "open_breakers": ["automation"],
        "open_breaker_ids": ["automation"],
        "rejection_breaker_ids": ["automation"],
        "rejection_breakers": ["automation"],
    }

    guard_metrics = {  # noqa: E111
        "executed": 7,
        "skipped": 2,
        "reasons": {"quiet_hours": 2},
        "last_results": [
            {
                "domain": "notify",
                "service": "mobile_app",
                "executed": False,
                "reason": "quiet_hours",
            },
            {
                "domain": "script",
                "service": "evening_reset",
                "executed": True,
                "description": "resumed schedule",
            },
        ],
    }

    card = templates.get_statistics_summary_template(  # noqa: E111
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
        coordinator_statistics={"rejection_metrics": coordinator_metrics},
        service_execution_metrics=service_metrics,
        service_guard_metrics=guard_metrics,
    )

    content = card["content"]  # noqa: E111
    iso_timestamp = datetime.fromtimestamp(last_rejection, UTC).isoformat()  # noqa: E111
    service_iso = datetime.fromtimestamp(last_rejection - 3600, UTC).isoformat()  # noqa: E111

    assert "Resilience metrics" in content  # noqa: E111
    assert "**Coordinator telemetry:**" in content  # noqa: E111
    assert "**Service execution telemetry:**" in content  # noqa: E111
    assert "- Rejected calls: 3" in content  # noqa: E111
    assert "- Rejecting breakers: 2" in content  # noqa: E111
    assert "- Rejection rate: 12.50%" in content  # noqa: E111
    assert f"- Last rejection: {iso_timestamp}" in content  # noqa: E111
    assert "- Last rejecting breaker: api" in content  # noqa: E111
    assert "- Open breaker names: api" in content  # noqa: E111
    assert "- Open breaker IDs: api" in content  # noqa: E111
    assert "- Half-open breaker names: cache" in content  # noqa: E111
    assert "- Half-open breaker IDs: cache" in content  # noqa: E111
    assert "- Unknown breaker names: legacy" in content  # noqa: E111
    assert "- Unknown breaker IDs: legacy" in content  # noqa: E111
    assert "- Rejecting breaker IDs: api, cache" in content  # noqa: E111
    assert "- Rejecting breaker names: api" in content  # noqa: E111
    assert "- Rejection rate: 5.00%" in content  # noqa: E111
    assert f"- Last rejection: {service_iso}" in content  # noqa: E111
    assert "- Last rejecting breaker: automation" in content  # noqa: E111
    assert "- Guard outcomes:" in content  # noqa: E111
    assert "  - Guarded calls executed: 7" in content  # noqa: E111
    assert "  - Guarded calls skipped: 2" in content  # noqa: E111
    assert "  - Skip reasons:" in content  # noqa: E111
    assert "    - quiet_hours: 2" in content  # noqa: E111
    assert "  - Recent guard results:" in content  # noqa: E111
    assert "    - notify.mobile_app: skipped (reason: quiet_hours)" in content  # noqa: E111
    assert "    - script.evening_reset: executed - resumed schedule" in content  # noqa: E111


def test_statistics_summary_template_localizes_breaker_labels(
    hass: HomeAssistant,
) -> None:
    """Localisation should translate breaker labels based on the HA language."""  # noqa: E111

    hass.config.language = "de"  # noqa: E111
    templates = DashboardTemplates(hass)  # noqa: E111
    card = templates.get_statistics_summary_template(  # noqa: E111
        [
            {
                CONF_DOG_ID: "fido",
                CONF_DOG_NAME: "Fido",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_HEALTH: True,
                    MODULE_NOTIFICATIONS: True,
                    MODULE_GPS: True,
                },
            }
        ],
        coordinator_statistics={
            "rejection_metrics": {
                **default_rejection_metrics(),
                "half_open_breakers": ["cache"],
                "half_open_breaker_ids": ["cache"],
                "unknown_breakers": ["legacy"],
                "unknown_breaker_ids": ["legacy"],
                "rejection_breakers": ["api"],
                "rejection_breaker_ids": ["api"],
                "last_rejection_breaker_name": "api",
                "rejection_breaker_count": 1,
                "rejected_call_count": 1,
                "open_breakers": [],
                "open_breaker_ids": [],
            }
        },
        service_execution_metrics={
            "rejection_metrics": default_rejection_metrics(),
        },
        service_guard_metrics={
            "executed": 4,
            "skipped": 1,
            "reasons": {"ruhezeit": 1},
            "last_results": [
                {
                    "domain": "notify",
                    "service": "mobile_app",
                    "executed": False,
                    "reason": "ruhezeit",
                }
            ],
        },
    )

    content = card["content"]  # noqa: E111
    assert "**Koordinator-Telemetrie:**" in content  # noqa: E111
    assert "- Letzter blockierender Breaker: api" in content  # noqa: E111
    assert "- Abgelehnte Aufrufe: 1" in content  # noqa: E111
    assert "- Blockierende Breaker: 1" in content  # noqa: E111
    assert "- Ablehnungsrate: 0.00%" in content  # noqa: E111
    assert "- Guard-Ergebnisse:" in content  # noqa: E111
    assert "  - Ausgeführte Guard-Aufrufe: 4" in content  # noqa: E111
    assert "  - Übersprungene Guard-Aufrufe: 1" in content  # noqa: E111
    assert "  - Übersprung-Gründe:" in content  # noqa: E111
    assert "    - ruhezeit: 1" in content  # noqa: E111
    assert "  - Aktuelle Guard-Ergebnisse:" in content  # noqa: E111
    assert "    - notify.mobile_app: übersprungen (Grund: ruhezeit)" in content  # noqa: E111
    assert "- Letzte Ablehnung: nie" in content  # noqa: E111
    assert "- Namen offener Breaker: keine" in content  # noqa: E111
    assert "- IDs blockierender Breaker: api" in content  # noqa: E111


def test_statistics_summary_template_localizes_empty_lists(hass: HomeAssistant) -> None:
    """Empty breaker lists should localize using the configured language."""  # noqa: E111

    hass.config.language = "fr"  # noqa: E111
    templates = DashboardTemplates(hass)  # noqa: E111
    card = templates.get_statistics_summary_template(  # noqa: E111
        [
            {
                CONF_DOG_ID: "fido",
                CONF_DOG_NAME: "Fido",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_HEALTH: True,
                    MODULE_NOTIFICATIONS: True,
                    MODULE_GPS: True,
                },
            }
        ],
        coordinator_statistics={
            "rejection_metrics": {
                **default_rejection_metrics(),
                "open_breakers": [],
                "open_breaker_ids": [],
                "half_open_breakers": [],
                "half_open_breaker_ids": [],
                "unknown_breakers": [],
                "unknown_breaker_ids": [],
                "rejection_breakers": [],
                "rejection_breaker_ids": [],
            }
        },
    )

    content = card["content"]  # noqa: E111
    assert "- Open breaker names: none" in content  # noqa: E111
    assert "- Open breaker IDs: none" in content  # noqa: E111


def test_statistics_summary_template_localizes_resilience_fallbacks(
    hass: HomeAssistant,
) -> None:
    """Rejection rate and time fallbacks should honor the active language."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    card = templates.get_statistics_summary_template(  # noqa: E111
        [
            {
                CONF_DOG_ID: "fido",
                CONF_DOG_NAME: "Fido",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_HEALTH: True,
                    MODULE_NOTIFICATIONS: True,
                    MODULE_GPS: True,
                },
            }
        ],
        coordinator_statistics={
            "rejection_metrics": {
                **default_rejection_metrics(),
                "rejection_rate": float("nan"),
                "last_rejection_time": None,
                "last_rejection_breaker_id": None,
                "last_rejection_breaker_name": None,
            }
        },
    )

    content = card["content"]  # noqa: E111
    assert "- Rejection rate: n/a" in content  # noqa: E111
    assert "- Last rejection: never" in content  # noqa: E111
    assert "- Last rejecting breaker" not in content  # noqa: E111

    hass.config.language = "de"  # noqa: E111
    templates_localized = DashboardTemplates(hass)  # noqa: E111
    localized_card = templates_localized.get_statistics_summary_template(  # noqa: E111
        [
            {
                CONF_DOG_ID: "fido",
                CONF_DOG_NAME: "Fido",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_HEALTH: True,
                    MODULE_NOTIFICATIONS: True,
                    MODULE_GPS: True,
                },
            }
        ],
        coordinator_statistics={
            "rejection_metrics": {
                **default_rejection_metrics(),
                "rejection_rate": float("nan"),
                "last_rejection_time": None,
                "last_rejection_breaker_id": None,
                "last_rejection_breaker_name": None,
            }
        },
    )

    localized_content = localized_card["content"]  # noqa: E111
    assert "- Ablehnungsrate: nicht verfügbar" in localized_content  # noqa: E111
    assert "- Letzte Ablehnung: nie" in localized_content  # noqa: E111
    assert "- Letzter blockierender Breaker" not in localized_content  # noqa: E111


@pytest.mark.asyncio
async def test_statistics_generator_ignores_untyped_dogs(
    hass: HomeAssistant,
) -> None:
    """Statistics generator should skip payloads without typed configs."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    generator = StatisticsCardGenerator(hass, templates)  # noqa: E111

    cards = await generator.generate_statistics_cards(  # noqa: E111
        [{"dog_name": "No identifier"}],
        {"theme": "modern"},
    )

    assert cards == []  # noqa: E111


@pytest.mark.asyncio
async def test_notification_templates_handle_missing_metrics(
    hass: HomeAssistant,
) -> None:
    """Notification overview should degrade gracefully without sensor data."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    overview = await templates.get_notifications_overview_card_template(  # noqa: E111
        "alpha", "Alpha", theme="modern"
    )

    assert "No notifications recorded" in overview["content"]  # noqa: E111

    settings = await templates.get_notification_settings_card_template(  # noqa: E111
        "alpha", "Alpha", [], theme="modern"
    )
    assert settings is None  # noqa: E111


@pytest.mark.asyncio
async def test_notification_templates_localize_labels(hass: HomeAssistant) -> None:
    """Notification dashboards should use translated labels for German locales."""  # noqa: E111

    hass.config.language = "de"  # noqa: E111
    templates = DashboardTemplates(hass)  # noqa: E111

    hass.states.async_set(  # noqa: E111
        "sensor.pawcontrol_notifications",
        "active",
        {
            "performance_metrics": {"notifications_failed": 2},
            "per_dog": {
                "alpha": {
                    "sent_today": 4,
                    "quiet_hours_active": True,
                    "channels": [],
                    "last_notification": {
                        "type": "system_info",
                        "priority": "high",
                        "sent_at": "2025-02-14T12:00:00Z",
                    },
                }
            },
        },
    )

    overview = await templates.get_notifications_overview_card_template(  # noqa: E111
        "alpha", "Alpha", theme="modern"
    )
    content = overview["content"]  # noqa: E111

    assert "Benachrichtigungsübersicht für Alpha" in content  # noqa: E111
    assert "**Heute gesendete Benachrichtigungen:** 4" in content  # noqa: E111
    assert "**Fehlgeschlagene Zustellungen:** 2" in content  # noqa: E111
    assert "**Ruhezeiten aktiv:** ✅" in content  # noqa: E111
    assert "### Bevorzugte Kanäle" in content  # noqa: E111
    assert "• Verwendet Standardkanäle der Integration" in content  # noqa: E111
    assert "### Letzte Benachrichtigung" in content  # noqa: E111
    assert "- **Typ:** system_info" in content  # noqa: E111
    assert "- **Priorität:** High" in content  # noqa: E111
    assert "- **Gesendet:** 2025-02-14T12:00:00Z" in content  # noqa: E111

    settings = await templates.get_notification_settings_card_template(  # noqa: E111
        "alpha", "Alpha", ["switch.alpha_notifications"], theme="modern"
    )
    assert settings is not None  # noqa: E111
    assert settings["title"] == "🔔 Alpha Benachrichtigungssteuerung"  # noqa: E111

    actions = await templates.get_notifications_actions_card_template(  # noqa: E111
        "alpha", theme="modern"
    )
    button_names = [card["name"] for card in actions["cards"]]  # noqa: E111
    assert "Testbenachrichtigung senden" in button_names  # noqa: E111
    assert "Ruhezeiten zurücksetzen" in button_names  # noqa: E111
    send_test_button = next(  # noqa: E111
        card for card in actions["cards"] if card["icon"] == "mdi:bell-check"
    )
    assert (  # noqa: E111
        send_test_button["tap_action"]["service_data"]["title"] == "PawControl-Diagnose"
    )
    assert (  # noqa: E111
        send_test_button["tap_action"]["service_data"]["message"]
        == "Testbenachrichtigung vom Dashboard"
    )

    hass.states.async_set(  # noqa: E111
        "sensor.pawcontrol_notifications",
        "idle",
        {
            "performance_metrics": {"notifications_failed": 0},
            "per_dog": {
                "alpha": {
                    "sent_today": 0,
                    "quiet_hours_active": False,
                    "channels": [],
                }
            },
        },
    )

    empty_overview = await templates.get_notifications_overview_card_template(  # noqa: E111
        "alpha", "Alpha", theme="modern"
    )
    assert (  # noqa: E111
        "Für diesen Hund wurden noch keine Benachrichtigungen aufgezeichnet."
        in empty_overview["content"]
    )


@pytest.mark.asyncio
async def test_feeding_templates_localize_labels(hass: HomeAssistant) -> None:
    """Feeding dashboards should translate titles and meal labels."""  # noqa: E111

    hass.config.language = "de"  # noqa: E111
    templates = DashboardTemplates(hass)  # noqa: E111

    schedule_modern = await templates.get_feeding_schedule_template(  # noqa: E111
        "fido", theme="modern"
    )
    assert schedule_modern["title"] == "🍽️ Fütterungsplan"  # noqa: E111

    schedule_minimal = await templates.get_feeding_schedule_template(  # noqa: E111
        "fido", theme="minimal"
    )
    assert schedule_minimal["title"] == "Fütterungsplan"  # noqa: E111

    controls = await templates.get_feeding_controls_template("fido", theme="modern")  # noqa: E111
    button_names = {  # noqa: E111
        button["name"] for row in controls["cards"] for button in row.get("cards", [])
    }
    assert button_names == {"Frühstück", "Mittagessen", "Abendessen", "Snack"}  # noqa: E111


@pytest.mark.asyncio
async def test_weather_recommendations_card_parses_structured_data(
    hass: HomeAssistant,
) -> None:
    """Weather recommendations card should flatten structured data safely."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    generator = WeatherCardGenerator(hass, templates)  # noqa: E111

    hass.states.async_set(  # noqa: E111
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

    card = await generator._generate_weather_recommendations_card("fido", "Fido", {})  # noqa: E111
    assert card is not None  # noqa: E111
    markdown = card["cards"][1]["content"]  # noqa: E111
    assert "• Hydrate" in markdown  # noqa: E111
    assert "Limit midday walks" in markdown  # noqa: E111
    assert "Bring water" in markdown  # noqa: E111


@pytest.mark.asyncio
async def test_weather_recommendations_template_includes_overflow(
    hass: HomeAssistant,
) -> None:
    """Weather recommendations template should embed overflow notes."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111

    card = await templates.get_weather_recommendations_card_template(  # noqa: E111
        "fido",
        "Fido",
        recommendations=["Stay hydrated", "Avoid midday sun"],
        overflow_recommendations=2,
    )

    markdown = card["content"]  # noqa: E111
    assert "• Stay hydrated" in markdown  # noqa: E111
    assert "• Avoid midday sun" in markdown  # noqa: E111
    assert "*... and 2 more recommendations*" in markdown  # noqa: E111


@pytest.mark.asyncio
async def test_generate_notification_cards_uses_templates(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Notification cards should be composed through the typed templates."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    generator = ModuleCardGenerator(hass, templates)  # noqa: E111

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:  # noqa: E111
        return [entity for entity in entities if "select" not in entity]

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)  # noqa: E111

    dog_config: DogConfigData = {  # noqa: E111
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_NOTIFICATIONS: True},
    }

    cards = await generator.generate_notification_cards(dog_config, {"theme": "dark"})  # noqa: E111

    assert any(card["type"] == "entities" for card in cards)  # noqa: E111
    assert any(card["type"] == "markdown" for card in cards)  # noqa: E111
    assert any(card["type"] == "horizontal-stack" for card in cards)  # noqa: E111


@pytest.mark.asyncio
async def test_generate_walk_cards_localizes_german(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Walk cards should honor the Home Assistant language."""  # noqa: E111

    hass.config.language = "de"  # noqa: E111
    templates = DashboardTemplates(hass)  # noqa: E111
    generator = ModuleCardGenerator(hass, templates)  # noqa: E111

    status_entities = [  # noqa: E111
        "binary_sensor.fido_is_walking",
        "sensor.fido_current_walk_duration",
        "sensor.fido_walks_today",
        "sensor.fido_walk_distance_today",
        "sensor.fido_last_walk_time",
        "sensor.fido_last_walk_distance",
    ]

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:  # noqa: E111
        assert entities == status_entities
        return list(status_entities)

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)  # noqa: E111

    captured_history: dict[str, str] = {}  # noqa: E111

    async def _fake_history(  # noqa: E111
        entities: list[str],
        title: str,
        hours_to_show: int,
        theme: str = "modern",
    ) -> dict[str, object]:
        captured_history["title"] = title
        return {"type": "history-graph", "title": title, "entities": entities}

    monkeypatch.setattr(
        generator.templates, "get_history_graph_template", _fake_history
    )  # noqa: E111

    dog_config: DogConfigData = {  # noqa: E111
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_WALK: True},
    }

    cards = await generator.generate_walk_cards(dog_config, {})  # noqa: E111

    assert len(cards) == 4  # noqa: E111
    entities_card, start_card, end_card, history_card = cards  # noqa: E111

    assert entities_card["title"] == "Spazierstatus"  # noqa: E111
    assert start_card["card"]["name"] == "Spaziergang starten"  # noqa: E111
    assert end_card["card"]["name"] == "Spaziergang beenden"  # noqa: E111
    assert history_card["title"] == "Spazierverlauf (7 Tage)"  # noqa: E111
    assert captured_history["title"] == "Spazierverlauf (7 Tage)"  # noqa: E111


@pytest.mark.asyncio
async def test_generate_quick_actions_localizes_walk_button(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quick actions should localize the walk status button."""  # noqa: E111

    hass.config.language = "de"  # noqa: E111
    templates = DashboardTemplates(hass)  # noqa: E111
    generator = OverviewCardGenerator(hass, templates)  # noqa: E111

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:  # noqa: E111
        assert entities == [f"sensor.{DOMAIN}_dogs_walking"]
        return list(entities)

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)  # noqa: E111

    dog_config: DogConfigData = {  # noqa: E111
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_WALK: True},
    }

    actions_card = await generator.generate_quick_actions([dog_config])  # noqa: E111

    assert actions_card is not None  # noqa: E111
    cards = actions_card["cards"]  # noqa: E111
    assert cards[0]["name"] == "Spazierstatus"  # noqa: E111


@pytest.mark.asyncio
async def test_generate_quick_actions_localizes_feed_all_and_reset(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quick actions should localize feed-all and reset buttons."""  # noqa: E111

    hass.config.language = "de"  # noqa: E111
    templates = DashboardTemplates(hass)  # noqa: E111
    generator = OverviewCardGenerator(hass, templates)  # noqa: E111

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:  # noqa: E111
        assert set(entities) == {
            f"button.{DOMAIN}_feed_all_dogs",
            f"sensor.{DOMAIN}_dogs_walking",
        }
        return list(entities)

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)  # noqa: E111

    dog_config: DogConfigData = {  # noqa: E111
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
    }

    actions_card = await generator.generate_quick_actions([dog_config])  # noqa: E111

    assert actions_card is not None  # noqa: E111
    cards = actions_card["cards"]  # noqa: E111
    assert [card["name"] for card in cards] == [  # noqa: E111
        "Alle füttern",
        "Spazierstatus",
        "Täglicher Reset",
    ]


@pytest.mark.asyncio
async def test_generate_visitor_cards_requires_enabled_module(
    hass: HomeAssistant,
) -> None:
    """Visitor cards should be skipped when the module is disabled."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    generator = ModuleCardGenerator(hass, templates)  # noqa: E111

    dog_config: DogConfigData = {  # noqa: E111
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_VISITOR: False},
    }

    cards = await generator.generate_visitor_cards(dog_config, {})  # noqa: E111

    assert cards == []  # noqa: E111


@pytest.mark.asyncio
async def test_generate_visitor_cards_includes_entities_and_markdown(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Visitor cards should render an entities card and markdown summary."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    generator = ModuleCardGenerator(hass, templates)  # noqa: E111

    validated_entities = [  # noqa: E111
        "switch.fido_visitor_mode",
        "binary_sensor.fido_visitor_mode",
    ]

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:  # noqa: E111
        assert entities == validated_entities
        return validated_entities

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)  # noqa: E111

    dog_config: DogConfigData = {  # noqa: E111
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_VISITOR: True},
    }

    cards = await generator.generate_visitor_cards(dog_config, {})  # noqa: E111

    assert len(cards) == 2  # noqa: E111
    entities_card, markdown_card = cards  # noqa: E111

    assert entities_card["type"] == "entities"  # noqa: E111
    assert entities_card["entities"] == validated_entities  # noqa: E111

    assert markdown_card["type"] == "markdown"  # noqa: E111
    assert markdown_card["title"] == "Fido visitor insights"  # noqa: E111
    content = markdown_card["content"]  # noqa: E111
    assert "Visitor mode status" in content  # noqa: E111
    assert "binary_sensor.fido_visitor_mode" in content  # noqa: E111


@pytest.mark.asyncio
async def test_generate_visitor_cards_only_outputs_markdown_when_entities_missing(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Visitor cards should fall back to markdown when no entities validate."""  # noqa: E111

    templates = DashboardTemplates(hass)  # noqa: E111
    generator = ModuleCardGenerator(hass, templates)  # noqa: E111

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:  # noqa: E111
        assert entities == [
            "switch.fido_visitor_mode",
            "binary_sensor.fido_visitor_mode",
        ]
        return []

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)  # noqa: E111

    dog_config: DogConfigData = {  # noqa: E111
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_VISITOR: True},
    }

    cards = await generator.generate_visitor_cards(dog_config, {})  # noqa: E111

    assert len(cards) == 1  # noqa: E111
    markdown_card = cards[0]  # noqa: E111
    assert markdown_card["type"] == "markdown"  # noqa: E111
    assert markdown_card["title"] == "Fido visitor insights"  # noqa: E111


@pytest.mark.asyncio
async def test_generate_visitor_cards_localizes_german(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Visitor cards should localize titles and fallback strings."""  # noqa: E111

    hass.config.language = "de"  # noqa: E111
    templates = DashboardTemplates(hass)  # noqa: E111
    generator = ModuleCardGenerator(hass, templates)  # noqa: E111

    validated_entities = [  # noqa: E111
        "switch.fido_visitor_mode",
        "binary_sensor.fido_visitor_mode",
    ]

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:  # noqa: E111
        assert entities == validated_entities
        return validated_entities

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)  # noqa: E111

    dog_config: DogConfigData = {  # noqa: E111
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_VISITOR: True},
    }

    cards = await generator.generate_visitor_cards(dog_config, {})  # noqa: E111

    assert len(cards) == 2  # noqa: E111
    entities_card, markdown_card = cards  # noqa: E111

    assert entities_card["title"] == "Steuerungen für den Besuchermodus"  # noqa: E111
    assert markdown_card["title"] == "Fido Besuchereinblicke"  # noqa: E111
    content = markdown_card["content"]  # noqa: E111
    assert "Status des Besuchermodus" in content  # noqa: E111
    assert '"Ja"' in content  # noqa: E111
    assert '"Keine"' in content  # noqa: E111


@pytest.mark.asyncio
async def test_health_feeding_overview_localizes_german(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Health-aware feeding overview should render localized German strings."""  # noqa: E111

    hass.config.language = "de"  # noqa: E111
    templates = DashboardTemplates(hass)  # noqa: E111
    generator = HealthAwareFeedingCardGenerator(hass, templates)  # noqa: E111

    async def _fake_exists(entity_id: str) -> bool:  # noqa: E111
        return True

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:  # noqa: E111
        return list(entities)

    monkeypatch.setattr(generator, "_entity_exists_cached", _fake_exists)  # noqa: E111
    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)  # noqa: E111

    dog_config: DogConfigData = {  # noqa: E111
        CONF_DOG_ID: "bella",
        CONF_DOG_NAME: "Bella",
        "modules": {MODULE_HEALTH: True, MODULE_FEEDING: True},
    }

    cards = await generator.generate_health_feeding_overview(dog_config, {})  # noqa: E111

    assert len(cards) == 4  # noqa: E111
    status_card = cards[0]  # noqa: E111
    assert status_card["title"] == "🔬 Bella Gesundheitsfütterung"  # noqa: E111
    status_names = [entity["name"] for entity in status_card["entities"]]  # noqa: E111
    assert status_names == [  # noqa: E111
        "Gesundheitsstatus",
        "Kalorienziel",
        "Kalorien heute",
        "Portionsanpassung",
    ]

    calorie_card = cards[1]  # noqa: E111
    assert calorie_card["title"] == "📊 Kalorienverlauf"  # noqa: E111

    weight_stack = cards[2]  # noqa: E111
    assert weight_stack["cards"][0]["title"] == "⚖️ Gewichtsmanagement"  # noqa: E111
    assert weight_stack["cards"][1]["name"] == "Fortschritt des Gewichtsziels"  # noqa: E111

    portion_stack = cards[3]  # noqa: E111
    portion_markdown = portion_stack["cards"][0]["content"]  # noqa: E111
    assert "Gesundheitsanpassungen" in portion_markdown  # noqa: E111
    buttons = portion_stack["cards"][1]["cards"]  # noqa: E111
    button_names = [button["name"] for button in buttons]  # noqa: E111
    assert "Neu berechnen" in button_names  # noqa: E111
    assert "Gesundheitsdaten aktualisieren" in button_names  # noqa: E111


@pytest.mark.asyncio
async def test_module_health_cards_localize_titles(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Health module cards should emit localized German titles and buttons."""  # noqa: E111

    hass.config.language = "de"  # noqa: E111
    templates = DashboardTemplates(hass)  # noqa: E111
    generator = ModuleCardGenerator(hass, templates)  # noqa: E111

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:  # noqa: E111
        return list(entities)

    async def _fake_exists(entity_id: str) -> bool:  # noqa: E111
        return True

    captured_history: dict[str, str] = {}  # noqa: E111

    async def _fake_history(  # noqa: E111
        entities: list[str], title: str, hours_to_show: int, theme: str = "modern"
    ) -> dict[str, object]:
        captured_history["title"] = title
        return {"type": "history-graph", "title": title, "entities": entities}

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)  # noqa: E111
    monkeypatch.setattr(generator, "_entity_exists_cached", _fake_exists)  # noqa: E111
    monkeypatch.setattr(templates, "get_history_graph_template", _fake_history)  # noqa: E111

    dog_config: DogConfigData = {  # noqa: E111
        CONF_DOG_ID: "bella",
        CONF_DOG_NAME: "Bella",
        "modules": {MODULE_HEALTH: True},
    }

    cards = await generator.generate_health_cards(dog_config, {})  # noqa: E111

    assert len(cards) == 4  # noqa: E111
    metrics_card, buttons_card, weight_card, schedule_card = cards  # noqa: E111

    assert metrics_card["title"] == "Gesundheitsmetriken"  # noqa: E111
    button_names = [card["name"] for card in buttons_card["cards"]]  # noqa: E111
    assert "Gesundheit protokollieren" in button_names  # noqa: E111
    assert "Medikation protokollieren" in button_names  # noqa: E111

    assert weight_card["title"] == "Gewichtsverlauf (30 Tage)"  # noqa: E111
    assert captured_history["title"] == "Gewichtsverlauf (30 Tage)"  # noqa: E111

    assert schedule_card["title"] == "Gesundheitsplan"  # noqa: E111


@pytest.mark.asyncio
async def test_weather_health_cards_localize_german(hass: HomeAssistant) -> None:
    """Weather health dashboards should localize titles and entity names."""  # noqa: E111

    hass.config.language = "de"  # noqa: E111
    templates = DashboardTemplates(hass)  # noqa: E111

    status_card = await templates.get_weather_status_card_template(  # noqa: E111
        "fido", "Fido", compact=False
    )
    assert status_card["title"].endswith("Wettergesundheit")  # noqa: E111
    entity_names = [entity["name"] for entity in status_card["entities"]]  # noqa: E111
    assert "Gesundheitswert" in entity_names  # noqa: E111
    assert "Temperaturrisiko" in entity_names  # noqa: E111
    assert "Aktivitätsniveau" in entity_names  # noqa: E111
    assert "Spaziersicherheit" in entity_names  # noqa: E111

    compact_card = await templates.get_weather_status_card_template(  # noqa: E111
        "fido", "Fido", compact=True
    )
    assert compact_card["name"].endswith("Wettergesundheit")  # noqa: E111

    chart_card = await templates.get_weather_chart_template(  # noqa: E111
        "fido", chart_type="health_score"
    )
    assert chart_card["name"] == "Wettergesundheitswirkung"  # noqa: E111
    assert chart_card["entities"][0]["name"] == "Gesundheitswert"  # noqa: E111
