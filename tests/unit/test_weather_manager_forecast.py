"""Tests for weather forecast analysis paths in weather_manager."""

from datetime import timedelta

import homeassistant.components.weather as weather_module
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest

from tests.weather_test_support import ensure_weather_module_compat

UnitOfTemperature = ensure_weather_module_compat()

from custom_components.pawcontrol.weather_manager import (  # noqa: E402
    ActivityTimeSlot,
    ForecastPoint,
    ForecastQuality,
    WeatherAlert,
    WeatherConditions,
    WeatherForecast,
    WeatherHealthImpact,
    WeatherHealthManager,
    WeatherSeverity,
)


@pytest.mark.unit
def test_coerce_helpers_reject_bool_values() -> None:
    """Boolean payloads should not be treated as numeric weather data."""
    assert WeatherHealthManager._coerce_float(True) is None
    assert WeatherHealthManager._coerce_int(False) is None
    assert WeatherHealthManager._coerce_float(3) == 3.0
    assert WeatherHealthManager._coerce_int(8.9) == 8


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_forecast_data_builds_forecast_and_windows(
    hass: HomeAssistant,
) -> None:
    """Forecast updates should normalize temperatures and expose planning windows."""
    manager = WeatherHealthManager(hass)
    await manager.async_load_translations()

    now = dt_util.utcnow()
    hass.states.async_set(
        "weather.home",
        "sunny",
        {
            weather_module.ATTR_FORECAST: [
                {
                    weather_module.ATTR_FORECAST_TIME: (
                        now + timedelta(hours=1)
                    ).isoformat(),
                    weather_module.ATTR_FORECAST_TEMP: 68.0,
                    weather_module.ATTR_FORECAST_TEMP_LOW: 59.0,
                    "temperature_unit": UnitOfTemperature.FAHRENHEIT,
                    weather_module.ATTR_FORECAST_HUMIDITY: 55,
                    weather_module.ATTR_FORECAST_UV_INDEX: 3,
                    weather_module.ATTR_FORECAST_WIND_SPEED: 8,
                    weather_module.ATTR_FORECAST_CONDITION: "partlycloudy",
                },
                {
                    weather_module.ATTR_FORECAST_TIME: (
                        now + timedelta(hours=2)
                    ).isoformat(),
                    weather_module.ATTR_FORECAST_TEMP: 20.0,
                    weather_module.ATTR_FORECAST_TEMP_LOW: 15.0,
                    "temperature_unit": UnitOfTemperature.CELSIUS,
                    weather_module.ATTR_FORECAST_HUMIDITY: 60,
                    weather_module.ATTR_FORECAST_UV_INDEX: 2,
                    weather_module.ATTR_FORECAST_WIND_SPEED: 7,
                    weather_module.ATTR_FORECAST_CONDITION: "sunny",
                },
                {
                    weather_module.ATTR_FORECAST_TIME: (
                        now + timedelta(hours=3)
                    ).isoformat(),
                    weather_module.ATTR_FORECAST_TEMP: 72.0,
                    weather_module.ATTR_FORECAST_TEMP_LOW: 60.0,
                    "temperature_unit": UnitOfTemperature.FAHRENHEIT,
                    weather_module.ATTR_FORECAST_HUMIDITY: 50,
                    weather_module.ATTR_FORECAST_UV_INDEX: 2,
                    weather_module.ATTR_FORECAST_WIND_SPEED: 8,
                    weather_module.ATTR_FORECAST_CONDITION: "sunny",
                },
            ]
        },
    )

    forecast = await manager.async_update_forecast_data(
        "weather.home", forecast_horizon_hours=6
    )

    assert forecast is not None
    assert forecast.source_entity == "weather.home"
    assert forecast.quality is ForecastQuality.POOR
    assert len(forecast.forecast_points) == 3
    assert forecast.forecast_points[0].temperature_c == pytest.approx(20.0)
    assert forecast.avg_health_score is not None
    assert manager.get_next_optimal_activity_time("walk") is not None


@pytest.mark.unit
def test_get_forecast_planning_summary_includes_next_slots_and_worst_period(
    hass: HomeAssistant,
) -> None:
    """Planning summary should serialize structured forecast details."""
    manager = WeatherHealthManager(hass)
    now = dt_util.utcnow()
    manager._current_forecast = WeatherForecast(
        forecast_points=[
            ForecastPoint(timestamp=now + timedelta(hours=1), health_score=85),
            ForecastPoint(timestamp=now + timedelta(hours=2), health_score=35),
        ],
        generated_at=now,
        quality=ForecastQuality.GOOD,
        min_health_score=35,
        max_health_score=85,
        avg_health_score=60,
        critical_periods=[(now + timedelta(hours=2), now + timedelta(hours=3))],
        optimal_activity_windows=[
            ActivityTimeSlot(
                start_time=now + timedelta(hours=1),
                end_time=now + timedelta(hours=2),
                health_score=85,
                activity_type="walk",
                recommendations=["Ideal conditions for this activity"],
                alert_level=WeatherSeverity.LOW,
            )
        ],
    )

    summary = manager.get_forecast_planning_summary()

    assert summary.status == "available"
    assert summary.forecast_quality == ForecastQuality.GOOD.value
    assert summary.score_range is not None
    assert summary.score_range.min == 35
    assert summary.next_walk_time is not None
    assert summary.worst_period is not None
    assert summary.worst_period.advice == "Plan indoor activities during this time"


@pytest.mark.unit
def test_get_recommendations_for_dog_adds_personalized_guidance(
    hass: HomeAssistant,
) -> None:
    """Breed, age, and health conditions should add personalized recommendations."""
    manager = WeatherHealthManager(hass)
    manager._current_conditions = WeatherConditions(
        temperature_c=32.0,
        humidity_percent=90,
        condition="rain",
        last_updated=dt_util.utcnow(),
    )
    manager._active_alerts = [
        WeatherAlert(
            alert_type=WeatherHealthImpact.HEAT_STRESS,
            severity=WeatherSeverity.HIGH,
            title="Heat alert",
            message="message",
            recommendations=["Provide water", "Provide water"],
            affected_breeds=["retriever"],
            age_considerations=["senior_dogs"],
        ),
        WeatherAlert(
            alert_type=WeatherHealthImpact.RESPIRATORY_RISK,
            severity=WeatherSeverity.MODERATE,
            title="Humidity alert",
            message="message",
            recommendations=["Keep sessions short"],
        ),
    ]

    recommendations = manager.get_recommendations_for_dog(
        dog_breed="Labrador Retriever",
        dog_age_months=120,
        health_conditions=["asthma", "cardiac"],
    )
    expected_breed = manager._get_translation(
        "weather.recommendations.breed_specific_caution",
        breed="Labrador Retriever",
        alert_type="heat alert",
    )
    expected_senior = manager._get_translation(
        "weather.recommendations.senior_extra_protection"
    )
    expected_respiratory = manager._get_translation(
        "weather.recommendations.respiratory_monitoring"
    )
    expected_heart = manager._get_translation(
        "weather.recommendations.heart_avoid_strenuous"
    )

    assert "Provide water" in recommendations
    assert expected_breed in recommendations
    assert expected_senior in recommendations
    assert expected_respiratory in recommendations
    assert expected_heart in recommendations
    assert recommendations.count("Provide water") == 1


@pytest.mark.unit
def test_get_active_alerts_filters_and_excludes_expired(hass: HomeAssistant) -> None:
    """Expired alerts should be hidden and filters should narrow the result set."""
    manager = WeatherHealthManager(hass)
    old = dt_util.utcnow() - timedelta(hours=10)
    manager._active_alerts = [
        WeatherAlert(
            alert_type=WeatherHealthImpact.HEAT_STRESS,
            severity=WeatherSeverity.HIGH,
            title="hot",
            message="msg",
            duration_hours=1,
            timestamp=old,
        ),
        WeatherAlert(
            alert_type=WeatherHealthImpact.UV_EXPOSURE,
            severity=WeatherSeverity.MODERATE,
            title="uv",
            message="msg",
            duration_hours=5,
            timestamp=dt_util.utcnow(),
        ),
    ]

    assert len(manager.get_active_alerts()) == 1
    assert (
        manager.get_active_alerts(severity_filter=WeatherSeverity.MODERATE)[0].title
        == "uv"
    )
    assert (
        manager.get_active_alerts(impact_filter=WeatherHealthImpact.HEAT_STRESS) == []
    )


@pytest.mark.unit
def test_find_activity_windows_splits_windows_on_state_transitions(
    hass: HomeAssistant,
) -> None:
    """Planning windows should split when forecast suitability flips."""
    manager = WeatherHealthManager(hass)
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    manager._current_forecast = WeatherForecast(
        forecast_points=[
            ForecastPoint(timestamp=now + timedelta(hours=1), health_score=82),
            ForecastPoint(timestamp=now + timedelta(hours=2), health_score=79),
            ForecastPoint(timestamp=now + timedelta(hours=3), health_score=55),
            ForecastPoint(timestamp=now + timedelta(hours=4), health_score=88),
            ForecastPoint(timestamp=now + timedelta(hours=5), health_score=90),
            ForecastPoint(timestamp=now + timedelta(hours=6), health_score=40),
        ],
    )

    windows = manager._find_activity_windows(
        activity_type="walk",
        min_score=60,
        min_duration_hours=1,
    )

    assert len(windows) == 2
    assert windows[0].start_time == now + timedelta(hours=1)
    assert windows[0].end_time == now + timedelta(hours=3)
    assert windows[0].health_score == 80
    assert windows[1].start_time == now + timedelta(hours=4)
    assert windows[1].end_time == now + timedelta(hours=6)
    assert windows[1].health_score == 89


@pytest.mark.unit
def test_find_activity_windows_ignores_too_short_time_windows(
    hass: HomeAssistant,
) -> None:
    """Sub-threshold windows should be rejected by duration guardrails."""
    manager = WeatherHealthManager(hass)
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    manager._current_forecast = WeatherForecast(
        forecast_points=[
            ForecastPoint(timestamp=now + timedelta(minutes=0), health_score=92),
            ForecastPoint(timestamp=now + timedelta(minutes=30), health_score=91),
            ForecastPoint(timestamp=now + timedelta(minutes=45), health_score=25),
            ForecastPoint(timestamp=now + timedelta(hours=1), health_score=95),
            ForecastPoint(timestamp=now + timedelta(hours=2), health_score=96),
            ForecastPoint(timestamp=now + timedelta(hours=3), health_score=20),
        ],
    )

    windows = manager._find_activity_windows(
        activity_type="exercise",
        min_score=75,
        min_duration_hours=1,
    )

    assert len(windows) == 1
    assert windows[0].start_time == now + timedelta(hours=1)
    assert windows[0].end_time == now + timedelta(hours=3)
    assert windows[0].health_score == 95
    assert windows[0].alert_level is WeatherSeverity.LOW


@pytest.mark.unit
def test_identify_optimal_activity_windows_handles_invalid_inputs_gracefully(
    hass: HomeAssistant,
) -> None:
    """None scores should act as invalid input and close active windows cleanly."""
    manager = WeatherHealthManager(hass)
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    manager._current_forecast = WeatherForecast(
        forecast_points=[
            ForecastPoint(timestamp=now + timedelta(hours=1), health_score=65),
            ForecastPoint(timestamp=now + timedelta(hours=2), health_score=None),
            ForecastPoint(timestamp=now + timedelta(hours=3), health_score=78),
            ForecastPoint(timestamp=now + timedelta(hours=4), health_score=82),
            ForecastPoint(timestamp=now + timedelta(hours=5), health_score=35),
        ],
    )

    windows = manager._find_activity_windows(
        activity_type="walk",
        min_score=60,
        min_duration_hours=1,
    )

    assert len(windows) == 2
    assert windows[0].start_time == now + timedelta(hours=1)
    assert windows[0].end_time == now + timedelta(hours=2)
    assert windows[0].health_score == 65
    assert windows[1].start_time == now + timedelta(hours=3)
    assert windows[1].end_time == now + timedelta(hours=5)
    assert windows[1].health_score == 80
    assert all(window.start_time < window.end_time for window in windows)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_identify_optimal_activity_windows_creates_sorted_planning_timeline(
    hass: HomeAssistant,
) -> None:
    """Planner should emit sorted windows across activity thresholds."""
    manager = WeatherHealthManager(hass)
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    manager._current_forecast = WeatherForecast(
        forecast_points=[
            ForecastPoint(timestamp=now + timedelta(hours=1), health_score=62),
            ForecastPoint(timestamp=now + timedelta(hours=2), health_score=74),
            ForecastPoint(timestamp=now + timedelta(hours=3), health_score=81),
            ForecastPoint(timestamp=now + timedelta(hours=4), health_score=84),
            ForecastPoint(timestamp=now + timedelta(hours=5), health_score=59),
            ForecastPoint(timestamp=now + timedelta(hours=6), health_score=76),
            ForecastPoint(timestamp=now + timedelta(hours=7), health_score=79),
            ForecastPoint(timestamp=now + timedelta(hours=8), health_score=45),
        ],
    )

    await manager._identify_optimal_activity_windows()
    timeline = manager._current_forecast.optimal_activity_windows

    assert timeline
    assert timeline == sorted(timeline, key=lambda slot: slot.start_time)
    assert {slot.activity_type for slot in timeline} >= {
        "walk",
        "play",
        "exercise",
        "basic_needs",
    }
    walk_windows = [slot for slot in timeline if slot.activity_type == "walk"]
    assert walk_windows[0].start_time == now + timedelta(hours=1)
    assert walk_windows[-1].end_time <= now + timedelta(hours=8)
