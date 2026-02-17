"""Supplementary sensors that expose derived PawControl telemetry."""

from collections.abc import Mapping
import contextlib
from datetime import datetime, timedelta
from typing import Protocol, TypeVar, cast

from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfLength, UnitOfTime
from homeassistant.util import dt as dt_util

from .coordinator import PawControlCoordinator
from .sensor import PawControlSensorBase, register_sensor
from .types import (
    FeedingModuleTelemetry,
    HealthModulePayload,
    JSONMutableMapping,
    JSONValue,
    WalkModuleTelemetry,
    WalkSessionSnapshot,
)
from .utils import DateTimeConvertible, ensure_utc_datetime, normalise_entity_attributes

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


T = TypeVar("T")


type ModuleSnapshot[T] = T | None
type WalkHistory = list[WalkSessionSnapshot]


class _ModuleDataProvider(Protocol):
    """Protocol describing objects that expose module data accessors."""  # noqa: E111

    def _get_module_data(self, module: str) -> Mapping[str, JSONValue] | None:  # noqa: E111
        """Return coordinator data for the requested module."""


def _walk_payload(
    provider: _ModuleDataProvider,
) -> ModuleSnapshot[WalkModuleTelemetry]:
    module_data = provider._get_module_data("walk")  # noqa: E111
    if module_data is None or not isinstance(module_data, Mapping):  # noqa: E111
        return None
    return cast(WalkModuleTelemetry, module_data)  # noqa: E111


def _health_payload(
    provider: _ModuleDataProvider,
) -> ModuleSnapshot[HealthModulePayload]:
    module_data = provider._get_module_data("health")  # noqa: E111
    if module_data is None or not isinstance(module_data, Mapping):  # noqa: E111
        return None
    return cast(HealthModulePayload, module_data)  # noqa: E111


def _feeding_payload(
    provider: _ModuleDataProvider,
) -> ModuleSnapshot[FeedingModuleTelemetry]:
    module_data = provider._get_module_data("feeding")  # noqa: E111
    if module_data is None or not isinstance(module_data, Mapping):  # noqa: E111
        return None
    return cast(FeedingModuleTelemetry, module_data)  # noqa: E111


def _normalise_attributes(attrs: Mapping[str, object]) -> JSONMutableMapping:
    """Return JSON-serialisable attributes for missing sensors."""  # noqa: E111

    return normalise_entity_attributes(attrs)  # noqa: E111


def calculate_activity_level(
    walk_data: ModuleSnapshot[WalkModuleTelemetry],
    health_data: ModuleSnapshot[HealthModulePayload],
) -> str:
    """Determine the activity level based on walk telemetry and health inputs."""  # noqa: E111

    if walk_data is None and health_data is None:  # noqa: E111
        return "unknown"

    try:  # noqa: E111
        walks_today = int(walk_data["walks_today"]) if walk_data else 0
        total_duration_today = (
            float(walk_data["total_duration_today"]) if walk_data else 0.0
        )

        if walks_today >= 3 and total_duration_today >= 90:
            calculated_level = "very_high"  # noqa: E111
        elif walks_today >= 2 and total_duration_today >= 60:
            calculated_level = "high"  # noqa: E111
        elif walks_today >= 1 and total_duration_today >= 30:
            calculated_level = "moderate"  # noqa: E111
        elif walks_today >= 1 or total_duration_today >= 15:
            calculated_level = "low"  # noqa: E111
        else:
            calculated_level = "very_low"  # noqa: E111

        health_activity: str | None = None
        if health_data and "activity_level" in health_data:
            candidate = health_data["activity_level"]  # noqa: E111
            health_activity = candidate if isinstance(candidate, str) else None  # noqa: E111

        if health_activity:
            activity_levels = [  # noqa: E111
                "very_low",
                "low",
                "moderate",
                "high",
                "very_high",
            ]
            health_index = (  # noqa: E111
                activity_levels.index(health_activity)
                if health_activity in activity_levels
                else 2
            )
            calculated_index = activity_levels.index(calculated_level)  # noqa: E111
            return activity_levels[max(health_index, calculated_index)]  # noqa: E111

        return calculated_level
    except TypeError, ValueError, IndexError:  # noqa: E111
        return "unknown"


def calculate_calories_burned_today(
    walk_data: ModuleSnapshot[WalkModuleTelemetry],
    dog_weight_kg: float,
    health_data: ModuleSnapshot[HealthModulePayload],
) -> float:
    """Estimate calories burned today using walk telemetry and weight."""  # noqa: E111

    if walk_data is None and health_data is None:  # noqa: E111
        return 0.0

    try:  # noqa: E111
        total_duration_minutes = (
            float(walk_data["total_duration_today"]) if walk_data else 0.0
        )
        total_distance_meters = (
            float(walk_data["total_distance_today"]) if walk_data else 0.0
        )

        calories_burned = 0.0
        if total_duration_minutes > 0:
            calories_burned += dog_weight_kg * total_duration_minutes * 0.5  # noqa: E111
        if total_distance_meters > 0:
            calories_burned += dog_weight_kg * (total_distance_meters / 100.0)  # noqa: E111

        raw_activity: str | None = None
        if health_data and "activity_level" in health_data:
            candidate = health_data["activity_level"]  # noqa: E111
            raw_activity = candidate if isinstance(candidate, str) else None  # noqa: E111
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
    except ValueError:  # noqa: E111
        return 0.0
    except TypeError:  # noqa: E111
        return 0.0


def calculate_hours_since(
    timestamp: DateTimeConvertible | None,
    *,
    reference: datetime | None = None,
) -> float | None:
    """Calculate elapsed hours since the provided timestamp."""  # noqa: E111

    if not timestamp:  # noqa: E111
        return None

    last_event = ensure_utc_datetime(timestamp)  # noqa: E111
    if last_event is None:  # noqa: E111
        return None

    now = reference or dt_util.utcnow()  # noqa: E111
    return (now - last_event).total_seconds() / 3600  # noqa: E111


def derive_next_feeding_time(
    feeding_data: ModuleSnapshot[FeedingModuleTelemetry],
) -> str | None:
    """Compute the next feeding time based on the configured schedule."""  # noqa: E111

    if feeding_data is None:  # noqa: E111
        return None

    try:  # noqa: E111
        if "config" not in feeding_data:
            return None  # noqa: E111
        config = feeding_data["config"]
        if "meals_per_day" not in config:
            return None  # noqa: E111
        meals_per_day = int(config["meals_per_day"])
        if meals_per_day <= 0:
            return None  # noqa: E111

        hours_between_meals = 24 / meals_per_day
        if "last_feeding" not in feeding_data or feeding_data["last_feeding"] is None:
            return None  # noqa: E111
        last_feeding_dt = ensure_utc_datetime(feeding_data["last_feeding"])
        if last_feeding_dt is None:
            return None  # noqa: E111

        next_feeding_dt = last_feeding_dt + timedelta(hours=hours_between_meals)
        return next_feeding_dt.strftime("%H:%M")
    except TypeError, ValueError, ZeroDivisionError:  # noqa: E111
        return None


@register_sensor("activity_level")
class PawControlActivityLevelSensor(PawControlSensorBase):
    """Sensor for the current activity level of a dog."""  # noqa: E111

    def __init__(  # noqa: E111
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

    @property  # noqa: E111
    def native_value(self) -> str:  # noqa: E111
        """Return the derived activity level from walk and health payloads."""
        walk_data = _walk_payload(self)
        health_data = _health_payload(self)
        return calculate_activity_level(walk_data, health_data)

    @property  # noqa: E111
    def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
        """Return supplemental activity telemetry for diagnostics."""
        attrs = dict(super().extra_state_attributes)
        walk_data = _walk_payload(self)
        health_data = _health_payload(self)

        if walk_data:
            with contextlib.suppress(TypeError, ValueError):  # noqa: E111
                last_walk = cast(
                    DateTimeConvertible | None,
                    walk_data.get("last_walk"),
                )
                attrs.update(
                    {
                        "walks_today": int(walk_data.get("walks_today", 0)),
                        "total_walk_minutes_today": float(
                            walk_data.get(
                                "total_duration_today",
                                0.0,
                            ),
                        ),
                        "last_walk_hours_ago": calculate_hours_since(last_walk),
                    },
                )

        if health_data:
            activity_level = health_data.get("activity_level")  # noqa: E111
            attrs["health_activity_level"] = activity_level  # noqa: E111
            attrs["activity_source"] = "health_data" if activity_level else "calculated"  # noqa: E111

        return _normalise_attributes(attrs)


@register_sensor("calories_burned_today")
class PawControlCaloriesBurnedTodaySensor(PawControlSensorBase):
    """Sensor estimating calories burned today."""  # noqa: E111

    def __init__(  # noqa: E111
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

    def _resolve_dog_weight(  # noqa: E111
        self,
        health_data: ModuleSnapshot[HealthModulePayload],
    ) -> float:
        weight = 25.0
        if health_data and "weight" in health_data:
            reported_weight = health_data["weight"]  # noqa: E111
            if reported_weight is not None:  # noqa: E111
                with contextlib.suppress(TypeError, ValueError):
                    weight = float(reported_weight)  # noqa: E111

        dog_data = self._get_dog_data()
        if dog_data and "dog_info" in dog_data:
            dog_info = dog_data["dog_info"]  # noqa: E111
            if "dog_weight" in dog_info and dog_info["dog_weight"] is not None:  # noqa: E111
                with contextlib.suppress(TypeError, ValueError):
                    weight = float(dog_info["dog_weight"])  # noqa: E111
        return weight

    @property  # noqa: E111
    def native_value(self) -> float:  # noqa: E111
        """Estimate the calories burned today for the active dog."""
        walk_data = _walk_payload(self)
        health_data = _health_payload(self)
        dog_weight = self._resolve_dog_weight(health_data)
        return calculate_calories_burned_today(walk_data, dog_weight, health_data)

    @property  # noqa: E111
    def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
        """Provide supporting data for the calories burned calculation."""
        attrs = dict(super().extra_state_attributes)
        walk_data = _walk_payload(self)
        health_data = _health_payload(self)
        dog_weight = self._resolve_dog_weight(health_data)

        with contextlib.suppress(TypeError, ValueError):
            walk_minutes = (
                float(walk_data["total_duration_today"]) if walk_data else 0.0
            )  # noqa: E111
            walk_distance = (
                float(walk_data["total_distance_today"]) if walk_data else 0.0
            )  # noqa: E111
            activity_level = "moderate"  # noqa: E111
            if health_data and "activity_level" in health_data:  # noqa: E111
                candidate = health_data["activity_level"]
                if isinstance(candidate, str):
                    activity_level = candidate  # noqa: E111
            attrs.update(  # noqa: E111
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
    """Sensor reporting hours since the last feeding."""  # noqa: E111

    def __init__(  # noqa: E111
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

    @property  # noqa: E111
    def native_value(self) -> float | None:  # noqa: E111
        """Return hours elapsed since the last recorded feeding."""
        feeding_data = _feeding_payload(self)
        if feeding_data is None:
            return None  # noqa: E111

        last_feeding = cast(
            DateTimeConvertible | None,
            feeding_data.get("last_feeding"),
        )
        hours_since = calculate_hours_since(last_feeding)
        return round(hours_since, 1) if hours_since is not None else None

    @property  # noqa: E111
    def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
        """Return contextual feeding metadata for diagnostics."""
        attrs = dict(super().extra_state_attributes)
        feeding_data = _feeding_payload(self)
        if feeding_data is None:
            return _normalise_attributes(attrs)  # noqa: E111

        with contextlib.suppress(TypeError, ValueError):
            last_feeding = feeding_data.get("last_feeding")  # noqa: E111
            feedings_today = int(  # noqa: E111
                feeding_data.get("total_feedings_today", 0) or 0,
            )
            serialized_last_feeding: str | float | int | None  # noqa: E111
            if isinstance(last_feeding, datetime):  # noqa: E111
                serialized_last_feeding = dt_util.as_utc(
                    last_feeding,
                ).isoformat()
            elif isinstance(last_feeding, float | int):  # noqa: E111
                serialized_last_feeding = float(last_feeding)
            elif isinstance(last_feeding, str):  # noqa: E111
                serialized_last_feeding = last_feeding
            else:  # noqa: E111
                serialized_last_feeding = None
            attrs.update(  # noqa: E111
                {
                    "last_feeding_time": serialized_last_feeding,
                    "feedings_today": int(feedings_today),
                    "is_overdue": self._is_feeding_overdue(feeding_data),
                    "next_feeding_due": derive_next_feeding_time(feeding_data),
                },
            )

        return _normalise_attributes(attrs)

    def _is_feeding_overdue(  # noqa: E111
        self,
        feeding_data: ModuleSnapshot[FeedingModuleTelemetry],
    ) -> bool:
        last_feeding = feeding_data.get("last_feeding") if feeding_data else None
        hours_since = calculate_hours_since(last_feeding)
        if hours_since is None:
            return False  # noqa: E111
        return hours_since > 8.0


@register_sensor("total_walk_distance")
class PawControlTotalWalkDistanceSensor(PawControlSensorBase):
    """Sensor exposing the lifetime walk distance."""  # noqa: E111

    def __init__(  # noqa: E111
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

    @property  # noqa: E111
    def native_value(self) -> float:  # noqa: E111
        """Return the lifetime walking distance expressed in kilometres."""
        walk_data = _walk_payload(self)
        if walk_data is None:
            return 0.0  # noqa: E111

        try:
            total_distance_value = cast(  # noqa: E111
                float | int | None,
                walk_data.get("total_distance_lifetime", 0.0),
            )
            total_distance_meters = float(total_distance_value or 0.0)  # noqa: E111
            if total_distance_meters == 0.0 and "walks_history" in walk_data:  # noqa: E111
                walks_history = walk_data["walks_history"]
                if walks_history:
                    for walk in walks_history:  # noqa: E111
                        with contextlib.suppress(TypeError, ValueError):
                            distance_value = cast(  # noqa: E111
                                float | int | None,
                                walk.get("distance"),
                            )
                            if isinstance(distance_value, int | float):  # noqa: E111
                                total_distance_meters += float(distance_value)
            return round(total_distance_meters / 1000, 2)  # noqa: E111
        except ValueError:
            return 0.0  # noqa: E111
        except TypeError:
            return 0.0  # noqa: E111

    @property  # noqa: E111
    def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
        """Return aggregated walk distance metrics for the dog."""
        attrs = dict(super().extra_state_attributes)
        walk_data = _walk_payload(self)
        if walk_data is None:
            return _normalise_attributes(attrs)  # noqa: E111

        with contextlib.suppress(TypeError, ValueError):
            total_distance_value = cast(  # noqa: E111
                float | int | None,
                walk_data.get("total_distance_lifetime", 0.0),
            )
            total_distance_m = float(total_distance_value or 0.0)  # noqa: E111
            total_walks_value = cast(  # noqa: E111
                int | float | None,
                walk_data.get("total_walks_lifetime", 0),
            )
            total_walks = int(total_walks_value or 0)  # noqa: E111
            distance_this_week = cast(  # noqa: E111
                float | int | None,
                walk_data.get("distance_this_week", 0.0),
            )
            distance_this_month = cast(  # noqa: E111
                float | int | None,
                walk_data.get("distance_this_month", 0.0),
            )
            attrs.update(  # noqa: E111
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
    """Sensor tracking the number of walks completed during the current week."""  # noqa: E111

    def __init__(  # noqa: E111
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

    @property  # noqa: E111
    def native_value(self) -> int:  # noqa: E111
        """Return the total number of walks completed during the week."""
        walk_data = _walk_payload(self)
        if walk_data is None:
            return 0  # noqa: E111

        try:
            walks_this_week = int(  # noqa: E111
                walk_data.get("walks_this_week", 0),
            )
            if walks_this_week:  # noqa: E111
                return walks_this_week

            if "walks_history" not in walk_data:  # noqa: E111
                return walks_this_week
            walks_history = walk_data["walks_history"]  # noqa: E111

            now = dt_util.utcnow()  # noqa: E111
            start_of_week = now - timedelta(days=now.weekday())  # noqa: E111
            start_of_week = start_of_week.replace(  # noqa: E111
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            for walk in walks_history:  # noqa: E111
                walk_time_candidate = walk.get("timestamp")
                if not walk_time_candidate:
                    walk_time_candidate = walk.get("end_time")  # noqa: E111
                if not isinstance(walk_time_candidate, str | datetime | int | float):
                    continue  # noqa: E111
                walk_time = ensure_utc_datetime(walk_time_candidate)
                if walk_time and walk_time >= start_of_week:
                    walks_this_week += 1  # noqa: E111
            return walks_this_week  # noqa: E111
        except ValueError:
            return 0  # noqa: E111
        except TypeError:
            return 0  # noqa: E111

    @property  # noqa: E111
    def extra_state_attributes(self) -> JSONMutableMapping:  # noqa: E111
        """Expose weekly walk statistics derived from coordinator payloads."""
        attrs = dict(super().extra_state_attributes)
        walk_data = _walk_payload(self)
        if walk_data is None:
            return _normalise_attributes(attrs)  # noqa: E111

        with contextlib.suppress(TypeError, ValueError):
            walks_today = int(walk_data.get("walks_today", 0))  # noqa: E111
            total_duration_this_week = float(  # noqa: E111
                walk_data.get("total_duration_this_week", 0.0),
            )
            distance_this_week = float(  # noqa: E111
                walk_data.get("distance_this_week", 0.0),
            )
            now = dt_util.utcnow()  # noqa: E111
            days_this_week = now.weekday() + 1  # noqa: E111
            avg_walks_per_day = (self.native_value or 0) / max(1, days_this_week)  # noqa: E111
            attrs.update(  # noqa: E111
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
