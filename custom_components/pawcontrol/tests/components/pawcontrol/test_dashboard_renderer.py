"""Tests for the dashboard renderer batching safeguards."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
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
