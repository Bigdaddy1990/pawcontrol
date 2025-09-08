"""Optimized feeding management with health-integrated portion calculation.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+

Features:
- Health-aware portion calculation
- Advanced calorie management
- Body condition score integration
- Medical condition adjustments
- Event-based reminders with caching
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Any, Optional

from homeassistant.util import dt as dt_util

# Support running as standalone module in tests
try:  # pragma: no cover - fallback for direct test execution
    from .health_calculator import (
        ActivityLevel,
        HealthCalculator,
        HealthMetrics,
        LifeStage,
    )
except ImportError:  # pragma: no cover
    from custom_components.pawcontrol.health_calculator import (
        ActivityLevel,
        HealthCalculator,
        HealthMetrics,
        LifeStage,
    )

_LOGGER = logging.getLogger(__name__)


# Portion safeguard constants
PUPPY_PORTION_SAFEGUARD_FACTOR = 0.8
MINIMUM_NUTRITION_PORTION_G = 50.1


class MealType(Enum):
    """Meal type enumeration."""

    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    TREAT = "treat"
    SUPPLEMENT = "supplement"


class FeedingScheduleType(Enum):
    """Feeding schedule type enumeration."""

    FLEXIBLE = "flexible"
    STRICT = "strict"
    CUSTOM = "custom"


@dataclass(slots=True, frozen=True)
class FeedingEvent:
    """Immutable feeding event for better caching."""

    time: datetime
    amount: float
    meal_type: Optional[MealType] = None
    portion_size: Optional[float] = None
    food_type: Optional[str] = None
    notes: Optional[str] = None
    feeder: Optional[str] = None
    scheduled: bool = False
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "time": self.time.isoformat(),
            "amount": self.amount,
            "meal_type": self.meal_type.value if self.meal_type else None,
            "portion_size": self.portion_size,
            "food_type": self.food_type,
            "notes": self.notes,
            "feeder": self.feeder,
            "scheduled": self.scheduled,
            "skipped": self.skipped,
        }


@dataclass(slots=True)
class MealSchedule:
    """Scheduled meal with configuration."""

    meal_type: MealType
    scheduled_time: time
    portion_size: float
    enabled: bool = True
    reminder_enabled: bool = True
    reminder_minutes_before: int = 15
    auto_log: bool = False
    days_of_week: Optional[list[int]] = None

    def is_due_today(self) -> bool:
        """Check if meal is scheduled for today."""
        if not self.enabled:
            return False

        if self.days_of_week is None:
            return True

        today = datetime.now().weekday()
        return today in self.days_of_week

    def get_next_feeding_time(self) -> datetime:
        """Get next scheduled feeding time."""
        now = dt_util.now()
        today = now.date()

        scheduled = datetime.combine(today, self.scheduled_time)
        scheduled = dt_util.as_local(scheduled)

        if scheduled <= now:
            scheduled += timedelta(days=1)

        if self.days_of_week is not None:
            while scheduled.weekday() not in self.days_of_week:
                scheduled += timedelta(days=1)

        return scheduled

    def get_reminder_time(self) -> Optional[datetime]:
        """Get reminder time for this meal."""
        if not self.reminder_enabled:
            return None

        next_feeding = self.get_next_feeding_time()
        return next_feeding - timedelta(minutes=self.reminder_minutes_before)


@dataclass
class FeedingConfig:
    """Enhanced feeding configuration with health integration."""

    dog_id: str
    meals_per_day: int = 2
    daily_food_amount: float = 500.0
    food_type: str = "dry_food"
    special_diet: list[str] = field(default_factory=list)
    schedule_type: FeedingScheduleType = FeedingScheduleType.FLEXIBLE
    meal_schedules: list[MealSchedule] = field(default_factory=list)
    treats_enabled: bool = True
    max_treats_per_day: int = 3
    water_tracking: bool = False
    calorie_tracking: bool = False
    calories_per_gram: Optional[float] = None
    portion_calculation_enabled: bool = True
    medication_with_meals: bool = False
    portion_tolerance: int = 10  # percentage

    # Health integration fields
    health_aware_portions: bool = True
    dog_weight: Optional[float] = None
    ideal_weight: Optional[float] = None
    age_months: Optional[int] = None
    breed_size: str = "medium"
    activity_level: Optional[str] = None
    body_condition_score: Optional[int] = None
    health_conditions: list[str] = field(default_factory=list)
    weight_goal: Optional[str] = None  # "maintain", "lose", "gain"
    spayed_neutered: bool = True

    # Diet validation integration
    diet_validation: Optional[dict[str, Any]] = None

    def calculate_portion_size(
        self,
        meal_type: Optional[MealType] = None,
        health_data: Optional[dict[str, Any]] = None,
    ) -> float:
        """Calculate health-aware portion size with advanced algorithms.

        Args:
            meal_type: Optional meal type for specialized portion calculation
            health_data: Optional real-time health data override

        Returns:
            Calculated portion size in grams
        """
        if self.meals_per_day <= 0:
            return 0.0

        base_portion = self.daily_food_amount / self.meals_per_day

        if not self.portion_calculation_enabled:
            return base_portion

        # Health-aware calculation if enabled
        if self.health_aware_portions:
            try:
                health_portion = self._calculate_health_aware_portion(
                    meal_type, health_data
                )
                if health_portion > 0:
                    return health_portion
            except Exception as err:
                _LOGGER.warning(
                    "Health-aware calculation failed for %s: %s", self.dog_id, err
                )

        # Fallback to basic meal-type calculation
        if not meal_type:
            return base_portion

        # Meal-specific multipliers for better nutrition distribution
        meal_multipliers = {
            MealType.BREAKFAST: 1.1,  # Larger breakfast for energy
            MealType.LUNCH: 0.9,  # Smaller lunch
            MealType.DINNER: 1.0,  # Standard dinner
            MealType.SNACK: 0.3,  # Small snacks
            MealType.TREAT: 0.1,  # Tiny treats
            MealType.SUPPLEMENT: 0.05,  # Minimal supplements
        }

        multiplier = meal_multipliers.get(meal_type, 1.0)
        calculated_portion = base_portion * multiplier

        # Apply tolerance if configured
        if self.portion_tolerance > 0:
            tolerance_factor = 1.0 + (self.portion_tolerance / 100.0)
            calculated_portion = min(
                calculated_portion * tolerance_factor, self.daily_food_amount * 0.6
            )  # Max 60% in one meal

        return round(calculated_portion, 1)

    def _calculate_health_aware_portion(
        self,
        meal_type: Optional[MealType] = None,
        health_data: Optional[dict[str, Any]] = None,
    ) -> float:
        """Calculate portion using health metrics and requirements.

        Args:
            meal_type: Meal type for distribution calculation
            health_data: Optional real-time health data

        Returns:
            Health-optimized portion size in grams
        """
        # Create health metrics from config and optional override data
        health_metrics = self._build_health_metrics(health_data)

        if not health_metrics.current_weight:
            # No weight data - fall back to basic calculation
            return 0.0

        # Calculate daily calorie requirement
        daily_calories = HealthCalculator.calculate_daily_calories(
            weight=health_metrics.current_weight,
            life_stage=health_metrics.life_stage or LifeStage.ADULT,
            activity_level=health_metrics.activity_level or ActivityLevel.MODERATE,
            body_condition_score=health_metrics.body_condition_score,
            health_conditions=health_metrics.health_conditions,
            spayed_neutered=self.spayed_neutered,
        )

        # Calculate portion adjustment factor with diet validation
        feeding_goals = {
            "weight_goal": self.weight_goal,
            "weight_loss_rate": "moderate",  # Could be configurable
        }

        adjustment_factor = HealthCalculator.calculate_portion_adjustment_factor(
            health_metrics, feeding_goals, self.diet_validation
        )

        # Convert calories to grams using food calorie density
        calories_per_gram = self.calories_per_gram or self._estimate_calories_per_gram()
        daily_grams = daily_calories / calories_per_gram

        # Apply adjustment factor
        adjusted_daily_grams = daily_grams * adjustment_factor

        # Calculate base portion per meal
        base_portion = adjusted_daily_grams / self.meals_per_day

        # Apply meal-type distribution if specified
        if meal_type:
            meal_distribution = self._get_meal_distribution()
            meal_factor = meal_distribution.get(meal_type, 1.0)
            portion = base_portion * meal_factor
        else:
            portion = base_portion

        # Ensure minimum nutrition thresholds
        portion = max(portion, MINIMUM_NUTRITION_PORTION_G)

        # Apply safety limits
        min_portion = (
            adjusted_daily_grams * MIN_PORTION_SAFETY_FACTOR
        )  # Min 10% of daily amount
        max_portion = (
            adjusted_daily_grams * MAX_PORTION_SAFETY_FACTOR
        )  # Max 60% of daily amount
        portion = max(min_portion, min(portion, max_portion))

        # Log diet validation adjustments if applied
        if self.diet_validation:
            validation_summary = self._get_diet_validation_summary()
            if validation_summary.get("has_adjustments"):
                _LOGGER.info(
                    "Diet validation adjustments applied to portion for %s: %s",
                    self.dog_id,
                    validation_summary["adjustment_info"],
                )

        return round(portion, 1)

    def _get_diet_validation_summary(self) -> dict[str, Any]:
        """Get summary of diet validation adjustments.

        Returns:
            Dictionary with validation adjustment information
        """
        if not self.diet_validation:
            return {"has_adjustments": False, "adjustment_info": "No validation data"}

        conflicts = self.diet_validation.get("conflicts", [])
        warnings = self.diet_validation.get("warnings", [])

        adjustments = []
        if conflicts:
            adjustments.extend(
                [f"Conflict: {c.get('type', 'unknown')}" for c in conflicts]
            )
        if warnings:
            adjustments.extend(
                [f"Warning: {w.get('type', 'unknown')}" for w in warnings]
            )

        return {
            "has_adjustments": bool(adjustments),
            "adjustment_info": "; ".join(adjustments)
            if adjustments
            else "No adjustments",
            "conflict_count": len(conflicts),
            "warning_count": len(warnings),
            "vet_consultation_recommended": self.diet_validation.get(
                "recommended_vet_consultation", False
            ),
        }

    def update_diet_validation(self, validation_data: dict[str, Any]) -> None:
        """Update diet validation data and trigger portion recalculation.

        Args:
            validation_data: Diet validation results from config flow
        """
        self.diet_validation = validation_data

        # Log validation update
        validation_summary = self._get_diet_validation_summary()
        if validation_summary.get("has_adjustments"):
            _LOGGER.info(
                "Diet validation updated for %s: %s",
                self.dog_id,
                validation_summary["adjustment_info"],
            )

    def _build_health_metrics(
        self, override_data: Optional[dict[str, Any]] = None
    ) -> HealthMetrics:
        """Build health metrics from config and optional override data.

        Args:
            override_data: Optional real-time health data

        Returns:
            HealthMetrics object
        """
        # Start with config data
        current_weight = self.dog_weight
        ideal_weight = self.ideal_weight
        age_months = self.age_months
        health_conditions = list(self.health_conditions)

        # Apply overrides if provided
        if override_data:
            current_weight = override_data.get("weight", current_weight)
            ideal_weight = override_data.get("ideal_weight", ideal_weight)
            age_months = override_data.get("age_months", age_months)
            additional_conditions = override_data.get("health_conditions", [])
            health_conditions.extend(additional_conditions)

        # Determine life stage
        life_stage = None
        if age_months is not None:
            life_stage = HealthCalculator.calculate_life_stage(
                age_months, self.breed_size
            )

        # Parse activity level
        activity_level = None
        if self.activity_level:
            try:
                activity_level = ActivityLevel(self.activity_level)
            except ValueError:
                _LOGGER.warning("Invalid activity level: %s", self.activity_level)

        # Parse body condition score
        body_condition_score = None
        if self.body_condition_score is not None:
            body_condition_score = HealthCalculator.estimate_body_condition_score(
                current_weight or 20.0,  # Default weight if missing
                ideal_weight,
                self.body_condition_score,
            )

        return HealthMetrics(
            current_weight=current_weight or 20.0,  # Default medium dog weight
            ideal_weight=ideal_weight,
            age_months=age_months,
            body_condition_score=body_condition_score,
            activity_level=activity_level,
            life_stage=life_stage,
            health_conditions=health_conditions,
            special_diet=list(self.special_diet),
        )

    def _estimate_calories_per_gram(self) -> float:
        """Estimate calories per gram based on food type.

        Returns:
            Estimated calories per gram
        """
        # Calorie density by food type (kcal/gram)
        calorie_densities = {
            "dry_food": 3.5,  # Standard dry kibble
            "wet_food": 1.2,  # Canned food (high moisture)
            "barf": 2.5,  # Raw diet
            "home_cooked": 2.0,  # Varies widely
            "mixed": 2.8,  # Average of dry/wet
        }

        return calorie_densities.get(self.food_type, 3.5)

    def _get_meal_distribution(self) -> dict[MealType, float]:
        """Get meal distribution factors for health-optimized feeding.

        Returns:
            Dictionary mapping meal types to distribution factors
        """
        # Health-optimized meal distribution
        return {
            MealType.BREAKFAST: 1.2,  # Larger breakfast for energy
            MealType.LUNCH: 0.8,  # Lighter lunch
            MealType.DINNER: 1.0,  # Standard dinner
            MealType.SNACK: 0.3,  # Small snacks
            MealType.TREAT: 0.1,  # Minimal treats
            MealType.SUPPLEMENT: 0.05,  # Tiny supplements
        }

    def get_health_summary(self) -> dict[str, Any]:
        """Get summary of health-related feeding configuration.

        Returns:
            Dictionary with health configuration summary
        """
        health_metrics = self._build_health_metrics()

        # Calculate daily calorie requirement if possible
        daily_calories = None
        if health_metrics.current_weight:
            try:
                daily_calories = HealthCalculator.calculate_daily_calories(
                    weight=health_metrics.current_weight,
                    life_stage=health_metrics.life_stage or LifeStage.ADULT,
                    activity_level=health_metrics.activity_level
                    or ActivityLevel.MODERATE,
                    body_condition_score=health_metrics.body_condition_score,
                    health_conditions=health_metrics.health_conditions,
                    spayed_neutered=self.spayed_neutered,
                )
            except Exception as err:
                _LOGGER.warning("Calorie calculation failed: %s", err)

        return {
            "health_aware_enabled": self.health_aware_portions,
            "current_weight": health_metrics.current_weight,
            "ideal_weight": health_metrics.ideal_weight,
            "life_stage": health_metrics.life_stage.value
            if health_metrics.life_stage
            else None,
            "activity_level": health_metrics.activity_level.value
            if health_metrics.activity_level
            else None,
            "body_condition_score": health_metrics.body_condition_score.value
            if health_metrics.body_condition_score
            else None,
            "daily_calorie_requirement": daily_calories,
            "calories_per_gram": self._estimate_calories_per_gram(),
            "health_conditions": health_metrics.health_conditions,
            "special_diet": health_metrics.special_diet,
            "weight_goal": self.weight_goal,
            "diet_validation_applied": self.diet_validation is not None,
        }

    def get_special_diet_info(self) -> dict[str, Any]:
        """Get information about special diet requirements.

        Returns:
            Dictionary with special diet information
        """
        if not self.special_diet:
            return {"has_special_diet": False, "requirements": [], "validation": None}

        # Categorize special diet requirements
        health_related = ["diabetic", "kidney_support", "prescription", "low_fat"]
        age_related = ["senior_formula", "puppy_formula"]
        allergy_related = ["grain_free", "hypoallergenic", "sensitive_stomach"]
        lifestyle_related = ["weight_control", "organic", "raw_diet"]
        care_related = ["dental_care", "joint_support"]

        categorized = {
            "health": [d for d in self.special_diet if d in health_related],
            "age": [d for d in self.special_diet if d in age_related],
            "allergy": [d for d in self.special_diet if d in allergy_related],
            "lifestyle": [d for d in self.special_diet if d in lifestyle_related],
            "care": [d for d in self.special_diet if d in care_related],
        }

        return {
            "has_special_diet": True,
            "requirements": self.special_diet,
            "categories": {k: v for k, v in categorized.items() if v},
            "total_requirements": len(self.special_diet),
            "priority_level": "high"
            if any(d in health_related for d in self.special_diet)
            else "normal",
            "validation": self.diet_validation,
        }

    def get_active_schedules(self) -> list[MealSchedule]:
        """Get enabled meal schedules."""
        return [s for s in self.meal_schedules if s.enabled]

    def get_todays_schedules(self) -> list[MealSchedule]:
        """Get schedules due today."""
        return [s for s in self.meal_schedules if s.is_due_today()]


class FeedingManager:
    """Optimized feeding management with event-based reminders and caching."""

    def __init__(self, max_history: int = 100) -> None:
        """Initialize with configurable history limit.

        Args:
            max_history: Maximum feeding events to keep per dog
        """
        self._feedings: dict[str, list[FeedingEvent]] = {}
        self._configs: dict[str, FeedingConfig] = {}
        self._lock = asyncio.Lock()
        self._max_history = max_history

        # OPTIMIZATION: Event-based reminder system
        self._reminder_events: dict[str, asyncio.Event] = {}
        self._reminder_tasks: dict[str, asyncio.Task] = {}
        self._next_reminders: dict[str, datetime] = {}

        # OPTIMIZATION: Feeding data cache
        self._data_cache: dict[str, dict] = {}
        self._cache_time: dict[str, datetime] = {}
        self._cache_ttl = timedelta(seconds=10)

        # OPTIMIZATION: Statistics cache
        self._stats_cache: dict[str, dict] = {}
        self._stats_cache_time: dict[str, datetime] = {}
        self._stats_cache_ttl = timedelta(minutes=5)

    async def async_initialize(self, dogs: list[dict[str, Any]]) -> None:
        """Initialize feeding configurations for dogs.

        Args:
            dogs: List of dog configurations
        """
        async with self._lock:
            batch_configs = {}

            for dog in dogs:
                dog_id = dog.get("dog_id")
                if not dog_id:
                    continue

                feeding_config = dog.get("feeding_config", {})
                config = await self._create_feeding_config(dog_id, feeding_config)
                batch_configs[dog_id] = config

            # OPTIMIZATION: Batch update configs
            self._configs.update(batch_configs)

            # Setup reminders for all dogs with schedules
            for dog_id, config in batch_configs.items():
                if config.schedule_type != FeedingScheduleType.FLEXIBLE:
                    await self._setup_reminder(dog_id)

    async def _create_feeding_config(
        self, dog_id: str, config_data: dict[str, Any]
    ) -> FeedingConfig:
        """Create enhanced feeding configuration with health integration."""
        config = FeedingConfig(
            dog_id=dog_id,
            meals_per_day=config_data.get("meals_per_day", 2),
            daily_food_amount=config_data.get("daily_food_amount", 500.0),
            food_type=config_data.get("food_type", "dry_food"),
            special_diet=config_data.get("special_diet", []),
            schedule_type=FeedingScheduleType(
                config_data.get("feeding_schedule", "flexible")
            ),
            treats_enabled=config_data.get("treats_enabled", True),
            water_tracking=config_data.get("water_tracking", False),
            calorie_tracking=config_data.get("calorie_tracking", False),
            portion_calculation_enabled=config_data.get("portion_calculation", True),
            medication_with_meals=config_data.get("medication_with_meals", False),
            portion_tolerance=config_data.get("portion_tolerance", 10),
            # Health integration fields
            health_aware_portions=config_data.get("health_aware_portions", True),
            dog_weight=config_data.get("dog_weight"),
            ideal_weight=config_data.get("ideal_weight"),
            age_months=config_data.get("age_months"),
            breed_size=config_data.get("breed_size", "medium"),
            activity_level=config_data.get("activity_level"),
            body_condition_score=config_data.get("body_condition_score"),
            health_conditions=config_data.get("health_conditions", []),
            weight_goal=config_data.get("weight_goal"),
            spayed_neutered=config_data.get("spayed_neutered", True),
            # Diet validation integration
            diet_validation=config_data.get("diet_validation"),
        )

        meal_schedules = []
        portion_size = config.calculate_portion_size()

        # Parse meal times
        for meal_name, meal_enum in [
            ("breakfast_time", MealType.BREAKFAST),
            ("lunch_time", MealType.LUNCH),
            ("dinner_time", MealType.DINNER),
        ]:
            if meal_time_str := config_data.get(meal_name):
                if parsed_time := self._parse_time(meal_time_str):
                    meal_schedules.append(
                        MealSchedule(
                            meal_type=meal_enum,
                            scheduled_time=parsed_time,
                            portion_size=config_data.get("portion_size", portion_size),
                            reminder_enabled=config_data.get("enable_reminders", True),
                            reminder_minutes_before=config_data.get(
                                "reminder_minutes_before", 15
                            ),
                        )
                    )

        # Parse snack times
        for snack_time_str in config_data.get("snack_times", []):
            if parsed_time := self._parse_time(snack_time_str):
                meal_schedules.append(
                    MealSchedule(
                        meal_type=MealType.SNACK,
                        scheduled_time=parsed_time,
                        portion_size=50.0,
                        reminder_enabled=False,
                    )
                )

        config.meal_schedules = meal_schedules
        return config

    def _parse_time(self, time_str: str | time) -> Optional[time]:
        """Parse time string to time object."""
        if isinstance(time_str, time):
            return time_str

        try:
            parts = time_str.split(":")
            if len(parts) == 2:
                return time(int(parts[0]), int(parts[1]))
            elif len(parts) == 3:
                return time(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, AttributeError):
            _LOGGER.warning("Failed to parse time: %s", time_str)

        return None

    async def _setup_reminder(self, dog_id: str) -> None:
        """Setup event-based reminder for a dog.

        OPTIMIZATION: Uses events instead of sleep loops.

        Args:
            dog_id: Dog identifier
        """
        # Cancel existing reminder
        if dog_id in self._reminder_tasks:
            self._reminder_tasks[dog_id].cancel()

        # Create event for reminder updates
        self._reminder_events[dog_id] = asyncio.Event()

        # Create reminder task
        self._reminder_tasks[dog_id] = asyncio.create_task(
            self._reminder_handler(dog_id)
        )

    async def _reminder_handler(self, dog_id: str) -> None:
        """Event-based reminder handler.

        OPTIMIZATION: Uses events to wake up instead of continuous sleeping.

        Args:
            dog_id: Dog identifier
        """
        event = self._reminder_events[dog_id]

        while True:
            try:
                config = self._configs.get(dog_id)
                if not config:
                    break

                # Calculate next reminder
                next_reminder = await self._calculate_next_reminder(config)

                if next_reminder:
                    self._next_reminders[dog_id] = next_reminder

                    # Wait until reminder time or event signal
                    now = dt_util.now()
                    if next_reminder > now:
                        wait_seconds = (next_reminder - now).total_seconds()

                        # Wait for timeout or event signal
                        try:
                            await asyncio.wait_for(event.wait(), timeout=wait_seconds)
                            # Event was set - recalculate
                            event.clear()
                            continue
                        except asyncio.TimeoutError:
                            # Time to send reminder
                            schedule = await self._get_reminder_schedule(
                                config, next_reminder
                            )
                            if schedule:
                                _LOGGER.info(
                                    "Feeding reminder for %s: %s in %d minutes",
                                    dog_id,
                                    schedule.meal_type.value,
                                    schedule.reminder_minutes_before,
                                )
                else:
                    # No reminders - wait for event signal
                    await event.wait()
                    event.clear()

            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in reminder handler for %s: %s", dog_id, err)
                await asyncio.sleep(60)  # Error recovery

    async def _calculate_next_reminder(
        self, config: FeedingConfig
    ) -> Optional[datetime]:
        """Calculate next reminder time for a config.

        Args:
            config: Feeding configuration

        Returns:
            Next reminder datetime or None
        """
        next_reminder = None

        for schedule in config.get_todays_schedules():
            reminder_time = schedule.get_reminder_time()
            if reminder_time and reminder_time > dt_util.now():
                if next_reminder is None or reminder_time < next_reminder:
                    next_reminder = reminder_time

        # If no reminders today, check tomorrow
        if next_reminder is None:
            tomorrow = dt_util.now() + timedelta(days=1)
            tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0)

            for schedule in config.get_active_schedules():
                reminder_time = schedule.get_reminder_time()
                if reminder_time and reminder_time >= tomorrow_start:
                    if next_reminder is None or reminder_time < next_reminder:
                        next_reminder = reminder_time

        return next_reminder

    async def _get_reminder_schedule(
        self, config: FeedingConfig, reminder_time: datetime
    ) -> Optional[MealSchedule]:
        """Get schedule for a reminder time.

        Args:
            config: Feeding configuration
            reminder_time: Reminder datetime

        Returns:
            Meal schedule or None
        """
        for schedule in config.get_active_schedules():
            if schedule.get_reminder_time() == reminder_time:
                return schedule
        return None

    async def async_add_feeding(
        self,
        dog_id: str,
        amount: float,
        meal_type: Optional[str] = None,
        time: Optional[datetime] = None,
        notes: Optional[str] = None,
        feeder: Optional[str] = None,
        scheduled: bool = False,
    ) -> FeedingEvent:
        """Record a feeding event.

        Args:
            dog_id: Identifier of the dog
            amount: Amount of food in grams
            meal_type: Type of meal
            time: Optional timestamp
            notes: Optional notes
            feeder: Who fed the dog
            scheduled: Whether scheduled feeding

        Returns:
            Created FeedingEvent
        """
        async with self._lock:
            meal_type_enum = None
            if meal_type:
                try:
                    meal_type_enum = MealType(meal_type)
                except ValueError:
                    _LOGGER.warning("Invalid meal type: %s", meal_type)

            config = self._configs.get(dog_id)
            portion_size = None

            if config and meal_type_enum:
                # Use health-aware portion calculation if enabled
                if config.portion_calculation_enabled:
                    portion_size = config.calculate_portion_size(
                        meal_type_enum,
                        health_data=None,  # Could pass real-time health data here
                    )
                else:
                    # Fall back to schedule-based portion size
                    for schedule in config.meal_schedules:
                        if schedule.meal_type == meal_type_enum:
                            portion_size = schedule.portion_size
                            break

            event = FeedingEvent(
                time=time or dt_util.now(),
                amount=amount,
                meal_type=meal_type_enum,
                portion_size=portion_size,
                food_type=config.food_type if config else None,
                notes=notes,
                feeder=feeder,
                scheduled=scheduled,
            )

            self._feedings.setdefault(dog_id, []).append(event)

            # OPTIMIZATION: Maintain history limit
            if len(self._feedings[dog_id]) > self._max_history:
                self._feedings[dog_id] = self._feedings[dog_id][-self._max_history :]

            # Invalidate caches
            self._invalidate_cache(dog_id)

            # Signal reminder update if scheduled feeding
            if scheduled and dog_id in self._reminder_events:
                self._reminder_events[dog_id].set()

            return event

    async def async_add_feeding_with_medication(
        self,
        dog_id: str,
        amount: float,
        meal_type: str,
        medication_data: Optional[dict[str, Any]] = None,
        time: Optional[datetime] = None,
        notes: Optional[str] = None,
        feeder: Optional[str] = None,
    ) -> FeedingEvent:
        """Record feeding with linked medication administration.

        Args:
            dog_id: Dog identifier
            amount: Food amount in grams
            meal_type: Type of meal
            medication_data: Optional medication information
            time: Optional timestamp
            notes: Optional notes
            feeder: Who fed the dog

        Returns:
            Created FeedingEvent with medication link
        """
        config = self._configs.get(dog_id)
        if not config or not config.medication_with_meals:
            # If medication linking is disabled, just record normal feeding
            return await self.async_add_feeding(
                dog_id, amount, meal_type, time, notes, feeder
            )

        # Combine feeding notes with medication info
        combined_notes = notes or ""
        if medication_data:
            med_name = medication_data.get("name", "Unknown")
            med_dose = medication_data.get("dose", "")
            med_time = medication_data.get("time", "with meal")

            med_note = f"Medication: {med_name}"
            if med_dose:
                med_note += f" ({med_dose})"
            if med_time != "with meal":
                med_note += f" at {med_time}"

            combined_notes = (
                f"{combined_notes}\n{med_note}" if combined_notes else med_note
            )

        # Record feeding with medication info
        return await self.async_add_feeding(
            dog_id=dog_id,
            amount=amount,
            meal_type=meal_type,
            time=time,
            notes=combined_notes,
            feeder=feeder,
            scheduled=True,  # Mark as scheduled since it includes medication
        )

    async def async_batch_add_feedings(
        self, feedings: list[dict[str, Any]]
    ) -> list[FeedingEvent]:
        """OPTIMIZATION: Add multiple feeding events at once.

        Args:
            feedings: List of feeding data dictionaries

        Returns:
            List of created FeedingEvents
        """
        events = []

        async with self._lock:
            for feeding_data in feedings:
                dog_id = feeding_data.pop("dog_id")
                event = await self.async_add_feeding(dog_id, **feeding_data)
                events.append(event)

        return events

    async def async_get_feedings(
        self, dog_id: str, since: Optional[datetime] = None
    ) -> list[FeedingEvent]:
        """Return feeding history for a dog.

        Args:
            dog_id: Dog identifier
            since: Optional datetime filter

        Returns:
            List of feeding events
        """
        async with self._lock:
            feedings = self._feedings.get(dog_id, [])

            if since:
                # OPTIMIZATION: Binary search for efficiency with large lists
                left, right = 0, len(feedings)
                while left < right:
                    mid = (left + right) // 2
                    if feedings[mid].time < since:
                        left = mid + 1
                    else:
                        right = mid
                feedings = feedings[left:]

            return list(feedings)

    async def async_get_feeding_data(self, dog_id: str) -> dict[str, Any]:
        """Get comprehensive feeding data with caching.

        OPTIMIZATION: Caches feeding data for 10 seconds.

        Args:
            dog_id: Dog identifier

        Returns:
            Dictionary with feeding statistics
        """
        async with self._lock:
            # Check cache
            if dog_id in self._data_cache:
                cache_time = self._cache_time.get(dog_id)
                if cache_time and (dt_util.now() - cache_time) < self._cache_ttl:
                    return self._data_cache[dog_id]

            # Calculate feeding data
            data = await self._calculate_feeding_data(dog_id)

            # Cache result
            self._data_cache[dog_id] = data
            self._cache_time[dog_id] = dt_util.now()

            return data

    async def _calculate_feeding_data(self, dog_id: str) -> dict[str, Any]:
        """Calculate feeding data without cache.

        OPTIMIZATION: Single pass through data with minimal lookups.

        Args:
            dog_id: Dog identifier

        Returns:
            Feeding data dictionary
        """
        feedings = self._feedings.get(dog_id, [])
        config = self._configs.get(dog_id)

        if not feedings:
            return self._empty_feeding_data(config)

        now = dt_util.now()
        today = now.date()

        # OPTIMIZATION: Single pass data collection
        feedings_today = {}
        daily_amount = 0.0
        last_feeding = None
        scheduled_count = 0

        for event in reversed(feedings):
            if event.time.date() == today and not event.skipped:
                meal = event.meal_type.value if event.meal_type else "unknown"
                feedings_today[meal] = feedings_today.get(meal, 0) + 1
                daily_amount += event.amount

                if event.scheduled:
                    scheduled_count += 1

            if not last_feeding and not event.skipped:
                last_feeding = event

        last_hours = None
        if last_feeding:
            last_hours = (now - last_feeding.time).total_seconds() / 3600

        # Calculate schedule adherence and missed feedings
        adherence = 100
        missed_feedings = []

        if config and config.schedule_type != FeedingScheduleType.FLEXIBLE:
            todays_schedules = config.get_todays_schedules()
            expected = len(todays_schedules)

            if expected > 0:
                # OPTIMIZATION: Pre-calculate time windows
                for schedule in todays_schedules:
                    scheduled_datetime = datetime.combine(
                        today, schedule.scheduled_time
                    )
                    scheduled_datetime = dt_util.as_local(scheduled_datetime)

                    if scheduled_datetime <= now:
                        # Check if fed within window
                        meal_type_found = schedule.meal_type.value in feedings_today

                        if not meal_type_found:
                            missed_feedings.append(
                                {
                                    "meal_type": schedule.meal_type.value,
                                    "scheduled_time": scheduled_datetime.isoformat(),
                                }
                            )

                completed = expected - len(missed_feedings)
                adherence = int((completed / expected) * 100)

        # Find next feeding
        next_feeding = None
        next_type = None

        if config:
            for schedule in config.get_active_schedules():
                next_time = schedule.get_next_feeding_time()
                if next_feeding is None or next_time < next_feeding:
                    next_feeding = next_time
                    next_type = schedule.meal_type.value

        return {
            "last_feeding": last_feeding.time.isoformat() if last_feeding else None,
            "last_feeding_type": (
                last_feeding.meal_type.value
                if last_feeding and last_feeding.meal_type
                else None
            ),
            "last_feeding_hours": last_hours,
            "last_feeding_amount": last_feeding.amount if last_feeding else None,
            "feedings_today": feedings_today,
            "total_feedings_today": sum(feedings_today.values()),
            "daily_amount_consumed": daily_amount,
            "daily_amount_target": config.daily_food_amount if config else 500,
            "daily_amount_percentage": (
                int((daily_amount / config.daily_food_amount * 100))
                if config and config.daily_food_amount > 0
                else 0
            ),
            "schedule_adherence": adherence,
            "next_feeding": next_feeding.isoformat() if next_feeding else None,
            "next_feeding_type": next_type,
            "missed_feedings": missed_feedings,
            "config": {
                "meals_per_day": config.meals_per_day if config else 2,
                "food_type": config.food_type if config else "dry_food",
                "schedule_type": (config.schedule_type.value if config else "flexible"),
            }
            if config
            else None,
        }

    def _empty_feeding_data(self, config: Optional[FeedingConfig]) -> dict[str, Any]:
        """Generate empty feeding data structure.

        Args:
            config: Optional feeding configuration

        Returns:
            Empty data dictionary
        """
        return {
            "last_feeding": None,
            "feedings_today": {},
            "total_feedings_today": 0,
            "daily_amount_consumed": 0,
            "daily_amount_target": config.daily_food_amount if config else 500,
            "schedule_adherence": 100,
            "next_feeding": None,
            "missed_feedings": [],
        }

    def _invalidate_cache(self, dog_id: str) -> None:
        """Invalidate caches for a dog.

        Args:
            dog_id: Dog identifier
        """
        self._data_cache.pop(dog_id, None)
        self._cache_time.pop(dog_id, None)

        # Clear stats cache entries
        keys_to_remove = [
            key for key in self._stats_cache if key.startswith(f"{dog_id}_")
        ]
        for key in keys_to_remove:
            self._stats_cache.pop(key, None)
            self._stats_cache_time.pop(key, None)

    async def async_update_config(
        self, dog_id: str, config_data: dict[str, Any]
    ) -> None:
        """Update feeding configuration for a dog.

        Args:
            dog_id: Dog identifier
            config_data: New configuration data
        """
        async with self._lock:
            config = await self._create_feeding_config(dog_id, config_data)
            self._configs[dog_id] = config

            # Invalidate caches
            self._invalidate_cache(dog_id)

            # Update reminders
            if config.schedule_type != FeedingScheduleType.FLEXIBLE:
                await self._setup_reminder(dog_id)
            elif dog_id in self._reminder_tasks:
                self._reminder_tasks[dog_id].cancel()
                del self._reminder_tasks[dog_id]
                del self._reminder_events[dog_id]
                self._next_reminders.pop(dog_id, None)

            # Signal reminder update
            if dog_id in self._reminder_events:
                self._reminder_events[dog_id].set()

    async def async_get_statistics(self, dog_id: str, days: int = 30) -> dict[str, Any]:
        """Get feeding statistics with caching.

        OPTIMIZATION: Caches statistics for 5 minutes.

        Args:
            dog_id: Dog identifier
            days: Number of days to analyze

        Returns:
            Dictionary with feeding statistics
        """
        cache_key = f"{dog_id}_{days}"

        async with self._lock:
            # Check cache
            if cache_key in self._stats_cache:
                cache_time = self._stats_cache_time.get(cache_key)
                if cache_time and (dt_util.now() - cache_time) < self._stats_cache_ttl:
                    return self._stats_cache[cache_key]

            # Calculate statistics
            stats = await self._calculate_statistics(dog_id, days)

            # Cache result
            self._stats_cache[cache_key] = stats
            self._stats_cache_time[cache_key] = dt_util.now()

            return stats

    async def _calculate_statistics(self, dog_id: str, days: int) -> dict[str, Any]:
        """Calculate statistics without cache.

        OPTIMIZATION: Efficient data aggregation.

        Args:
            dog_id: Dog identifier
            days: Days to analyze

        Returns:
            Statistics dictionary
        """
        feedings = self._feedings.get(dog_id, [])
        config = self._configs.get(dog_id)

        since = dt_util.now() - timedelta(days=days)

        # OPTIMIZATION: Binary search for start position
        left, right = 0, len(feedings)
        while left < right:
            mid = (left + right) // 2
            if feedings[mid].time < since:
                left = mid + 1
            else:
                right = mid

        recent_feedings = feedings[left:]

        if not recent_feedings:
            return {
                "period_days": days,
                "total_feedings": 0,
                "average_daily_feedings": 0,
                "average_daily_amount": 0,
                "most_common_meal": None,
                "schedule_adherence": 100,
            }

        # OPTIMIZATION: Single pass aggregation
        daily_counts = {}
        daily_amounts = {}
        meal_counts = {}

        for feeding in recent_feedings:
            if feeding.skipped:
                continue

            date = feeding.time.date()
            daily_counts[date] = daily_counts.get(date, 0) + 1
            daily_amounts[date] = daily_amounts.get(date, 0.0) + feeding.amount

            if feeding.meal_type:
                meal = feeding.meal_type.value
                meal_counts[meal] = meal_counts.get(meal, 0) + 1

        # Calculate metrics
        avg_daily_feedings = (
            sum(daily_counts.values()) / len(daily_counts) if daily_counts else 0
        )
        avg_daily_amount = (
            sum(daily_amounts.values()) / len(daily_amounts) if daily_amounts else 0
        )

        most_common_meal = (
            max(meal_counts, key=meal_counts.get) if meal_counts else None
        )

        # Calculate adherence
        adherence = 100
        if config and config.schedule_type != FeedingScheduleType.FLEXIBLE:
            expected_daily = len(config.get_active_schedules())
            if expected_daily > 0:
                adherence = min(100, int((avg_daily_feedings / expected_daily) * 100))

        return {
            "period_days": days,
            "total_feedings": len([f for f in recent_feedings if not f.skipped]),
            "average_daily_feedings": round(avg_daily_feedings, 1),
            "average_daily_amount": round(avg_daily_amount, 1),
            "most_common_meal": most_common_meal,
            "schedule_adherence": adherence,
            "daily_target_met_percentage": (
                int((avg_daily_amount / config.daily_food_amount * 100))
                if config and config.daily_food_amount > 0
                else 0
            ),
        }

    async def async_get_reminders(self) -> dict[str, datetime]:
        """Get all next reminder times.

        Returns:
            Dictionary mapping dog_id to next reminder time
        """
        async with self._lock:
            return dict(self._next_reminders)

    async def async_calculate_health_aware_portion(
        self, dog_id: str, meal_type: str, health_data: Optional[dict[str, Any]] = None
    ) -> Optional[float]:
        """Calculate health-aware portion for a specific meal.

        Args:
            dog_id: Dog identifier
            meal_type: Type of meal
            health_data: Optional real-time health data

        Returns:
            Calculated portion size in grams or None if not possible
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config or not config.health_aware_portions:
                return None

            try:
                meal_type_enum = MealType(meal_type)
                return config.calculate_portion_size(meal_type_enum, health_data)
            except (ValueError, Exception) as err:
                _LOGGER.warning(
                    "Health-aware portion calculation failed for %s: %s", dog_id, err
                )
                return None

    async def async_analyze_feeding_health(
        self, dog_id: str, days: int = 7
    ) -> dict[str, Any]:
        """Analyze feeding patterns from health perspective.

        Args:
            dog_id: Dog identifier
            days: Number of days to analyze

        Returns:
            Health analysis of feeding patterns
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            feedings = self._feedings.get(dog_id, [])

            if not config or not feedings:
                return {
                    "status": "insufficient_data",
                    "message": "Need feeding configuration and history",
                }

            # Get recent feeding events
            since = dt_util.now() - timedelta(days=days)
            recent_events = [
                {
                    "time": event.time,
                    "amount": event.amount,
                    "meal_type": event.meal_type.value if event.meal_type else None,
                }
                for event in feedings
                if event.time > since and not event.skipped
            ]

            if not recent_events:
                return {
                    "status": "no_recent_data",
                    "message": f"No feeding data in last {days} days",
                }

            # Get health summary for target calories
            health_summary = config.get_health_summary()
            target_calories = health_summary.get("daily_calorie_requirement")

            if not target_calories:
                return {
                    "status": "no_health_data",
                    "message": "Insufficient health data for analysis",
                }

            # Use health calculator to analyze patterns
            calories_per_gram = health_summary.get("calories_per_gram", 3.5)

            analysis = HealthCalculator.analyze_feeding_history(
                recent_events, target_calories, calories_per_gram
            )

            # Add health-specific recommendations
            analysis["health_context"] = {
                "weight_goal": config.weight_goal,
                "body_condition_score": health_summary.get("body_condition_score"),
                "life_stage": health_summary.get("life_stage"),
                "activity_level": health_summary.get("activity_level"),
                "health_conditions": health_summary.get("health_conditions"),
                "special_diet": health_summary.get("special_diet"),
            }

            return analysis

    async def async_generate_health_report(
        self, dog_id: str
    ) -> Optional[dict[str, Any]]:
        """Generate comprehensive health report for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Health report or None if insufficient data
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config or not config.health_aware_portions:
                return None

            try:
                # Build health metrics
                health_metrics = config._build_health_metrics()

                # Generate health report
                report = HealthCalculator.generate_health_report(health_metrics)

                # Add feeding-specific insights
                health_summary = config.get_health_summary()
                report["feeding_insights"] = {
                    "daily_calorie_target": health_summary.get(
                        "daily_calorie_requirement"
                    ),
                    "portion_adjustment_factor": HealthCalculator.calculate_portion_adjustment_factor(
                        health_metrics, {"weight_goal": config.weight_goal}
                    ),
                    "recommended_meals_per_day": self._recommend_meal_frequency(
                        health_metrics
                    ),
                    "food_type_recommendation": self._recommend_food_type(
                        health_metrics
                    ),
                }

                # Add recent feeding analysis
                feeding_analysis = await self.async_analyze_feeding_health(dog_id, 14)
                if feeding_analysis.get("status") == "good":
                    report["recent_feeding_performance"] = feeding_analysis

                return report

            except Exception as err:
                _LOGGER.error("Health report generation failed for %s: %s", dog_id, err)
                return None

    def _recommend_meal_frequency(self, health_metrics: HealthMetrics) -> int:
        """Recommend optimal meal frequency based on health metrics.

        Args:
            health_metrics: Health metrics for the dog

        Returns:
            Recommended number of meals per day
        """
        # Base recommendation on life stage and health conditions
        if health_metrics.life_stage == LifeStage.PUPPY:
            if health_metrics.age_months and health_metrics.age_months < 6:
                return 4  # Very young puppies need frequent meals
            return 3  # Older puppies

        # Check for health conditions requiring frequent meals
        frequent_meal_conditions = ["diabetes", "digestive_issues", "hypoglycemia"]
        if any(
            condition in health_metrics.health_conditions
            for condition in frequent_meal_conditions
        ):
            return 3

        # Senior dogs often benefit from smaller, frequent meals
        if health_metrics.life_stage in [LifeStage.SENIOR, LifeStage.GERIATRIC]:
            return 3

        # Default for healthy adult dogs
        return 2

    def _recommend_food_type(self, health_metrics: HealthMetrics) -> str:
        """Recommend food type based on health metrics.

        Args:
            health_metrics: Health metrics for the dog

        Returns:
            Recommended food type
        """
        # Check for specific health conditions
        if "kidney_disease" in health_metrics.health_conditions:
            return "prescription"  # Requires prescription diet

        if "diabetes" in health_metrics.health_conditions:
            return "prescription"  # Requires controlled diet

        if "digestive_issues" in health_metrics.health_conditions:
            return "wet_food"  # Easier to digest

        # Age-based recommendations
        if health_metrics.life_stage == LifeStage.PUPPY:
            return "puppy_formula"

        if health_metrics.life_stage in [LifeStage.SENIOR, LifeStage.GERIATRIC]:
            if health_metrics.activity_level == ActivityLevel.VERY_LOW:
                return "senior_formula"

        # Weight management
        if (
            health_metrics.body_condition_score
            and health_metrics.body_condition_score.value >= 7
        ):
            return "weight_control"

        # Default recommendation
        return "dry_food"

    async def async_update_health_data(
        self, dog_id: str, health_data: dict[str, Any]
    ) -> bool:
        """Update health data for a dog and recalculate portions.

        Args:
            dog_id: Dog identifier
            health_data: Updated health information

        Returns:
            True if update successful
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config:
                return False

            try:
                # Update health-related fields
                if "weight" in health_data:
                    config.dog_weight = health_data["weight"]
                if "ideal_weight" in health_data:
                    config.ideal_weight = health_data["ideal_weight"]
                if "age_months" in health_data:
                    config.age_months = health_data["age_months"]
                if "activity_level" in health_data:
                    config.activity_level = health_data["activity_level"]
                if "body_condition_score" in health_data:
                    config.body_condition_score = health_data["body_condition_score"]
                if "health_conditions" in health_data:
                    config.health_conditions = health_data["health_conditions"]
                if "weight_goal" in health_data:
                    config.weight_goal = health_data["weight_goal"]

                # Invalidate caches to force recalculation
                self._invalidate_cache(dog_id)

                _LOGGER.info("Updated health data for dog %s", dog_id)
                return True

            except Exception as err:
                _LOGGER.error("Failed to update health data for %s: %s", dog_id, err)
                return False

    async def async_update_diet_validation(
        self, dog_id: str, validation_data: dict[str, Any]
    ) -> bool:
        """Update diet validation data for a dog.

        Args:
            dog_id: Dog identifier
            validation_data: Diet validation results from config flow

        Returns:
            True if update successful
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config:
                _LOGGER.warning("No config found for dog %s", dog_id)
                return False

            try:
                # Update diet validation in config
                config.update_diet_validation(validation_data)

                # Invalidate caches to force recalculation
                self._invalidate_cache(dog_id)

                _LOGGER.info(
                    "Updated diet validation for dog %s: %d conflicts, %d warnings",
                    dog_id,
                    len(validation_data.get("conflicts", [])),
                    len(validation_data.get("warnings", [])),
                )
                return True

            except Exception as err:
                _LOGGER.error(
                    "Failed to update diet validation for %s: %s", dog_id, err
                )
                return False

    async def async_get_diet_validation_status(
        self, dog_id: str
    ) -> Optional[dict[str, Any]]:
        """Get current diet validation status for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Diet validation status or None if not available
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config or not config.diet_validation:
                return None

            return {
                "validation_data": config.diet_validation,
                "summary": config._get_diet_validation_summary(),
                "special_diets": config.special_diet,
                "last_updated": dt_util.now().isoformat(),
            }

    async def async_validate_portion_with_diet(
        self,
        dog_id: str,
        meal_type: str,
        override_health_data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Calculate portion with diet validation and safety checks.

        Args:
            dog_id: Dog identifier
            meal_type: Type of meal
            override_health_data: Optional real-time health data

        Returns:
            Dictionary with portion calculation and validation results
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config:
                return {"error": "No configuration found", "portion": 0.0}

            try:
                # Calculate health-aware portion
                meal_type_enum = MealType(meal_type)
                portion = config.calculate_portion_size(
                    meal_type_enum, override_health_data
                )

                # Growth safeguard for puppies
                base_unadjusted = config.daily_food_amount / config.meals_per_day
                health_metrics = config._build_health_metrics(override_health_data)
                if health_metrics.life_stage == LifeStage.PUPPY:
                    portion = max(
                        portion, base_unadjusted * PUPPY_PORTION_SAFEGUARD_FACTOR
                    )

                # Validate portion safety with diet considerations
                if config.dog_weight and portion > 0:
                    safety_result = HealthCalculator.validate_portion_safety(
                        calculated_portion=portion,
                        dog_weight=config.dog_weight,
                        life_stage=HealthCalculator.calculate_life_stage(
                            config.age_months or 24, config.breed_size
                        ),
                        special_diets=config.special_diet,
                        diet_validation=config.diet_validation,
                    )
                else:
                    safety_result = {
                        "safe": True,
                        "warnings": [],
                        "recommendations": [],
                    }

                # Include diet validation info
                validation_summary = (
                    config._get_diet_validation_summary()
                    if config.diet_validation
                    else None
                )

                return {
                    "portion": portion,
                    "meal_type": meal_type,
                    "safety_validation": safety_result,
                    "diet_validation_summary": validation_summary,
                    "health_aware_calculation": config.health_aware_portions,
                    "config_id": dog_id,
                }

            except Exception as err:
                _LOGGER.error("Portion validation failed for %s: %s", dog_id, err)
                return {"error": str(err), "portion": 0.0, "meal_type": meal_type}

    async def async_shutdown(self) -> None:
        """Clean shutdown of feeding manager."""
        # Cancel all reminder tasks
        for task in self._reminder_tasks.values():
            task.cancel()

        if self._reminder_tasks:
            await asyncio.gather(*self._reminder_tasks.values(), return_exceptions=True)

        # Clear all data
        self._reminder_tasks.clear()
        self._reminder_events.clear()
        self._next_reminders.clear()
        self._feedings.clear()
        self._configs.clear()
        self._data_cache.clear()
        self._cache_time.clear()
        self._stats_cache.clear()
        self._stats_cache_time.clear()
