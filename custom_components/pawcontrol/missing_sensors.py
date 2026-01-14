"""Supplementary sensors that expose derived PawControl telemetry."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Protocol, cast

from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfLength, UnitOfTime
from homeassistant.util import dt as dt_util

from .coordinator import PawControlCoordinator
from .diagnostics import normalize_value
from .sensor import PawControlSensorBase, register_sensor
from .types import (
    DogConfigData,
    FeedingModuleTelemetry,
    HealthModulePayload,
    JSONMutableMapping,
    JSONValue,
    WalkModuleTelemetry,
    WalkSessionSnapshot,
    ensure_json_mapping,
)
from .utils import DateTimeConvertible, ensure_utc_datetime

__all__ = [
    "PawControlActivityLevelSensor",
    "PawControlCaloriesBurnedTodaySensor",
    "PawControlLastFeedingHoursSensor",
    "PawControlTotalWalkDistanceSensor",
    "PawControlWalksThisWeekSensor",
    "calculate_activity_level",
    "calculate_calories_burned_today",
    "calculate_hours_since",
    "derive_next_feeding_time",
]


type ModuleSnapshot[T] = T | None
type WalkHistory = list[WalkSessionSnapshot]


class _ModuleDataProvider(Protocol):
    """Protocol describing objects that expose module data accessors."""

    def _get_module_data(self, module: str) -> Mapping[str, JSONValue] | None:
        """Return coordinator data for the requested module."""


def _walk_payload(
    provider: _ModuleDataProvider,
) -> ModuleSnapshot[WalkModuleTelemetry]:
    module_data = provider._get_module_data("walk")
    if module_data is None or not isinstance(module_data, Mapping):
        return None
    return cast(WalkModuleTelemetry, module_data)


def _health_payload(
    provider: _ModuleDataProvider,
) -> ModuleSnapshot[HealthModulePayload]:
    module_data = provider._get_module_data("health")
    if module_data is None or not isinstance(module_data, Mapping):
        return None
    return cast(HealthModulePayload, module_data)


def _feeding_payload(
    provider: _ModuleDataProvider,
) -> ModuleSnapshot[FeedingModuleTelemetry]:
    module_data = provider._get_module_data("feeding")
    if module_data is None or not isinstance(module_data, Mapping):
        return None
    return cast(FeedingModuleTelemetry, module_data)


def _normalise_attributes(attrs: JSONMutableMapping) -> JSONMutableMapping:
    """Return JSON-serialisable attributes for missing sensors."""

    return cast(JSONMutableMapping, normalize_value(attrs))


def calculate_activity_level(
    walk_data: ModuleSnapshot[WalkModuleTelemetry],
    health_data: ModuleSnapshot[HealthModulePayload],
) -> str:
    """Determine the activity level based on walk telemetry and health inputs."""

    if walk_data is None and health_data is None:
        return "unknown"

    try:
        walks_today = int(walk_data["walks_today"]) if walk_data else 0
        total_duration_today = (
            float(walk_data["total_duration_today"]) if walk_data else 0.0
        )

        if walks_today >= 3 and total_duration_today >= 90:
            calculated_level = "very_high"
        elif walks_today >= 2 and total_duration_today >= 60:
            calculated_level = "high"
        elif walks_today >= 1 and total_duration_today >= 30:
            calculated_level = "moderate"
        elif walks_today >= 1 or total_duration_today >= 15:
            calculated_level = "low"
        else:
            calculated_level = "very_low"

        health_activity: str | None = None
        if health_data and "activity_level" in health_data:
            candidate = health_data["activity_level"]
            health_activity = candidate if isinstance(candidate, str) else None

        if health_activity:
            activity_levels = [
                "very_low",
                "low",
                "moderate",
                "high",
                "very_high",
            ]
            health_index = (
                activity_levels.index(health_activity)
                if health_activity in activity_levels
                else 2
            )
            calculated_index = activity_levels.index(calculated_level)
            return activity_levels[max(health_index, calculated_index)]

        return calculated_level
    except (TypeError, ValueError, IndexError):
        return "unknown"


def calculate_calories_burned_today(
    walk_data: ModuleSnapshot[WalkModuleTelemetry],
    dog_weight_kg: float,
    health_data: ModuleSnapshot[HealthModulePayload],
) -> float:
    """Estimate calories burned today using walk telemetry and weight."""

    if walk_data is None and health_data is None:
        return 0.0

    try:
        total_duration_minutes = (
            float(walk_data["total_duration_today"]) if walk_data else 0.0
        )
        total_distance_meters = (
            float(walk_data["total_distance_today"]) if walk_data else 0.0
        )

        calories_burned = 0.0
        if total_duration_minutes > 0:
            calories_burned += dog_weight_kg * total_duration_minutes * 0.5
        if total_distance_meters > 0:
            calories_burned += dog_weight_kg * (total_distance_meters / 100.0)

        raw_activity: str | None = None
        if health_data and "activity_level" in health_data:
            candidate = health_data["activity_level"]
            raw_activity = candidate if isinstance(candidate, str) else None
        activity_level = raw_activity or "moderate"
        multipliers = {
            "very_low": 0.7,
            "low": 0.85,
            "moderate": 1.0,
            "high": 1.2,
            "very_high": 1.4,
        }
        multiplier = multipliers.get(activity_level, 1.0)
        return round(calories_burned * multiplier, 1)
    except (TypeError, ValueError):
        return 0.0


def calculate_hours_since(
    timestamp: DateTimeConvertible | None,
    *,
    reference: datetime | None = None,
) -> float | None:
    """Calculate elapsed hours since the provided timestamp."""

    if not timestamp:
        return None

    last_event = ensure_utc_datetime(timestamp)
    if last_event is None:
        return None

    now = reference or dt_util.utcnow()
    return (now - last_event).total_seconds() / 3600


def derive_next_feeding_time(
    feeding_data: ModuleSnapshot[FeedingModuleTelemetry],
) -> str | None:
    """Compute the next feeding time based on the configured schedule."""

    if feeding_data is None:
        return None

    try:
        if "config" not in feeding_data:
            return None
        config = feeding_data["config"]
        if "meals_per_day" not in config:
            return None
        meals_per_day = int(config["meals_per_day"])
        if meals_per_day <= 0:
            return None

        hours_between_meals = 24 / meals_per_day
        if "last_feeding" not in feeding_data or feeding_data["last_feeding"] is None:
            return None
        last_feeding_dt = ensure_utc_datetime(feeding_data["last_feeding"])
        if last_feeding_dt is None:
            return None

        next_feeding_dt = last_feeding_dt + timedelta(hours=hours_between_meals)
        return next_feeding_dt.strftime("%H:%M")
    except (TypeError, ValueError, ZeroDivisionError):
        return None


@register_sensor("activity_level")
class PawControlActivityLevelSensor(PawControlSensorBase):
    """Sensor for the current activity level of a dog."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
    ) -> None:
        """Initialize the activity level sensor for the specified dog."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "activity_level",
            icon="mdi:run",
            translation_key="activity_level",
        )

    @property
    def native_value(self) -> str:
        """Return the derived activity level from walk and health payloads."""
        walk_data = _walk_payload(self)
        health_data = _health_payload(self)
        return calculate_activity_level(walk_data, health_data)

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return supplemental activity telemetry for diagnostics."""
        attrs = ensure_json_mapping(super().extra_state_attributes)
        walk_data = _walk_payload(self)
        health_data = _health_payload(self)

        if walk_data:
            with contextlib.suppress(TypeError, ValueError):
                last_walk = cast(
                    DateTimeConvertible | None,
                    walk_data.get("last_walk"),
                )
                attrs.update(
                    {
                        "walks_today": int(cast(int, walk_data.get("walks_today", 0))),
                        "total_walk_minutes_today": float(
                            cast(
                                float,
                                walk_data.get(
                                    "total_duration_today",
                                    0.0,
                                ),
                            ),
                        ),
                        "last_walk_hours_ago": calculate_hours_since(last_walk),
                    },
                )

        if health_data:
            activity_level = cast(
                str | None,
                health_data.get("activity_level"),
            )
            attrs["health_activity_level"] = activity_level
            attrs["activity_source"] = "health_data" if activity_level else "calculated"

        return _normalise_attributes(attrs)


@register_sensor("calories_burned_today")
class PawControlCaloriesBurnedTodaySensor(PawControlSensorBase):
    """Sensor estimating calories burned today."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
    ) -> None:
        """Initialize the calories burned sensor for the specified dog."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "calories_burned_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfEnergy.KILO_CALORIE,
            icon="mdi:fire",
            translation_key="calories_burned_today",
        )

    def _resolve_dog_weight(
        self,
        health_data: ModuleSnapshot[HealthModulePayload],
    ) -> float:
        weight = 25.0
        if health_data and "weight" in health_data:
            reported_weight = health_data["weight"]
            if reported_weight is not None:
                with contextlib.suppress(TypeError, ValueError):
                    weight = float(reported_weight)

        dog_data = self._get_dog_data()
        if dog_data and "dog_info" in dog_data:
            dog_info = cast(DogConfigData, dog_data["dog_info"])
            if "dog_weight" in dog_info and dog_info["dog_weight"] is not None:
                with contextlib.suppress(TypeError, ValueError):
                    weight = float(dog_info["dog_weight"])
        return weight

    @property
    def native_value(self) -> float:
        """Estimate the calories burned today for the active dog."""
        walk_data = _walk_payload(self)
        health_data = _health_payload(self)
        dog_weight = self._resolve_dog_weight(health_data)
        return calculate_calories_burned_today(walk_data, dog_weight, health_data)

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Provide supporting data for the calories burned calculation."""
        attrs = ensure_json_mapping(super().extra_state_attributes)
        walk_data = _walk_payload(self)
        health_data = _health_payload(self)
        dog_weight = self._resolve_dog_weight(health_data)

        with contextlib.suppress(TypeError, ValueError):
            walk_minutes = (
                float(walk_data["total_duration_today"]) if walk_data else 0.0
            )
            walk_distance = (
                float(walk_data["total_distance_today"]) if walk_data else 0.0
            )
            activity_level = "moderate"
            if health_data and "activity_level" in health_data:
                candidate = health_data["activity_level"]
                if isinstance(candidate, str):
                    activity_level = candidate
            attrs.update(
                {
                    "dog_weight_kg": dog_weight,
                    "walk_minutes_today": walk_minutes,
                    "walk_distance_meters_today": walk_distance,
                    "activity_level": activity_level,
                    "calories_per_minute": round(dog_weight * 0.5, 2),
                    "calories_per_100m": round(dog_weight * 1.0, 2),
                },
            )

        return _normalise_attributes(attrs)


@register_sensor("last_feeding_hours")
class PawControlLastFeedingHoursSensor(PawControlSensorBase):
    """Sensor reporting hours since the last feeding."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
    ) -> None:
        """Initialize the last feeding hours sensor for the specified dog."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_feeding_hours",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTime.HOURS,
            icon="mdi:clock-time-four",
            translation_key="last_feeding_hours",
        )

    @property
    def native_value(self) -> float | None:
        """Return hours elapsed since the last recorded feeding."""
        feeding_data = _feeding_payload(self)
        if feeding_data is None:
            return None

        last_feeding = cast(
            DateTimeConvertible | None,
            feeding_data.get("last_feeding"),
        )
        hours_since = calculate_hours_since(last_feeding)
        return round(hours_since, 1) if hours_since is not None else None

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return contextual feeding metadata for diagnostics."""
        attrs = ensure_json_mapping(super().extra_state_attributes)
        feeding_data = _feeding_payload(self)
        if feeding_data is None:
            return attrs

        with contextlib.suppress(TypeError, ValueError):
            last_feeding = cast(
                DateTimeConvertible | None,
                feeding_data.get("last_feeding"),
            )
            feedings_today = cast(
                int,
                feeding_data.get("total_feedings_today", 0),
            )
            serialized_last_feeding: str | float | int | None
            if isinstance(last_feeding, datetime):
                serialized_last_feeding = dt_util.as_utc(
                    last_feeding,
                ).isoformat()
            elif isinstance(last_feeding, (float, int)):
                serialized_last_feeding = float(last_feeding)
            elif isinstance(last_feeding, str):
                serialized_last_feeding = last_feeding
            else:
                serialized_last_feeding = None
            attrs.update(
                {
                    "last_feeding_time": serialized_last_feeding,
                    "feedings_today": int(feedings_today),
                    "is_overdue": self._is_feeding_overdue(feeding_data),
                    "next_feeding_due": derive_next_feeding_time(feeding_data),
                },
            )

        return _normalise_attributes(attrs)

    def _is_feeding_overdue(
        self,
        feeding_data: ModuleSnapshot[FeedingModuleTelemetry],
    ) -> bool:
        last_feeding = cast(
            DateTimeConvertible | None,
            feeding_data.get("last_feeding") if feeding_data else None,
        )
        hours_since = calculate_hours_since(last_feeding)
        if hours_since is None:
            return False
        return hours_since > 8.0


@register_sensor("total_walk_distance")
class PawControlTotalWalkDistanceSensor(PawControlSensorBase):
    """Sensor exposing the lifetime walk distance."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
    ) -> None:
        """Initialize the lifetime walk distance sensor for the specified dog."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "total_walk_distance",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfLength.KILOMETERS,
            icon="mdi:map-marker-path",
            translation_key="total_walk_distance",
        )

    @property
    def native_value(self) -> float:
        """Return the lifetime walking distance expressed in kilometres."""
        walk_data = _walk_payload(self)
        if walk_data is None:
            return 0.0

        try:
            total_distance_value = cast(
                float | int | None,
                walk_data.get("total_distance_lifetime", 0.0),
            )
            total_distance_meters = float(total_distance_value or 0.0)
            if total_distance_meters == 0.0 and "walks_history" in walk_data:
                walks_history = walk_data["walks_history"]
                if walks_history:
                    for walk in walks_history:
                        with contextlib.suppress(TypeError, ValueError):
                            distance_value = cast(
                                float | int | None,
                                walk.get("distance"),
                            )
                            if isinstance(distance_value, int | float):
                                total_distance_meters += float(distance_value)
            return round(total_distance_meters / 1000, 2)
        except (TypeError, ValueError):
            return 0.0

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return aggregated walk distance metrics for the dog."""
        attrs = ensure_json_mapping(super().extra_state_attributes)
        walk_data = _walk_payload(self)
        if walk_data is None:
            return attrs

        with contextlib.suppress(TypeError, ValueError):
            total_distance_value = cast(
                float | int | None,
                walk_data.get("total_distance_lifetime", 0.0),
            )
            total_distance_m = float(total_distance_value or 0.0)
            total_walks_value = cast(
                int | float | None,
                walk_data.get("total_walks_lifetime", 0),
            )
            total_walks = int(total_walks_value or 0)
            distance_this_week = cast(
                float | int | None,
                walk_data.get("distance_this_week", 0.0),
            )
            distance_this_month = cast(
                float | int | None,
                walk_data.get("distance_this_month", 0.0),
            )
            attrs.update(
                {
                    "total_walks": total_walks,
                    "total_distance_meters": total_distance_m,
                    "average_distance_per_walk_km": round(
                        (total_distance_m / 1000) / max(1, total_walks),
                        2,
                    ),
                    "distance_this_week_km": round(
                        float(distance_this_week or 0.0) / 1000,
                        2,
                    ),
                    "distance_this_month_km": round(
                        float(distance_this_month or 0.0) / 1000,
                        2,
                    ),
                },
            )

        return _normalise_attributes(attrs)


@register_sensor("walks_this_week")
class PawControlWalksThisWeekSensor(PawControlSensorBase):
    """Sensor tracking the number of walks completed during the current week."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
    ) -> None:
        """Initialize the weekly walk count sensor for the specified dog."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "walks_this_week",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:calendar-week",
            translation_key="walks_this_week",
        )

    @property
    def native_value(self) -> int:
        """Return the total number of walks completed during the week."""
        walk_data = _walk_payload(self)
        if walk_data is None:
            return 0

        try:
            walks_this_week = int(
                cast(int, walk_data.get("walks_this_week", 0)),
            )
            if walks_this_week:
                return walks_this_week

            if "walks_history" not in walk_data:
                return walks_this_week
            walks_history = walk_data["walks_history"]

            now = dt_util.utcnow()
            start_of_week = now - timedelta(days=now.weekday())
            start_of_week = start_of_week.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            for walk in walks_history:
                walk_time_candidate = walk.get("timestamp")
                if not walk_time_candidate:
                    walk_time_candidate = walk.get("end_time")
                if not isinstance(walk_time_candidate, str | datetime | int | float):
                    continue
                walk_time = ensure_utc_datetime(walk_time_candidate)
                if walk_time and walk_time >= start_of_week:
                    walks_this_week += 1
            return walks_this_week
        except (TypeError, ValueError):
            return 0

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Expose weekly walk statistics derived from coordinator payloads."""
        attrs = ensure_json_mapping(super().extra_state_attributes)
        walk_data = _walk_payload(self)
        if walk_data is None:
            return attrs

        with contextlib.suppress(TypeError, ValueError):
            walks_today = int(cast(int, walk_data.get("walks_today", 0)))
            total_duration_this_week = float(
                cast(float, walk_data.get("total_duration_this_week", 0.0)),
            )
            distance_this_week = float(
                cast(float, walk_data.get("distance_this_week", 0.0)),
            )
            now = dt_util.utcnow()
            days_this_week = now.weekday() + 1
            avg_walks_per_day = (self.native_value or 0) / max(1, days_this_week)
            attrs.update(
                {
                    "walks_today": walks_today,
                    "total_duration_this_week_minutes": total_duration_this_week,
                    "total_distance_this_week_meters": distance_this_week,
                    "average_walks_per_day": round(avg_walks_per_day, 1),
                    "days_this_week": days_this_week,
                    "distance_this_week_km": round(distance_this_week / 1000, 2),
                },
            )

        return _normalise_attributes(attrs)
