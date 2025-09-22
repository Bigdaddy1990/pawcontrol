# NEW: Missing sensor implementations per requirements_inventory.md
# These will be added to the main sensor.py file

import contextlib
from datetime import timedelta

from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfLength, UnitOfTime
from homeassistant.util import dt as dt_util


@register_sensor("activity_level")
class PawControlActivityLevelSensor(PawControlSensorBase):
    """Sensor for current activity level.

    NEW: This sensor was identified as missing in requirements_inventory.md
    and is mentioned in comprehensive_readme.md.
    """

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
        """Return current activity level based on recent data."""
        walk_data = self._get_module_data("walk")
        health_data = self._get_module_data("health")

        if not walk_data and not health_data:
            return "unknown"

        try:
            # Get recent walk data
            walks_today = int(walk_data.get("walks_today", 0) if walk_data else 0)
            total_duration_today = float(
                walk_data.get("total_duration_today", 0) if walk_data else 0
            )

            # Get health-based activity level if available
            health_activity = health_data.get("activity_level") if health_data else None

            # Calculate activity level based on recent walks
            if walks_today >= 3 and total_duration_today >= 90:  # 3+ walks, 1.5+ hours
                calculated_level = "very_high"
            elif walks_today >= 2 and total_duration_today >= 60:  # 2+ walks, 1+ hour
                calculated_level = "high"
            elif walks_today >= 1 and total_duration_today >= 30:  # 1+ walk, 30+ min
                calculated_level = "moderate"
            elif walks_today >= 1 or total_duration_today >= 15:  # Any walk or 15+ min
                calculated_level = "low"
            else:
                calculated_level = "very_low"

            # Use health-based activity if available and higher
            if health_activity:
                activity_levels = ["very_low", "low", "moderate", "high", "very_high"]
                health_index = (
                    activity_levels.index(health_activity)
                    if health_activity in activity_levels
                    else 2
                )
                calc_index = activity_levels.index(calculated_level)

                # Use the higher of the two assessments
                return activity_levels[max(health_index, calc_index)]

            return calculated_level

        except (TypeError, ValueError, IndexError):
            return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes

        walk_data = self._get_module_data("walk")
        health_data = self._get_module_data("health")

        if walk_data:
            with contextlib.suppress(TypeError, ValueError):
                attrs.update(
                    {
                        "walks_today": int(walk_data.get("walks_today", 0)),
                        "total_walk_minutes_today": float(
                            walk_data.get("total_duration_today", 0)
                        ),
                        "last_walk_hours_ago": self._calculate_hours_since_last_walk(
                            walk_data
                        ),
                    }
                )

        if health_data:
            with contextlib.suppress(TypeError, ValueError):
                attrs.update(
                    {
                        "health_activity_level": health_data.get("activity_level"),
                        "activity_source": "health_data"
                        if health_data.get("activity_level")
                        else "calculated",
                    }
                )

        return attrs

    def _calculate_hours_since_last_walk(
        self, walk_data: dict[str, Any]
    ) -> float | None:
        """Calculate hours since last walk."""
        last_walk = walk_data.get("last_walk")
        if not last_walk:
            return None

        from .utils import ensure_utc_datetime

        last_walk_dt = ensure_utc_datetime(last_walk)
        if last_walk_dt:
            return (dt_util.utcnow() - last_walk_dt).total_seconds() / 3600
        return None


@register_sensor("calories_burned_today")
class PawControlCaloriesBurnedTodaySensor(PawControlSensorBase):
    """Sensor for calories burned today.

    NEW: This sensor was identified as missing in requirements_inventory.md
    and is mentioned in comprehensive_readme.md.
    """

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

    @property
    def native_value(self) -> float:
        """Return calories burned today based on activity."""
        walk_data = self._get_module_data("walk")
        health_data = self._get_module_data("health")

        if not walk_data and not health_data:
            return 0.0

        try:
            # Get walk data
            total_duration_minutes = float(
                walk_data.get("total_duration_today", 0) if walk_data else 0
            )
            total_distance_meters = float(
                walk_data.get("total_distance_today", 0) if walk_data else 0
            )

            # Get dog weight for calculation
            dog_weight_kg = 25.0  # Default weight
            if health_data:
                dog_weight_kg = float(health_data.get("weight", 25.0))

            # Get dog info for more accurate calculation
            dog_data = self._get_dog_data()
            if dog_data and "dog_info" in dog_data:
                dog_info = dog_data["dog_info"]
                dog_weight_kg = float(dog_info.get("dog_weight", dog_weight_kg))

            # Calculate calories burned
            calories_burned = 0.0

            # Walking calories (rough estimate: 0.5 cal/kg/minute of walking)
            if total_duration_minutes > 0:
                walking_calories = dog_weight_kg * total_duration_minutes * 0.5
                calories_burned += walking_calories

            # Distance-based bonus (1 cal per 100m per kg)
            if total_distance_meters > 0:
                distance_calories = dog_weight_kg * (total_distance_meters / 100) * 1.0
                calories_burned += distance_calories

            # Activity level multiplier
            activity_level = (
                health_data.get("activity_level", "moderate")
                if health_data
                else "moderate"
            )
            multipliers = {
                "very_low": 0.7,
                "low": 0.85,
                "moderate": 1.0,
                "high": 1.2,
                "very_high": 1.4,
            }
            multiplier = multipliers.get(activity_level, 1.0)

            calories_burned *= multiplier

            return round(calories_burned, 1)

        except (TypeError, ValueError):
            return 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes

        walk_data = self._get_module_data("walk")
        health_data = self._get_module_data("health")

        with contextlib.suppress(TypeError, ValueError):
            dog_weight = 25.0
            if health_data:
                dog_weight = float(health_data.get("weight", 25.0))

            walk_minutes = float(
                walk_data.get("total_duration_today", 0) if walk_data else 0
            )
            walk_distance = float(
                walk_data.get("total_distance_today", 0) if walk_data else 0
            )

            attrs.update(
                {
                    "dog_weight_kg": dog_weight,
                    "walk_minutes_today": walk_minutes,
                    "walk_distance_meters_today": walk_distance,
                    "activity_level": health_data.get("activity_level", "moderate")
                    if health_data
                    else "moderate",
                    "calories_per_minute": round(dog_weight * 0.5, 2),
                    "calories_per_100m": round(dog_weight * 1.0, 2),
                }
            )

        return attrs


@register_sensor("last_feeding_hours")
class PawControlLastFeedingHoursSensor(PawControlSensorBase):
    """Sensor for hours since last feeding.

    NEW: This sensor was identified as missing in requirements_inventory.md
    and is mentioned in comprehensive_readme.md.
    """

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
        """Return hours since last feeding."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return None

        last_feeding = feeding_data.get("last_feeding")
        if not last_feeding:
            return None

        try:
            from .utils import ensure_utc_datetime

            last_feeding_dt = ensure_utc_datetime(last_feeding)
            if last_feeding_dt:
                hours_ago = (dt_util.utcnow() - last_feeding_dt).total_seconds() / 3600
                return round(hours_ago, 1)
        except (TypeError, ValueError):
            pass

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes

        feeding_data = self._get_module_data("feeding")
        if feeding_data:
            with contextlib.suppress(TypeError, ValueError):
                last_feeding = feeding_data.get("last_feeding")
                feedings_today = int(feeding_data.get("total_feedings_today", 0))

                attrs.update(
                    {
                        "last_feeding_time": last_feeding,
                        "feedings_today": feedings_today,
                        "is_overdue": self._is_feeding_overdue(feeding_data),
                        "next_feeding_due": self._calculate_next_feeding_time(
                            feeding_data
                        ),
                    }
                )

        return attrs

    def _is_feeding_overdue(self, feeding_data: dict[str, Any]) -> bool:
        """Check if feeding is overdue."""
        hours_since = self.native_value
        if hours_since is None:
            return False

        # Consider overdue if more than 8 hours since last feeding
        return hours_since > 8.0

    def _calculate_next_feeding_time(self, feeding_data: dict[str, Any]) -> str | None:
        """Calculate next expected feeding time."""
        try:
            # Get feeding schedule from config
            config = feeding_data.get("config", {})
            meals_per_day = int(config.get("meals_per_day", 2))

            if meals_per_day <= 0:
                return None

            # Calculate hours between meals
            hours_between_meals = 24 / meals_per_day

            last_feeding = feeding_data.get("last_feeding")
            if last_feeding:
                from .utils import ensure_utc_datetime

                last_feeding_dt = ensure_utc_datetime(last_feeding)
                if last_feeding_dt:
                    next_feeding_dt = last_feeding_dt + timedelta(
                        hours=hours_between_meals
                    )
                    return next_feeding_dt.strftime("%H:%M")

        except (TypeError, ValueError, ZeroDivisionError):
            pass

        return None


@register_sensor("total_walk_distance")
class PawControlTotalWalkDistanceSensor(PawControlSensorBase):
    """Sensor for total walk distance (lifetime).

    NEW: This sensor was identified as missing in requirements_inventory.md
    and is mentioned in comprehensive_readme.md.
    """

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
        """Return total lifetime walk distance in kilometers."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return 0.0

        try:
            # Get total distance from walk data
            total_distance_meters = float(walk_data.get("total_distance_lifetime", 0))

            # Fallback calculation from individual walks if lifetime not available
            if total_distance_meters == 0:
                walks_history = walk_data.get("walks_history", [])
                if isinstance(walks_history, list):
                    for walk in walks_history:
                        if isinstance(walk, dict):
                            distance = float(walk.get("distance", 0))
                            total_distance_meters += distance

            # Convert to kilometers
            return round(total_distance_meters / 1000, 2)

        except (TypeError, ValueError):
            return 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes

        walk_data = self._get_module_data("walk")
        if walk_data:
            with contextlib.suppress(TypeError, ValueError):
                total_walks = int(walk_data.get("total_walks_lifetime", 0))
                total_distance_m = float(walk_data.get("total_distance_lifetime", 0))

                attrs.update(
                    {
                        "total_walks": total_walks,
                        "total_distance_meters": total_distance_m,
                        "average_distance_per_walk_km": round(
                            (total_distance_m / 1000) / max(1, total_walks), 2
                        ),
                        "distance_this_week_km": round(
                            float(walk_data.get("distance_this_week", 0)) / 1000, 2
                        ),
                        "distance_this_month_km": round(
                            float(walk_data.get("distance_this_month", 0)) / 1000, 2
                        ),
                    }
                )

        return attrs


@register_sensor("walks_this_week")
class PawControlWalksThisWeekSensor(PawControlSensorBase):
    """Sensor for walks completed this week.

    NEW: This sensor was identified as missing in requirements_inventory.md
    and is mentioned in comprehensive_readme.md.
    """

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
        """Return number of walks completed this week."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return 0

        try:
            # Get walks this week from walk data
            walks_this_week = int(walk_data.get("walks_this_week", 0))

            # Fallback calculation if not directly available
            if walks_this_week == 0:
                walks_history = walk_data.get("walks_history", [])
                if isinstance(walks_history, list):
                    # Calculate start of this week (Monday)
                    now = dt_util.utcnow()
                    start_of_week = now - timedelta(days=now.weekday())
                    start_of_week = start_of_week.replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )

                    for walk in walks_history:
                        if isinstance(walk, dict):
                            walk_time_str = walk.get("timestamp") or walk.get(
                                "end_time"
                            )
                            if walk_time_str:
                                from .utils import ensure_utc_datetime

                                walk_time = ensure_utc_datetime(walk_time_str)
                                if walk_time and walk_time >= start_of_week:
                                    walks_this_week += 1

            return walks_this_week

        except (TypeError, ValueError):
            return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes

        walk_data = self._get_module_data("walk")
        if walk_data:
            with contextlib.suppress(TypeError, ValueError):
                walks_today = int(walk_data.get("walks_today", 0))
                total_duration_this_week = float(
                    walk_data.get("total_duration_this_week", 0)
                )
                distance_this_week = float(walk_data.get("distance_this_week", 0))

                # Calculate average walks per day this week
                now = dt_util.utcnow()
                days_this_week = now.weekday() + 1  # Monday = 0, so +1 for days elapsed
                avg_walks_per_day = self.native_value / max(1, days_this_week)

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
