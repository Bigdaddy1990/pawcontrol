"""Supplementary sensors that expose derived PawControl telemetry."""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
from typing import Any, Protocol, cast

from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfLength, UnitOfTime
from homeassistant.util import dt as dt_util

from .coordinator import PawControlCoordinator
from .sensor import AttributeDict, PawControlSensorBase, register_sensor
from .types import (
    FeedingModuleTelemetry,
    HealthModulePayload,
    WalkModuleTelemetry,
    WalkSessionSnapshot,
)
from .utils import ensure_utc_datetime

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

    def _get_module_data(self, module: str) -> dict[str, Any] | None:
        """Return coordinator data for the requested module."""


def _walk_payload(
    provider: _ModuleDataProvider,
) -> ModuleSnapshot[WalkModuleTelemetry]:
    module_data = provider._get_module_data("walk")
    if module_data is None:
        return None
    return cast(WalkModuleTelemetry, module_data)


def _health_payload(
    provider: _ModuleDataProvider,
) -> ModuleSnapshot[HealthModulePayload]:
    module_data = provider._get_module_data("health")
    if module_data is None:
        return None
    return cast(HealthModulePayload, module_data)


def _feeding_payload(
    provider: _ModuleDataProvider,
) -> ModuleSnapshot[FeedingModuleTelemetry]:
    module_data = provider._get_module_data("feeding")
    if module_data is None:
        return None
    return cast(FeedingModuleTelemetry, module_data)


def calculate_activity_level(
    walk_data: ModuleSnapshot[WalkModuleTelemetry],
    health_data: ModuleSnapshot[HealthModulePayload],
) -> str:
    """Determine the activity level based on walk telemetry and health inputs."""

    if not walk_data and not health_data:
        return "unknown"

    try:
        walks_today = int(walk_data.get("walks_today", 0)) if walk_data else 0
        total_duration_today = float(
            walk_data.get("total_duration_today", 0.0)
        ) if walk_data else 0.0

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

        health_activity = (
            health_data.get("activity_level") if health_data else None
        )
        if health_activity:
            activity_levels = ["very_low", "low", "moderate", "high", "very_high"]
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

    if not walk_data and not health_data:
        return 0.0

    try:
        total_duration_raw = (
            walk_data.get("total_duration_today") if walk_data else 0.0
        )
        total_distance_raw = (
            walk_data.get("total_distance_today") if walk_data else 0.0
        )
        total_duration_minutes = float(total_duration_raw or 0.0)
        total_distance_meters = float(total_distance_raw or 0.0)

        calories_burned = 0.0
        if total_duration_minutes > 0:
            calories_burned += dog_weight_kg * total_duration_minutes * 0.5
        if total_distance_meters > 0:
            calories_burned += dog_weight_kg * (total_distance_meters / 100.0)

        raw_activity = health_data.get("activity_level") if health_data else None
        activity_level = raw_activity if isinstance(raw_activity, str) else "moderate"
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
    timestamp: Any,
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

    if not feeding_data:
        return None

    try:
        config = feeding_data.get("config") or {}
        meals_per_day = int(config.get("meals_per_day", 2))
        if meals_per_day <= 0:
            return None

        hours_between_meals = 24 / meals_per_day
        last_feeding = feeding_data.get("last_feeding")
        if not last_feeding:
            return None

        last_feeding_dt = ensure_utc_datetime(last_feeding)
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
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
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
        walk_data = _walk_payload(self)
        health_data = _health_payload(self)
        return calculate_activity_level(walk_data, health_data)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        attrs: AttributeDict = dict(super().extra_state_attributes or {})
        walk_data = _walk_payload(self)
        health_data = _health_payload(self)

        if walk_data:
            with contextlib.suppress(TypeError, ValueError):
                attrs.update(
                    {
                        "walks_today": int(walk_data.get("walks_today", 0)),
                        "total_walk_minutes_today": float(
                            walk_data.get("total_duration_today", 0.0)
                        ),
                        "last_walk_hours_ago": calculate_hours_since(
                            walk_data.get("last_walk")
                        ),
                    }
                )

        if health_data:
            attrs["health_activity_level"] = health_data.get("activity_level")
            attrs["activity_source"] = (
                "health_data"
                if health_data.get("activity_level")
                else "calculated"
            )

        return attrs


@register_sensor("calories_burned_today")
class PawControlCaloriesBurnedTodaySensor(PawControlSensorBase):
    """Sensor estimating calories burned today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
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
        self, health_data: ModuleSnapshot[HealthModulePayload]
    ) -> float:
        weight = 25.0
        if health_data and (reported_weight := health_data.get("weight")) is not None:
            with contextlib.suppress(TypeError, ValueError):
                weight = float(reported_weight)

        dog_data = self._get_dog_data()
        if dog_data and isinstance(dog_data.get("dog_info"), dict):
            dog_info = cast(dict[str, Any], dog_data["dog_info"])
            with contextlib.suppress(TypeError, ValueError):
                weight = float(dog_info.get("dog_weight", weight))
        return weight

    @property
    def native_value(self) -> float:
        walk_data = _walk_payload(self)
        health_data = _health_payload(self)
        dog_weight = self._resolve_dog_weight(health_data)
        return calculate_calories_burned_today(walk_data, dog_weight, health_data)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        attrs: AttributeDict = dict(super().extra_state_attributes or {})
        walk_data = _walk_payload(self)
        health_data = _health_payload(self)
        dog_weight = self._resolve_dog_weight(health_data)

        with contextlib.suppress(TypeError, ValueError):
            walk_minutes_raw = (
                walk_data.get("total_duration_today") if walk_data else 0.0
            )
            walk_distance_raw = (
                walk_data.get("total_distance_today") if walk_data else 0.0
            )
            walk_minutes = float(walk_minutes_raw or 0.0)
            walk_distance = float(walk_distance_raw or 0.0)
            activity_level = (
                health_data.get("activity_level", "moderate")
                if health_data
                else "moderate"
            )
            attrs.update(
                {
                    "dog_weight_kg": dog_weight,
                    "walk_minutes_today": walk_minutes,
                    "walk_distance_meters_today": walk_distance,
                    "activity_level": activity_level,
                    "calories_per_minute": round(dog_weight * 0.5, 2),
                    "calories_per_100m": round(dog_weight * 1.0, 2),
                }
            )

        return attrs


@register_sensor("last_feeding_hours")
class PawControlLastFeedingHoursSensor(PawControlSensorBase):
    """Sensor reporting hours since the last feeding."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
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
        feeding_data = _feeding_payload(self)
        if not feeding_data:
            return None

        hours_since = calculate_hours_since(feeding_data.get("last_feeding"))
        return round(hours_since, 1) if hours_since is not None else None

    @property
    def extra_state_attributes(self) -> AttributeDict:
        attrs: AttributeDict = dict(super().extra_state_attributes or {})
        feeding_data = _feeding_payload(self)
        if not feeding_data:
            return attrs

        with contextlib.suppress(TypeError, ValueError):
            attrs.update(
                {
                    "last_feeding_time": feeding_data.get("last_feeding"),
                    "feedings_today": int(
                        feeding_data.get("total_feedings_today", 0)
                    ),
                    "is_overdue": self._is_feeding_overdue(feeding_data),
                    "next_feeding_due": derive_next_feeding_time(feeding_data),
                }
            )

        return attrs

    def _is_feeding_overdue(
        self, feeding_data: ModuleSnapshot[FeedingModuleTelemetry]
    ) -> bool:
        hours_since = calculate_hours_since(
            feeding_data.get("last_feeding") if feeding_data else None
        )
        if hours_since is None:
            return False
        return hours_since > 8.0


@register_sensor("total_walk_distance")
class PawControlTotalWalkDistanceSensor(PawControlSensorBase):
    """Sensor exposing the lifetime walk distance."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
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
        walk_data = _walk_payload(self)
        if not walk_data:
            return 0.0

        try:
            total_distance_meters = float(
                walk_data.get("total_distance_lifetime", 0.0)
            )
            if total_distance_meters == 0.0:
                walks_history = cast(WalkHistory | None, walk_data.get("walks_history"))
                if walks_history:
                    for walk in walks_history:
                        with contextlib.suppress(TypeError, ValueError):
                            distance_value = walk.get("distance")
                            if isinstance(distance_value, int | float):
                                total_distance_meters += float(distance_value)
            return round(total_distance_meters / 1000, 2)
        except (TypeError, ValueError):
            return 0.0

    @property
    def extra_state_attributes(self) -> AttributeDict:
        attrs: AttributeDict = dict(super().extra_state_attributes or {})
        walk_data = _walk_payload(self)
        if not walk_data:
            return attrs

        with contextlib.suppress(TypeError, ValueError):
            total_distance_m = float(
                walk_data.get("total_distance_lifetime") or 0.0
            )
            total_walks = int(walk_data.get("total_walks_lifetime", 0))
            attrs.update(
                {
                    "total_walks": total_walks,
                    "total_distance_meters": total_distance_m,
                    "average_distance_per_walk_km": round(
                        (total_distance_m / 1000) / max(1, total_walks), 2
                    ),
                    "distance_this_week_km": round(
                        float(walk_data.get("distance_this_week") or 0.0) / 1000, 2
                    ),
                    "distance_this_month_km": round(
                        float(walk_data.get("distance_this_month") or 0.0) / 1000, 2
                    ),
                }
            )

        return attrs


@register_sensor("walks_this_week")
class PawControlWalksThisWeekSensor(PawControlSensorBase):
    """Sensor tracking the number of walks completed during the current week."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
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
        walk_data = _walk_payload(self)
        if not walk_data:
            return 0

        try:
            walks_this_week = int(walk_data.get("walks_this_week", 0))
            if walks_this_week:
                return walks_this_week

            walks_history = cast(WalkHistory | None, walk_data.get("walks_history"))
            if not walks_history:
                return walks_this_week

            now = dt_util.utcnow()
            start_of_week = now - timedelta(days=now.weekday())
            start_of_week = start_of_week.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            for walk in walks_history:
                walk_time_candidate = walk.get("timestamp")
                if not walk_time_candidate:
                    walk_time_candidate = walk.get("end_time")
                if not isinstance(
                    walk_time_candidate, str | datetime | int | float
                ):
                    continue
                walk_time = ensure_utc_datetime(walk_time_candidate)
                if walk_time and walk_time >= start_of_week:
                    walks_this_week += 1
            return walks_this_week
        except (TypeError, ValueError):
            return 0

    @property
    def extra_state_attributes(self) -> AttributeDict:
        attrs: AttributeDict = dict(super().extra_state_attributes or {})
        walk_data = _walk_payload(self)
        if not walk_data:
            return attrs

        with contextlib.suppress(TypeError, ValueError):
            walks_today = int(walk_data.get("walks_today", 0))
            total_duration_raw = walk_data.get("total_duration_this_week") or 0.0
            distance_week_raw = walk_data.get("distance_this_week") or 0.0
            total_duration_this_week = float(total_duration_raw)
            distance_this_week = float(distance_week_raw)
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
                }
            )

        return attrs
