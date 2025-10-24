"""Tests for the dashboard renderer batching safeguards."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
)
from custom_components.pawcontrol.coordinator_tasks import default_rejection_metrics
from custom_components.pawcontrol.dashboard_renderer import DashboardRenderer


@pytest.mark.asyncio
async def test_render_dog_views_batch_returns_empty_for_no_dogs() -> None:
    """Ensure no views are generated when there are no dog configurations."""

    hass = MagicMock()
    hass.states = MagicMock()
    renderer = DashboardRenderer(hass)

    result = await renderer._render_dog_views_batch([], {})

    assert result == []


@pytest.mark.asyncio
async def test_render_dog_views_batch_enforces_minimum_batch_size(monkeypatch) -> None:
    """Ensure the renderer never calculates an invalid zero batch size."""

    hass = MagicMock()
    hass.states = MagicMock()
    renderer = DashboardRenderer(hass)

    monkeypatch.setattr(
        "custom_components.pawcontrol.dashboard_renderer.MAX_CARDS_PER_BATCH",
        5,
        raising=False,
    )

    renderer._render_single_dog_view = AsyncMock(
        return_value={"title": "Dog", "cards": []}
    )

    dogs = [{"dog_id": "doggo", "dog_name": "Doggo"}]

    result = await renderer._render_dog_views_batch(dogs, {})

    assert result == [{"title": "Dog", "cards": []}]
    renderer._render_single_dog_view.assert_awaited_once_with(dogs[0], 0, {})


@pytest.mark.asyncio
async def test_statistics_view_includes_resilience_metrics(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure the statistics view surfaces the resilience summary markdown."""

    renderer = DashboardRenderer(hass)

    monkeypatch.setattr(
        renderer,
        "_render_overview_view",
        AsyncMock(return_value={"path": "overview", "cards": []}),
    )
    monkeypatch.setattr(
        renderer,
        "_render_dog_views_batch",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        renderer,
        "_render_settings_view",
        AsyncMock(return_value={"path": "settings", "cards": []}),
    )

    monkeypatch.setattr(
        renderer.stats_generator,
        "_generate_activity_statistics",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        renderer.stats_generator,
        "_generate_feeding_statistics",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        renderer.stats_generator,
        "_generate_walk_statistics",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        renderer.stats_generator,
        "_generate_health_statistics",
        AsyncMock(return_value=None),
    )

    last_rejection = 1_700_000_000.0
    rejection_metrics = default_rejection_metrics()
    rejection_metrics.update(
        {
            "rejected_call_count": 3,
            "rejection_breaker_count": 2,
            "rejection_rate": 0.125,
            "last_rejection_time": last_rejection,
            "last_rejection_breaker_name": "api",
            "open_breaker_count": 1,
            "open_breakers": ["api"],
            "open_breaker_ids": ["api"],
            "rejection_breaker_ids": ["api"],
            "rejection_breakers": ["api"],
        }
    )
    coordinator_statistics = {"rejection_metrics": rejection_metrics}

    result = await renderer.render_main_dashboard(
        [
            {
                CONF_DOG_ID: "buddy",
                CONF_DOG_NAME: "Buddy",
                "modules": {MODULE_NOTIFICATIONS: True},
            }
        ],
        coordinator_statistics=coordinator_statistics,
    )

    statistics_view = next(
        view for view in result["views"] if view.get("path") == "statistics"
    )

    summary_card = next(
        card for card in statistics_view["cards"] if card.get("type") == "markdown"
    )

    content = summary_card["content"]
    iso_timestamp = datetime.fromtimestamp(last_rejection, tz=UTC).isoformat()

    assert "### Resilience metrics" in content
    assert "- Rejected calls: 3" in content
    assert "- Rejecting breakers: 2" in content
    assert "- Rejection rate: 12.50%" in content
    assert f"- Last rejection: {iso_timestamp}" in content
    assert "- Last rejecting breaker: api" in content
    assert "- Open breaker names: api" in content
    assert "- Open breaker IDs: api" in content
    assert "- Rejecting breaker names: api" in content
    assert "- Rejecting breaker IDs: api" in content


@pytest.mark.asyncio
async def test_render_dog_dashboard_localizes_visitor_cards(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure assembled visitor views retain localized card content."""

    hass.config.language = "de"
    renderer = DashboardRenderer(hass)

    validated_entities = [
        "switch.fido_visitor_mode",
        "binary_sensor.fido_visitor_mode",
    ]

    async def _fake_validate(
        entities: list[str], use_cache: bool = True
    ) -> list[str]:
        assert entities == validated_entities
        return validated_entities

    monkeypatch.setattr(
        renderer.module_generator,
        "_validate_entities_batch",
        _fake_validate,
    )

    dog_config = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        "modules": {MODULE_VISITOR: True},
    }

    dashboard = await renderer.render_dog_dashboard(dog_config)

    visitor_view = next(
        view for view in dashboard["views"] if view.get("path") == MODULE_VISITOR
    )

    assert visitor_view["title"] == "Visitors"

    visitor_cards = visitor_view["cards"]
    assert len(visitor_cards) == 2

    entities_card = visitor_cards[0]
    markdown_card = visitor_cards[1]

    assert entities_card["type"] == "entities"
    assert entities_card["title"] == "Steuerungen für den Besuchermodus"
    assert entities_card["entities"] == validated_entities

    assert markdown_card["type"] == "markdown"
    assert markdown_card["title"] == "Fido Besuchereinblicke"
    content = markdown_card["content"]
    assert "Status des Besuchermodus" in content
    assert "\"Ja\"" in content
    assert "\"Keine\"" in content
