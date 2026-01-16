from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.pawcontrol.dashboard_cards import (
    BaseCardGenerator,
    _resolve_dashboard_theme_option,
)
from custom_components.pawcontrol.dashboard_templates import DashboardTemplates
from custom_components.pawcontrol.types import (
    DashboardCardOptions,
    DashboardCardPerformanceStats,
)
from homeassistant.core import HomeAssistant


async def test_performance_stats_returns_copy(hass: HomeAssistant) -> None:
    """BaseCardGenerator should expose an immutable performance stats snapshot."""

    templates = MagicMock(spec=DashboardTemplates)
    generator = BaseCardGenerator(hass, templates)

    initial_stats = generator.performance_stats
    expected: DashboardCardPerformanceStats = {
        "validations_count": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "generation_time_total": 0.0,
        "errors_handled": 0,
    }
    assert initial_stats == expected

    # Mutating the returned mapping must not affect the generator internals.
    initial_stats["cache_hits"] = 5
    assert generator.performance_stats["cache_hits"] == 0


def test_resolve_dashboard_theme_option_defaults() -> None:
    """The helper should default to the modern dashboard theme when unset."""

    options: DashboardCardOptions = {}
    assert _resolve_dashboard_theme_option(options) == "modern"


def test_resolve_dashboard_theme_option_custom() -> None:
    """Custom themes should be preserved after whitespace normalisation."""

    options: DashboardCardOptions = {"theme": "  classic  "}
    assert _resolve_dashboard_theme_option(options) == "classic"


def test_resolve_dashboard_theme_option_rejects_invalid() -> None:
    """Non-string or blank themes should fall back to the default."""

    options: DashboardCardOptions = {"theme": ""}
    assert _resolve_dashboard_theme_option(options) == "modern"
