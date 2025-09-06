"""Profile-based entity factory for PawControl integration.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+

FIXED: Removes references to non-existent sensor classes
Reduces entity count from 54+ to 8-18 per dog based on user profiles.
Solves performance issues through intelligent entity selection.
"""

from __future__ import annotations

import logging
from typing import Any

from .const import (
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# Profile definitions with entity limits
ENTITY_PROFILES = {
    "basic": {
        "max_entities": 8,
        "description": "Essential monitoring only",
        "modules": {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_HEALTH: False,
            MODULE_GPS: False,
        },
    },
    "standard": {
        "max_entities": 12,
        "description": "Balanced monitoring with GPS",
        "modules": {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_HEALTH: True,
            MODULE_GPS: True,
        },
    },
    "advanced": {
        "max_entities": 18,
        "description": "Comprehensive monitoring",
        "modules": {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_HEALTH: True,
            MODULE_GPS: True,
        },
    },
    "gps_focus": {
        "max_entities": 10,
        "description": "GPS tracking focused",
        "modules": {
            MODULE_FEEDING: False,
            MODULE_WALK: True,
            MODULE_HEALTH: False,
            MODULE_GPS: True,
        },
    },
    "health_focus": {
        "max_entities": 10,
        "description": "Health monitoring focused",
        "modules": {
            MODULE_FEEDING: True,
            MODULE_WALK: False,
            MODULE_HEALTH: True,
            MODULE_GPS: False,
        },
    },
}

# Entity priorities (1=highest, 5=lowest) - UPDATED: Only for existing entities
ENTITY_PRIORITIES = {
    # Core entities (always included)
    "dog_status": 1,
    "last_action": 1,
    "activity_score": 1,
    # Essential feeding
    "last_feeding": 2,
    "feeding_schedule_adherence": 2,
    "health_aware_portion": 2,
    # Essential walk
    "last_walk": 2,
    "walk_count_today": 2,
    # Essential GPS
    "current_zone": 2,
    "distance_from_home": 2,
    # Essential health
    "health_status": 2,
    "weight": 2,
    # Advanced feeding (existing only)
    "total_feedings_today": 3,
    "daily_calories": 3,
    "feeding_recommendation": 3,
    "diet_validation_status": 3,
    # Advanced walk (existing only)
    "last_walk_duration": 3,
    "total_walk_time_today": 3,
    "weekly_walk_count": 3,
    "average_walk_duration": 3,
    # Advanced GPS (existing only)
    "current_speed": 3,
    "gps_accuracy": 3,
    "total_distance_today": 3,
    "gps_battery_level": 4,
    # Advanced health (existing only)
    "body_condition_score": 3,
    "weight_trend": 3,
    "last_vet_visit": 3,
    # Detailed feeding (for advanced profile only)
    "feeding_count_today_breakfast": 4,
    "feeding_count_today_lunch": 4,
    "feeding_count_today_dinner": 4,
    "feeding_count_today_snack": 4,
    "breakfast_portion": 4,
    "lunch_portion": 4,
    "dinner_portion": 4,
    "snack_portion": 4,
}


class EntityFactory:
    """Factory for creating profile-aware entities with count limits.

    FIXED: Only creates entities that actually exist in sensor.py
    """

    def __init__(self, coordinator: PawControlCoordinator) -> None:
        """Initialize entity factory.

        Args:
            coordinator: PawControl coordinator instance
        """
        self.coordinator = coordinator

    def create_entities_for_dog(
        self,
        dog_id: str,
        dog_name: str,
        profile: str = "standard",
        modules: dict[str, bool] | None = None,
    ) -> list[Any]:
        """Create entities for a dog based on profile and modules.

        Args:
            dog_id: Dog identifier
            dog_name: Dog display name
            profile: Entity profile (basic, standard, advanced, gps_focus, health_focus)
            modules: Module configuration override

        Returns:
            List of entity instances
        """
        if profile not in ENTITY_PROFILES:
            _LOGGER.warning("Unknown profile '%s', using 'standard'", profile)
            profile = "standard"

        profile_config = ENTITY_PROFILES[profile]
        max_entities = profile_config["max_entities"]

        # Use provided modules or profile defaults
        if modules is None:
            modules = profile_config["modules"]

        _LOGGER.info(
            "Creating entities for %s (%s) with profile '%s' (max: %d entities)",
            dog_name,
            dog_id,
            profile,
            max_entities,
        )

        # Create entity candidates by priority
        entity_candidates = []

        # Always add core entities
        entity_candidates.extend(self._create_core_entities(dog_id, dog_name))

        # Add module-specific entities by priority
        if modules.get(MODULE_FEEDING, False):
            entity_candidates.extend(
                self._create_feeding_entities(dog_id, dog_name, profile)
            )

        if modules.get(MODULE_WALK, False):
            entity_candidates.extend(
                self._create_walk_entities(dog_id, dog_name, profile)
            )

        if modules.get(MODULE_GPS, False):
            entity_candidates.extend(
                self._create_gps_entities(dog_id, dog_name, profile)
            )

        if modules.get(MODULE_HEALTH, False):
            entity_candidates.extend(
                self._create_health_entities(dog_id, dog_name, profile)
            )

        # Sort by priority and limit count
        entity_candidates.sort(key=lambda x: x["priority"])
        selected_entities = entity_candidates[:max_entities]

        # Extract actual entity instances
        entities = [candidate["entity"] for candidate in selected_entities]

        # Log entity selection
        selected_types = [candidate["type"] for candidate in selected_entities]
        _LOGGER.info(
            "Selected %d/%d entities for %s: %s",
            len(entities),
            len(entity_candidates),
            dog_name,
            ", ".join(selected_types),
        )

        return entities

    def _create_core_entities(self, dog_id: str, dog_name: str) -> list[dict[str, Any]]:
        """Create core entities (always included) - FIXED: Only existing classes."""
        from .sensor import (
            PawControlActivityScoreSensor,
            PawControlDogStatusSensor,
            PawControlLastActionSensor,
        )

        return [
            {
                "entity": PawControlDogStatusSensor(self.coordinator, dog_id, dog_name),
                "type": "dog_status",
                "priority": ENTITY_PRIORITIES["dog_status"],
            },
            {
                "entity": PawControlLastActionSensor(
                    self.coordinator, dog_id, dog_name
                ),
                "type": "last_action",
                "priority": ENTITY_PRIORITIES["last_action"],
            },
            {
                "entity": PawControlActivityScoreSensor(
                    self.coordinator, dog_id, dog_name
                ),
                "type": "activity_score",
                "priority": ENTITY_PRIORITIES["activity_score"],
            },
        ]

    def _create_feeding_entities(
        self, dog_id: str, dog_name: str, profile: str
    ) -> list[dict[str, Any]]:
        """Create feeding entities based on profile - FIXED: Only existing classes."""
        from .sensor import (
            PawControlDailyCaloriesSensor,
            PawControlDietValidationStatusSensor,
            PawControlFeedingCountTodaySensor,
            PawControlFeedingRecommendationSensor,
            PawControlFeedingScheduleAdherenceSensor,
            PawControlHealthAwarePortionSensor,
            PawControlLastFeedingSensor,
            PawControlMealPortionSensor,
            PawControlTotalFeedingsTodaySensor,
        )

        entities = []

        # Essential feeding entities (all profiles)
        entities.extend(
            [
                {
                    "entity": PawControlLastFeedingSensor(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "last_feeding",
                    "priority": ENTITY_PRIORITIES["last_feeding"],
                },
                {
                    "entity": PawControlFeedingScheduleAdherenceSensor(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "feeding_schedule_adherence",
                    "priority": ENTITY_PRIORITIES["feeding_schedule_adherence"],
                },
                {
                    "entity": PawControlHealthAwarePortionSensor(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "health_aware_portion",
                    "priority": ENTITY_PRIORITIES["health_aware_portion"],
                },
            ]
        )

        # Standard+ feeding entities
        if profile in ["standard", "advanced", "health_focus"]:
            entities.extend(
                [
                    {
                        "entity": PawControlTotalFeedingsTodaySensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "total_feedings_today",
                        "priority": ENTITY_PRIORITIES["total_feedings_today"],
                    },
                    {
                        "entity": PawControlDailyCaloriesSensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "daily_calories",
                        "priority": ENTITY_PRIORITIES["daily_calories"],
                    },
                    {
                        "entity": PawControlFeedingRecommendationSensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "feeding_recommendation",
                        "priority": ENTITY_PRIORITIES["feeding_recommendation"],
                    },
                ]
            )

        # Advanced feeding entities
        if profile == "advanced":
            entities.extend(
                [
                    {
                        "entity": PawControlDietValidationStatusSensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "diet_validation_status",
                        "priority": ENTITY_PRIORITIES["diet_validation_status"],
                    },
                    # Add detailed meal sensors for advanced users
                    {
                        "entity": PawControlFeedingCountTodaySensor(
                            self.coordinator, dog_id, dog_name, "breakfast"
                        ),
                        "type": "feeding_count_today_breakfast",
                        "priority": ENTITY_PRIORITIES["feeding_count_today_breakfast"],
                    },
                    {
                        "entity": PawControlFeedingCountTodaySensor(
                            self.coordinator, dog_id, dog_name, "dinner"
                        ),
                        "type": "feeding_count_today_dinner",
                        "priority": ENTITY_PRIORITIES["feeding_count_today_dinner"],
                    },
                    {
                        "entity": PawControlMealPortionSensor(
                            self.coordinator, dog_id, dog_name, "breakfast"
                        ),
                        "type": "breakfast_portion",
                        "priority": ENTITY_PRIORITIES["breakfast_portion"],
                    },
                    {
                        "entity": PawControlMealPortionSensor(
                            self.coordinator, dog_id, dog_name, "dinner"
                        ),
                        "type": "dinner_portion",
                        "priority": ENTITY_PRIORITIES["dinner_portion"],
                    },
                ]
            )

        return entities

    def _create_walk_entities(
        self, dog_id: str, dog_name: str, profile: str
    ) -> list[dict[str, Any]]:
        """Create walk entities based on profile - FIXED: Only existing classes."""
        from .sensor import (
            PawControlAverageWalkDurationSensor,
            PawControlLastWalkDurationSensor,
            PawControlLastWalkSensor,
            PawControlTotalWalkTimeTodaySensor,
            PawControlWalkCountTodaySensor,
            PawControlWeeklyWalkCountSensor,
        )

        entities = []

        # Essential walk entities (all profiles with walk enabled)
        entities.extend(
            [
                {
                    "entity": PawControlLastWalkSensor(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "last_walk",
                    "priority": ENTITY_PRIORITIES["last_walk"],
                },
                {
                    "entity": PawControlWalkCountTodaySensor(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "walk_count_today",
                    "priority": ENTITY_PRIORITIES["walk_count_today"],
                },
            ]
        )

        # Standard+ walk entities
        if profile in ["standard", "advanced", "gps_focus"]:
            entities.extend(
                [
                    {
                        "entity": PawControlLastWalkDurationSensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "last_walk_duration",
                        "priority": ENTITY_PRIORITIES["last_walk_duration"],
                    },
                    {
                        "entity": PawControlTotalWalkTimeTodaySensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "total_walk_time_today",
                        "priority": ENTITY_PRIORITIES["total_walk_time_today"],
                    },
                ]
            )

        # Advanced walk entities
        if profile == "advanced":
            entities.extend(
                [
                    {
                        "entity": PawControlWeeklyWalkCountSensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "weekly_walk_count",
                        "priority": ENTITY_PRIORITIES["weekly_walk_count"],
                    },
                    {
                        "entity": PawControlAverageWalkDurationSensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "average_walk_duration",
                        "priority": ENTITY_PRIORITIES["average_walk_duration"],
                    },
                ]
            )

        return entities

    def _create_gps_entities(
        self, dog_id: str, dog_name: str, profile: str
    ) -> list[dict[str, Any]]:
        """Create GPS entities based on profile - FIXED: Only existing classes."""
        from .sensor import (
            PawControlCurrentSpeedSensor,
            PawControlCurrentZoneSensor,
            PawControlDistanceFromHomeSensor,
            PawControlGPSAccuracySensor,
            PawControlGPSBatteryLevelSensor,
            PawControlTotalDistanceTodaySensor,
        )

        entities = []

        # Essential GPS entities (all profiles with GPS enabled)
        entities.extend(
            [
                {
                    "entity": PawControlCurrentZoneSensor(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "current_zone",
                    "priority": ENTITY_PRIORITIES["current_zone"],
                },
                {
                    "entity": PawControlDistanceFromHomeSensor(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "distance_from_home",
                    "priority": ENTITY_PRIORITIES["distance_from_home"],
                },
            ]
        )

        # Standard+ GPS entities
        if profile in ["standard", "advanced", "gps_focus"]:
            entities.extend(
                [
                    {
                        "entity": PawControlCurrentSpeedSensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "current_speed",
                        "priority": ENTITY_PRIORITIES["current_speed"],
                    },
                    {
                        "entity": PawControlGPSAccuracySensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "gps_accuracy",
                        "priority": ENTITY_PRIORITIES["gps_accuracy"],
                    },
                ]
            )

        # Advanced/GPS focus entities
        if profile in ["advanced", "gps_focus"]:
            entities.extend(
                [
                    {
                        "entity": PawControlTotalDistanceTodaySensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "total_distance_today",
                        "priority": ENTITY_PRIORITIES["total_distance_today"],
                    },
                    {
                        "entity": PawControlGPSBatteryLevelSensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "gps_battery_level",
                        "priority": ENTITY_PRIORITIES["gps_battery_level"],
                    },
                ]
            )

        return entities

    def _create_health_entities(
        self, dog_id: str, dog_name: str, profile: str
    ) -> list[dict[str, Any]]:
        """Create health entities based on profile - FIXED: Only existing classes."""
        from .sensor import (
            PawControlBodyConditionScoreSensor,
            PawControlHealthStatusSensor,
            PawControlLastVetVisitSensor,
            PawControlWeightSensor,
            PawControlWeightTrendSensor,
        )

        entities = []

        # Essential health entities (all profiles with health enabled)
        entities.extend(
            [
                {
                    "entity": PawControlHealthStatusSensor(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "health_status",
                    "priority": ENTITY_PRIORITIES["health_status"],
                },
                {
                    "entity": PawControlWeightSensor(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "weight",
                    "priority": ENTITY_PRIORITIES["weight"],
                },
            ]
        )

        # Standard+ health entities
        if profile in ["standard", "advanced", "health_focus"]:
            entities.extend(
                [
                    {
                        "entity": PawControlBodyConditionScoreSensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "body_condition_score",
                        "priority": ENTITY_PRIORITIES["body_condition_score"],
                    },
                    {
                        "entity": PawControlWeightTrendSensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "weight_trend",
                        "priority": ENTITY_PRIORITIES["weight_trend"],
                    },
                ]
            )

        # Advanced/Health focus entities
        if profile in ["advanced", "health_focus"]:
            entities.extend(
                [
                    {
                        "entity": PawControlLastVetVisitSensor(
                            self.coordinator, dog_id, dog_name
                        ),
                        "type": "last_vet_visit",
                        "priority": ENTITY_PRIORITIES["last_vet_visit"],
                    },
                ]
            )

        return entities

    def get_profile_info(self, profile: str) -> dict[str, Any]:
        """Get information about a profile.

        Args:
            profile: Profile name

        Returns:
            Profile configuration dictionary
        """
        return ENTITY_PROFILES.get(profile, ENTITY_PROFILES["standard"])

    def get_available_profiles(self) -> list[str]:
        """Get list of available profiles.

        Returns:
            List of profile names
        """
        return list(ENTITY_PROFILES.keys())

    def estimate_entity_count(self, profile: str, modules: dict[str, bool]) -> int:
        """Estimate entity count for profile and modules.

        Args:
            profile: Entity profile
            modules: Module configuration

        Returns:
            Estimated entity count
        """
        # Core entities (always 3)
        count = 3

        # Module entity counts by profile
        feeding_counts = {"basic": 3, "standard": 6, "advanced": 10, "health_focus": 6}
        walk_counts = {"basic": 2, "standard": 4, "advanced": 6, "gps_focus": 4}
        gps_counts = {"basic": 2, "standard": 4, "advanced": 6, "gps_focus": 6}
        health_counts = {"basic": 2, "standard": 4, "advanced": 5, "health_focus": 5}

        if modules.get(MODULE_FEEDING, False):
            count += feeding_counts.get(profile, 3)

        if modules.get(MODULE_WALK, False):
            count += walk_counts.get(profile, 2)

        if modules.get(MODULE_GPS, False):
            count += gps_counts.get(profile, 2)

        if modules.get(MODULE_HEALTH, False):
            count += health_counts.get(profile, 2)

        # Apply profile limit
        max_entities = ENTITY_PROFILES.get(profile, {}).get("max_entities", 12)
        return min(count, max_entities)
