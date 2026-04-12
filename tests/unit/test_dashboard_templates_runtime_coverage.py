"""Runtime-heavy coverage tests for ``dashboard_templates.py``."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from homeassistant.const import STATE_UNKNOWN
import pytest

from custom_components.pawcontrol import dashboard_templates as dt
from custom_components.pawcontrol.const import (
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)

pytestmark = pytest.mark.unit


class _StateStore:
    """Simple mapping-backed state registry."""

    def __init__(self, states: Mapping[str, object] | None = None) -> None:
        self._states = dict(states or {})

    def get(self, entity_id: str) -> object | None:
        return self._states.get(entity_id)


def _state(state: str = "ok", attributes: Mapping[str, object] | None = None) -> Any:
    """Return a compact Home Assistant state double."""
    return SimpleNamespace(state=state, attributes=dict(attributes or {}))


def _hass(
    states: Mapping[str, object] | None = None,
    *,
    language: str = "en",
) -> Any:
    """Create a lightweight Home Assistant-style object."""
    return SimpleNamespace(
        config=SimpleNamespace(language=language),
        states=_StateStore(states),
    )


@pytest.mark.asyncio
async def test_template_cache_and_formatting_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover template cache internals, list cloning, and formatting fallbacks."""
    clock = {"now": 1_000.0}
    monkeypatch.setattr(
        dt.dt_util,
        "utcnow",
        lambda: datetime.fromtimestamp(clock["now"], tz=UTC),
    )

    cache: dt.TemplateCache[dt.CardTemplatePayload] = dt.TemplateCache(maxsize=1)
    assert await cache.get("missing") is None

    cloned_list = dt._clone_template([{"type": "markdown"}])
    assert cloned_list == [{"type": "markdown"}]

    await cache.set("k1", {"type": "markdown", "content": "ok"})
    fetched = await cache.get("k1")
    assert fetched == {"type": "markdown", "content": "ok"}

    clock["now"] += dt.TEMPLATE_TTL_SECONDS + 1
    assert await cache.get("k1") is None

    large_payload = {
        "type": "markdown",
        "content": "x" * (dt.MAX_TEMPLATE_SIZE + 10),
    }
    await cache.set("too-large", large_payload)

    clock["now"] += 1
    await cache.set("k1", {"type": "markdown", "content": "first"})
    clock["now"] += 1
    await cache.set("k2", {"type": "markdown", "content": "second"})
    assert await cache.get("k1") is None
    assert await cache.get("k2") is not None

    await cache.clear()
    await cache._evict_lru()
    stats = cache.get_stats()
    metadata = cache.get_metadata()
    snapshot = cache.coordinator_snapshot()
    assert stats["cached_items"] == 0
    assert metadata["cached_keys"] == []
    assert snapshot["stats"]["max_size"] == 1

    translation_lookup = ({}, {})
    assert dt._format_breaker_list([], translation_lookup) == "none"
    assert dt._format_guard_reasons({}, translation_lookup) == ["none"]

    formatted_results = dt._format_guard_results(
        [
            "invalid-entry",
            {
                "domain": "notify",
                "service": "mobile",
                "executed": False,
                "reason": "guarded",
                "description": "skipped",
            },
        ],
        translation_lookup,
    )
    assert any("notify.mobile" in line for line in formatted_results)


@pytest.mark.asyncio
async def test_dashboard_templates_parsers_and_status_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover parser utilities, status templates, and cache hit branches."""
    templates = dt.DashboardTemplates(_hass(language="de"))

    async def _async_lookup(*_args: object, **_kwargs: object) -> tuple[dict[str, str], dict[str, str]]:
        return ({}, {})

    monkeypatch.setattr(dt, "async_get_component_translation_lookup", _async_lookup)
    monkeypatch.setattr(
        dt,
        "get_cached_component_translation_lookup",
        lambda *_args, **_kwargs: ({}, {}),
    )
    monkeypatch.setattr(dt, "load_bundled_component_translations_fresh", lambda _lang: {})

    assert dt.DashboardTemplates._get_base_card_template("unknown") == {"type": "unknown"}
    assert templates._card_mod({}) == {}
    assert templates._ensure_card_mod({"card_mod": {"style": "x"}}, {}) == {"style": "x"}

    assert templates._parse_int(True) == 1
    assert templates._parse_int(2.7) == 2
    assert templates._parse_int("3.2") == 3
    assert templates._parse_int("bad", default=9) == 9

    assert templates._parse_bool(1) is True
    assert templates._parse_bool("off") is False
    assert templates._parse_bool("yes") is True

    assert templates._parse_channels("push, sms") == ["push", "sms"]
    assert templates._parse_channels([" push ", 7, ""]) == ["push", "7"]
    assert templates._parse_channels(None) == []

    last_event = templates._parse_last_notification(
        {
            "type": "alert",
            "priority": "high",
            "sent_at": 12345,
        },
    )
    assert last_event is not None
    assert last_event["sent_at"] == "12345"

    metrics_none, per_dog_none = templates._normalise_notifications_state(None)
    assert metrics_none["notifications_failed"] == 0
    assert per_dog_none == {}

    metrics_bad, per_dog_bad = templates._normalise_notifications_state(
        SimpleNamespace(attributes="invalid"),
    )
    assert metrics_bad["notifications_failed"] == 0
    assert per_dog_bad == {}

    metrics, per_dog = templates._normalise_notifications_state(
        SimpleNamespace(
            attributes={
                "performance_metrics": "bad",
                "per_dog": {
                    1: {},
                    "dog-a": {
                        "sent_today": "3",
                        "quiet_hours_active": "1",
                        "channels": ["push", 5],
                        "last_notification": {
                            "type": "summary",
                            "title": "Hi",
                            "sent_at": "2026-04-12T00:00:00+00:00",
                        },
                    },
                },
            },
        ),
    )
    assert metrics["notifications_failed"] == 0
    assert per_dog["dog-a"]["sent_today"] == 3

    modules = {
        MODULE_FEEDING: True,
        MODULE_WALK: True,
        MODULE_HEALTH: True,
        MODULE_GPS: True,
        MODULE_NOTIFICATIONS: True,
    }
    first = await templates.get_dog_status_card_template("alpha", "Alpha", modules, theme="playful")
    second = await templates.get_dog_status_card_template("alpha", "Alpha", modules, theme="playful")
    assert first["type"] == "entities"
    assert second == first

    modern = await templates._generate_dog_status_template("beta", "Beta", modules, theme="modern")
    assert modern["show_state"] is True
    assert templates._get_dog_emoji("unknown") == "🐕"

@pytest.mark.asyncio
async def test_action_map_and_statistics_templates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover action button rendering, map normalization, and statistics cards."""
    templates = dt.DashboardTemplates(_hass(language="en"))

    async def _async_lookup(*_args: object, **_kwargs: object) -> tuple[dict[str, str], dict[str, str]]:
        return ({}, {})

    monkeypatch.setattr(dt, "async_get_component_translation_lookup", _async_lookup)
    monkeypatch.setattr(
        dt,
        "get_cached_component_translation_lookup",
        lambda *_args, **_kwargs: ({}, {}),
    )
    monkeypatch.setattr(dt, "load_bundled_component_translations_fresh", lambda _lang: {})

    modules = {
        MODULE_FEEDING: True,
        MODULE_WALK: True,
        MODULE_HEALTH: True,
    }

    grid_buttons = await templates.get_action_buttons_template(
        "alpha",
        modules,
        theme="modern",
        layout="grid",
    )
    assert grid_buttons and grid_buttons[0]["type"] == "grid"

    cached_buttons = await templates.get_action_buttons_template(
        "alpha",
        modules,
        theme="modern",
        layout="grid",
    )
    assert cached_buttons == grid_buttons

    panel_buttons = await templates.get_action_buttons_template(
        "beta",
        modules,
        theme="playful",
        layout="panels",
    )
    assert panel_buttons and panel_buttons[0]["type"] == "horizontal-stack"

    assert templates._gradient_style("#111", "#222")["card_mod"]
    assert templates._get_button_style("modern")["card_mod"]
    assert templates._get_button_style("playful")["card_mod"]
    assert templates._get_button_style("minimal") == {}
    assert templates._wrap_buttons_layout([], "cards") is None

    options_bad_mapping = dt.DashboardTemplates._normalise_map_options({1: "x", "unsupported": 3})
    assert options_bad_mapping["zoom"] == dt.DEFAULT_MAP_ZOOM

    options_iterable = dt.DashboardTemplates._normalise_map_options(
        [
            {"zoom": "9", 4: "bad", "unsupported": 1},
            ("default_zoom", "7"),
            (5, 6),
            ["bad"],
            {"hours_to_show": "12"},
            ("dark_mode", "off"),
        ],
    )
    assert options_iterable["zoom"] == 9
    assert options_iterable["default_zoom"] == 7
    assert options_iterable["hours_to_show"] == 12
    assert options_iterable["dark_mode"] is False

    options_invalid_type = dt.DashboardTemplates._normalise_map_options(object())
    assert options_invalid_type["zoom"] == dt.DEFAULT_MAP_ZOOM

    nan_options = dt.DashboardTemplates._normalise_map_options(
        {
            "zoom": "nan",
            "default_zoom": "inf",
            "hours_to_show": "bad",
            "dark_mode": "no",
        },
    )
    assert nan_options["zoom"] == dt.DEFAULT_MAP_ZOOM
    assert nan_options["dark_mode"] is False

    templates._normalise_map_options = lambda _options: {"default_zoom": 8}  # type: ignore[method-assign]
    map_from_default = await templates.get_map_card_template("alpha", None, theme="modern")
    assert map_from_default["zoom"] == 8

    templates._normalise_map_options = lambda _options: {"zoom": 5}  # type: ignore[method-assign]
    map_from_zoom = await templates.get_map_card_template("alpha", None, theme="playful")
    assert map_from_zoom["default_zoom"] == 5
    assert map_from_zoom["card_mod"]

    stats_card = await templates.get_statistics_card_template(
        "alpha",
        "Alpha",
        modules,
        theme="modern",
    )
    assert stats_card["type"] == "markdown"

    assert await templates.get_statistics_graph_template(
        "Empty",
        [],
        ["mean"],
        days_to_show=7,
    ) is None

    templates._card_mod = lambda _theme_styles: {}  # type: ignore[method-assign]
    graph_without_mod = await templates.get_statistics_graph_template(
        "Non-empty",
        ["sensor.a"],
        ["mean"],
        days_to_show=7,
    )
    assert graph_without_mod is not None
    assert "card_mod" not in graph_without_mod

    summary_with_metrics = templates.get_statistics_summary_template(
        [
            {
                "dog_id": "alpha",
                "dog_name": "Alpha",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_HEALTH: True,
                    MODULE_GPS: True,
                    MODULE_NOTIFICATIONS: True,
                },
            }
        ],
        coordinator_statistics={"rejection_metrics": {"rejected_call_count": 2}},
        service_execution_metrics={"rejection_metrics": {"rejected_call_count": 3}},
        service_guard_metrics={
            "executed": "7",
            "skipped": 2.5,
            "reasons": {"quiet": "2", 4: 9},
            "last_results": [{"domain": "notify", "service": "mobile"}],
        },
    )
    assert "Resilience" in summary_with_metrics["content"] or "metrics" in summary_with_metrics["content"]

    summary_without_coordinator_metrics = templates.get_statistics_summary_template(
        [
            {
                "dog_id": "beta",
                "dog_name": "Beta",
                "modules": {MODULE_FEEDING: False},
            }
        ],
        coordinator_statistics={"rejection_metrics": "bad"},
    )
    assert summary_without_coordinator_metrics["type"] == "markdown"

    assert templates.get_diagnostics_guard_metrics_card_template()
    assert templates.get_notification_rejection_metrics_card_template()
    assert templates.get_guard_notification_error_metrics_card_template()


@pytest.mark.asyncio
async def test_notification_feeding_health_and_timeline_templates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover notification, feeding, health chart, and timeline template paths."""
    notifications_state = _state(
        "ok",
        {
            "performance_metrics": {"notifications_failed": 1},
            "per_dog": {
                "alpha": {
                    "sent_today": 4,
                    "quiet_hours_active": True,
                    "channels": ["push", "email"],
                    "last_notification": {
                        "type": "feeding",
                        "priority": "high",
                        "title": "Fed",
                        "sent_at": "2026-04-12T10:00:00+00:00",
                    },
                }
            },
        },
    )
    hass = _hass({"sensor.pawcontrol_notifications": notifications_state}, language="de")
    templates = dt.DashboardTemplates(hass)

    async def _async_lookup(*_args: object, **_kwargs: object) -> tuple[dict[str, str], dict[str, str]]:
        return ({}, {})

    monkeypatch.setattr(dt, "async_get_component_translation_lookup", _async_lookup)
    monkeypatch.setattr(
        dt,
        "get_cached_component_translation_lookup",
        lambda *_args, **_kwargs: ({}, {}),
    )

    assert (
        await templates.get_notification_settings_card_template("alpha", "Alpha", [], theme="modern")
    ) is None

    settings = await templates.get_notification_settings_card_template(
        "alpha",
        "Alpha",
        ["switch.alpha_notifications_enabled"],
        theme="modern",
    )
    assert settings is not None

    overview = await templates.get_notifications_overview_card_template("alpha", "Alpha", theme="modern")
    assert "push" in overview["content"].lower()

    overview_fallback = await templates.get_notifications_overview_card_template(
        "missing",
        "Missing",
        theme="modern",
    )
    assert "No notifications" in overview_fallback["content"] or "notifications" in overview_fallback["content"]

    actions = await templates.get_notifications_actions_card_template("alpha", theme="modern")
    assert actions["type"] == "horizontal-stack"

    schedule_modern = await templates.get_feeding_schedule_template("alpha", theme="modern")
    assert schedule_modern["type"] == "custom:scheduler-card"

    schedule_playful = await templates.get_feeding_schedule_template("alpha", theme="playful")
    assert schedule_playful["type"] in {"horizontal-stack", "vertical-stack"}

    schedule_minimal = await templates.get_feeding_schedule_template("alpha", theme="minimal")
    assert schedule_minimal["type"] == "entities"

    controls_modern = await templates.get_feeding_controls_template("alpha", theme="modern")
    assert controls_modern["type"] == "vertical-stack"

    controls_playful = await templates.get_feeding_controls_template("alpha", theme="playful")
    assert controls_playful["type"] == "horizontal-stack"

    health_modern = await templates.get_health_charts_template("alpha", theme="modern")
    assert health_modern["type"] == "custom:mini-graph-card"

    health_dark = await templates.get_health_charts_template("alpha", theme="dark")
    assert health_dark["type"] == "custom:mini-graph-card"

    health_playful = await templates.get_health_charts_template("alpha", theme="playful")
    assert health_playful["type"] == "horizontal-stack"

    health_minimal = await templates.get_health_charts_template("alpha", theme="minimal")
    assert health_minimal["type"] == "history-graph"

    timeline = await templates.get_timeline_template("alpha", "Alpha", theme="modern")
    assert timeline["type"] == "markdown"

@pytest.mark.asyncio
async def test_weather_templates_history_and_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover weather template variants, history filtering, cleanup, and layouts."""
    states = {
        "sensor.alpha_breed_weather_advice": _state(
            "ok",
            {"comfort_range": {"min": "8", "max": "24"}},
        ),
        "sensor.valid": _state("12"),
        "sensor.unknown": _state(STATE_UNKNOWN),
    }
    templates = dt.DashboardTemplates(_hass(states, language="en"))

    async def _async_lookup(*_args: object, **_kwargs: object) -> tuple[dict[str, str], dict[str, str]]:
        return ({}, {})

    monkeypatch.setattr(dt, "async_get_component_translation_lookup", _async_lookup)
    monkeypatch.setattr(
        dt,
        "get_cached_component_translation_lookup",
        lambda *_args, **_kwargs: ({}, {}),
    )

    compact_status = await templates.get_weather_status_card_template(
        "alpha",
        "Alpha",
        theme="modern",
        compact=True,
    )
    assert compact_status["type"] == "custom:mushroom-entity"

    full_status = await templates.get_weather_status_card_template(
        "alpha",
        "Alpha",
        theme="playful",
        compact=False,
    )
    assert full_status["type"] == "entities"

    full_status_minimal = await templates.get_weather_status_card_template(
        "alpha",
        "Alpha",
        theme="minimal",
        compact=False,
    )
    assert full_status_minimal["type"] == "entities"

    cached_status = await templates.get_weather_status_card_template(
        "alpha",
        "Alpha",
        theme="playful",
        compact=False,
    )
    assert cached_status == full_status

    alerts_modern = await templates.get_weather_alerts_card_template("alpha", "Alpha", theme="modern")
    assert alerts_modern["type"] == "markdown"

    alerts_playful = await templates.get_weather_alerts_card_template("alpha", "Alpha", theme="playful")
    assert alerts_playful["type"] == "markdown"

    alerts_minimal = await templates.get_weather_alerts_card_template("alpha", "Alpha", theme="minimal")
    assert alerts_minimal["type"] == "markdown"

    recommendations_default = await templates.get_weather_recommendations_card_template(
        "alpha",
        "Alpha",
        theme="modern",
        include_breed_specific=False,
        recommendations=None,
    )
    assert recommendations_default["type"] == "markdown"

    recommendations_breed = await templates.get_weather_recommendations_card_template(
        "alpha",
        "Alpha",
        theme="modern",
        include_breed_specific=True,
        recommendations=["Stay hydrated", "  "],
        overflow_recommendations=2,
    )
    assert "... and 2 more" in recommendations_breed["content"]

    chart_health = await templates.get_weather_chart_template("alpha", chart_type="health_score", theme="modern")
    assert chart_health["type"] == "custom:mini-graph-card"

    chart_temperature = await templates.get_weather_chart_template("alpha", chart_type="temperature", theme="modern")
    assert chart_temperature["type"] == "custom:mini-graph-card"

    chart_activity = await templates.get_weather_chart_template("alpha", chart_type="activity", theme="modern")
    assert chart_activity["type"] == "custom:mini-graph-card"

    chart_fallback = await templates.get_weather_chart_template("alpha", chart_type="activity", theme="minimal")
    assert chart_fallback["type"] == "history-graph"

    advisory_modern = await templates.get_weather_breed_advisory_template(
        "alpha",
        "Alpha",
        "Husky",
        theme="modern",
    )
    assert advisory_modern["type"] == "markdown"

    advisory_minimal = await templates.get_weather_breed_advisory_template(
        "alpha",
        "Alpha",
        "Unknown Breed",
        theme="minimal",
    )
    assert advisory_minimal["type"] == "markdown"

    buttons_vertical = await templates.get_weather_action_buttons_template(
        "alpha",
        theme="modern",
        layout="vertical",
    )
    assert buttons_vertical["type"] == "vertical-stack"

    buttons_grid = await templates.get_weather_action_buttons_template(
        "alpha",
        theme="playful",
        layout="grid",
    )
    assert buttons_grid["type"] == "grid"

    buttons_default = await templates.get_weather_action_buttons_template(
        "alpha",
        theme="minimal",
        layout="horizontal",
    )
    assert buttons_default["type"] == "horizontal-stack"

    assert templates._get_weather_icon("unknown") == "🌤️"
    assert templates._get_weather_color_by_score("modern")
    assert templates._get_breed_emoji("husky", "playful") != "🐶"
    assert templates._get_breed_emoji("unknown", "playful") == "🐶"
    assert templates._get_breed_emoji("husky", "modern") == "🐕"

    history_empty = await templates.get_history_graph_template(
        ["sensor.missing"],
        "Missing",
        24,
    )
    assert history_empty["type"] == "markdown"

    history_valid = await templates.get_history_graph_template(
        ["sensor.valid", "sensor.unknown"],
        "Valid",
        24,
        theme="modern",
    )
    assert history_valid["type"] == "history-graph"

    filtered = await templates._filter_valid_entities(["sensor.valid", "sensor.unknown", "sensor.none"])
    assert filtered == ["sensor.valid"]

    compact_layout = await templates.get_weather_dashboard_layout_template(
        "alpha",
        "Alpha",
        "Husky",
        theme="modern",
        layout="compact",
    )
    assert compact_layout["type"] == "vertical-stack"

    mobile_layout = await templates.get_weather_dashboard_layout_template(
        "alpha",
        "Alpha",
        "Husky",
        theme="modern",
        layout="mobile",
    )
    assert mobile_layout["type"] == "vertical-stack"

    full_layout = await templates.get_weather_dashboard_layout_template(
        "alpha",
        "Alpha",
        "Husky",
        theme="modern",
        layout="full",
    )
    assert full_layout["type"] == "vertical-stack"

    await templates.cleanup()
    assert templates.get_cache_stats()["cached_items"] >= 0
    snapshot = templates.get_cache_snapshot()
    assert "stats" in snapshot and "metadata" in snapshot


@pytest.mark.asyncio
async def test_dashboard_templates_branch_fillers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fill remaining branch gaps in dashboard template helpers."""
    states = {
        "sensor.oops_breed_weather_advice": _state(
            "ok",
            {"comfort_range": {"min": 5, "max": "oops"}},
        ),
        "sensor.badattrs_breed_weather_advice": SimpleNamespace(
            state="ok",
            attributes="invalid",
        ),
    }
    templates = dt.DashboardTemplates(_hass(states))

    async def _async_lookup(*_args: object, **_kwargs: object) -> tuple[dict[str, str], dict[str, str]]:
        return ({}, {})

    monkeypatch.setattr(dt, "async_get_component_translation_lookup", _async_lookup)
    monkeypatch.setattr(
        dt,
        "get_cached_component_translation_lookup",
        lambda *_args, **_kwargs: ({}, {}),
    )

    non_dict_template: dict[str, Any] = {"card_mod": "invalid"}
    ensured = templates._ensure_card_mod(non_dict_template, {"card_mod": {"style": "x"}})
    assert isinstance(ensured, dict)
    assert non_dict_template["card_mod"] == ensured

    assert templates._parse_int(object(), default=7) == 7
    assert templates._parse_bool(object()) is False
    assert templates._parse_last_notification({}) is None

    metrics_non_mapping, per_dog_non_mapping = templates._normalise_notifications_state(
        SimpleNamespace(attributes={"performance_metrics": {}, "per_dog": "invalid"}),
    )
    assert metrics_non_mapping["notifications_failed"] == 0
    assert per_dog_non_mapping == {}

    modules_minimal = {MODULE_HEALTH: True, MODULE_GPS: True}
    status_card = await templates._generate_dog_status_template(
        "branchdog",
        "Branch Dog",
        modules_minimal,
        theme="minimal",
    )
    assert any("device_tracker.branchdog_location" == entity for entity in status_card["entities"])

    no_module_buttons = await templates.get_action_buttons_template(
        "empty",
        {},
        theme="minimal",
        layout="cards",
    )
    assert no_module_buttons == []

    ignored_iterable = dt.DashboardTemplates._normalise_map_options(
        [
            ("unsupported", 1),
            (5, 2),
            ["bad"],
        ],
    )
    assert ignored_iterable["zoom"] == dt.DEFAULT_MAP_ZOOM

    odd_numeric = dt.DashboardTemplates._normalise_map_options(
        {
            "zoom": float("nan"),
            "default_zoom": " ",
            "hours_to_show": object(),
            "dark_mode": "maybe",
        },
    )
    assert odd_numeric["zoom"] == dt.DEFAULT_MAP_ZOOM
    assert "dark_mode" not in odd_numeric or odd_numeric["dark_mode"] in {True, False}

    stats_without_modules = await templates.get_statistics_card_template(
        "branchdog",
        "Branch Dog",
        {},
        theme="modern",
    )
    assert stats_without_modules["type"] == "markdown"

    monkeypatch.setattr(
        dt,
        "_translated_statistics_label",
        lambda _lookup, key: key,
    )
    monkeypatch.setattr(dt, "load_bundled_component_translations_fresh", lambda _lang: {})

    summary_branch = templates.get_statistics_summary_template(
        [{"dog_id": "branchdog", "dog_name": "Branch Dog", "modules": {}}],
        service_execution_metrics=cast(Any, 5),
        service_guard_metrics=cast(Any, 5),
    )
    assert summary_branch["type"] == "markdown"

    summary_guard_numbers = templates.get_statistics_summary_template(
        [{"dog_id": "branchdog", "dog_name": "Branch Dog", "modules": {}}],
        service_execution_metrics={"rejected_call_count": 1},
        service_guard_metrics={
            "executed": "bad",
            "skipped": True,
            "reasons": "invalid",
            "last_results": None,
        },
    )
    assert summary_guard_numbers["type"] == "markdown"

    odd_value = object()
    summary_guard_object_values = templates.get_statistics_summary_template(
        [{"dog_id": "branchdog", "dog_name": "Branch Dog", "modules": {}}],
        service_execution_metrics={"rejected_call_count": 0},
        service_guard_metrics={
            "executed": odd_value,
            "skipped": odd_value,
            "reasons": {"odd": odd_value},
            "last_results": None,
        },
    )
    assert summary_guard_object_values["type"] == "markdown"

    controls_minimal = await templates.get_feeding_controls_template("branchdog", theme="minimal")
    assert controls_minimal["type"] == "vertical-stack"

    status_full_modern = await templates.get_weather_status_card_template(
        "branchdog",
        "Branch Dog",
        theme="modern",
        compact=False,
    )
    assert status_full_modern["type"] == "entities"

    recommendations_minimal = await templates.get_weather_recommendations_card_template(
        "branchdog",
        "Branch Dog",
        theme="minimal",
        include_breed_specific=False,
    )
    assert recommendations_minimal["type"] == "markdown"

    advisory_missing_state = await templates.get_weather_breed_advisory_template(
        "missing",
        "Missing",
        "Unknown",
        theme="modern",
    )
    assert advisory_missing_state["type"] == "markdown"

    advisory_bad_attrs = await templates.get_weather_breed_advisory_template(
        "badattrs",
        "Bad Attrs",
        "Unknown",
        theme="minimal",
    )
    assert advisory_bad_attrs["type"] == "markdown"

    advisory_invalid_temperature = await templates.get_weather_breed_advisory_template(
        "oops",
        "Oops",
        "Unknown",
        theme="modern",
    )
    assert advisory_invalid_temperature["type"] == "markdown"
