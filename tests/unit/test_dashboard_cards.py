from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant

from custom_components.pawcontrol.dashboard_cards import (
    BaseCardGenerator,
    _resolve_dashboard_theme_option,
)
from custom_components.pawcontrol.dashboard_templates import DashboardTemplates
from custom_components.pawcontrol.types import (
    DashboardCardOptions,
    DashboardCardPerformanceStats,
)


async def test_performance_stats_returns_copy(hass: HomeAssistant) -> None:
    """BaseCardGenerator should expose an immutable performance stats snapshot."""  # noqa: E111

    templates = MagicMock(spec=DashboardTemplates)  # noqa: E111
    generator = BaseCardGenerator(hass, templates)  # noqa: E111

    initial_stats = generator.performance_stats  # noqa: E111
    expected: DashboardCardPerformanceStats = {  # noqa: E111
        "validations_count": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "generation_time_total": 0.0,
        "errors_handled": 0,
    }
    assert initial_stats == expected  # noqa: E111

    # Mutating the returned mapping must not affect the generator internals.  # noqa: E114
    initial_stats["cache_hits"] = 5  # noqa: E111
    assert generator.performance_stats["cache_hits"] == 0  # noqa: E111


def test_resolve_dashboard_theme_option_defaults() -> None:
    """The helper should default to the modern dashboard theme when unset."""  # noqa: E111

    options: DashboardCardOptions = {}  # noqa: E111
    assert _resolve_dashboard_theme_option(options) == "modern"  # noqa: E111


def test_resolve_dashboard_theme_option_custom() -> None:
    """Custom themes should be preserved after whitespace normalisation."""  # noqa: E111

    options: DashboardCardOptions = {"theme": "  classic  "}  # noqa: E111
    assert _resolve_dashboard_theme_option(options) == "classic"  # noqa: E111


def test_resolve_dashboard_theme_option_rejects_invalid() -> None:
    """Non-string or blank themes should fall back to the default."""  # noqa: E111

    options: DashboardCardOptions = {"theme": ""}  # noqa: E111
    assert _resolve_dashboard_theme_option(options) == "modern"  # noqa: E111
