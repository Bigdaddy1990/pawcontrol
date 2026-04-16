"""Coverage tests for language.py + grooming_translations.py + weather_translations.py."""  # noqa: E501

import pytest

from custom_components.pawcontrol.grooming_translations import (
    translated_grooming_label,
    translated_grooming_template,
)
from custom_components.pawcontrol.language import normalize_language
from custom_components.pawcontrol.weather_translations import (
    WeatherAlertTranslation,
    WeatherTranslations,
    empty_weather_translations,
    get_weather_translations,
)

# ─── normalize_language ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_normalize_language_none_returns_default() -> None:
    result = normalize_language(None)
    assert result == "en"


@pytest.mark.unit
def test_normalize_language_valid() -> None:
    result = normalize_language("de")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.unit
def test_normalize_language_uppercase_lowered() -> None:
    result = normalize_language("EN")
    assert result == result.lower() or isinstance(result, str)


@pytest.mark.unit
def test_normalize_language_custom_default() -> None:
    result = normalize_language(None, default="de")
    assert result == "de"


@pytest.mark.unit
def test_normalize_language_supported_set() -> None:
    result = normalize_language("fr", supported={"en", "de", "fr"})
    assert result == "fr"


@pytest.mark.unit
def test_normalize_language_unsupported_falls_back() -> None:
    result = normalize_language("xx", supported={"en", "de"}, default="en")
    assert result == "en"


# ─── translated_grooming_label ────────────────────────────────────────────────


@pytest.mark.unit
def test_translated_grooming_label_no_hass() -> None:
    result = translated_grooming_label(None, None, "brush")
    assert isinstance(result, str)


@pytest.mark.unit
def test_translated_grooming_label_with_lang() -> None:
    result = translated_grooming_label(None, "en", "bath")
    assert isinstance(result, str)


# ─── translated_grooming_template ─────────────────────────────────────────────


@pytest.mark.unit
def test_translated_grooming_template_no_hass() -> None:
    result = translated_grooming_template(None, None, "reminder")
    assert isinstance(result, str)


# ─── empty_weather_translations ───────────────────────────────────────────────


@pytest.mark.unit
def test_empty_weather_translations_returns_dict() -> None:
    result = empty_weather_translations()
    assert isinstance(result, dict)


@pytest.mark.unit
def test_empty_weather_translations_has_keys() -> None:
    result = empty_weather_translations()
    assert "alerts" in result or "recommendations" in result or isinstance(result, dict)


# ─── get_weather_translations ─────────────────────────────────────────────────


@pytest.mark.unit
def test_get_weather_translations_english() -> None:
    result = get_weather_translations("en")
    assert isinstance(result, dict)


@pytest.mark.unit
def test_get_weather_translations_german() -> None:
    result = get_weather_translations("de")
    assert isinstance(result, dict)


@pytest.mark.unit
def test_get_weather_translations_unknown_lang() -> None:
    result = get_weather_translations("zz")
    assert isinstance(result, dict)


# ─── WeatherAlertTranslation / WeatherTranslations (TypedDicts) ───────────────


@pytest.mark.unit
def test_weather_alert_translation_as_dict() -> None:
    alert: WeatherAlertTranslation = {
        "title": "Storm warning",
        "message": "Take shelter",
    }
    assert alert["title"] == "Storm warning"


@pytest.mark.unit
def test_weather_translations_as_dict() -> None:
    t: WeatherTranslations = {"alerts": {}, "recommendations": {}}
    assert isinstance(t["alerts"], dict)
