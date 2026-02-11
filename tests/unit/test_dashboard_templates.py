from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

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
from custom_components.pawcontrol.types import (
    DogConfigData,
    ensure_dog_modules_config,
)
from homeassistant.core import HomeAssistant


@pytest.mark.asyncio
async def test_statistics_graph_template_returns_card(hash: HomeAssistant) -> None:
    """The statistics graph helper should return a typed card."""

    templates = DashboardTemplates(hash)
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
    hash: HomeAssistant,
) -> None:
    """Dog status template should accept ``DogModulesConfig`` payloads."""

    templates = DashboardTemplates(hash)
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


def test_statistics_summary_template_counts_modules(hash: HomeAssistant) -> None:
    """Summary card should count enabled modules across dogs."""

    templates = DashboardTemplates(hash)
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


def test_statistics_summary_template_localises_general_sections(
    hash: HomeAssistant,
) -> None:
    """Summary card should localise header, counts, and title."""

    hash.config.language = "de"
    templates = DashboardTemplates(hash)
    raw_dogs = [
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

    card = templates.get_statistics_summary_template(raw_dogs)

    content = card["content"]
    assert "## Paw Control Statistiken" in content
    assert "**Verwaltete Hunde:** 1" in content
    assert "**Active Module:**" in content
    assert "- Fütterung: 1" in content
    assert "- Spaziergänge: 1" in content
    assert "- Gesundheit: 1" in content
    assert "- GPS: 1" in content
    assert "- Benachrichtigungen: 1" in content
    assert "*Zuletzt aktualisiert:" in content
    assert card["title"] == "Zusammenfassung"


@pytest.mark.asyncio
async def test_map_card_template_normalises_options(hash: HomeAssistant) -> None:
    """Map card helper should coerce raw option payloads."""

    templates = DashboardTemplates(hash)
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
    hash: HomeAssistant,
) -> None:
    """Legacy ``default_zoom`` keys should be recognised and values clamped."""

    templates = DashboardTemplates(hash)
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
    hash: HomeAssistant,
) -> None:
    """Missing zoom options should fall back to ``DEFAULT_MAP_ZOOM``."""

    templates = DashboardTemplates(hash)
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
    hash: HomeAssistant,
) -> None:
    """Explicit dark-mode overrides should take precedence over theme defaults."""

    templates = DashboardTemplates(hash)

    card = await templates.get_map_card_template(
        "alpha",
        options={"dark_mode": False},
        theme="dark",
    )

    assert card["dark_mode"] is False


@pytest.mark.asyncio
async def test_map_card_template_accepts_dark_mode_enable_override(
    hash: HomeAssistant,
) -> None:
    """Explicitly enabling dark mode should apply even when theme is light."""

    templates = DashboardTemplates(hash)

    card = await templates.get_map_card_template(
        "beta",
        options={"dark_mode": True},
        theme="modern",
    )

    assert card["dark_mode"] is True


@pytest.mark.asyncio
async def test_statistics_generator_normalises_raw_dog_configs(
    hash: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Statistics generator should normalise raw payloads before rendering."""

    templates = DashboardTemplates(hash)
    generator = StatisticsCardGenerator(hash, templates)

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
    hash: HomeAssistant,
) -> None:
    """The summary markdown should embed rejection metrics when provided."""

    templates = DashboardTemplates(hash)
    last_rejection = 1_700_000_000.0
    coordinator_metrics = {
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
    service_metrics = {
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

    guard_metrics = {
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
        coordinator_statistics={"rejection_metrics": coordinator_metrics},
        service_execution_metrics=service_metrics,
        service_guard_metrics=guard_metrics,
    )

    content = card["content"]
    iso_timestamp = datetime.fromtimestamp(last_rejection, UTC).isoformat()
    service_iso = datetime.fromtimestamp(last_rejection - 3600, UTC).isoformat()

    assert "Resilience metrics" in content
    assert "**Coordinator telemetry:**" in content
    assert "**Service execution telemetry:**" in content
    assert "- Rejected calls: 3" in content
    assert "- Rejecting breakers: 2" in content
    assert "- Rejection rate: 12.50%" in content
    assert f"- Last rejection: {iso_timestamp}" in content
    assert "- Last rejecting breaker: api" in content
    assert "- Open breaker names: api" in content
    assert "- Open breaker IDs: api" in content
    assert "- Half-open breaker names: cache" in content
    assert "- Half-open breaker IDs: cache" in content
    assert "- Unknown breaker names: legacy" in content
    assert "- Unknown breaker IDs: legacy" in content
    assert "- Rejecting breaker IDs: api, cache" in content
    assert "- Rejecting breaker names: api" in content
    assert "- Rejection rate: 5.00%" in content
    assert f"- Last rejection: {service_iso}" in content
    assert "- Last rejecting breaker: automation" in content
    assert "- Guard outcomes:" in content
    assert "  - Guarded calls executed: 7" in content
    assert "  - Guarded calls skipped: 2" in content
    assert "  - Skip reasons:" in content
    assert "    - quiet_hours: 2" in content
    assert "  - Recent guard results:" in content
    assert "    - notify.mobile_app: skipped (reason: quiet_hours)" in content
    assert "    - script.evening_reset: executed - resumed schedule" in content


def test_statistics_summary_template_localizes_breaker_labels(
    hash: HomeAssistant,
) -> None:
    """Localisation should translate breaker labels based on the HA language."""

    hash.config.language = "de"
    templates = DashboardTemplates(hash)
    card = templates.get_statistics_summary_template(
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

    content = card["content"]
    assert "**Koordinator-Telemetrie:**" in content
    assert "- Letzter blockierender Breaker: api" in content
    assert "- Abgelehnte Aufrufe: 1" in content
    assert "- Blockierende Breaker: 1" in content
    assert "- Ablehnungsrate: 0.00%" in content
    assert "- Guard-Ergebnisse:" in content
    assert "  - Ausgeführte Guard-Aufrufe: 4" in content
    assert "  - Übersprungene Guard-Aufrufe: 1" in content
    assert "  - Übersprung-Gründe:" in content
    assert "    - ruhezeit: 1" in content
    assert "  - Aktuelle Guard-Ergebnisse:" in content
    assert "    - notify.mobile_app: übersprungen (Grund: ruhezeit)" in content
    assert "- Letzte Ablehnung: nie" in content
    assert "- Namen oftener Breaker: keine" in content
    assert "- IDs blockierender Breaker: api" in content


def test_statistics_summary_template_localizes_empty_lists(hash: HomeAssistant) -> None:
    """Empty breaker lists should localize using the configured language."""

    hash.config.language = "fr"
    templates = DashboardTemplates(hash)
    card = templates.get_statistics_summary_template(
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

    content = card["content"]
    assert "- Open breaker names: none" in content
    assert "- Open breaker IDs: none" in content


def test_statistics_summary_template_localizes_resilience_fallbacks(
    hash: HomeAssistant,
) -> None:
    """Rejection rate and time fallbacks should honor the active language."""

    templates = DashboardTemplates(hash)
    card = templates.get_statistics_summary_template(
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

    content = card["content"]
    assert "- Rejection rate: n/a" in content
    assert "- Last rejection: never" in content
    assert "- Last rejecting breaker" not in content

    hash.config.language = "de"
    templates_localized = DashboardTemplates(hash)
    localized_card = templates_localized.get_statistics_summary_template(
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

    localized_content = localized_card["content"]
    assert "- Ablehnungsrate: nicht verfügbar" in localized_content
    assert "- Letzte Ablehnung: nie" in localized_content
    assert "- Letzter blockierender Breaker" not in localized_content


@pytest.mark.asyncio
async def test_statistics_generator_ignores_untyped_dogs(
    hash: HomeAssistant,
) -> None:
    """Statistics generator should skip payloads without typed configs."""

    templates = DashboardTemplates(hash)
    generator = StatisticsCardGenerator(hash, templates)

    cards = await generator.generate_statistics_cards(
        [{"dog_name": "No identifier"}],
        {"theme": "modern"},
    )

    assert cards == []


@pytest.mark.asyncio
async def test_notification_templates_handle_missing_metrics(
    hash: HomeAssistant,
) -> None:
    """Notification overview should degrade gracefully without sensor data."""

    templates = DashboardTemplates(hash)
    overview = await templates.get_notifications_overview_card_template(
        "alpha", "Alpha", theme="modern"
    )

    assert "No notifications recorded" in overview["content"]

    settings = await templates.get_notification_settings_card_template(
        "alpha", "Alpha", [], theme="modern"
    )
    assert settings is None


@pytest.mark.asyncio
async def test_notification_templates_localize_labels(hash: HomeAssistant) -> None:
    """Notification dashboards should use translated labels for German locales."""

    hash.config.language = "de"
    templates = DashboardTemplates(hash)

    hash.states.async_set(
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

    overview = await templates.get_notifications_overview_card_template(
        "alpha", "Alpha", theme="modern"
    )
    content = overview["content"]

    assert "Benachrichtigungsübersicht für Alpha" in content
    assert "**Heute gesendete Benachrichtigungen:** 4" in content
    assert "**Fehlgeschlagene Zustellungen:** 2" in content
    assert "**Ruhezeiten aktiv:** ✅" in content
    assert "### Bevorzugte Kanäle" in content
    assert "• Verwendet Standardkanäle der Integration" in content
    assert "### Letzte Benachrichtigung" in content
    assert "- **Typ:** system_info" in content
    assert "- **Priorität:** High" in content
    assert "- **Gesendet:** 2025-02-14T12:00:00Z" in content

    settings = await templates.get_notification_settings_card_template(
        "alpha", "Alpha", ["switch.alpha_notifications"], theme="modern"
    )
    assert settings is not None
    assert settings["title"] == "🔔 Alpha Benachrichtigungssteuerung"

    actions = await templates.get_notifications_actions_card_template(
        "alpha", theme="modern"
    )
    button_names = [card["name"] for card in actions["cards"]]
    assert "Testbenachrichtigung senden" in button_names
    assert "Ruhezeiten zurücksetzen" in button_names
    send_test_button = next(
        card for card in actions["cards"] if card["icon"] == "mdi:bell-check"
    )
    assert (
        send_test_button["tap_action"]["service_data"]["title"] == "PawControl-Diagnose"
    )
    assert (
        send_test_button["tap_action"]["service_data"]["message"]
        == "Testbenachrichtigung vom Dashboard"
    )

    hash.states.async_set(
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

    empty_overview = await templates.get_notifications_overview_card_template(
        "alpha", "Alpha", theme="modern"
    )
    assert (
        "Für diesen Hund wurden noch keine Benachrichtigungen aufgezeichnet."
        in empty_overview["content"]
    )


@pytest.mark.asyncio
async def test_feeding_templates_localize_labels(hash: HomeAssistant) -> None:
    """Feeding dashboards should translate titles and meal labels."""

    hash.config.language = "de"
    templates = DashboardTemplates(hash)

    schedule_modern = await templates.get_feeding_schedule_template(
        "fido", theme="modern"
    )
    assert schedule_modern["title"] == "🍽️ Fütterungsplan"

    schedule_minimal = await templates.get_feeding_schedule_template(
        "fido", theme="minimal"
    )
    assert schedule_minimal["title"] == "Fütterungsplan"

    controls = await templates.get_feeding_controls_template("fido", theme="modern")
    button_names = {
        button["name"] for row in controls["cards"] for button in row.get("cards", [])
    }
    assert button_names == {"Frühstück", "Mittagessen", "Abendessen", "Snack"}


@pytest.mark.asyncio
async def test_weather_recommendations_card_parses_structured_data(
    hash: HomeAssistant,
) -> None:
    """Weather recommendations card should flatten structured data safely."""

    templates = DashboardTemplates(hash)
    generator = WeatherCardGenerator(hash, templates)

    hash.states.async_set(
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
    hash: HomeAssistant,
) -> None:
    """Weather recommendations template should embed overflow notes."""

    templates = DashboardTemplates(hash)

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
    hash: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Notification cards should be composed through the typed templates."""

    templates = DashboardTemplates(hash)
    generator = ModuleCardGenerator(hash, templates)

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
async def test_generate_walk_cards_localizes_german(
    hash: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Walk cards should honor the Home Assistant language."""

    hash.config.language = "de"
    templates = DashboardTemplates(hash)
    generator = ModuleCardGenerator(hash, templates)

    status_entities = [
        "binary_sensor.fido_is_walking",
        "sensor.fido_current_walk_duration",
        "sensor.fido_walks_today",
        "sensor.fido_walk_distance_today",
        "sensor.fido_last_walk_time",
        "sensor.fido_last_walk_distance",
    ]

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:
        assert entities == status_entities
        return list(status_entities)

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)

    captured_history: dict[str, str] = {}

    async def _fake_history(
        entities: list[str],
        title: str,
        hours_to_show: int,
        theme: str = "modern",
    ) -> dict[str, object]:
        captured_history["title"] = title
        return {"type": "history-graph", "title": title, "entities": entities}

    monkeypatch.setattr(
        generator.templates, "get_history_graph_template", _fake_history
    )

    dog_config: DogConfigData = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_WALK: True},
    }

    cards = await generator.generate_walk_cards(dog_config, {})

    assert len(cards) == 4
    entities_card, start_card, end_card, history_card = cards

    assert entities_card["title"] == "Spazierstatus"
    assert start_card["card"]["name"] == "Spaziergang starten"
    assert end_card["card"]["name"] == "Spaziergang beenden"
    assert history_card["title"] == "Spazierverlauf (7 Tage)"
    assert captured_history["title"] == "Spazierverlauf (7 Tage)"


@pytest.mark.asyncio
async def test_generate_quick_actions_localizes_walk_button(
    hash: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quick actions should localize the walk status button."""

    hash.config.language = "de"
    templates = DashboardTemplates(hash)
    generator = OverviewCardGenerator(hash, templates)

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:
        assert entities == [f"sensor.{DOMAIN}_dogs_walking"]
        return list(entities)

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)

    dog_config: DogConfigData = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_WALK: True},
    }

    actions_card = await generator.generate_quick_actions([dog_config])

    assert actions_card is not None
    cards = actions_card["cards"]
    assert cards[0]["name"] == "Spazierstatus"


@pytest.mark.asyncio
async def test_generate_quick_actions_localizes_feed_all_and_reset(
    hash: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quick actions should localize feed-all and reset buttons."""

    hash.config.language = "de"
    templates = DashboardTemplates(hash)
    generator = OverviewCardGenerator(hash, templates)

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:
        assert set(entities) == {
            f"button.{DOMAIN}_feed_all_dogs",
            f"sensor.{DOMAIN}_dogs_walking",
        }
        return list(entities)

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)

    dog_config: DogConfigData = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
    }

    actions_card = await generator.generate_quick_actions([dog_config])

    assert actions_card is not None
    cards = actions_card["cards"]
    assert [card["name"] for card in cards] == [
        "Alle füttern",
        "Spazierstatus",
        "Täglicher Reset",
    ]


@pytest.mark.asyncio
async def test_generate_visitor_cards_requires_enabled_module(
    hash: HomeAssistant,
) -> None:
    """Visitor cards should be skipped when the module is disabled."""

    templates = DashboardTemplates(hash)
    generator = ModuleCardGenerator(hash, templates)

    dog_config: DogConfigData = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_VISITOR: False},
    }

    cards = await generator.generate_visitor_cards(dog_config, {})

    assert cards == []


@pytest.mark.asyncio
async def test_generate_visitor_cards_includes_entities_and_markdown(
    hash: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Visitor cards should render an entities card and markdown summary."""

    templates = DashboardTemplates(hash)
    generator = ModuleCardGenerator(hash, templates)

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
    hash: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Visitor cards should fall back to markdown when no entities validate."""

    templates = DashboardTemplates(hash)
    generator = ModuleCardGenerator(hash, templates)

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


@pytest.mark.asyncio
async def test_generate_visitor_cards_localizes_german(
    hash: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Visitor cards should localize titles and fallback strings."""

    hash.config.language = "de"
    templates = DashboardTemplates(hash)
    generator = ModuleCardGenerator(hash, templates)

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

    assert entities_card["title"] == "Steuerungen für den Besuchermodus"
    assert markdown_card["title"] == "Fido Besuchereinblicke"
    content = markdown_card["content"]
    assert "Status des Besuchermodus" in content
    assert '"Ja"' in content
    assert '"Keine"' in content


@pytest.mark.asyncio
async def test_health_feeding_overview_localizes_german(
    hash: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Health-aware feeding overview should render localized German strings."""

    hash.config.language = "de"
    templates = DashboardTemplates(hash)
    generator = HealthAwareFeedingCardGenerator(hash, templates)

    async def _fake_exists(entity_id: str) -> bool:
        return True

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:
        return list(entities)

    monkeypatch.setattr(generator, "_entity_exists_cached", _fake_exists)
    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)

    dog_config: DogConfigData = {
        CONF_DOG_ID: "bella",
        CONF_DOG_NAME: "Bella",
        "modules": {MODULE_HEALTH: True, MODULE_FEEDING: True},
    }

    cards = await generator.generate_health_feeding_overview(dog_config, {})

    assert len(cards) == 4
    status_card = cards[0]
    assert status_card["title"] == "🔬 Bella Gesundheitsfütterung"
    status_names = [entity["name"] for entity in status_card["entities"]]
    assert status_names == [
        "Gesundheitsstatus",
        "Kalorienziel",
        "Kalorien heute",
        "Portionsanpassung",
    ]

    calorie_card = cards[1]
    assert calorie_card["title"] == "📊 Kalorienverlauf"

    weight_stack = cards[2]
    assert weight_stack["cards"][0]["title"] == "⚖️ Gewichtsmanagement"
    assert weight_stack["cards"][1]["name"] == "Fortschritt des Gewichtsziels"

    portion_stack = cards[3]
    portion_markdown = portion_stack["cards"][0]["content"]
    assert "Gesundheitsanpassungen" in portion_markdown
    buttons = portion_stack["cards"][1]["cards"]
    button_names = [button["name"] for button in buttons]
    assert "Neu berechnen" in button_names
    assert "Gesundheitsdaten aktualisieren" in button_names


@pytest.mark.asyncio
async def test_module_health_cards_localize_titles(
    hash: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Health module cards should emit localized German titles and buttons."""

    hash.config.language = "de"
    templates = DashboardTemplates(hash)
    generator = ModuleCardGenerator(hash, templates)

    async def _fake_validate(entities: list[str], use_cache: bool = True) -> list[str]:
        return list(entities)

    async def _fake_exists(entity_id: str) -> bool:
        return True

    captured_history: dict[str, str] = {}

    async def _fake_history(
        entities: list[str], title: str, hours_to_show: int, theme: str = "modern"
    ) -> dict[str, object]:
        captured_history["title"] = title
        return {"type": "history-graph", "title": title, "entities": entities}

    monkeypatch.setattr(generator, "_validate_entities_batch", _fake_validate)
    monkeypatch.setattr(generator, "_entity_exists_cached", _fake_exists)
    monkeypatch.setattr(templates, "get_history_graph_template", _fake_history)

    dog_config: DogConfigData = {
        CONF_DOG_ID: "bella",
        CONF_DOG_NAME: "Bella",
        "modules": {MODULE_HEALTH: True},
    }

    cards = await generator.generate_health_cards(dog_config, {})

    assert len(cards) == 4
    metrics_card, buttons_card, weight_card, schedule_card = cards

    assert metrics_card["title"] == "Gesundheitsmetriken"
    button_names = [card["name"] for card in buttons_card["cards"]]
    assert "Gesundheit protokollieren" in button_names
    assert "Medikation protokollieren" in button_names

    assert weight_card["title"] == "Gewichtsverlauf (30 Tage)"
    assert captured_history["title"] == "Gewichtsverlauf (30 Tage)"

    assert schedule_card["title"] == "Gesundheitsplan"


@pytest.mark.asyncio
async def test_weather_health_cards_localize_german(hash: HomeAssistant) -> None:
    """Weather health dashboards should localize titles and entity names."""

    hash.config.language = "de"
    templates = DashboardTemplates(hash)

    status_card = await templates.get_weather_status_card_template(
        "fido", "Fido", compact=False
    )
    assert status_card["title"].endswith("Wettergesundheit")
    entity_names = [entity["name"] for entity in status_card["entities"]]
    assert "Gesundheitswert" in entity_names
    assert "Temperaturrisiko" in entity_names
    assert "Aktivitätsniveau" in entity_names
    assert "Spaziersicherheit" in entity_names

    compact_card = await templates.get_weather_status_card_template(
        "fido", "Fido", compact=True
    )
    assert compact_card["name"].endswith("Wettergesundheit")

    chart_card = await templates.get_weather_chart_template(
        "fido", chart_type="health_score"
    )
    assert chart_card["name"] == "Wettergesundheitswirkung"
    assert chart_card["entities"][0]["name"] == "Gesundheitswert"
