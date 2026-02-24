"""Unit tests for weather translation helper module."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
import pytest

from tests.weather_test_support import ensure_weather_module_compat

ensure_weather_module_compat()

from custom_components.pawcontrol import weather_translations


def _write_translation_fixture(
    tmp_path: Path,
    language: str,
    payload: str,
) -> None:
    """Create a translation file in a temporary module fixture tree."""
    translations_dir = tmp_path / "translations"
    translations_dir.mkdir(exist_ok=True)
    (translations_dir / f"{language}.json").write_text(payload, encoding="utf-8")


def test_empty_weather_translations_returns_empty_catalog() -> None:
    """The empty helper should return an alert/recommendation skeleton."""
    assert weather_translations.empty_weather_translations() == {
        "alerts": {},
        "recommendations": {},
    }


def test_get_weather_translations_uses_default_language_for_unknown_locale() -> None:
    """Unsupported locale codes should fall back to English strings."""
    english = weather_translations.get_weather_translations("en")
    unknown = weather_translations.get_weather_translations("xx")

    assert unknown == english


def test_load_static_common_translations_handles_invalid_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Malformed files or non-mapping common sections should resolve safely."""
    module_file = tmp_path / "weather_translations.py"
    module_file.write_text("# fixture module path", encoding="utf-8")

    _write_translation_fixture(
        tmp_path,
        "en",
        '{"common": {"weather_alert_storm_warning_title": "English Storm"}}',
    )
    _write_translation_fixture(tmp_path, "de", '{"common": "invalid"}')
    _write_translation_fixture(tmp_path, "fr", "{not-json")

    monkeypatch.setattr(weather_translations, "__file__", str(module_file))

    german_common = weather_translations._load_static_common_translations("DE")
    french_common = weather_translations._load_static_common_translations("fr")

    assert german_common["weather_alert_storm_warning_title"] == "English Storm"
    assert french_common["weather_alert_storm_warning_title"] == "English Storm"


@pytest.mark.asyncio
async def test_async_get_weather_translations_uses_lookup_and_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The async API should resolve every key via translation helper lookups."""
    captured: list[tuple[str, str]] = []

    async def _fake_lookup(
        hass: HomeAssistant,
        language: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        assert language == "de"
        assert isinstance(hass, HomeAssistant)
        return ({"common": {}}, {"common": {}})

    def _fake_resolve(
        translations: dict[str, Any],
        fallback: dict[str, Any],
        key: str,
        *,
        default: str,
    ) -> str:
        del translations, fallback
        captured.append((key, default))
        return f"resolved:{key}"

    monkeypatch.setattr(
        weather_translations,
        "async_get_component_translation_lookup",
        _fake_lookup,
    )
    monkeypatch.setattr(
        weather_translations,
        "resolve_component_translation",
        _fake_resolve,
    )

    catalog = await weather_translations.async_get_weather_translations(
        MagicMock(spec=HomeAssistant),
        "de",
    )

    first_alert = weather_translations.WEATHER_ALERT_KEYS[0]
    first_recommendation = weather_translations.WEATHER_RECOMMENDATION_KEYS[0]
    assert catalog["alerts"][first_alert]["title"] == (
        f"resolved:weather_alert_{first_alert}_title"
    )
    assert catalog["alerts"][first_alert]["message"] == (
        f"resolved:weather_alert_{first_alert}_message"
    )
    assert catalog["recommendations"][first_recommendation] == (
        f"resolved:weather_recommendation_{first_recommendation}"
    )

    assert (
        f"weather_alert_{first_alert}_title",
        first_alert,
    ) in captured
    assert (
        f"weather_alert_{first_alert}_message",
        first_alert,
    ) in captured
    assert (
        f"weather_recommendation_{first_recommendation}",
        first_recommendation,
    ) in captured
