"""Weather integration for PawControl health warnings.

Provides weather-based health warnings and recommendations for dogs based on
current and forecasted weather conditions.

Quality Scale: Platinum target
Home Assistant: 2025.9.4+
Python: 3.13+
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
from typing import Any, Final, Literal, NamedTuple, TypedDict, TypeGuard, TypeVar, cast

from homeassistant.components.weather import (
  ATTR_FORECAST,
  ATTR_FORECAST_CONDITION,
  ATTR_FORECAST_HUMIDITY,
  ATTR_FORECAST_PRECIPITATION,
  ATTR_FORECAST_PRECIPITATION_PROBABILITY,
  ATTR_FORECAST_PRESSURE,
  ATTR_FORECAST_TEMP,
  ATTR_FORECAST_TEMP_LOW,
  ATTR_FORECAST_TIME,
  ATTR_FORECAST_UV_INDEX,
  ATTR_FORECAST_WIND_SPEED,
  ATTR_WEATHER_HUMIDITY,
  ATTR_WEATHER_PRESSURE,
  ATTR_WEATHER_TEMPERATURE,
  ATTR_WEATHER_UV_INDEX,
  ATTR_WEATHER_VISIBILITY,
  ATTR_WEATHER_WIND_SPEED,
  DOMAIN as WEATHER_DOMAIN,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .resilience import ResilienceManager, RetryConfig
from .weather_translations import (
  DEFAULT_LANGUAGE,
  SUPPORTED_LANGUAGES,
  WEATHER_ALERT_KEY_SET,
  WEATHER_RECOMMENDATION_KEY_SET,
  WeatherAlertKey,
  WeatherAlertTranslations,
  WeatherRecommendationKey,
  WeatherRecommendationTranslations,
  WeatherTranslations,
  async_get_weather_translations,  # noqa: F401
  empty_weather_translations,
  get_weather_translations as _get_weather_translations,
)


class ForecastEntry(TypedDict, total=False):
  """Raw weather forecast entry provided by Home Assistant."""  # noqa: E111

  datetime: datetime | str  # noqa: E111
  temperature: float | int  # noqa: E111
  templow: float | int  # noqa: E111
  temperature_unit: UnitOfTemperature | str  # noqa: E111
  condition: str  # noqa: E111
  humidity: float | int  # noqa: E111
  uv_index: float | int  # noqa: E111
  wind_speed: float | int  # noqa: E111
  pressure: float | int  # noqa: E111
  precipitation: float | int  # noqa: E111
  precipitation_probability: float | int  # noqa: E111


class WeatherEntityAttributes(TypedDict, total=False):
  """Subset of weather entity attributes consumed by the manager."""  # noqa: E111

  temperature: float | int  # noqa: E111
  humidity: float | int  # noqa: E111
  uv_index: float | int  # noqa: E111
  wind_speed: float | int  # noqa: E111
  pressure: float | int  # noqa: E111
  visibility: float | int  # noqa: E111
  temperature_unit: UnitOfTemperature | str  # noqa: E111
  forecast: Sequence[ForecastEntry]  # noqa: E111


type ForecastEntries = Sequence[ForecastEntry]
type AlertField = Literal["title", "message"]
type ActivityType = Literal["walk", "play", "exercise", "basic_needs"]
type ActivityThresholdMap = dict[ActivityType, int]
type AlertTranslationParts = tuple[
  Literal["alerts"],
  WeatherAlertKey,
  AlertField,
]
type RecommendationTranslationParts = tuple[
  Literal["recommendations"],
  WeatherRecommendationKey,
]
type WeatherTranslationParts = AlertTranslationParts | RecommendationTranslationParts

TRANSLATION_PREFIX: Final[str] = "weather"
ALERT_FIELD_TOKENS: Final[frozenset[AlertField]] = frozenset(("title", "message"))
PRIMARY_ACTIVITIES: Final[
  tuple[Literal["walk"], Literal["play"], Literal["exercise"]]
] = ("walk", "play", "exercise")


def _is_alert_field(value: str) -> TypeGuard[AlertField]:
  """Return whether ``value`` is a valid alert translation field token."""  # noqa: E111

  return value in ALERT_FIELD_TOKENS  # noqa: E111


def _is_weather_alert_key(value: str) -> TypeGuard[WeatherAlertKey]:
  """Return whether ``value`` is a known weather alert translation key."""  # noqa: E111

  return value in WEATHER_ALERT_KEY_SET  # noqa: E111


def _is_weather_recommendation_key(value: str) -> TypeGuard[WeatherRecommendationKey]:
  """Return whether ``value`` is a known weather recommendation key."""  # noqa: E111

  return value in WEATHER_RECOMMENDATION_KEY_SET  # noqa: E111


_LOGGER = logging.getLogger(__name__)


def get_weather_translations(language: str) -> WeatherTranslations:
  """Backward-compatible wrapper for weather translation loading."""  # noqa: E111

  return _get_weather_translations(language)  # noqa: E111


class WeatherSeverity(Enum):
  """Weather condition severity levels for dog health."""  # noqa: E111

  LOW = "low"  # noqa: E111
  MODERATE = "moderate"  # noqa: E111
  HIGH = "high"  # noqa: E111
  EXTREME = "extreme"  # noqa: E111


T = TypeVar("T")


type SeverityMap[T] = dict[WeatherSeverity, T]
type TemperatureBand = Literal["hot", "cold"]
type TemperatureThresholdMap = dict[TemperatureBand, SeverityMap[float]]


class WeatherHealthImpact(Enum):
  """Types of health impacts from weather conditions."""  # noqa: E111

  HEAT_STRESS = "heat_stress"  # noqa: E111
  COLD_STRESS = "cold_stress"  # noqa: E111
  UV_EXPOSURE = "uv_exposure"  # noqa: E111
  AIR_QUALITY = "air_quality"  # noqa: E111
  EXERCISE_LIMITATION = "exercise_limitation"  # noqa: E111
  HYDRATION_RISK = "hydration_risk"  # noqa: E111
  PAW_PROTECTION = "paw_protection"  # noqa: E111
  RESPIRATORY_RISK = "respiratory_risk"  # noqa: E111


class ForecastQuality(Enum):
  """Quality indicators for weather forecast data."""  # noqa: E111

  EXCELLENT = "excellent"  # <6h old, high confidence  # noqa: E111
  GOOD = "good"  # <12h old, medium confidence  # noqa: E111
  FAIR = "fair"  # <24h old, basic data  # noqa: E111
  POOR = "poor"  # >24h old or incomplete  # noqa: E111


class ActivityTimeSlot(NamedTuple):
  """Optimal activity time slot with health score."""  # noqa: E111

  start_time: datetime  # noqa: E111
  end_time: datetime  # noqa: E111
  health_score: int  # noqa: E111
  activity_type: ActivityType  # noqa: E111
  recommendations: list[str]  # noqa: E111
  alert_level: WeatherSeverity  # noqa: E111


@dataclass
class ForecastPoint:
  """Single forecast data point for weather prediction."""  # noqa: E111

  timestamp: datetime  # noqa: E111
  temperature_c: float | None = None  # noqa: E111
  temperature_low_c: float | None = None  # noqa: E111
  humidity_percent: float | None = None  # noqa: E111
  uv_index: float | None = None  # noqa: E111
  wind_speed_kmh: float | None = None  # noqa: E111
  pressure_hpa: float | None = None  # noqa: E111
  precipitation_mm: float | None = None  # noqa: E111
  precipitation_probability: int | None = None  # noqa: E111
  condition: str | None = None  # noqa: E111

  # Calculated health metrics  # noqa: E114
  health_score: int | None = None  # noqa: E111
  heat_index: float | None = None  # noqa: E111
  wind_chill: float | None = None  # noqa: E111
  predicted_alerts: list[WeatherHealthImpact] = field(default_factory=list)  # noqa: E111

  @property  # noqa: E111
  def is_daytime(self) -> bool:  # noqa: E111
    """Check if forecast point is during daytime hours."""
    hour = self.timestamp.hour
    return 6 <= hour <= 19

  @property  # noqa: E111
  def time_category(self) -> str:  # noqa: E111
    """Get time category for display purposes."""
    hour = self.timestamp.hour
    if 6 <= hour < 12:
      return "morning"  # noqa: E111
    if 12 <= hour < 17:
      return "afternoon"  # noqa: E111
    if 17 <= hour < 21:
      return "evening"  # noqa: E111
    return "night"


@dataclass
class WeatherForecast:
  """Comprehensive weather forecast with health analysis."""  # noqa: E111

  forecast_points: list[ForecastPoint] = field(default_factory=list)  # noqa: E111
  source_entity: str | None = None  # noqa: E111
  generated_at: datetime = field(default_factory=dt_util.utcnow)  # noqa: E111
  forecast_horizon_hours: int = 24  # noqa: E111
  quality: ForecastQuality = ForecastQuality.FAIR  # noqa: E111

  # Summary statistics  # noqa: E114
  min_health_score: int | None = None  # noqa: E111
  max_health_score: int | None = None  # noqa: E111
  avg_health_score: int | None = None  # noqa: E111
  critical_periods: list[tuple[datetime, datetime]] = field(default_factory=list)  # noqa: E111
  optimal_activity_windows: list[ActivityTimeSlot] = field(  # noqa: E111
    default_factory=list,
  )

  @property  # noqa: E111
  def is_valid(self) -> bool:  # noqa: E111
    """Check if forecast data is valid and recent."""
    if not self.forecast_points:
      return False  # noqa: E111

    # Forecast should be less than 6 hours old for excellent quality
    age_hours = (dt_util.utcnow() - self.generated_at).total_seconds() / 3600
    return age_hours < 24  # Accept up to 24h old forecast

  @property  # noqa: E111
  def forecast_summary(self) -> str:  # noqa: E111
    """Get human-readable forecast summary."""
    if not self.forecast_points:
      return "No forecast data available"  # noqa: E111

    if self.avg_health_score is None:
      return "Forecast data incomplete"  # noqa: E111

    score = self.avg_health_score
    if score >= 80:
      return f"Excellent conditions ahead (avg score: {score}/100)"  # noqa: E111
    if score >= 60:
      return f"Good conditions with some caution needed (avg score: {score}/100)"  # noqa: E111
    if score >= 40:
      return f"Challenging conditions requiring precautions (avg score: {score}/100)"  # noqa: E111
    return f"Dangerous conditions - outdoor activities not recommended (avg score: {score}/100)"  # noqa: E501

  def get_next_optimal_window(  # noqa: E111
    self,
    activity_type: ActivityType = "walk",
  ) -> ActivityTimeSlot | None:
    """Get the next optimal time window for specified activity."""
    for window in self.optimal_activity_windows:
      if window.activity_type == activity_type and window.start_time > dt_util.utcnow():  # noqa: E111
        return window
    return None

  def get_worst_period(self) -> tuple[datetime, datetime] | None:  # noqa: E111
    """Get the time period with worst weather conditions."""
    if not self.critical_periods:
      return None  # noqa: E111
    return self.critical_periods[0]  # First (most severe) critical period


@dataclass(slots=True)
class ScoreRangeSummary:
  """Range of forecast health scores for planning."""  # noqa: E111

  min: int | None  # noqa: E111
  max: int | None  # noqa: E111


@dataclass(slots=True)
class CriticalPeriodSummary:
  """Summary of critical forecast periods."""  # noqa: E111

  start: str  # noqa: E111
  end: str  # noqa: E111
  duration_hours: float  # noqa: E111


@dataclass(slots=True)
class OptimalWindowSummary:
  """Summary of optimal activity windows."""  # noqa: E111

  activity: ActivityType  # noqa: E111
  start: str  # noqa: E111
  end: str  # noqa: E111
  health_score: int  # noqa: E111
  alert_level: WeatherSeverity  # noqa: E111
  recommendations: list[str]  # noqa: E111


@dataclass(slots=True)
class ActivityWindowSummary:
  """Summary for the next recommended activity window."""  # noqa: E111

  start: str  # noqa: E111
  health_score: int  # noqa: E111
  alert_level: WeatherSeverity  # noqa: E111


@dataclass(slots=True)
class WorstPeriodSummary:
  """Summary of the worst forecast period."""  # noqa: E111

  start: str  # noqa: E111
  end: str  # noqa: E111
  advice: str  # noqa: E111


@dataclass(slots=True)
class ForecastPlanningSummary:
  """Typed representation of forecast planning guidance."""  # noqa: E111

  status: Literal["available", "unavailable"]  # noqa: E111
  message: str | None = None  # noqa: E111
  forecast_quality: str | None = None  # noqa: E111
  forecast_summary: str | None = None  # noqa: E111
  avg_health_score: int | None = None  # noqa: E111
  score_range: ScoreRangeSummary | None = None  # noqa: E111
  critical_periods: list[CriticalPeriodSummary] = field(default_factory=list)  # noqa: E111
  optimal_windows: list[OptimalWindowSummary] = field(default_factory=list)  # noqa: E111
  next_walk_time: ActivityWindowSummary | None = None  # noqa: E111
  next_play_time: ActivityWindowSummary | None = None  # noqa: E111
  next_exercise_time: ActivityWindowSummary | None = None  # noqa: E111
  worst_period: WorstPeriodSummary | None = None  # noqa: E111


@dataclass
class WeatherAlert:
  """Weather-based health alert for dogs."""  # noqa: E111

  alert_type: WeatherHealthImpact  # noqa: E111
  severity: WeatherSeverity  # noqa: E111
  title: str  # noqa: E111
  message: str  # noqa: E111
  recommendations: list[str] = field(default_factory=list)  # noqa: E111
  duration_hours: int | None = None  # noqa: E111
  affected_breeds: list[str] = field(default_factory=list)  # noqa: E111
  age_considerations: list[str] = field(default_factory=list)  # noqa: E111
  timestamp: datetime = field(default_factory=dt_util.utcnow)  # noqa: E111

  @property  # noqa: E111
  def is_active(self) -> bool:  # noqa: E111
    """Check if alert is still active based on duration."""
    if self.duration_hours is None:
      return True  # noqa: E111

    elapsed = (dt_util.utcnow() - self.timestamp).total_seconds() / 3600
    return elapsed < self.duration_hours


@dataclass
class WeatherConditions:
  """Current weather conditions relevant to dog health."""  # noqa: E111

  temperature_c: float | None = None  # noqa: E111
  humidity_percent: float | None = None  # noqa: E111
  uv_index: float | None = None  # noqa: E111
  wind_speed_kmh: float | None = None  # noqa: E111
  pressure_hpa: float | None = None  # noqa: E111
  visibility_km: float | None = None  # noqa: E111
  condition: str | None = None  # noqa: E111

  # Calculated values  # noqa: E114
  heat_index: float | None = None  # noqa: E111
  wind_chill: float | None = None  # noqa: E111
  air_quality_index: int | None = None  # noqa: E111

  # Metadata  # noqa: E114
  source_entity: str | None = None  # noqa: E111
  last_updated: datetime = field(default_factory=dt_util.utcnow)  # noqa: E111

  @property  # noqa: E111
  def is_valid(self) -> bool:  # noqa: E111
    """Check if weather data is valid and recent."""
    if self.temperature_c is None:
      return False  # noqa: E111

    # Data should be less than 2 hours old
    age_hours = (dt_util.utcnow() - self.last_updated).total_seconds() / 3600
    return age_hours < 2


class WeatherHealthManager:
  """Manages weather-based health warnings for dogs."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    hass: HomeAssistant,
    resilience_manager: ResilienceManager | None = None,
  ) -> None:
    """Initialize weather health manager.

    Args:
        hass: Home Assistant instance
        resilience_manager: Optional ResilienceManager for fault tolerance
    """
    self.hass = hass
    self._current_conditions: WeatherConditions | None = None
    self._active_alerts: list[WeatherAlert] = []
    self._translations: WeatherTranslations = empty_weather_translations()
    self._english_translations: WeatherTranslations = self._translations
    self._current_forecast: WeatherForecast | None = None

    # RESILIENCE: Fault tolerance for weather API calls
    self.resilience_manager = resilience_manager
    self._retry_config = RetryConfig(
      max_attempts=2,  # Limited retries for weather data
      initial_delay=2.0,
      max_delay=5.0,
      exponential_base=1.5,
      jitter=True,
    )

    # Temperature thresholds for different severity levels (Celsius)
    self.temperature_thresholds: TemperatureThresholdMap = {
      "hot": {
        WeatherSeverity.MODERATE: 25.0,
        WeatherSeverity.HIGH: 30.0,
        WeatherSeverity.EXTREME: 35.0,
      },
      "cold": {
        WeatherSeverity.MODERATE: 5.0,
        WeatherSeverity.HIGH: 0.0,
        WeatherSeverity.EXTREME: -10.0,
      },
    }

    # UV Index thresholds
    self.uv_thresholds: SeverityMap[float] = {
      WeatherSeverity.MODERATE: 6.0,
      WeatherSeverity.HIGH: 8.0,
      WeatherSeverity.EXTREME: 11.0,
    }

    # Humidity thresholds (%)
    self.humidity_thresholds: SeverityMap[float] = {
      WeatherSeverity.MODERATE: 70.0,
      WeatherSeverity.HIGH: 85.0,
      WeatherSeverity.EXTREME: 95.0,
    }

  async def async_load_translations(self, language: str = "en") -> None:  # noqa: E111
    """Load translations for weather alerts and recommendations.

    Args:
        language: Language code (e.g., 'en', 'de')
    """
    try:
      if language not in SUPPORTED_LANGUAGES:  # noqa: E111
        _LOGGER.debug(
          "Weather translations for %s not available, using English fallback",
          language,
        )
      self._translations = get_weather_translations(language)  # noqa: E111
      if language == DEFAULT_LANGUAGE:  # noqa: E111
        self._english_translations = self._translations
      else:  # noqa: E111
        self._english_translations = get_weather_translations(DEFAULT_LANGUAGE)
      _LOGGER.debug(  # noqa: E111
        "Loaded weather translations for language: %s",
        language,
      )
    except Exception as err:  # pragma: no cover - defensive fallback
      _LOGGER.warning("Failed to load weather translations: %s", err)  # noqa: E111
      self._translations = empty_weather_translations()  # noqa: E111
      self._english_translations = self._translations  # noqa: E111

  @staticmethod  # noqa: E111
  def _parse_translation_key(key: str) -> WeatherTranslationParts | None:  # noqa: E111
    """Normalise dotted translation keys into typed translation segments."""

    segments = tuple(part for part in key.split(".") if part)
    if segments and segments[0] == TRANSLATION_PREFIX:
      segments = segments[1:]  # noqa: E111

    if not segments:
      return None  # noqa: E111

    section = segments[0]
    if section == "alerts":
      if len(segments) != 3:  # noqa: E111
        return None
      alert_key, field_token = segments[1], segments[2]  # noqa: E111
      if not _is_weather_alert_key(alert_key) or not _is_alert_field(field_token):  # noqa: E111
        return None
      return ("alerts", alert_key, field_token)  # noqa: E111

    if section == "recommendations":
      if len(segments) != 2:  # noqa: E111
        return None
      recommendation_key = segments[1]  # noqa: E111
      if not _is_weather_recommendation_key(recommendation_key):  # noqa: E111
        return None
      return ("recommendations", recommendation_key)  # noqa: E111

    return None

  def _get_translation(self, key: str, **kwargs: Any) -> str:  # noqa: E111
    """Get translated string with variable substitution.

    Args:
        key: Translation key (e.g., 'weather.alerts.extreme_heat_warning.title')
        **kwargs: Variables for string formatting

    Returns:
        Translated string or fallback English text
    """

    parts = self._parse_translation_key(key)
    if parts is None:
      return key  # noqa: E111

    try:
      resolved = self._resolve_translation_value(  # noqa: E111
        self._translations,
        parts,
      )
    except ValueError as err:
      _LOGGER.debug("Translation key not found: %s (%s)", key, err)  # noqa: E111
      resolved = None  # noqa: E111

    if resolved is not None:
      if not kwargs:  # noqa: E111
        return resolved
      try:  # noqa: E111
        return resolved.format(**kwargs)
      except (KeyError, ValueError) as err:  # noqa: E111
        _LOGGER.debug(
          "Translation formatting failed for %s: %s",
          key,
          err,
        )

    return self._get_english_fallback(parts, key, **kwargs)

  def _get_english_fallback(  # noqa: E111
    self,
    parts: WeatherTranslationParts,
    original_key: str,
    **kwargs: Any,
  ) -> str:
    """Get English fallback text for translation keys."""

    try:
      resolved = self._resolve_translation_value(  # noqa: E111
        self._english_translations,
        parts,
      )
    except ValueError:
      resolved = None  # noqa: E111

    if resolved is None:
      return original_key  # noqa: E111

    try:
      return resolved.format(**kwargs) if kwargs else resolved  # noqa: E111
    except KeyError, ValueError:
      return resolved  # noqa: E111

  @staticmethod  # noqa: E111
  def _resolve_translation_value(  # noqa: E111
    catalog: WeatherTranslations,
    parts: WeatherTranslationParts,
  ) -> str | None:
    """Resolve a nested translation value from the provided catalog."""

    section = parts[0]
    if section == "alerts":
      alert_parts = cast(AlertTranslationParts, parts)  # noqa: E111
      _, alert_key, field = alert_parts  # noqa: E111
      return WeatherHealthManager._resolve_alert_translation(  # noqa: E111
        catalog["alerts"],
        alert_key,
        field,
      )

    if section == "recommendations":
      recommendation_parts = cast(RecommendationTranslationParts, parts)  # noqa: E111
      _, recommendation_key = recommendation_parts  # noqa: E111
      return WeatherHealthManager._resolve_recommendation_translation(  # noqa: E111
        catalog["recommendations"],
        recommendation_key,
      )

    raise ValueError(f"Unknown weather translation section: {section}")

  @staticmethod  # noqa: E111
  def _resolve_alert_translation(  # noqa: E111
    alerts: WeatherAlertTranslations,
    alert_key: WeatherAlertKey,
    field: AlertField,
  ) -> str | None:
    """Resolve an alert translation field from the alerts catalog."""

    if alert_key not in alerts:
      return None  # noqa: E111

    alert = alerts[alert_key]
    if field not in ALERT_FIELD_TOKENS:
      raise ValueError(f"Unsupported alert translation field: {field}")  # noqa: E111

    value = cast(object, alert.get(field))
    return value if isinstance(value, str) else None

  @staticmethod  # noqa: E111
  def _resolve_recommendation_translation(  # noqa: E111
    recommendations: WeatherRecommendationTranslations,
    recommendation_key: WeatherRecommendationKey,
  ) -> str | None:
    """Resolve a recommendation translation string from the catalog."""

    if recommendation_key not in recommendations:
      return None  # noqa: E111

    value = cast(object, recommendations[recommendation_key])
    return value if isinstance(value, str) else None

  @staticmethod  # noqa: E111
  def _coerce_float(value: object) -> float | None:  # noqa: E111
    """Convert integers or floats to float, rejecting bools and others."""

    if isinstance(value, bool):
      return None  # noqa: E111
    if isinstance(value, int | float):
      return float(value)  # noqa: E111
    return None

  @staticmethod  # noqa: E111
  def _coerce_int(value: object) -> int | None:  # noqa: E111
    """Convert numeric values to integers for probability fields."""

    if isinstance(value, bool):
      return None  # noqa: E111
    if isinstance(value, int):
      return value  # noqa: E111
    if isinstance(value, float):
      return int(value)  # noqa: E111
    return None

  async def async_update_weather_data(  # noqa: E111
    self,
    weather_entity_id: str | None = None,
  ) -> WeatherConditions | None:
    """Update weather data from Home Assistant weather entity with resilience.

    Uses retry logic for transient failures when fetching weather data.

    Args:
        weather_entity_id: Weather entity ID, if None will try to find one

    Returns:
        Updated weather conditions or None if unavailable
    """

    async def _fetch_weather_data() -> WeatherConditions | None:
      """Internal fetch function wrapped by resilience manager."""  # noqa: E111
      # Load translations if not already loaded  # noqa: E114
      if not self._translations:  # noqa: E111
        await self.async_load_translations()

      # Find weather entity if not specified  # noqa: E114
      weather_entity_id_local = weather_entity_id  # noqa: E111
      if weather_entity_id_local is None:  # noqa: E111
        weather_entity_id_local = await self._find_weather_entity()

      if weather_entity_id_local is None:  # noqa: E111
        _LOGGER.warning(
          "No weather entity found for weather health monitoring",
        )
        return None

      # Get weather state  # noqa: E114
      weather_state = self.hass.states.get(weather_entity_id_local)  # noqa: E111
      if not weather_state or weather_state.state in [  # noqa: E111
        STATE_UNAVAILABLE,
        STATE_UNKNOWN,
      ]:
        _LOGGER.warning(
          "Weather entity %s is unavailable",
          weather_entity_id,
        )
        return None

      # Extract weather data  # noqa: E114
      attributes = cast(  # noqa: E111
        WeatherEntityAttributes,
        weather_state.attributes,
      )

      temperature_c = self._coerce_float(  # noqa: E111
        attributes.get(ATTR_WEATHER_TEMPERATURE),
      )
      if temperature_c is not None:  # noqa: E111
        # Convert temperature to Celsius if needed
        temp_unit = attributes.get(
          "temperature_unit",
          UnitOfTemperature.CELSIUS,
        )
        if temp_unit == UnitOfTemperature.FAHRENHEIT:
          temperature_c = (temperature_c - 32) * 5 / 9  # noqa: E111
        elif temp_unit == UnitOfTemperature.KELVIN:
          temperature_c = temperature_c - 273.15  # noqa: E111

      self._current_conditions = WeatherConditions(  # noqa: E111
        temperature_c=temperature_c,
        humidity_percent=self._coerce_float(
          attributes.get(ATTR_WEATHER_HUMIDITY),
        ),
        uv_index=self._coerce_float(
          attributes.get(ATTR_WEATHER_UV_INDEX),
        ),
        wind_speed_kmh=self._coerce_float(
          attributes.get(ATTR_WEATHER_WIND_SPEED),
        ),
        pressure_hpa=self._coerce_float(
          attributes.get(ATTR_WEATHER_PRESSURE),
        ),
        visibility_km=self._coerce_float(
          attributes.get(ATTR_WEATHER_VISIBILITY),
        ),
        condition=weather_state.state,
        source_entity=weather_entity_id_local,
        last_updated=dt_util.utcnow(),
      )

      # Calculate derived values  # noqa: E114
      self._calculate_derived_conditions()  # noqa: E111

      # Update alerts based on new conditions  # noqa: E114
      await self._update_weather_alerts()  # noqa: E111

      _LOGGER.debug(  # noqa: E111
        "Updated weather conditions: %.1f°C, %s, UV: %s",
        temperature_c or 0,
        weather_state.state,
        attributes.get(ATTR_WEATHER_UV_INDEX, "unknown"),
      )

      return self._current_conditions  # noqa: E111

    # RESILIENCE: Wrap weather data fetch with retry logic
    try:
      if self.resilience_manager:  # noqa: E111
        return await self.resilience_manager.execute_with_resilience(
          _fetch_weather_data,
          retry_config=self._retry_config,
        )
      # Fallback if no resilience manager  # noqa: E114
      return await _fetch_weather_data()  # noqa: E111
    except Exception as err:
      _LOGGER.error(  # noqa: E111
        "Failed to update weather data after retries: %s",
        err,
      )
      return None  # noqa: E111

  async def async_update_forecast_data(  # noqa: E111
    self,
    weather_entity_id: str | None = None,
    forecast_horizon_hours: int = 24,
  ) -> WeatherForecast | None:
    """Update weather forecast data for advanced health planning with resilience.

    Uses retry logic for transient failures when fetching forecast data.

    Args:
        weather_entity_id: Weather entity ID, if None will try to find one
        forecast_horizon_hours: Hours ahead to forecast (6-48)

    Returns:
        Updated weather forecast or None if unavailable
    """

    async def _fetch_forecast_data() -> WeatherForecast | None:
      """Internal fetch function wrapped by resilience manager."""  # noqa: E111
      # Load translations if not already loaded  # noqa: E114
      if not self._translations:  # noqa: E111
        await self.async_load_translations()

      # Find weather entity if not specified  # noqa: E114
      weather_entity_id_local = weather_entity_id  # noqa: E111
      if weather_entity_id_local is None:  # noqa: E111
        weather_entity_id_local = await self._find_weather_entity()

      if weather_entity_id_local is None:  # noqa: E111
        _LOGGER.warning(
          "No weather entity found for forecast analysis",
        )
        return None

      # Get weather entity with forecast data  # noqa: E114
      weather_state = self.hass.states.get(weather_entity_id_local)  # noqa: E111
      if not weather_state or weather_state.state in [  # noqa: E111
        STATE_UNAVAILABLE,
        STATE_UNKNOWN,
      ]:
        _LOGGER.warning(
          "Weather entity %s is unavailable for forecast",
          weather_entity_id,
        )
        return None

      # Extract forecast data from attributes  # noqa: E114
      attributes = cast(  # noqa: E111
        WeatherEntityAttributes,
        weather_state.attributes,
      )
      forecast_data_raw = attributes.get(ATTR_FORECAST)  # noqa: E111
      if not isinstance(forecast_data_raw, Sequence):  # noqa: E111
        _LOGGER.debug(
          "Weather entity %s does not expose a forecast sequence",
          weather_entity_id_local,
        )
        return None

      if not all(isinstance(item, Mapping) for item in forecast_data_raw):  # noqa: E111
        _LOGGER.debug(
          "Weather entity %s returned non-mapping forecast entries",
          weather_entity_id_local,
        )
        return None

      forecast_data: ForecastEntries = [  # noqa: E111
        cast(ForecastEntry, item) for item in forecast_data_raw
      ]
      if not forecast_data:  # noqa: E111
        _LOGGER.debug(
          "No forecast data available in weather entity %s",
          weather_entity_id,
        )
        return None

      # Process forecast data into structured format  # noqa: E114
      forecast_points = await self._process_forecast_data(  # noqa: E111
        forecast_data,
        forecast_horizon_hours,
      )

      if not forecast_points:  # noqa: E111
        _LOGGER.warning("No valid forecast points generated")
        return None

      # Create forecast object  # noqa: E114
      self._current_forecast = WeatherForecast(  # noqa: E111
        forecast_points=forecast_points,
        source_entity=weather_entity_id_local,
        generated_at=dt_util.utcnow(),
        forecast_horizon_hours=forecast_horizon_hours,
        quality=self._assess_forecast_quality(forecast_data),
      )

      # Calculate health scores for all forecast points  # noqa: E114
      await self._calculate_forecast_health_scores()  # noqa: E111

      # Calculate summary statistics  # noqa: E114
      self._calculate_forecast_statistics()  # noqa: E111

      # Identify optimal activity windows  # noqa: E114
      await self._identify_optimal_activity_windows()  # noqa: E111

      _LOGGER.debug(  # noqa: E111
        "Updated weather forecast: %d points, %dh horizon, quality: %s",
        len(forecast_points),
        forecast_horizon_hours,
        self._current_forecast.quality.value,
      )

      return self._current_forecast  # noqa: E111

    # RESILIENCE: Wrap forecast data fetch with retry logic
    try:
      if self.resilience_manager:  # noqa: E111
        return await self.resilience_manager.execute_with_resilience(
          _fetch_forecast_data,
          retry_config=self._retry_config,
        )
      # Fallback if no resilience manager  # noqa: E114
      return await _fetch_forecast_data()  # noqa: E111
    except Exception as err:
      _LOGGER.error(  # noqa: E111
        "Failed to update weather forecast data after retries: %s",
        err,
      )
      return None  # noqa: E111

  async def _process_forecast_data(  # noqa: E111
    self,
    forecast_data: ForecastEntries,
    horizon_hours: int,
  ) -> list[ForecastPoint]:
    """Process raw forecast data into structured forecast points.

    Args:
        forecast_data: Raw forecast data from weather entity
        horizon_hours: Maximum hours ahead to process

    Returns:
        List of processed forecast points
    """
    forecast_points: list[ForecastPoint] = []
    cutoff_time = dt_util.utcnow() + timedelta(hours=horizon_hours)

    for forecast_item in forecast_data:
      try:  # noqa: E111
        # Parse forecast timestamp
        forecast_time_obj = forecast_item.get(ATTR_FORECAST_TIME)
        forecast_time: datetime | None
        if isinstance(forecast_time_obj, str):
          forecast_time = dt_util.parse_datetime(forecast_time_obj)  # noqa: E111
        elif isinstance(forecast_time_obj, datetime):
          forecast_time = forecast_time_obj  # noqa: E111
        else:
          forecast_time = None  # noqa: E111

        if not forecast_time or forecast_time > cutoff_time:
          continue  # noqa: E111

        # Extract temperature data
        temp_high = self._coerce_float(
          forecast_item.get(ATTR_FORECAST_TEMP),
        )
        temp_low = self._coerce_float(
          forecast_item.get(ATTR_FORECAST_TEMP_LOW),
        )

        # Convert temperature units if needed
        if temp_high is not None:
          temp_unit = forecast_item.get(  # noqa: E111
            "temperature_unit",
            UnitOfTemperature.CELSIUS,
          )
          if temp_unit == UnitOfTemperature.FAHRENHEIT:  # noqa: E111
            temp_high = (temp_high - 32.0) * 5 / 9
            if temp_low is not None:
              temp_low = (temp_low - 32.0) * 5 / 9  # noqa: E111
          elif temp_unit == UnitOfTemperature.KELVIN:  # noqa: E111
            temp_high = temp_high - 273.15
            if temp_low is not None:
              temp_low = temp_low - 273.15  # noqa: E111

        humidity = self._coerce_float(
          forecast_item.get(ATTR_FORECAST_HUMIDITY),
        )
        uv_index = self._coerce_float(
          forecast_item.get(ATTR_FORECAST_UV_INDEX),
        )
        wind_speed = self._coerce_float(
          forecast_item.get(ATTR_FORECAST_WIND_SPEED),
        )
        pressure = self._coerce_float(
          forecast_item.get(ATTR_FORECAST_PRESSURE),
        )
        precipitation = self._coerce_float(
          forecast_item.get(ATTR_FORECAST_PRECIPITATION),
        )
        precipitation_probability = self._coerce_int(
          forecast_item.get(ATTR_FORECAST_PRECIPITATION_PROBABILITY),
        )
        condition_obj = forecast_item.get(ATTR_FORECAST_CONDITION)
        condition = (
          condition_obj
          if isinstance(
            condition_obj,
            str,
          )
          else None
        )

        # Create forecast point
        forecast_point = ForecastPoint(
          timestamp=forecast_time,
          temperature_c=temp_high,
          temperature_low_c=temp_low,
          humidity_percent=humidity,
          uv_index=uv_index,
          wind_speed_kmh=wind_speed,
          pressure_hpa=pressure,
          precipitation_mm=precipitation,
          precipitation_probability=precipitation_probability,
          condition=condition,
        )

        # Calculate derived values for forecast point
        self._calculate_forecast_point_derived_values(forecast_point)

        forecast_points.append(forecast_point)

      except Exception as err:  # noqa: E111
        _LOGGER.debug("Error processing forecast item: %s", err)
        continue

    # Sort by timestamp
    forecast_points.sort(key=lambda x: x.timestamp)

    return forecast_points

  def _assess_forecast_quality(  # noqa: E111
    self,
    forecast_data: ForecastEntries,
  ) -> ForecastQuality:
    """Assess the quality of forecast data.

    Args:
        forecast_data: Raw forecast data

    Returns:
        Quality assessment of forecast data
    """
    if not forecast_data:
      return ForecastQuality.POOR  # noqa: E111

    # Check data completeness
    complete_points = 0
    total_points = len(forecast_data)

    for item in forecast_data:
      required_fields = [ATTR_FORECAST_TIME, ATTR_FORECAST_TEMP]  # noqa: E111
      optional_fields = [  # noqa: E111
        ATTR_FORECAST_HUMIDITY,
        ATTR_FORECAST_UV_INDEX,
        ATTR_FORECAST_CONDITION,
      ]

      has_required = all(item.get(field) is not None for field in required_fields)  # noqa: E111
      has_optional = sum(1 for field in optional_fields if item.get(field) is not None)  # noqa: E111

      if has_required and has_optional >= 2:  # noqa: E111
        complete_points += 1

    completeness_ratio = complete_points / total_points if total_points > 0 else 0

    # Assess quality based on completeness and data points
    if completeness_ratio >= 0.8 and total_points >= 24:  # Hourly data for 24h
      return ForecastQuality.EXCELLENT  # noqa: E111
    if completeness_ratio >= 0.6 and total_points >= 8:  # 3-hourly data
      return ForecastQuality.GOOD  # noqa: E111
    if completeness_ratio >= 0.4 and total_points >= 4:  # 6-hourly data
      return ForecastQuality.FAIR  # noqa: E111
    return ForecastQuality.POOR

  def _calculate_forecast_point_derived_values(  # noqa: E111
    self,
    forecast_point: ForecastPoint,
  ) -> None:
    """Calculate derived values for a forecast point.

    Args:
        forecast_point: Forecast point to enhance with derived values
    """
    if forecast_point.temperature_c is None:
      return  # noqa: E111

    temp_c = forecast_point.temperature_c
    temp_f = temp_c * 9 / 5 + 32

    # Calculate heat index if hot and humid
    if (
      temp_c >= 20
      and forecast_point.humidity_percent is not None
      and forecast_point.humidity_percent >= 40
    ):
      humidity = forecast_point.humidity_percent  # noqa: E111

      # Heat index formula (Fahrenheit)  # noqa: E114
      heat_index_f = (  # noqa: E111
        -42.379
        + 2.04901523 * temp_f
        + 10.14333127 * humidity
        - 0.22475541 * temp_f * humidity
        - 0.00683783 * temp_f * temp_f
        - 0.05481717 * humidity * humidity
        + 0.00122874 * temp_f * temp_f * humidity
        + 0.00085282 * temp_f * humidity * humidity
        - 0.00000199 * temp_f * temp_f * humidity * humidity
      )

      # Convert back to Celsius  # noqa: E114
      forecast_point.heat_index = (heat_index_f - 32) * 5 / 9  # noqa: E111

    # Calculate wind chill if cold and windy
    if (
      temp_c <= 10
      and forecast_point.wind_speed_kmh is not None
      and forecast_point.wind_speed_kmh > 5
    ):
      wind_mph = forecast_point.wind_speed_kmh * 0.621371  # noqa: E111

      # Wind chill formula (Fahrenheit)  # noqa: E114
      if wind_mph > 3:  # noqa: E111
        wind_chill_f = (
          35.74
          + 0.6215 * temp_f
          - 35.75 * (wind_mph**0.16)
          + 0.4275 * temp_f * (wind_mph**0.16)
        )

        # Convert back to Celsius
        forecast_point.wind_chill = (wind_chill_f - 32) * 5 / 9

  async def _calculate_forecast_health_scores(self) -> None:  # noqa: E111
    """Calculate health scores for all forecast points."""
    if not self._current_forecast or not self._current_forecast.forecast_points:
      return  # noqa: E111

    for forecast_point in self._current_forecast.forecast_points:
      forecast_point.health_score = self._calculate_point_health_score(  # noqa: E111
        forecast_point,
      )
      forecast_point.predicted_alerts = self._predict_point_alerts(  # noqa: E111
        forecast_point,
      )

  def _calculate_point_health_score(self, forecast_point: ForecastPoint) -> int:  # noqa: E111
    """Calculate health score for a single forecast point.

    Args:
        forecast_point: Forecast point to score

    Returns:
        Health score (0-100) where 100 is optimal conditions
    """
    score = 100

    # Temperature scoring
    if forecast_point.temperature_c is not None:
      temp = forecast_point.temperature_c  # noqa: E111
      effective_temp = forecast_point.heat_index or forecast_point.wind_chill or temp  # noqa: E111

      # Ideal temperature range for dogs: 15-22°C  # noqa: E114
      if 15 <= temp <= 22:  # noqa: E111
        score += 0  # Perfect
      elif 10 <= temp < 15 or 22 < temp <= 25:  # noqa: E111
        score -= 10  # Good
      elif 5 <= temp < 10 or 25 < temp <= 30:  # noqa: E111
        score -= 25  # Moderate concern
      elif 0 <= temp < 5 or 30 < temp <= 35:  # noqa: E111
        score -= 40  # High concern
      else:  # noqa: E111
        score -= 60  # Extreme concern

      # Additional penalty for extreme feels-like temperatures  # noqa: E114
      if effective_temp != temp:  # noqa: E111
        temp_diff = abs(effective_temp - temp)
        if temp_diff > 5:
          # 2 points per degree difference  # noqa: E114
          score -= int(temp_diff * 2)  # noqa: E111

    # UV index scoring
    if forecast_point.uv_index is not None:
      uv = forecast_point.uv_index  # noqa: E111
      if uv > 8:  # noqa: E111
        score -= 20
      elif uv > 6:  # noqa: E111
        score -= 10
      elif uv > 3:  # noqa: E111
        score -= 5

    # Humidity scoring
    if forecast_point.humidity_percent is not None:
      humidity = forecast_point.humidity_percent  # noqa: E111
      if humidity > 85:  # noqa: E111
        score -= 15
      elif humidity > 70:  # noqa: E111
        score -= 10
      elif humidity < 30:  # noqa: E111
        score -= 5

    # Precipitation scoring
    if forecast_point.precipitation_probability is not None:
      precip_prob = forecast_point.precipitation_probability  # noqa: E111
      if precip_prob > 80:  # noqa: E111
        score -= 15  # Very likely rain
      elif precip_prob > 50:  # noqa: E111
        score -= 10  # Likely rain
      elif precip_prob > 30:  # noqa: E111
        score -= 5  # Possible rain

    # Wind scoring
    if forecast_point.wind_speed_kmh is not None:
      wind = forecast_point.wind_speed_kmh  # noqa: E111
      if wind > 40:  # Very windy  # noqa: E111
        score -= 15
      elif wind > 25:  # Windy  # noqa: E111
        score -= 10
      elif wind > 15:  # Breezy  # noqa: E111
        score -= 5

    # Weather condition scoring
    if forecast_point.condition:
      condition = forecast_point.condition.lower()  # noqa: E111
      if any(keyword in condition for keyword in ["storm", "thunder", "lightning"]):  # noqa: E111
        score -= 30
      elif any(keyword in condition for keyword in ["snow", "ice", "sleet"]):  # noqa: E111
        score -= 20
      elif any(keyword in condition for keyword in ["rain", "drizzle"]):  # noqa: E111
        score -= 15
      elif "fog" in condition:  # noqa: E111
        score -= 10

    return max(0, min(100, score))

  def _predict_point_alerts(  # noqa: E111
    self,
    forecast_point: ForecastPoint,
  ) -> list[WeatherHealthImpact]:
    """Predict weather health alerts for a forecast point.

    Args:
        forecast_point: Forecast point to analyze

    Returns:
        List of predicted health impacts
    """
    alerts: list[WeatherHealthImpact] = []

    if forecast_point.temperature_c is None:
      return alerts  # noqa: E111

    temp = forecast_point.temperature_c

    # Temperature-based alerts
    if temp >= self.temperature_thresholds["hot"][WeatherSeverity.MODERATE]:
      alerts.append(WeatherHealthImpact.HEAT_STRESS)  # noqa: E111

    if temp <= self.temperature_thresholds["cold"][WeatherSeverity.MODERATE]:
      alerts.append(WeatherHealthImpact.COLD_STRESS)  # noqa: E111

    # UV alerts
    if (
      forecast_point.uv_index is not None
      and forecast_point.uv_index >= self.uv_thresholds[WeatherSeverity.MODERATE]
    ):
      alerts.append(WeatherHealthImpact.UV_EXPOSURE)  # noqa: E111

    # Humidity alerts
    if (
      forecast_point.humidity_percent is not None
      and forecast_point.humidity_percent
      >= self.humidity_thresholds[WeatherSeverity.MODERATE]
    ):
      alerts.append(WeatherHealthImpact.RESPIRATORY_RISK)  # noqa: E111

    # Precipitation alerts
    if (
      forecast_point.precipitation_probability is not None
      and forecast_point.precipitation_probability > 60
    ):
      alerts.append(WeatherHealthImpact.PAW_PROTECTION)  # noqa: E111

    # Storm alerts
    if forecast_point.condition and any(
      keyword in forecast_point.condition.lower()
      for keyword in ["storm", "thunder", "lightning"]
    ):
      alerts.append(WeatherHealthImpact.EXERCISE_LIMITATION)  # noqa: E111

    return alerts

  def _calculate_forecast_statistics(self) -> None:  # noqa: E111
    """Calculate summary statistics for the forecast."""
    if not self._current_forecast or not self._current_forecast.forecast_points:
      return  # noqa: E111

    health_scores = [
      point.health_score
      for point in self._current_forecast.forecast_points
      if point.health_score is not None
    ]

    if health_scores:
      self._current_forecast.min_health_score = min(health_scores)  # noqa: E111
      self._current_forecast.max_health_score = max(health_scores)  # noqa: E111
      self._current_forecast.avg_health_score = int(  # noqa: E111
        sum(health_scores) / len(health_scores),
      )

    # Identify critical periods (health score < 40)
    critical_periods = []
    current_period_start = None

    for point in self._current_forecast.forecast_points:
      if point.health_score is not None and point.health_score < 40:  # noqa: E111
        if current_period_start is None:
          current_period_start = point.timestamp  # noqa: E111
      else:  # noqa: E111
        if current_period_start is not None:
          # End of critical period  # noqa: E114
          critical_periods.append(  # noqa: E111
            (current_period_start, point.timestamp),
          )
          current_period_start = None  # noqa: E111

    # Handle ongoing critical period
    if current_period_start is not None:
      last_point = self._current_forecast.forecast_points[-1]  # noqa: E111
      critical_periods.append(  # noqa: E111
        (current_period_start, last_point.timestamp),
      )

    self._current_forecast.critical_periods = critical_periods

  async def _identify_optimal_activity_windows(self) -> None:  # noqa: E111
    """Identify optimal time windows for different activities."""
    if not self._current_forecast or not self._current_forecast.forecast_points:
      return  # noqa: E111

    # Activity thresholds (minimum health scores)
    activity_thresholds: ActivityThresholdMap = {
      "walk": 60,  # Regular walks
      "play": 70,  # Active play sessions
      "exercise": 75,  # Intensive exercise
      "basic_needs": 30,  # Essential outdoor time
    }

    for activity_type, min_score in activity_thresholds.items():
      windows = self._find_activity_windows(activity_type, min_score)  # noqa: E111
      self._current_forecast.optimal_activity_windows.extend(windows)  # noqa: E111

    # Sort windows by start time
    self._current_forecast.optimal_activity_windows.sort(
      key=lambda x: x.start_time,
    )

  def _find_activity_windows(  # noqa: E111
    self,
    activity_type: ActivityType,
    min_score: int,
    min_duration_hours: int = 1,
  ) -> list[ActivityTimeSlot]:
    """Find optimal time windows for a specific activity.

    Args:
        activity_type: Type of activity (walk, play, exercise, basic_needs)
        min_score: Minimum health score required
        min_duration_hours: Minimum window duration in hours

    Returns:
        List of optimal activity time slots
    """
    if not self._current_forecast:
      return []  # noqa: E111

    windows = []
    current_window_start = None
    current_window_scores = []

    for point in self._current_forecast.forecast_points:
      if point.health_score is not None and point.health_score >= min_score:  # noqa: E111
        # Good conditions for activity
        if current_window_start is None:
          current_window_start = point.timestamp  # noqa: E111
          current_window_scores = [point.health_score]  # noqa: E111
        else:
          current_window_scores.append(point.health_score)  # noqa: E111
      else:  # noqa: E111
        # Conditions not suitable, end current window
        if current_window_start is not None:
          window_duration = (  # noqa: E111
            point.timestamp - current_window_start
          ).total_seconds() / 3600

          if window_duration >= min_duration_hours:  # noqa: E111
            # Create activity window
            avg_score = int(
              sum(current_window_scores) / len(current_window_scores),
            )

            # Determine alert level based on average score
            if avg_score >= 80:
              alert_level = WeatherSeverity.LOW  # noqa: E111
            elif avg_score >= 60:
              alert_level = WeatherSeverity.MODERATE  # noqa: E111
            else:
              alert_level = WeatherSeverity.HIGH  # noqa: E111

            recommendations = self._get_activity_recommendations(
              activity_type,
              avg_score,
              alert_level,
            )

            windows.append(
              ActivityTimeSlot(
                start_time=current_window_start,
                end_time=point.timestamp,
                health_score=avg_score,
                activity_type=activity_type,
                recommendations=recommendations,
                alert_level=alert_level,
              ),
            )

          current_window_start = None  # noqa: E111
          current_window_scores = []  # noqa: E111

    # Handle ongoing window at end of forecast
    if current_window_start is not None and current_window_scores:
      last_point = self._current_forecast.forecast_points[-1]  # noqa: E111
      window_duration = (  # noqa: E111
        last_point.timestamp - current_window_start
      ).total_seconds() / 3600

      if window_duration >= min_duration_hours:  # noqa: E111
        avg_score = int(
          sum(current_window_scores) / len(current_window_scores),
        )

        if avg_score >= 80:
          alert_level = WeatherSeverity.LOW  # noqa: E111
        elif avg_score >= 60:
          alert_level = WeatherSeverity.MODERATE  # noqa: E111
        else:
          alert_level = WeatherSeverity.HIGH  # noqa: E111

        recommendations = self._get_activity_recommendations(
          activity_type,
          avg_score,
          alert_level,
        )

        windows.append(
          ActivityTimeSlot(
            start_time=current_window_start,
            end_time=last_point.timestamp,
            health_score=avg_score,
            activity_type=activity_type,
            recommendations=recommendations,
            alert_level=alert_level,
          ),
        )

    return windows

  def _get_activity_recommendations(  # noqa: E111
    self,
    activity_type: ActivityType,
    avg_score: int,
    alert_level: WeatherSeverity,
  ) -> list[str]:
    """Get recommendations for specific activity during a time window.

    Args:
        activity_type: Type of activity
        avg_score: Average health score for the window
        alert_level: Alert level for the window

    Returns:
        List of activity-specific recommendations
    """
    recommendations = []

    # Base recommendations by activity type
    if activity_type == "walk":
      if alert_level == WeatherSeverity.LOW:  # noqa: E111
        recommendations.extend(
          [
            "Excellent conditions for regular walks",
            "Normal duration and intensity recommended",
          ],
        )
      else:  # noqa: E111
        recommendations.extend(
          [
            "Monitor weather conditions during walk",
            "Be prepared to cut walk short if needed",
          ],
        )
    elif activity_type == "play":
      if alert_level == WeatherSeverity.LOW:  # noqa: E111
        recommendations.extend(
          [
            "Great time for active play sessions",
            "Consider outdoor training activities",
          ],
        )
      else:  # noqa: E111
        recommendations.extend(
          [
            "Moderate play activities recommended",
            "Monitor for signs of stress or discomfort",
          ],
        )
    elif activity_type == "exercise":
      if alert_level == WeatherSeverity.LOW:  # noqa: E111
        recommendations.extend(
          [
            "Optimal conditions for intensive exercise",
            "Running and high-energy activities safe",
          ],
        )
      else:  # noqa: E111
        recommendations.extend(
          [
            "Reduce exercise intensity",
            "Take frequent breaks for monitoring",
          ],
        )
    elif activity_type == "basic_needs":
      recommendations.extend(  # noqa: E111
        [
          "Quick potty breaks acceptable",
          "Minimize outdoor exposure time",
        ],
      )

    # Add score-based recommendations
    if avg_score < 50:
      recommendations.append("Use extra caution during this window")  # noqa: E111
    elif avg_score >= 80:
      recommendations.append("Ideal conditions for this activity")  # noqa: E111

    return recommendations

  async def _find_weather_entity(self) -> str | None:  # noqa: E111
    """Find a suitable weather entity in Home Assistant.

    Returns:
        Weather entity ID or None if not found
    """
    # Look for weather entities
    weather_entities = [
      state.entity_id
      for state in self.hass.states.async_all(WEATHER_DOMAIN)
      if state.state not in [STATE_UNAVAILABLE, STATE_UNKNOWN]
    ]

    if weather_entities:
      # Prefer entities with "weather" in the name  # noqa: E114
      for entity_id in weather_entities:  # noqa: E111
        if "weather" in entity_id.lower():
          return entity_id  # noqa: E111
      # Fall back to first available  # noqa: E114
      return weather_entities[0]  # noqa: E111

    return None

  def _calculate_derived_conditions(self) -> None:  # noqa: E111
    """Calculate derived weather conditions like heat index and wind chill."""
    if not self._current_conditions or self._current_conditions.temperature_c is None:
      return  # noqa: E111

    temp_c = self._current_conditions.temperature_c
    temp_f = temp_c * 9 / 5 + 32  # Convert to Fahrenheit for calculations

    # Calculate heat index if hot and humid
    if (
      temp_c >= 20
      and self._current_conditions.humidity_percent is not None
      and self._current_conditions.humidity_percent >= 40
    ):
      humidity = self._current_conditions.humidity_percent  # noqa: E111

      # Heat index formula (Fahrenheit)  # noqa: E114
      heat_index_f = (  # noqa: E111
        -42.379
        + 2.04901523 * temp_f
        + 10.14333127 * humidity
        - 0.22475541 * temp_f * humidity
        - 0.00683783 * temp_f * temp_f
        - 0.05481717 * humidity * humidity
        + 0.00122874 * temp_f * temp_f * humidity
        + 0.00085282 * temp_f * humidity * humidity
        - 0.00000199 * temp_f * temp_f * humidity * humidity
      )

      # Convert back to Celsius  # noqa: E114
      self._current_conditions.heat_index = (heat_index_f - 32) * 5 / 9  # noqa: E111

    # Calculate wind chill if cold and windy
    if (
      temp_c <= 10
      and self._current_conditions.wind_speed_kmh is not None
      and self._current_conditions.wind_speed_kmh > 5
    ):
      wind_mph = self._current_conditions.wind_speed_kmh * 0.621371  # noqa: E111

      # Wind chill formula (Fahrenheit)  # noqa: E114
      if wind_mph > 3:  # noqa: E111
        wind_chill_f = (
          35.74
          + 0.6215 * temp_f
          - 35.75 * (wind_mph**0.16)
          + 0.4275 * temp_f * (wind_mph**0.16)
        )

        # Convert back to Celsius
        self._current_conditions.wind_chill = (wind_chill_f - 32) * 5 / 9

  async def _update_weather_alerts(self) -> None:  # noqa: E111
    """Update weather alerts based on current conditions."""
    if not self._current_conditions or not self._current_conditions.is_valid:
      return  # noqa: E111

    # Clear expired alerts
    self._active_alerts = [alert for alert in self._active_alerts if alert.is_active]

    new_alerts: list[WeatherAlert] = []

    # Temperature-based alerts
    new_alerts.extend(self._check_temperature_alerts())

    # UV index alerts
    new_alerts.extend(self._check_uv_alerts())

    # Humidity alerts
    new_alerts.extend(self._check_humidity_alerts())

    # Weather condition alerts
    new_alerts.extend(self._check_condition_alerts())

    # Add new alerts that aren't already active
    for new_alert in new_alerts:
      if not any(  # noqa: E111
        existing.alert_type == new_alert.alert_type
        and existing.severity == new_alert.severity
        for existing in self._active_alerts
      ):
        self._active_alerts.append(new_alert)
        _LOGGER.info(
          "New weather health alert: %s (%s)",
          new_alert.title,
          new_alert.severity.value,
        )

  def _check_temperature_alerts(self) -> list[WeatherAlert]:  # noqa: E111
    """Check for temperature-based health alerts.

    Returns:
        List of temperature-related alerts
    """
    alerts: list[WeatherAlert] = []

    if not self._current_conditions or self._current_conditions.temperature_c is None:
      return alerts  # noqa: E111

    temp = self._current_conditions.temperature_c
    effective_temp = (
      self._current_conditions.heat_index or self._current_conditions.wind_chill or temp
    )

    # Hot weather alerts
    if temp >= self.temperature_thresholds["hot"][WeatherSeverity.EXTREME]:
      alerts.append(  # noqa: E111
        WeatherAlert(
          alert_type=WeatherHealthImpact.HEAT_STRESS,
          severity=WeatherSeverity.EXTREME,
          title=self._get_translation(
            "weather.alerts.extreme_heat_warning.title",
          ),
          message=self._get_translation(
            "weather.alerts.extreme_heat_warning.message",
            temperature=temp,
            feels_like=effective_temp,
          ),
          recommendations=[
            self._get_translation(
              "weather.recommendations.avoid_peak_hours",
            ),
            self._get_translation(
              "weather.recommendations.provide_water",
            ),
            self._get_translation(
              "weather.recommendations.keep_indoors",
            ),
            self._get_translation(
              "weather.recommendations.watch_heat_signs",
            ),
            self._get_translation(
              "weather.recommendations.use_cooling_aids",
            ),
            self._get_translation(
              "weather.recommendations.never_leave_in_car",
            ),
          ],
          duration_hours=6,
          affected_breeds=[
            "brachycephalic",
            "thick_coat",
            "elderly",
            "overweight",
          ],
          age_considerations=["puppies", "senior_dogs"],
        ),
      )
    elif temp >= self.temperature_thresholds["hot"][WeatherSeverity.HIGH]:
      alerts.append(  # noqa: E111
        WeatherAlert(
          alert_type=WeatherHealthImpact.HEAT_STRESS,
          severity=WeatherSeverity.HIGH,
          title=self._get_translation(
            "weather.alerts.high_heat_advisory.title",
          ),
          message=self._get_translation(
            "weather.alerts.high_heat_advisory.message",
            temperature=temp,
          ),
          recommendations=[
            self._get_translation(
              "weather.recommendations.limit_outdoor_time",
            ),
            self._get_translation(
              "weather.recommendations.ensure_shade",
            ),
            self._get_translation(
              "weather.recommendations.provide_shade_always",
            ),
            self._get_translation(
              "weather.recommendations.monitor_overheating",
            ),
            self._get_translation(
              "weather.recommendations.cooler_surfaces",
            ),
          ],
          duration_hours=4,
          affected_breeds=["brachycephalic", "thick_coat"],
        ),
      )
    elif temp >= self.temperature_thresholds["hot"][WeatherSeverity.MODERATE]:
      alerts.append(  # noqa: E111
        WeatherAlert(
          alert_type=WeatherHealthImpact.HEAT_STRESS,
          severity=WeatherSeverity.MODERATE,
          title=self._get_translation(
            "weather.alerts.warm_weather_caution.title",
          ),
          message=self._get_translation(
            "weather.alerts.warm_weather_caution.message",
            temperature=temp,
          ),
          recommendations=[
            self._get_translation(
              "weather.recommendations.extra_water",
            ),
            self._get_translation(
              "weather.recommendations.cooler_day_parts",
            ),
            self._get_translation(
              "weather.recommendations.watch_heat_stress",
            ),
          ],
          duration_hours=3,
        ),
      )

    # Cold weather alerts
    if temp <= self.temperature_thresholds["cold"][WeatherSeverity.EXTREME]:
      alerts.append(  # noqa: E111
        WeatherAlert(
          alert_type=WeatherHealthImpact.COLD_STRESS,
          severity=WeatherSeverity.EXTREME,
          title=self._get_translation(
            "weather.alerts.extreme_cold_warning.title",
          ),
          message=self._get_translation(
            "weather.alerts.extreme_cold_warning.message",
            temperature=temp,
            feels_like=effective_temp,
          ),
          recommendations=[
            self._get_translation(
              "weather.recommendations.essential_only",
            ),
            self._get_translation(
              "weather.recommendations.protective_clothing",
            ),
            self._get_translation(
              "weather.recommendations.protect_paws",
            ),
            self._get_translation(
              "weather.recommendations.warm_shelter",
            ),
            self._get_translation(
              "weather.recommendations.watch_hypothermia",
            ),
            self._get_translation(
              "weather.recommendations.postpone_activities",
            ),
          ],
          duration_hours=8,
          affected_breeds=[
            "short_hair",
            "small_breeds",
            "elderly",
            "sick",
          ],
          age_considerations=["puppies", "senior_dogs"],
        ),
      )
    elif temp <= self.temperature_thresholds["cold"][WeatherSeverity.HIGH]:
      alerts.append(  # noqa: E111
        WeatherAlert(
          alert_type=WeatherHealthImpact.COLD_STRESS,
          severity=WeatherSeverity.HIGH,
          title=self._get_translation(
            "weather.alerts.high_cold_advisory.title",
          ),
          message=self._get_translation(
            "weather.alerts.high_cold_advisory.message",
            temperature=temp,
          ),
          recommendations=[
            self._get_translation(
              "weather.recommendations.shorten_activities",
            ),
            self._get_translation(
              "weather.recommendations.consider_clothing",
            ),
            self._get_translation(
              "weather.recommendations.cold_surface_protection",
            ),
            self._get_translation(
              "weather.recommendations.warm_shelter_available",
            ),
          ],
          duration_hours=6,
          affected_breeds=["short_hair", "small_breeds"],
        ),
      )

    return alerts

  def _check_uv_alerts(self) -> list[WeatherAlert]:  # noqa: E111
    """Check for UV index-based health alerts.

    Returns:
        List of UV-related alerts
    """
    alerts: list[WeatherAlert] = []

    if not self._current_conditions or self._current_conditions.uv_index is None:
      return alerts  # noqa: E111

    uv = self._current_conditions.uv_index

    if uv >= self.uv_thresholds[WeatherSeverity.EXTREME]:
      alerts.append(  # noqa: E111
        WeatherAlert(
          alert_type=WeatherHealthImpact.UV_EXPOSURE,
          severity=WeatherSeverity.EXTREME,
          title=self._get_translation(
            "weather.alerts.extreme_uv_warning.title",
          ),
          message=self._get_translation(
            "weather.alerts.extreme_uv_warning.message",
            uv_index=uv,
          ),
          recommendations=[
            self._get_translation(
              "weather.recommendations.avoid_peak_uv",
            ),
            self._get_translation(
              "weather.recommendations.provide_shade_always",
            ),
            self._get_translation(
              "weather.recommendations.uv_protective_clothing",
            ),
            self._get_translation(
              "weather.recommendations.protect_nose_ears",
            ),
            self._get_translation(
              "weather.recommendations.pet_sunscreen",
            ),
          ],
          duration_hours=6,
          affected_breeds=[
            "light_colored",
            "pink_skin",
            "sparse_hair",
          ],
        ),
      )
    elif uv >= self.uv_thresholds[WeatherSeverity.HIGH]:
      alerts.append(  # noqa: E111
        WeatherAlert(
          alert_type=WeatherHealthImpact.UV_EXPOSURE,
          severity=WeatherSeverity.HIGH,
          title=self._get_translation(
            "weather.alerts.high_uv_advisory.title",
          ),
          message=self._get_translation(
            "weather.alerts.high_uv_advisory.message",
            uv_index=uv,
          ),
          recommendations=[
            self._get_translation(
              "weather.recommendations.shade_during_activities",
            ),
            self._get_translation(
              "weather.recommendations.limit_peak_exposure",
            ),
            self._get_translation(
              "weather.recommendations.monitor_skin_irritation",
            ),
          ],
          duration_hours=4,
        ),
      )

    return alerts

  def _check_humidity_alerts(self) -> list[WeatherAlert]:  # noqa: E111
    """Check for humidity-based health alerts.

    Returns:
        List of humidity-related alerts
    """
    alerts: list[WeatherAlert] = []

    if (
      not self._current_conditions or self._current_conditions.humidity_percent is None
    ):
      return alerts  # noqa: E111

    humidity = self._current_conditions.humidity_percent

    if humidity >= self.humidity_thresholds[WeatherSeverity.HIGH]:
      alerts.append(  # noqa: E111
        WeatherAlert(
          alert_type=WeatherHealthImpact.RESPIRATORY_RISK,
          severity=WeatherSeverity.HIGH,
          title=self._get_translation(
            "weather.alerts.high_humidity_alert.title",
          ),
          message=self._get_translation(
            "weather.alerts.high_humidity_alert.message",
            humidity=humidity,
          ),
          recommendations=[
            self._get_translation(
              "weather.recommendations.reduce_exercise_intensity",
            ),
            self._get_translation(
              "weather.recommendations.good_air_circulation",
            ),
            self._get_translation(
              "weather.recommendations.monitor_breathing",
            ),
            self._get_translation(
              "weather.recommendations.cool_ventilated_areas",
            ),
          ],
          duration_hours=4,
          affected_breeds=["brachycephalic", "respiratory_issues"],
        ),
      )

    return alerts

  def _check_condition_alerts(self) -> list[WeatherAlert]:  # noqa: E111
    """Check for weather condition-based alerts.

    Returns:
        List of condition-related alerts
    """
    alerts: list[WeatherAlert] = []

    if not self._current_conditions or not self._current_conditions.condition:
      return alerts  # noqa: E111

    condition = self._current_conditions.condition.lower()

    # Rain/wet conditions
    if any(keyword in condition for keyword in ["rain", "drizzle", "shower"]):
      alerts.append(  # noqa: E111
        WeatherAlert(
          alert_type=WeatherHealthImpact.PAW_PROTECTION,
          severity=WeatherSeverity.MODERATE,
          title=self._get_translation(
            "weather.alerts.wet_weather_advisory.title",
          ),
          message=self._get_translation(
            "weather.alerts.wet_weather_advisory.message",
          ),
          recommendations=[
            self._get_translation(
              "weather.recommendations.dry_paws_thoroughly",
            ),
            self._get_translation(
              "weather.recommendations.check_toe_irritation",
            ),
            self._get_translation(
              "weather.recommendations.use_paw_balm",
            ),
            self._get_translation(
              "weather.recommendations.waterproof_protection",
            ),
          ],
          duration_hours=2,
        ),
      )

    # Storm conditions
    if any(keyword in condition for keyword in ["storm", "thunder", "lightning"]):
      alerts.append(  # noqa: E111
        WeatherAlert(
          alert_type=WeatherHealthImpact.EXERCISE_LIMITATION,
          severity=WeatherSeverity.HIGH,
          title=self._get_translation(
            "weather.alerts.storm_warning.title",
          ),
          message=self._get_translation(
            "weather.alerts.storm_warning.message",
          ),
          recommendations=[
            self._get_translation(
              "weather.recommendations.keep_indoors_storm",
            ),
            self._get_translation(
              "weather.recommendations.comfort_anxious",
            ),
            self._get_translation(
              "weather.recommendations.secure_id_tags",
            ),
            self._get_translation(
              "weather.recommendations.avoid_until_passes",
            ),
          ],
          duration_hours=3,
          age_considerations=["anxious_dogs", "noise_sensitive"],
        ),
      )

    # Snow/ice conditions
    if any(keyword in condition for keyword in ["snow", "ice", "sleet"]):
      alerts.append(  # noqa: E111
        WeatherAlert(
          alert_type=WeatherHealthImpact.PAW_PROTECTION,
          severity=WeatherSeverity.MODERATE,
          title=self._get_translation(
            "weather.alerts.snow_ice_alert.title",
          ),
          message=self._get_translation(
            "weather.alerts.snow_ice_alert.message",
          ),
          recommendations=[
            self._get_translation(
              "weather.recommendations.use_paw_protection",
            ),
            self._get_translation(
              "weather.recommendations.watch_ice_buildup",
            ),
            self._get_translation(
              "weather.recommendations.rinse_salt_chemicals",
            ),
            self._get_translation(
              "weather.recommendations.provide_traction",
            ),
          ],
          duration_hours=4,
        ),
      )

    return alerts

  def get_current_conditions(self) -> WeatherConditions | None:  # noqa: E111
    """Get current weather conditions.

    Returns:
        Current weather conditions or None if unavailable
    """
    return self._current_conditions

  def get_current_forecast(self) -> WeatherForecast | None:  # noqa: E111
    """Get current weather forecast.

    Returns:
        Current weather forecast or None if unavailable
    """
    return self._current_forecast

  def get_next_optimal_activity_time(  # noqa: E111
    self,
    activity_type: ActivityType = "walk",
  ) -> ActivityTimeSlot | None:
    """Get the next optimal time for a specific activity.

    Args:
        activity_type: Type of activity to find optimal time for

    Returns:
        Next optimal activity time slot or None
    """
    if not self._current_forecast:
      return None  # noqa: E111

    return self._current_forecast.get_next_optimal_window(activity_type)

  def get_forecast_planning_summary(  # noqa: E111
    self,
    dog_breed: str | None = None,
    dog_age_months: int | None = None,
  ) -> ForecastPlanningSummary:
    """Get comprehensive forecast summary for planning purposes.

    Args:
        dog_breed: Dog breed for breed-specific advice
        dog_age_months: Dog age for age-specific recommendations

    Returns:
        Comprehensive forecast planning summary
    """
    if not self._current_forecast or not self._current_forecast.is_valid:
      return ForecastPlanningSummary(  # noqa: E111
        status="unavailable",
        message="Weather forecast data not available",
      )

    forecast = self._current_forecast

    summary = ForecastPlanningSummary(
      status="available",
      forecast_quality=forecast.quality.value,
      forecast_summary=forecast.forecast_summary,
      avg_health_score=forecast.avg_health_score,
      score_range=ScoreRangeSummary(
        min=forecast.min_health_score,
        max=forecast.max_health_score,
      ),
      critical_periods=[
        CriticalPeriodSummary(
          start=period[0].isoformat(),
          end=period[1].isoformat(),
          duration_hours=(period[1] - period[0]).total_seconds() / 3600,
        )
        for period in forecast.critical_periods
      ],
      optimal_windows=[
        OptimalWindowSummary(
          activity=window.activity_type,
          start=window.start_time.isoformat(),
          end=window.end_time.isoformat(),
          health_score=window.health_score,
          alert_level=window.alert_level,
          recommendations=window.recommendations,
        )
        for window in forecast.optimal_activity_windows[:5]
      ],
    )

    # Add next optimal times for common activities
    for activity_literal in PRIMARY_ACTIVITIES:
      activity: ActivityType = cast(ActivityType, activity_literal)  # noqa: E111
      next_window = forecast.get_next_optimal_window(activity)  # noqa: E111
      if next_window:  # noqa: E111
        setattr(
          summary,
          f"next_{activity}_time",
          ActivityWindowSummary(
            start=next_window.start_time.isoformat(),
            health_score=next_window.health_score,
            alert_level=next_window.alert_level,
          ),
        )

    # Add worst period info
    worst_period = forecast.get_worst_period()
    if worst_period:
      summary.worst_period = WorstPeriodSummary(  # noqa: E111
        start=worst_period[0].isoformat(),
        end=worst_period[1].isoformat(),
        advice="Plan indoor activities during this time",
      )

    return summary

  def get_active_alerts(  # noqa: E111
    self,
    severity_filter: WeatherSeverity | None = None,
    impact_filter: WeatherHealthImpact | None = None,
  ) -> list[WeatherAlert]:
    """Get currently active weather health alerts.

    Args:
        severity_filter: Filter by severity level
        impact_filter: Filter by health impact type

    Returns:
        List of active alerts matching filters
    """
    alerts = [alert for alert in self._active_alerts if alert.is_active]

    if severity_filter:
      alerts = [alert for alert in alerts if alert.severity == severity_filter]  # noqa: E111

    if impact_filter:
      alerts = [alert for alert in alerts if alert.alert_type == impact_filter]  # noqa: E111

    return alerts

  def get_weather_health_score(self) -> int:  # noqa: E111
    """Calculate weather-based health score for dogs (0-100).

    Returns:
        Health score where 100 is perfect conditions, 0 is dangerous
    """
    if not self._current_conditions or not self._current_conditions.is_valid:
      return 50  # Unknown conditions  # noqa: E111

    score = 100

    # Temperature scoring
    if self._current_conditions.temperature_c is not None:
      temp = self._current_conditions.temperature_c  # noqa: E111

      # Ideal temperature range for dogs: 15-22°C  # noqa: E114
      if 15 <= temp <= 22:  # noqa: E111
        score += 0  # Perfect
      elif 10 <= temp < 15 or 22 < temp <= 25:  # noqa: E111
        score -= 10  # Good
      elif 5 <= temp < 10 or 25 < temp <= 30:  # noqa: E111
        score -= 25  # Moderate concern
      elif 0 <= temp < 5 or 30 < temp <= 35:  # noqa: E111
        score -= 40  # High concern
      else:  # noqa: E111
        score -= 60  # Extreme concern

    # UV index scoring
    if self._current_conditions.uv_index is not None:
      uv = self._current_conditions.uv_index  # noqa: E111
      if uv > 8:  # noqa: E111
        score -= 20
      elif uv > 6:  # noqa: E111
        score -= 10
      elif uv > 3:  # noqa: E111
        score -= 5

    # Humidity scoring
    if self._current_conditions.humidity_percent is not None:
      humidity = self._current_conditions.humidity_percent  # noqa: E111
      if humidity > 85:  # noqa: E111
        score -= 15
      elif humidity > 70:  # noqa: E111
        score -= 10
      elif humidity < 30:  # noqa: E111
        score -= 5

    # Active alerts penalty
    for alert in self.get_active_alerts():
      if alert.severity == WeatherSeverity.EXTREME:  # noqa: E111
        score -= 30
      elif alert.severity == WeatherSeverity.HIGH:  # noqa: E111
        score -= 20
      elif alert.severity == WeatherSeverity.MODERATE:  # noqa: E111
        score -= 10

    return max(0, min(100, score))

  def get_recommendations_for_dog(  # noqa: E111
    self,
    dog_breed: str | None = None,
    dog_age_months: int | None = None,
    health_conditions: list[str] | None = None,
  ) -> list[str]:
    """Get personalized weather recommendations for specific dog.

    Args:
        dog_breed: Dog breed for breed-specific recommendations
        dog_age_months: Dog age for age-specific recommendations
        health_conditions: List of health conditions

    Returns:
        List of personalized recommendations
    """
    recommendations = []

    active_alerts = self.get_active_alerts()
    if not active_alerts:
      recommendations.append(  # noqa: E111
        "Weather conditions are suitable for normal activities",
      )
      return recommendations  # noqa: E111

    # Collect all recommendations from active alerts
    for alert in active_alerts:
      recommendations.extend(alert.recommendations)  # noqa: E111

      # Add breed-specific recommendations  # noqa: E114
      if dog_breed:  # noqa: E111
        breed_lower = dog_breed.lower()
        if breed_lower in alert.affected_breeds or any(
          breed_type in breed_lower for breed_type in alert.affected_breeds
        ):
          recommendations.append(  # noqa: E111
            self._get_translation(
              "weather.recommendations.breed_specific_caution",
              breed=dog_breed,
              alert_type=alert.title.lower(),
            ),
          )

      # Add age-specific recommendations  # noqa: E114
      if dog_age_months is not None:  # noqa: E111
        if dog_age_months < 12 and "puppies" in alert.age_considerations:
          recommendations.append(  # noqa: E111
            self._get_translation(
              "weather.recommendations.puppy_extra_monitoring",
            ),
          )
        elif dog_age_months > 84 and "senior_dogs" in alert.age_considerations:
          recommendations.append(  # noqa: E111
            self._get_translation(
              "weather.recommendations.senior_extra_protection",
            ),
          )

      # Add health condition considerations  # noqa: E114
      if health_conditions:  # noqa: E111
        for condition in health_conditions:
          condition_lower = condition.lower()  # noqa: E111
          if condition_lower in ["respiratory", "breathing", "asthma"] and (  # noqa: E111
            alert.alert_type
            in [
              WeatherHealthImpact.RESPIRATORY_RISK,
              WeatherHealthImpact.AIR_QUALITY,
            ]
          ):
            recommendations.append(
              self._get_translation(
                "weather.recommendations.respiratory_monitoring",
              ),
            )
          elif condition_lower in ["heart", "cardiac"] and (  # noqa: E111
            alert.alert_type
            in [
              WeatherHealthImpact.HEAT_STRESS,
              WeatherHealthImpact.EXERCISE_LIMITATION,
            ]
          ):
            recommendations.append(
              self._get_translation(
                "weather.recommendations.heart_avoid_strenuous",
              ),
            )

    # Remove duplicates while preserving order
    unique_recommendations = []
    for rec in recommendations:
      if rec not in unique_recommendations:  # noqa: E111
        unique_recommendations.append(rec)

    return unique_recommendations

  async def async_cleanup(self) -> None:  # noqa: E111
    """Cleanup weather manager resources."""
    self._active_alerts.clear()
    self._current_conditions = None
    self._current_forecast = None
    self._translations = empty_weather_translations()
    self._english_translations = self._translations
    _LOGGER.debug("Weather health manager cleaned up")
