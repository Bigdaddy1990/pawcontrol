import asyncio
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
import pytest

from custom_components.pawcontrol import dashboard_cards
from custom_components.pawcontrol.dashboard_cards import (
    BaseCardGenerator,
    _resolve_dashboard_theme_option,
    _translated_health_label,
    _translated_health_template,
    _translated_quick_action_label,
    _translated_visitor_label,
    _translated_visitor_template,
    _translated_visitor_value,
    _translated_walk_label,
    _translated_walk_template,
    cleanup_validation_cache,
    get_global_performance_stats,
)
from custom_components.pawcontrol.dashboard_templates import DashboardTemplates
from custom_components.pawcontrol.types import (
    DashboardCardOptions,
    DashboardCardPerformanceStats,
)


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


@pytest.mark.parametrize(
    ("func", "key", "expected_de", "expected_fallback"),
    [
        (
            _translated_health_label,
            "health_status",
            "Gesundheitsstatus",
            "Health Status",
        ),
        (
            _translated_visitor_label,
            "entities_title",
            "Steuerungen für den Besuchermodus",
            "Visitor mode controls",
        ),
        (_translated_visitor_value, "yes", "Ja", "Yes"),
        (_translated_quick_action_label, "feed_all", "Alle füttern", "Feed All"),
        (_translated_walk_label, "start", "Spaziergang starten", "Start Walk"),
    ],
)
def test_translation_label_helpers_support_language_and_english_fallback(
    func: object,
    key: str,
    expected_de: str,
    expected_fallback: str,
) -> None:
    """Label translation helpers should localise and then fall back to English."""
    assert func("de", key) == expected_de
    assert func("fr", key) == expected_fallback


def test_translation_helpers_return_input_for_unknown_keys() -> None:
    """Unknown labels and values should be returned unchanged."""
    assert _translated_health_label("de", "unknown_key") == "unknown_key"
    assert _translated_visitor_label("de", "unknown_key") == "unknown_key"
    assert _translated_visitor_value("de", "unknown_value") == "unknown_value"
    assert _translated_quick_action_label("de", "unknown_action") == "unknown_action"
    assert _translated_walk_label("de", "unknown_walk") == "unknown_walk"


def test_translated_templates_are_localized_and_formatted() -> None:
    """Template translation helpers should localize and format placeholders."""
    assert (
        _translated_health_template("de", "weight_history_title", days="30")
        == "Gewichtsverlauf (30 Tage)"
    )
    assert (
        _translated_visitor_template("de", "insights_title", dog_name="Bello")
        == "Bello Besuchereinblicke"
    )
    assert (
        _translated_walk_template("de", "history_title", days=7)
        == "Spazierverlauf (7 Tage)"
    )


def test_translated_templates_fall_back_to_english_and_unknown_template_format() -> (
    None
):
    """Template helpers should fall back to English and format unknown templates."""
    assert (
        _translated_health_template("fr", "weight_history_title", days="14")
        == "Weight Tracking (14 days)"
    )
    assert (
        _translated_visitor_template("fr", "insights_title", dog_name="Luna")
        == "Luna visitor insights"
    )
    assert (
        _translated_walk_template("fr", "statistics_title", days=30)
        == "Walk Statistics (30 days)"
    )

    assert _translated_health_template(None, "Hello {name}", name="Paw") == "Hello Paw"
    assert _translated_visitor_template(None, "Hi {name}", name="Paw") == "Hi Paw"
    assert _translated_walk_template(None, "Walk in {city}", city="Berlin") == (
        "Walk in Berlin"
    )


@pytest.mark.asyncio
async def test_cleanup_validation_cache_removes_only_expired_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Global cache cleanup should remove entries older than the threshold."""
    monkeypatch.setattr(
        dashboard_cards,
        "_entity_validation_cache",
        {
            "sensor.expired": (1.0, True),
            "sensor.active": (300.0, False),
        },
    )

    class _FakeLoop:
        def time(self) -> float:
            return 400.0

    monkeypatch.setattr(asyncio, "get_running_loop", lambda: _FakeLoop())
    monkeypatch.setattr(dashboard_cards, "_cache_cleanup_threshold", 100)

    await cleanup_validation_cache()

    assert "sensor.expired" not in dashboard_cards._entity_validation_cache
    assert dashboard_cards._entity_validation_cache["sensor.active"] == (300.0, False)


def test_get_global_performance_stats_returns_current_cache_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Global stats should include runtime cache shape and static thresholds."""
    monkeypatch.setattr(
        dashboard_cards,
        "_entity_validation_cache",
        {"sensor.one": (1.0, True), "sensor.two": (2.0, False)},
    )

    stats = get_global_performance_stats()

    assert stats["validation_cache_size"] == 2
    assert stats["cache_threshold"] == float(dashboard_cards._cache_cleanup_threshold)
    assert (
        stats["max_concurrent_validations"]
        == dashboard_cards.MAX_CONCURRENT_VALIDATIONS
    )
    assert stats["validation_timeout"] == dashboard_cards.ENTITY_VALIDATION_TIMEOUT
    assert stats["card_generation_timeout"] == dashboard_cards.CARD_GENERATION_TIMEOUT
