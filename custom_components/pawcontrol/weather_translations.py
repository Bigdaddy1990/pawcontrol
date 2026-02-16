"""Helpers for PawControl weather translations."""

import json
from pathlib import Path
from typing import Final, Literal, TypedDict

from homeassistant.core import HomeAssistant

from .translation_helpers import (
  async_get_component_translation_lookup,
  resolve_component_translation,
)


class WeatherAlertTranslation(TypedDict):
  """Localized strings for a specific weather alert."""  # noqa: E111

  title: str  # noqa: E111
  message: str  # noqa: E111


_WEATHER_ALERT_KEYS: Final = (
  "extreme_cold_warning",
  "extreme_heat_warning",
  "extreme_uv_warning",
  "high_cold_advisory",
  "high_heat_advisory",
  "high_humidity_alert",
  "high_uv_advisory",
  "snow_ice_alert",
  "storm_warning",
  "warm_weather_caution",
  "wet_weather_advisory",
)

WEATHER_ALERT_KEYS: Final = _WEATHER_ALERT_KEYS

# mypy does not support unpacking tuple constants into Literal parameters.
# Keep keys as string aliases and validate against runtime key sets below.
type WeatherAlertKey = str


type WeatherAlertTranslations = dict[WeatherAlertKey, WeatherAlertTranslation]


_WEATHER_RECOMMENDATION_KEYS: Final = (
  "avoid_peak_hours",
  "avoid_peak_uv",
  "avoid_until_passes",
  "breed_specific_caution",
  "check_toe_irritation",
  "cold_surface_protection",
  "comfort_anxious",
  "consider_clothing",
  "cool_ventilated_areas",
  "cooler_day_parts",
  "cooler_surfaces",
  "dry_paws_thoroughly",
  "ensure_shade",
  "essential_only",
  "extra_water",
  "good_air_circulation",
  "heart_avoid_strenuous",
  "keep_indoors",
  "keep_indoors_storm",
  "limit_outdoor_time",
  "limit_peak_exposure",
  "monitor_breathing",
  "monitor_overheating",
  "monitor_skin_irritation",
  "never_leave_in_car",
  "pet_sunscreen",
  "postpone_activities",
  "protect_nose_ears",
  "protect_paws",
  "protective_clothing",
  "provide_shade_always",
  "provide_traction",
  "provide_water",
  "puppy_extra_monitoring",
  "reduce_exercise_intensity",
  "respiratory_monitoring",
  "rinse_salt_chemicals",
  "secure_id_tags",
  "senior_extra_protection",
  "shade_during_activities",
  "shorten_activities",
  "use_cooling_aids",
  "use_paw_balm",
  "use_paw_protection",
  "uv_protective_clothing",
  "warm_shelter",
  "warm_shelter_available",
  "watch_heat_signs",
  "watch_heat_stress",
  "watch_hypothermia",
  "watch_ice_buildup",
  "waterproof_protection",
)

WEATHER_RECOMMENDATION_KEYS: Final = _WEATHER_RECOMMENDATION_KEYS

type WeatherRecommendationKey = str


type WeatherRecommendationTranslations = dict[WeatherRecommendationKey, str]


class WeatherTranslations(TypedDict):
  """Structured translation catalog for weather health guidance."""  # noqa: E111

  alerts: WeatherAlertTranslations  # noqa: E111
  recommendations: WeatherRecommendationTranslations  # noqa: E111


type LanguageCode = Literal["de", "en", "es", "fr"]


DEFAULT_LANGUAGE: Final[LanguageCode] = "en"

WEATHER_ALERT_KEY_SET: Final[frozenset[WeatherAlertKey]] = frozenset(
  _WEATHER_ALERT_KEYS,
)
WEATHER_RECOMMENDATION_KEY_SET: Final[frozenset[WeatherRecommendationKey]] = frozenset(
  _WEATHER_RECOMMENDATION_KEYS,
)

SUPPORTED_LANGUAGES: Final[frozenset[LanguageCode]] = frozenset(
  {"en", "de", "es", "fr"},
)


def _weather_alert_title_key(alert: WeatherAlertKey) -> str:
  """Return the translation key name for a weather alert title."""  # noqa: E111

  return f"weather_alert_{alert}_title"  # noqa: E111


def _weather_alert_message_key(alert: WeatherAlertKey) -> str:
  """Return the translation key name for a weather alert message."""  # noqa: E111

  return f"weather_alert_{alert}_message"  # noqa: E111


def _weather_recommendation_key(recommendation: WeatherRecommendationKey) -> str:
  """Return the translation key name for a recommendation string."""  # noqa: E111

  return f"weather_recommendation_{recommendation}"  # noqa: E111


def empty_weather_translations() -> WeatherTranslations:
  """Return an empty weather translations payload."""  # noqa: E111

  return {"alerts": {}, "recommendations": {}}  # noqa: E111


def _load_static_common_translations(language: str) -> dict[str, str]:
  """Load component ``common`` translations from packaged language files."""  # noqa: E111

  normalized_language = language.lower()  # noqa: E111
  translations_path = Path(__file__).resolve().parent / "translations"  # noqa: E111

  def _read_common(lang: str) -> dict[str, str]:  # noqa: E111
    file_path = translations_path / f"{lang}.json"
    if not file_path.exists():
      return {}  # noqa: E111
    try:
      data = json.loads(file_path.read_text(encoding="utf-8"))  # noqa: E111
    except OSError, ValueError:
      return {}  # noqa: E111
    common = data.get("common", {})
    return common if isinstance(common, dict) else {}

  fallback = _read_common(DEFAULT_LANGUAGE)  # noqa: E111
  localized = _read_common(normalized_language)  # noqa: E111
  return {**fallback, **localized}  # noqa: E111


def get_weather_translations(language: str) -> WeatherTranslations:
  """Return weather translations without requiring Home Assistant runtime APIs."""  # noqa: E111

  normalized_language = (  # noqa: E111
    language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
  )
  common = _load_static_common_translations(normalized_language)  # noqa: E111

  alerts: WeatherAlertTranslations = {  # noqa: E111
    alert_key: {
      "title": str(common.get(_weather_alert_title_key(alert_key), alert_key)),
      "message": str(common.get(_weather_alert_message_key(alert_key), alert_key)),
    }
    for alert_key in _WEATHER_ALERT_KEYS
  }

  recommendations: WeatherRecommendationTranslations = {  # noqa: E111
    recommendation_key: str(
      common.get(
        _weather_recommendation_key(recommendation_key),
        recommendation_key,
      )
    )
    for recommendation_key in _WEATHER_RECOMMENDATION_KEYS
  }

  return {"alerts": alerts, "recommendations": recommendations}  # noqa: E111


async def async_get_weather_translations(
  hass: HomeAssistant,
  language: str,
) -> WeatherTranslations:
  """Return weather translations for the requested language.

  Falls back to English when translations are unavailable.
  """  # noqa: E111

  translations, fallback = await async_get_component_translation_lookup(  # noqa: E111
    hass,
    language,
  )

  alerts: WeatherAlertTranslations = {  # noqa: E111
    alert_key: {
      "title": resolve_component_translation(
        translations,
        fallback,
        _weather_alert_title_key(alert_key),
        default=alert_key,
      ),
      "message": resolve_component_translation(
        translations,
        fallback,
        _weather_alert_message_key(alert_key),
        default=alert_key,
      ),
    }
    for alert_key in _WEATHER_ALERT_KEYS
  }

  recommendations: WeatherRecommendationTranslations = {  # noqa: E111
    recommendation_key: resolve_component_translation(
      translations,
      fallback,
      _weather_recommendation_key(recommendation_key),
      default=recommendation_key,
    )
    for recommendation_key in _WEATHER_RECOMMENDATION_KEYS
  }

  return {"alerts": alerts, "recommendations": recommendations}  # noqa: E111
