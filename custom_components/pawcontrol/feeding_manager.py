"""Feeding management with health-aware portions for PawControl."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from time import perf_counter
from typing import Any, Literal, TypedDict, TypeVar, cast

from homeassistant.util import dt as dt_util

from .utils import is_number

# Support running as standalone module in tests
try:  # pragma: no cover - fallback for direct test execution
    from .health_calculator import (
        ActivityLevel,
        DietSafetyResult,
        HealthCalculator,
        HealthMetrics,
        LifeStage,
    )
except ImportError:  # pragma: no cover
    from custom_components.pawcontrol.health_calculator import (
        ActivityLevel,
        DietSafetyResult,
        HealthCalculator,
        HealthMetrics,
        LifeStage,
    )

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


# Portion safeguard constants
PUPPY_PORTION_SAFEGUARD_FACTOR = 0.95
MINIMUM_NUTRITION_PORTION_G = 50.1
# Portion safety limits relative to daily ration (0.0-1.0)
# Defines min/max allowable portion size as fraction of daily ration
MIN_PORTION_SAFETY_FACTOR = 0.1  # Minimum 10% of daily ration per portion
MAX_PORTION_SAFETY_FACTOR = 0.6  # Maximum 60% of daily ration per portion


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
    meal_type: MealType | None = None
    portion_size: float | None = None
    food_type: str | None = None
    notes: str | None = None
    feeder: str | None = None
    scheduled: bool = False
    skipped: bool = False
    with_medication: bool = False
    medication_name: str | None = None
    medication_dose: str | None = None
    medication_time: str | None = None

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
            "with_medication": self.with_medication,
            "medication_name": self.medication_name,
            "medication_dose": self.medication_dose,
            "medication_time": self.medication_time,
        }


@dataclass(slots=True)
class _DailyComplianceAccumulator:
    """Internal accumulator for per-day compliance statistics."""

    date: str
    feedings: list[FeedingEvent] = field(default_factory=list)
    total_amount: float = 0.0
    meal_types: set[str] = field(default_factory=set)
    scheduled_feedings: int = 0


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
    days_of_week: list[int] | None = None

    def is_due_today(self) -> bool:
        """Check if meal is scheduled for today."""
        if not self.enabled:
            return False

        if self.days_of_week is None:
            return True

        today = dt_util.now().weekday()
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

    def get_reminder_time(self) -> datetime | None:
        """Get reminder time for this meal."""
        if not self.reminder_enabled:
            return None

        next_feeding = self.get_next_feeding_time()
        return next_feeding - timedelta(minutes=self.reminder_minutes_before)


class FeedingTransitionData(TypedDict):
    """Telemetry describing an in-progress feeding transition."""

    active: bool
    start_date: str
    old_food_type: str
    new_food_type: str
    transition_days: int
    gradual_increase_percent: int
    schedule: list[dict[str, Any]]
    current_day: int


class ComplianceIssue(TypedDict):
    """Structured compliance issue telemetry."""

    date: str
    issues: list[str]
    severity: str


class MissedMealEntry(TypedDict):
    """Metadata describing a missed scheduled meal."""

    date: str
    expected: int
    actual: int


class FeedingEventTelemetry(TypedDict, total=False):
    """Serialized telemetry describing a recorded feeding event."""

    time: str
    amount: float
    meal_type: str | None
    portion_size: float | None
    food_type: str | None
    notes: str | None
    feeder: str | None
    scheduled: bool
    skipped: bool
    with_medication: bool
    medication_name: str | None
    medication_dose: str | None
    medication_time: str | None


class DailyComplianceTelemetry(TypedDict):
    """Telemetry summarising compliance statistics for a day."""

    date: str
    feedings: list[FeedingEventTelemetry]
    total_amount: float
    meal_types: list[str]
    scheduled_feedings: int


class FeedingComplianceSummary(TypedDict):
    """Summary metrics for the compliance analysis window."""

    average_daily_amount: float
    average_meals_per_day: float
    expected_daily_amount: float
    expected_meals_per_day: int


class FeedingComplianceCompleted(TypedDict):
    """Successful compliance analysis payload."""

    status: Literal["completed"]
    dog_id: str
    compliance_score: int
    compliance_rate: float
    days_analyzed: int
    days_with_issues: int
    compliance_issues: list[ComplianceIssue]
    missed_meals: list[MissedMealEntry]
    daily_analysis: dict[str, DailyComplianceTelemetry]
    recommendations: list[str]
    summary: FeedingComplianceSummary
    checked_at: str


class FeedingComplianceNoData(TypedDict):
    """Compliance analysis result when insufficient telemetry exists."""

    status: Literal["no_data", "no_recent_data"]
    message: str


FeedingComplianceResult = FeedingComplianceCompleted | FeedingComplianceNoData


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
    calories_per_gram: float | None = None
    portion_calculation_enabled: bool = True
    medication_with_meals: bool = False
    portion_tolerance: int = 10  # percentage

    # Health integration fields
    health_aware_portions: bool = True
    dog_weight: float | None = None
    ideal_weight: float | None = None
    age_months: int | None = None
    breed_size: str = "medium"
    activity_level: str | None = None
    body_condition_score: int | None = None
    health_conditions: list[str] = field(default_factory=list)
    weight_goal: str | None = None  # "maintain", "lose", "gain"
    spayed_neutered: bool = True

    # Diet validation integration
    diet_validation: dict[str, Any] | None = None
    transition_data: FeedingTransitionData | None = None

    def calculate_portion_size(
        self,
        meal_type: MealType | None = None,
        health_data: dict[str, Any] | None = None,
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
        meal_type: MealType | None = None,
        health_data: dict[str, Any] | None = None,
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

        # Apply safety limits
        min_portion = (
            adjusted_daily_grams * MIN_PORTION_SAFETY_FACTOR
        )  # Min 10% of daily amount
        max_factor = 1.0 if self.meals_per_day == 1 else MAX_PORTION_SAFETY_FACTOR
        max_portion = (
            adjusted_daily_grams * max_factor
        )  # Max 60% of daily amount (100% if single meal)
        portion = max(min_portion, min(portion, max_portion))

        # Ensure minimum nutrition thresholds after safety limits
        portion = max(portion, MINIMUM_NUTRITION_PORTION_G)

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
        """Get summary of diet validation adjustments."""

        total_diets = len(self.special_diet or [])

        if not self.diet_validation:
            return {
                "has_adjustments": False,
                "adjustment_info": "No validation data",
                "conflict_count": 0,
                "warning_count": 0,
                "vet_consultation_recommended": False,
                "vet_consultation_state": "not_needed",
                "consultation_urgency": "none",
                "total_diets": total_diets,
                "diet_validation_adjustment": 1.0,
                "percentage_adjustment": 0.0,
                "adjustment_direction": "none",
                "safety_factor": "normal",
                "compatibility_score": 100,
                "compatibility_level": "excellent",
                "conflicts": [],
                "warnings": [],
            }

        conflicts = self.diet_validation.get("conflicts", [])
        warnings = self.diet_validation.get("warnings", [])
        total_diets = max(
            total_diets,
            int(self.diet_validation.get("total_diets", total_diets) or total_diets),
        )

        try:
            validation_adjustment = (
                HealthCalculator.calculate_diet_validation_adjustment(
                    self.diet_validation,
                    self.special_diet,
                )
            )
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.debug(
                "Failed to calculate diet validation adjustment for %s: %s",
                self.dog_id,
                err,
            )
            validation_adjustment = 1.0

        percentage_adjustment = round((validation_adjustment - 1.0) * 100.0, 1)

        if percentage_adjustment > 0.5:
            adjustment_direction = "increase"
        elif percentage_adjustment < -0.5:
            adjustment_direction = "decrease"
        else:
            adjustment_direction = "none"

        safety_factor = "conservative" if validation_adjustment < 1.0 else "normal"

        adjustments = []
        if conflicts:
            adjustments.extend(
                [f"Conflict: {c.get('type', 'unknown')}" for c in conflicts]
            )
        if warnings:
            adjustments.extend(
                [f"Warning: {w.get('type', 'unknown')}" for w in warnings]
            )

        conflict_count = len(conflicts)
        warning_count = len(warnings)

        compatibility_score = 100
        compatibility_score -= conflict_count * 25
        compatibility_score -= min(warning_count * 10, 40)
        compatibility_score -= max(0, total_diets - 3) * 5
        compatibility_score = max(0, min(100, compatibility_score))

        if compatibility_score >= 85:
            compatibility_level = "excellent"
        elif compatibility_score >= 70:
            compatibility_level = "good"
        elif compatibility_score >= 55:
            compatibility_level = "acceptable"
        elif compatibility_score >= 40:
            compatibility_level = "concerning"
        else:
            compatibility_level = "poor"

        vet_recommended = bool(
            self.diet_validation.get("recommended_vet_consultation", False)
            or conflict_count > 0
        )

        if conflict_count > 0:
            consultation_urgency = "high"
        elif warning_count >= 2 or total_diets >= 5:
            consultation_urgency = "medium"
        elif warning_count > 0 or total_diets >= 4:
            consultation_urgency = "low"
        else:
            consultation_urgency = "none"

        has_adjustments = bool(adjustments) or abs(validation_adjustment - 1.0) > 0.005

        return {
            "has_adjustments": has_adjustments,
            "adjustment_info": "; ".join(adjustments)
            if adjustments
            else "No adjustments",
            "conflict_count": conflict_count,
            "warning_count": warning_count,
            "vet_consultation_recommended": vet_recommended,
            "vet_consultation_state": "recommended"
            if vet_recommended
            else "not_needed",
            "consultation_urgency": consultation_urgency,
            "total_diets": total_diets,
            "diet_validation_adjustment": round(validation_adjustment, 3),
            "percentage_adjustment": percentage_adjustment,
            "adjustment_direction": adjustment_direction,
            "safety_factor": safety_factor,
            "compatibility_score": compatibility_score,
            "compatibility_level": compatibility_level,
            "conflicts": conflicts,
            "warnings": warnings,
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
        self, override_data: dict[str, Any] | None = None
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
            try:
                life_stage = HealthCalculator.calculate_life_stage(
                    age_months, self.breed_size
                )
            except ValueError:
                _LOGGER.warning(
                    "Received invalid age_months=%s for %s; skipping life stage determination",
                    age_months,
                    self.dog_id,
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

    _MAX_SINGLE_FEEDING_GRAMS = 5000.0

    def __init__(self, max_history: int = 100) -> None:
        """Initialize with configurable history limit.

        Args:
            max_history: Maximum feeding events to keep per dog
        """
        self._feedings: dict[str, list[FeedingEvent]] = {}
        self._configs: dict[str, FeedingConfig] = {}
        # Historic FeedingManager implementations exposed ``_dogs`` as a cache
        # of per-dog metadata.  Several diagnostics and tests rely on that
        # attribute, so we continue to populate it even though the refactored
        # manager primarily works with FeedingConfig instances.
        self._dogs: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._max_history = max_history

        # OPTIMIZATION: Event-based reminder system
        self._reminder_events: dict[str, asyncio.Event] = {}
        self._reminder_tasks: dict[str, asyncio.Task] = {}
        self._next_reminders: dict[str, datetime] = {}

        # Track emergency feeding modes for health-aware entities
        self._active_emergencies: dict[str, dict[str, Any]] = {}
        self._emergency_restore_tasks: dict[str, asyncio.Task] = {}

        # Track scheduled reversion tasks so we can cancel or clean them up
        self._activity_reversion_tasks: dict[str, asyncio.Task] = {}
        self._portion_reversion_tasks: dict[str, asyncio.Task] = {}

        # Async dependency audit instrumentation
        self._profile_threshold = 0.05

        # OPTIMIZATION: Feeding data cache
        self._data_cache: dict[str, dict] = {}
        self._cache_time: dict[str, datetime] = {}
        self._cache_ttl = timedelta(seconds=10)

        # OPTIMIZATION: Statistics cache
        self._stats_cache: dict[str, dict] = {}
        self._stats_cache_time: dict[str, datetime] = {}
        self._stats_cache_ttl = timedelta(minutes=5)

    async def _offload_blocking(
        self,
        description: str,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Run *func* in a worker thread and emit async profiling logs."""

        start = perf_counter()
        result = await asyncio.to_thread(func, *args, **kwargs)
        duration = perf_counter() - start
        if duration >= self._profile_threshold:
            _LOGGER.debug(
                "Async dependency audit: %s completed in %.3fs off the event loop",
                description,
                duration,
            )
        return result

    def _apply_emergency_restoration(
        self,
        config: FeedingConfig,
        original_config: dict[str, Any],
        dog_id: str,
    ) -> None:
        """Restore baseline feeding parameters after emergency mode."""

        config.daily_food_amount = original_config["daily_food_amount"]
        config.meals_per_day = original_config["meals_per_day"]
        config.schedule_type = original_config["schedule_type"]
        config.food_type = original_config["food_type"]

        self._invalidate_cache(dog_id)

    async def async_initialize(self, dogs: list[dict[str, Any]]) -> None:
        """Initialize feeding configurations for dogs.

        Args:
            dogs: List of dog configurations
        """
        async with self._lock:
            # Reset caches so repeated initialisation (common in tests) does not
            # leak previous dog metadata or reminder tasks.
            for task in self._reminder_tasks.values():
                task.cancel()
            self._reminder_tasks.clear()
            self._reminder_events.clear()
            self._next_reminders.clear()
            self._feedings.clear()
            self._configs.clear()
            self._dogs.clear()
            self._data_cache.clear()
            self._cache_time.clear()
            self._stats_cache.clear()
            self._stats_cache_time.clear()

            batch_configs: dict[str, FeedingConfig] = {}
            batch_dogs: dict[str, dict[str, Any]] = {}

            for dog in dogs:
                dog_id = dog.get("dog_id")
                if not dog_id:
                    continue

                weight = dog.get("weight")
                if weight is None or float(weight) <= 0:
                    raise ValueError(
                        f"Invalid feeding configuration for {dog_id}: weight is required"
                    )

                feeding_config = dog.get("feeding_config", {})
                config = await self._create_feeding_config(dog_id, feeding_config)

                config.dog_weight = float(weight)
                if (ideal_weight := dog.get("ideal_weight")) is not None:
                    try:
                        config.ideal_weight = float(ideal_weight)
                    except (TypeError, ValueError):  # pragma: no cover - defensive
                        _LOGGER.debug(
                            "Invalid ideal weight %s for %s; keeping existing value",
                            ideal_weight,
                            dog_id,
                        )
                if (age_months := dog.get("age_months")) is not None:
                    config.age_months = int(age_months)
                if activity := dog.get("activity_level"):
                    config.activity_level = activity
                if (health_conditions := dog.get("health_conditions")) is not None:
                    config.health_conditions = list(health_conditions)
                if (weight_goal := dog.get("weight_goal")) is not None:
                    config.weight_goal = weight_goal
                if (special_diet := dog.get("special_diet")) is not None:
                    config.special_diet = self._normalize_special_diet(special_diet)

                self._feedings[dog_id] = []
                batch_configs[dog_id] = config

                batch_dogs[dog_id] = {
                    "dog_id": dog_id,
                    "dog_name": dog.get("dog_name"),
                    "weight": float(weight),
                    "ideal_weight": config.ideal_weight,
                    "activity_level": config.activity_level or "moderate",
                    "age_months": config.age_months,
                    "breed": dog.get("breed"),
                    "breed_size": config.breed_size,
                    "weight_goal": config.weight_goal,
                    "health_conditions": list(config.health_conditions),
                    "feeding_config": feeding_config,
                    "meals_per_day": config.meals_per_day,
                    "diabetic_mode": False,
                }

            # OPTIMIZATION: Batch update configs
            self._configs.update(batch_configs)
            self._dogs.update(batch_dogs)

            # Setup reminders for all dogs with schedules
            for dog_id, config in batch_configs.items():
                if config.schedule_type != FeedingScheduleType.FLEXIBLE:
                    await self._setup_reminder(dog_id)

    async def _create_feeding_config(
        self, dog_id: str, config_data: dict[str, Any]
    ) -> FeedingConfig:
        """Create enhanced feeding configuration with health integration."""
        special_diet = self._normalize_special_diet(config_data.get("special_diet", []))

        config = FeedingConfig(
            dog_id=dog_id,
            meals_per_day=config_data.get("meals_per_day", 2),
            daily_food_amount=config_data.get("daily_food_amount", 500.0),
            food_type=config_data.get("food_type", "dry_food"),
            special_diet=special_diet,
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
            if meal_time_str := config_data.get(meal_name):  # noqa: SIM102
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
                meal_schedules.append(  # noqa: PERF401
                    MealSchedule(
                        meal_type=MealType.SNACK,
                        scheduled_time=parsed_time,
                        portion_size=50.0,
                        reminder_enabled=False,
                    )
                )

        config.meal_schedules = meal_schedules
        return config

    def _parse_time(self, time_str: str | time) -> time | None:
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

    def _normalize_special_diet(self, raw_value: Any) -> list[str]:
        """Normalize special diet configuration values into a list of strings."""

        if raw_value is None:
            return []

        if isinstance(raw_value, str):
            stripped_value = raw_value.strip()
            return [stripped_value] if stripped_value else []

        if isinstance(raw_value, Iterable) and not isinstance(raw_value, bytes | str):
            normalized: list[str] = []
            for item in raw_value:
                if not isinstance(item, str):
                    _LOGGER.debug(
                        "Ignoring non-string special diet entry for %s: %s",
                        type(item).__name__,
                        item,
                    )
                    continue

                stripped_item = item.strip()
                if stripped_item:
                    normalized.append(stripped_item)

            return normalized

        _LOGGER.debug("Unsupported special diet format: %s", raw_value)
        return []

    def _require_config(self, dog_id: str) -> FeedingConfig:
        """Return the FeedingConfig for ``dog_id`` or raise KeyError."""

        config = self._configs.get(dog_id)
        if config is None:
            raise KeyError(dog_id)
        return config

    def _require_dog_record(self, dog_id: str) -> dict[str, Any]:
        """Return the cached dog metadata for ``dog_id``."""

        try:
            return self._dogs[dog_id]
        except KeyError as err:  # pragma: no cover - defensive
            raise KeyError(dog_id) from err

    def _calculate_rer(self, weight: float, *, adjusted: bool = True) -> float:
        """Calculate resting energy requirement for ``weight`` in kilograms."""

        if not is_number(weight):
            raise ValueError("Weight must be a number")

        weight_value = float(weight)
        if weight_value <= 0:
            raise ValueError("Weight must be greater than zero")

        effective_weight = (
            weight_value - 7 if adjusted and weight_value > 7 else weight_value
        )
        effective_weight = max(effective_weight, 0.1)

        return 70.0 * (effective_weight**0.75)

    def calculate_daily_calories(self, dog_id: str) -> float:
        """Return the daily calorie recommendation for ``dog_id``."""

        dog = self._require_dog_record(dog_id)
        config = self._require_config(dog_id)

        weight = dog.get("weight") or config.dog_weight
        if weight is None:
            raise ValueError("Dog weight is required for calorie calculation")

        weight_value = float(weight)
        target_weight = config.ideal_weight
        if config.weight_goal in {"lose", "gain"} and target_weight:
            with contextlib.suppress(TypeError, ValueError):
                weight_value = float(target_weight)

        age_months = dog.get("age_months") or config.age_months or 24
        breed_size = dog.get("breed_size") or config.breed_size or "medium"

        with contextlib.suppress(ValueError, TypeError):
            HealthCalculator.calculate_life_stage(int(age_months), breed_size)

        activity_source = (
            config.activity_level
            or dog.get("activity_level")
            or ActivityLevel.MODERATE.value
        )
        try:
            activity_level = ActivityLevel(activity_source)
        except ValueError:
            activity_level = ActivityLevel.MODERATE

        base_weight = weight_value
        adjusted_rer = True
        if config.weight_goal == "lose" and config.ideal_weight:
            try:
                base_weight = float(config.ideal_weight)
                adjusted_rer = False
            except (TypeError, ValueError):  # pragma: no cover - defensive
                base_weight = weight_value
        elif config.weight_goal == "gain" and config.ideal_weight:
            try:
                base_weight = float(config.ideal_weight)
            except (TypeError, ValueError):
                base_weight = weight_value

        rer = self._calculate_rer(base_weight, adjusted=adjusted_rer)

        activity_map = {
            ActivityLevel.VERY_LOW.value: 1.2,
            ActivityLevel.LOW.value: 1.4,
            ActivityLevel.MODERATE.value: 1.6,
            ActivityLevel.HIGH.value: 2.0,
            ActivityLevel.VERY_HIGH.value: 2.4,
        }
        multiplier = activity_map.get(activity_level.value, 1.6)

        return round(rer * multiplier, 1)

    def calculate_portion(self, dog_id: str, meal_type: str | None = None) -> float:
        """Return the suggested portion size for ``dog_id`` and ``meal_type``."""

        config = self._require_config(dog_id)

        daily_grams = float(config.daily_food_amount)
        dog_record = self._dogs.get(dog_id, {})
        meals = dog_record.get("meals_per_day", config.meals_per_day)
        meals = max(1, int(meals))
        portion = daily_grams / meals
        return round(portion, 1)

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
                        except TimeoutError:
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

    async def _calculate_next_reminder(self, config: FeedingConfig) -> datetime | None:
        """Calculate next reminder time for a config.

        Args:
            config: Feeding configuration

        Returns:
            Next reminder datetime or None
        """
        next_reminder = None

        for schedule in config.get_todays_schedules():
            reminder_time = schedule.get_reminder_time()
            if reminder_time and reminder_time > dt_util.now():  # noqa: SIM102
                if next_reminder is None or reminder_time < next_reminder:
                    next_reminder = reminder_time

        # If no reminders today, check tomorrow
        if next_reminder is None:
            tomorrow = dt_util.now() + timedelta(days=1)
            tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0)

            for schedule in config.get_active_schedules():
                reminder_time = schedule.get_reminder_time()
                if reminder_time and reminder_time >= tomorrow_start:  # noqa: SIM102
                    if next_reminder is None or reminder_time < next_reminder:
                        next_reminder = reminder_time

        return next_reminder

    async def _get_reminder_schedule(
        self, config: FeedingConfig, reminder_time: datetime
    ) -> MealSchedule | None:
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
        meal_type: str | None = None,
        time: datetime | None = None,
        *,
        timestamp: datetime | None = None,
        notes: str | None = None,
        feeder: str | None = None,
        scheduled: bool = False,
        with_medication: bool = False,
        medication_name: str | None = None,
        medication_dose: str | None = None,
        medication_time: str | None = None,
    ) -> FeedingEvent:
        """Record a feeding event.

        Args:
            dog_id: Identifier of the dog
            amount: Amount of food in grams
            meal_type: Type of meal
            time: Optional timestamp
            timestamp: Legacy alias for ``time`` used by historic helpers
            notes: Optional notes
            feeder: Who fed the dog
            scheduled: Whether scheduled feeding

        Returns:
            Created FeedingEvent
        """
        if not is_number(amount):
            raise ValueError("Feeding amount must be a numeric value in grams")

        amount_value = float(amount)
        if not (0 < amount_value <= self._MAX_SINGLE_FEEDING_GRAMS):
            raise ValueError(
                "Feeding amount must be between 0 and "
                f"{self._MAX_SINGLE_FEEDING_GRAMS} grams"
            )

        if timestamp is not None:
            time = timestamp

        async with self._lock:
            if dog_id not in self._configs:
                raise KeyError(dog_id)

            event_time = time or dt_util.now()
            if event_time.tzinfo is None:
                event_time = dt_util.as_local(dt_util.as_utc(event_time))
            else:
                event_time = dt_util.as_local(event_time)

            meal_type_enum = None
            is_medication_meal = False
            if meal_type:
                normalized_meal = meal_type.lower()
                try:
                    meal_type_enum = MealType(normalized_meal)
                except ValueError:
                    if normalized_meal == "medication":
                        is_medication_meal = True
                    else:
                        _LOGGER.warning("Invalid meal type: %s", meal_type)

            if is_medication_meal and not with_medication:
                with_medication = True

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
                time=event_time,
                amount=amount_value,
                meal_type=meal_type_enum,
                portion_size=portion_size,
                food_type=config.food_type if config else None,
                notes=notes,
                feeder=feeder,
                scheduled=scheduled,
                with_medication=with_medication,
                medication_name=medication_name,
                medication_dose=medication_dose,
                medication_time=medication_time,
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
        medication_data: dict[str, Any] | None = None,
        time: datetime | None = None,
        notes: str | None = None,
        feeder: str | None = None,
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
                dog_id=dog_id,
                amount=amount,
                meal_type=meal_type,
                time=time,
                notes=notes,
                feeder=feeder,
                scheduled=True,
                with_medication=True,
                medication_name=medication_data.get("name")
                if medication_data
                else None,
                medication_dose=medication_data.get("dose")
                if medication_data
                else None,
                medication_time=medication_data.get("time")
                if medication_data
                else None,
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
            with_medication=True,
            medication_name=medication_data.get("name") if medication_data else None,
            medication_dose=medication_data.get("dose") if medication_data else None,
            medication_time=medication_data.get("time") if medication_data else None,
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
        self, dog_id: str, since: datetime | None = None
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
            if dog_id not in self._configs and dog_id not in self._feedings:
                return {}

            # Check cache
            if dog_id in self._data_cache:
                cache_time = self._cache_time.get(dog_id)
                if cache_time and (dt_util.now() - cache_time) < self._cache_ttl:
                    return self._data_cache[dog_id]

            # Calculate feeding data
            data = self._build_feeding_snapshot(dog_id)

            # Cache result
            self._data_cache[dog_id] = data
            self._cache_time[dog_id] = dt_util.now()

            return data

    def get_feeding_data(self, dog_id: str) -> dict[str, Any]:
        """Synchronously return the feeding snapshot for ``dog_id``.

        Legacy tests and diagnostics relied on a synchronous accessor.  The
        helper reuses the async cache but falls back to building the snapshot
        inline when the cached value has expired.
        """

        if dog_id not in self._configs and dog_id not in self._feedings:
            return {}

        cache_time = self._cache_time.get(dog_id)
        if cache_time and (dt_util.now() - cache_time) < self._cache_ttl:
            cached = self._data_cache.get(dog_id)
            if cached is not None:
                return cached

        data = self._build_feeding_snapshot(dog_id)
        self._data_cache[dog_id] = data
        self._cache_time[dog_id] = dt_util.now()
        return data

    def get_daily_stats(self, dog_id: str) -> dict[str, Any]:
        """Return today's feeding statistics for the given dog."""

        data = self.get_feeding_data(dog_id)
        stats = data.get("daily_stats", {})
        return dict(stats)

    def get_feeding_config(self, dog_id: str) -> FeedingConfig | None:
        """Return feeding configuration for a dog if available."""

        return self._configs.get(dog_id)

    def get_active_emergency(self, dog_id: str) -> dict[str, Any] | None:
        """Return active or most recent emergency feeding state for a dog."""

        emergency = self._active_emergencies.get(dog_id)
        if not emergency:
            return None

        return dict(emergency)

    def _build_feeding_snapshot(self, dog_id: str) -> dict[str, Any]:
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
        feedings_today: dict[str, int] = {}
        daily_amount = 0.0
        last_feeding: FeedingEvent | None = None
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
        missed_feedings: list[dict[str, Any]] = []

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

        data: dict[str, Any] = {
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
                int(daily_amount / config.daily_food_amount * 100)
                if config and config.daily_food_amount > 0
                else 0
            ),
            "schedule_adherence": adherence,
            "next_feeding": next_feeding.isoformat() if next_feeding else None,
            "next_feeding_type": next_type,
            "missed_feedings": missed_feedings,
            "status": "ready" if feedings else "no_data",
        }

        data["daily_target"] = data["daily_amount_target"]

        if config:
            data["config"] = {
                "meals_per_day": config.meals_per_day,
                "food_type": config.food_type,
                "schedule_type": config.schedule_type.value,
            }

        health_summary: dict[str, Any] = {}
        calories_per_gram: float | None = None
        if config:
            health_summary = config.get_health_summary()
            calories_per_gram = health_summary.get("calories_per_gram")
            if calories_per_gram is None:
                calories_per_gram = config._estimate_calories_per_gram()

        if calories_per_gram is not None:
            data["calories_per_gram"] = round(float(calories_per_gram), 2)

        daily_calorie_target: float | None = None
        if health_summary:
            daily_calorie_target = health_summary.get("daily_calorie_requirement")

        if daily_calorie_target is None and config and calories_per_gram is not None:
            daily_calorie_target = round(
                float(config.daily_food_amount) * float(calories_per_gram), 1
            )

        if daily_calorie_target is not None:
            data["daily_calorie_target"] = daily_calorie_target

        total_calories_today: float | None = None
        if calories_per_gram is not None and daily_amount:
            total_calories_today = round(daily_amount * float(calories_per_gram), 1)
            data["total_calories_today"] = total_calories_today

        if total_calories_today is not None and daily_calorie_target:
            try:
                progress = (total_calories_today / daily_calorie_target) * 100
                data["calorie_goal_progress"] = round(min(progress, 150.0), 1)
            except (TypeError, ZeroDivisionError):
                data["calorie_goal_progress"] = 0.0

        portion_adjustment: float | None = None
        if config:
            try:
                health_metrics = config._build_health_metrics()
                feeding_goals = {"weight_goal": config.weight_goal}
                portion_adjustment = (
                    HealthCalculator.calculate_portion_adjustment_factor(
                        health_metrics,
                        feeding_goals if config.weight_goal else None,
                        config.diet_validation,
                    )
                )
            except Exception as err:
                _LOGGER.debug(
                    "Failed to calculate portion adjustment factor for %s: %s",
                    dog_id,
                    err,
                )

        if portion_adjustment is not None:
            data["portion_adjustment_factor"] = portion_adjustment

        if config and config.diet_validation:
            data["diet_validation_summary"] = config._get_diet_validation_summary()
        else:
            data["diet_validation_summary"] = None

        health_conditions: list[str] = []
        if health_summary:
            health_conditions = list(health_summary.get("health_conditions", []))

        if config and config.health_conditions:
            # Ensure unique conditions preserving order
            seen: set[str] = set(health_conditions)
            for condition in config.health_conditions:
                if condition not in seen:
                    health_conditions.append(condition)
                    seen.add(condition)

        if health_conditions:
            data["health_conditions"] = health_conditions

        if health_summary and health_summary.get("activity_level"):
            data["daily_activity_level"] = health_summary.get("activity_level")

        if portion_adjustment is not None or data.get("daily_activity_level"):
            data["health_summary"] = health_summary

        data["medication_with_meals"] = bool(
            config.medication_with_meals if config else False
        )
        data["health_aware_feeding"] = bool(
            config.health_aware_portions if config else False
        )
        data["weight_goal"] = config.weight_goal if config else None

        weight_goal_progress: float | None = None
        if config and health_summary:
            current_weight = health_summary.get("current_weight")
            ideal_weight = health_summary.get("ideal_weight")
            if is_number(current_weight) and is_number(ideal_weight):
                current = float(current_weight)
                ideal = float(ideal_weight)
                try:
                    if config.weight_goal == "lose":
                        ratio = ideal / current if current else 0
                        weight_goal_progress = max(0.0, min(ratio * 100, 100.0))
                    elif config.weight_goal == "gain":
                        ratio = current / ideal if ideal else 0
                        weight_goal_progress = max(0.0, min(ratio * 100, 100.0))
                    else:
                        diff = abs(current - ideal)
                        weight_goal_progress = max(
                            0.0,
                            min(100.0, 100.0 - (diff / max(ideal, 1.0)) * 100.0),
                        )
                except (TypeError, ZeroDivisionError):
                    weight_goal_progress = None

        if weight_goal_progress is not None:
            data["weight_goal_progress"] = round(weight_goal_progress, 1)

        emergency_state = self._active_emergencies.get(dog_id)
        if emergency_state:
            emergency_copy = dict(emergency_state)
            expires_at = emergency_copy.get("expires_at")
            if expires_at:
                expires_dt = dt_util.parse_datetime(expires_at)
                if expires_dt and expires_dt < dt_util.utcnow():
                    emergency_copy["active"] = False
                    emergency_copy["status"] = emergency_copy.get("status", "resolved")
            data["emergency_mode"] = emergency_copy
            data["health_emergency"] = bool(emergency_copy.get("active", True))
        else:
            data["emergency_mode"] = None
            data["health_emergency"] = False

        data["feedings"] = [event.to_dict() for event in feedings]

        meals_today = sum(feedings_today.values())
        remaining_calories: float | None = None
        if daily_calorie_target is not None and total_calories_today is not None:
            remaining_calories = max(0.0, daily_calorie_target - total_calories_today)
        elif calories_per_gram is not None:
            try:
                target_calories = float(data["daily_amount_target"]) * float(
                    calories_per_gram
                )
                consumed_calories = daily_amount * float(calories_per_gram)
                remaining_calories = max(0.0, target_calories - consumed_calories)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                remaining_calories = None

        data["daily_stats"] = {
            "total_fed_today": round(daily_amount, 1),
            "meals_today": meals_today,
            "remaining_calories": round(remaining_calories, 1)
            if remaining_calories is not None
            else None,
        }

        # Derive overall health feeding status
        status = "insufficient_data"
        if data.get("health_emergency"):
            status = "emergency"
        elif total_calories_today is not None and daily_calorie_target:
            try:
                ratio = total_calories_today / daily_calorie_target
                if ratio < 0.85:
                    status = "underfed"
                elif ratio > 1.15:
                    status = "overfed"
                else:
                    status = "on_track"
            except (TypeError, ZeroDivisionError):
                status = "unknown"
        elif portion_adjustment is not None:
            status = "monitoring"

        data["health_feeding_status"] = status

        return data

    def _empty_feeding_data(self, config: FeedingConfig | None) -> dict[str, Any]:
        """Generate empty feeding data structure.

        Args:
            config: Optional feeding configuration

        Returns:
            Empty data dictionary
        """
        calories_per_gram = config._estimate_calories_per_gram() if config else None

        data: dict[str, Any] = {
            "last_feeding": None,
            "feedings_today": {},
            "total_feedings_today": 0,
            "daily_amount_consumed": 0.0,
            "daily_amount_target": config.daily_food_amount if config else 500,
            "schedule_adherence": 100,
            "next_feeding": None,
            "missed_feedings": [],
            "status": "no_data",
            "health_feeding_status": "insufficient_data",
            "medication_with_meals": bool(
                config.medication_with_meals if config else False
            ),
            "health_aware_feeding": bool(
                config.health_aware_portions if config else False
            ),
            "weight_goal": config.weight_goal if config else None,
            "weight_goal_progress": None,
            "health_conditions": list(config.health_conditions)
            if config and config.health_conditions
            else [],
            "daily_activity_level": None,
            "health_emergency": False,
            "emergency_mode": None,
            "diet_validation_summary": None,
        }

        data["daily_target"] = data["daily_amount_target"]

        if calories_per_gram is not None:
            data["calories_per_gram"] = round(float(calories_per_gram), 2)
            data["daily_calorie_target"] = round(
                float(data["daily_amount_target"]) * float(calories_per_gram), 1
            )
            data["total_calories_today"] = 0.0

        data["feedings"] = []

        remaining_calories: float | None = None
        if calories_per_gram is not None:
            try:
                target_calories = float(data["daily_amount_target"]) * float(
                    calories_per_gram
                )
                remaining_calories = max(0.0, target_calories)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                remaining_calories = None

        data["daily_stats"] = {
            "total_fed_today": 0.0,
            "meals_today": 0,
            "remaining_calories": round(remaining_calories, 1)
            if remaining_calories is not None
            else None,
        }

        return data

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

            dog_record = self._dogs.get(dog_id)
            if dog_record is not None:
                if (weight := dog_record.get("weight")) is not None:
                    with contextlib.suppress(TypeError, ValueError):
                        config.dog_weight = float(weight)
                if (ideal_weight := dog_record.get("ideal_weight")) is not None:
                    with contextlib.suppress(TypeError, ValueError):
                        config.ideal_weight = float(ideal_weight)

                dog_record.update(
                    {
                        "activity_level": config.activity_level
                        or dog_record.get("activity_level"),
                        "breed_size": config.breed_size,
                        "weight_goal": config.weight_goal,
                        "health_conditions": list(config.health_conditions),
                        "meals_per_day": config.meals_per_day,
                    }
                )

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
        daily_counts: dict[date, int] = {}
        daily_amounts: dict[date, float] = {}
        meal_counts: dict[str, int] = {}

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
            max(meal_counts.items(), key=lambda item: item[1])[0]
            if meal_counts
            else None
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
                int(avg_daily_amount / config.daily_food_amount * 100)
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
        self, dog_id: str, meal_type: str, health_data: dict[str, Any] | None = None
    ) -> float | None:
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

    async def async_generate_health_report(self, dog_id: str) -> dict[str, Any] | None:
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

        if health_metrics.life_stage in [LifeStage.SENIOR, LifeStage.GERIATRIC]:  # noqa: SIM102
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
    ) -> dict[str, Any] | None:
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
        override_health_data: dict[str, Any] | None = None,
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
                elif (
                    health_metrics.life_stage in (LifeStage.SENIOR, LifeStage.GERIATRIC)
                    and config.dog_weight
                    and config.dog_weight <= 10
                ):
                    portion = max(portion, 7 * config.dog_weight)

                # Validate portion safety with diet considerations
                safety_result: DietSafetyResult
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
                        "portion_per_kg": 0.0,
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

    async def async_recalculate_health_portions(
        self,
        dog_id: str,
        force_recalculation: bool = False,
        update_feeding_schedule: bool = True,
    ) -> dict[str, Any]:
        """Recalculate health-aware portions and optionally update feeding schedule.

        Args:
            dog_id: Dog identifier
            force_recalculation: Force recalculation even if recent
            update_feeding_schedule: Whether to update meal schedules with new portions

        Returns:
            Dictionary with recalculation results
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config:
                raise ValueError(f"No feeding configuration found for dog {dog_id}")

            if not config.health_aware_portions:
                return {
                    "status": "disabled",
                    "message": "Health-aware portions are disabled for this dog",
                }

            # Build current health metrics
            health_metrics = await self._offload_blocking(
                f"build health metrics for {dog_id}",
                config._build_health_metrics,
            )

            if not health_metrics.current_weight:
                return {
                    "status": "insufficient_data",
                    "message": "Weight data required for health-aware portion calculation",
                }

            # Calculate new portions for all meal types
            new_portions = {}
            total_daily_calculated = 0.0

            for meal_type in [
                MealType.BREAKFAST,
                MealType.LUNCH,
                MealType.DINNER,
                MealType.SNACK,
            ]:
                portion = config.calculate_portion_size(meal_type)
                new_portions[meal_type.value] = portion

                if meal_type != MealType.SNACK:  # Don't count snacks in daily total
                    total_daily_calculated += portion

            # Update meal schedules if requested
            updated_schedules = 0
            if update_feeding_schedule and config.meal_schedules:
                for schedule in config.meal_schedules:
                    if schedule.meal_type in new_portions:
                        old_portion = schedule.portion_size
                        schedule.portion_size = new_portions[schedule.meal_type.value]
                        if (
                            abs(old_portion - schedule.portion_size) > 1.0
                        ):  # Significant change
                            updated_schedules += 1

            # Invalidate caches
            self._invalidate_cache(dog_id)

            result = {
                "status": "success",
                "dog_id": dog_id,
                "new_portions": new_portions,
                "total_daily_amount": round(total_daily_calculated, 1),
                "previous_daily_target": config.daily_food_amount,
                "updated_schedules": updated_schedules,
                "health_metrics_used": {
                    "weight": health_metrics.current_weight,
                    "life_stage": health_metrics.life_stage.value
                    if health_metrics.life_stage
                    else None,
                    "activity_level": health_metrics.activity_level.value
                    if health_metrics.activity_level
                    else None,
                    "body_condition_score": health_metrics.body_condition_score.value
                    if health_metrics.body_condition_score
                    else None,
                },
                "recalculated_at": dt_util.now().isoformat(),
            }

            _LOGGER.info(
                "Recalculated health portions for %s: %s",
                dog_id,
                {k: v for k, v in new_portions.items() if k != "snack"},
            )

            return result

    async def async_adjust_calories_for_activity(
        self,
        dog_id: str,
        activity_level: str,
        duration_hours: int | None = None,
        temporary: bool = True,
    ) -> dict[str, Any]:
        """Adjust daily calorie target based on activity level change.

        Args:
            dog_id: Dog identifier
            activity_level: New activity level
            duration_hours: How long to maintain this adjustment (None = permanent)
            temporary: Whether this is a temporary adjustment

        Returns:
            Dictionary with adjustment results
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config:
                raise ValueError(f"No feeding configuration found for dog {dog_id}")

            try:
                from .health_calculator import ActivityLevel

                activity_enum = ActivityLevel(activity_level)
            except (ImportError, ValueError) as err:
                raise ValueError(f"Invalid activity level '{activity_level}'") from err

            # Store original activity level if temporary
            original_activity = config.activity_level

            # Update activity level
            config.activity_level = activity_level

            # Recalculate portions with new activity level
            health_metrics = await self._offload_blocking(
                f"build health metrics for {dog_id}",
                config._build_health_metrics,
            )

            if not health_metrics.current_weight:
                return {
                    "status": "insufficient_data",
                    "message": "Weight data required for calorie adjustment",
                }

            # Calculate new daily calorie requirement
            try:
                from .health_calculator import HealthCalculator, LifeStage

                new_daily_calories = await self._offload_blocking(
                    f"calculate calories for {dog_id}",
                    HealthCalculator.calculate_daily_calories,
                    weight=health_metrics.current_weight,
                    life_stage=health_metrics.life_stage or LifeStage.ADULT,
                    activity_level=activity_enum,
                    body_condition_score=health_metrics.body_condition_score,
                    health_conditions=health_metrics.health_conditions,
                    spayed_neutered=config.spayed_neutered,
                )
            except ImportError as err:
                raise ValueError("Health calculator not available") from err

            # Convert calories to food amount
            calories_per_gram = await self._offload_blocking(
                f"estimate calories per gram for {dog_id}",
                config._estimate_calories_per_gram,
            )
            new_daily_amount = new_daily_calories / calories_per_gram

            # Update daily food amount
            old_daily_amount = config.daily_food_amount
            config.daily_food_amount = round(new_daily_amount, 1)

            # Invalidate caches
            self._invalidate_cache(dog_id)

            result = {
                "status": "success",
                "dog_id": dog_id,
                "old_activity_level": original_activity,
                "new_activity_level": activity_level,
                "old_daily_calories": round(old_daily_amount * calories_per_gram, 0),
                "new_daily_calories": round(new_daily_calories, 0),
                "old_daily_amount_g": old_daily_amount,
                "new_daily_amount_g": config.daily_food_amount,
                "adjustment_percent": round(
                    ((config.daily_food_amount - old_daily_amount) / old_daily_amount)
                    * 100,
                    1,
                ),
                "temporary": temporary,
                "duration_hours": duration_hours,
                "adjusted_at": dt_util.now().isoformat(),
            }

            _LOGGER.info(
                "Adjusted calories for %s: %s activity level, %.0fg daily (was %.0fg)",
                dog_id,
                activity_level,
                config.daily_food_amount,
                old_daily_amount,
            )

            # Schedule reversion if temporary
            if temporary and duration_hours and original_activity:
                if existing_task := self._activity_reversion_tasks.pop(dog_id, None):
                    existing_task.cancel()

                async def _revert_activity() -> None:
                    try:
                        await asyncio.sleep(duration_hours * 3600)
                        try:
                            await self.async_adjust_calories_for_activity(
                                dog_id, original_activity, None, False
                            )
                            _LOGGER.info(
                                "Reverted activity level for %s back to %s",
                                dog_id,
                                original_activity,
                            )
                        except Exception as err:  # pragma: no cover - logging only
                            _LOGGER.error(
                                "Failed to revert activity level for %s: %s",
                                dog_id,
                                err,
                            )
                    finally:
                        self._activity_reversion_tasks.pop(dog_id, None)

                revert_task = asyncio.create_task(_revert_activity())
                self._activity_reversion_tasks[dog_id] = revert_task
                result["reversion_scheduled"] = True

            return result

    async def async_activate_diabetic_feeding_mode(
        self,
        dog_id: str,
        meal_frequency: int = 4,
        carb_limit_percent: int = 20,
        monitor_blood_glucose: bool = True,
    ) -> dict[str, Any]:
        """Activate specialized feeding mode for diabetic dogs.

        Args:
            dog_id: Dog identifier
            meal_frequency: Number of meals per day (3-6)
            carb_limit_percent: Maximum carbohydrate percentage (5-30)
            monitor_blood_glucose: Whether to enable glucose monitoring reminders

        Returns:
            Dictionary with activation results
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config:
                raise ValueError(f"No feeding configuration found for dog {dog_id}")

            # Validate parameters
            if not 3 <= meal_frequency <= 6:
                raise ValueError("Meal frequency must be between 3 and 6")
            if not 5 <= carb_limit_percent <= 30:
                raise ValueError("Carb limit must be between 5% and 30%")

            # Add diabetes to health conditions if not present
            if "diabetes" not in config.health_conditions:
                config.health_conditions.append("diabetes")

            # Update special diet requirements
            if "diabetic" not in config.special_diet:
                config.special_diet.append("diabetic")
            if "low_carb" not in config.special_diet:
                config.special_diet.append("low_carb")

            # Update feeding configuration
            old_meals_per_day = config.meals_per_day
            config.meals_per_day = meal_frequency

            # Create diabetic feeding schedule
            diabetic_schedules = self._create_diabetic_meal_schedule(
                meal_frequency, config.daily_food_amount
            )

            # Replace existing schedules with diabetic schedule
            config.meal_schedules = diabetic_schedules

            # Enable strict scheduling for diabetes management
            config.schedule_type = FeedingScheduleType.STRICT

            # Invalidate caches
            self._invalidate_cache(dog_id)

            # Setup reminders if needed
            await self._setup_reminder(dog_id)

            result = {
                "status": "activated",
                "dog_id": dog_id,
                "old_meals_per_day": old_meals_per_day,
                "new_meals_per_day": meal_frequency,
                "carb_limit_percent": carb_limit_percent,
                "monitor_blood_glucose": monitor_blood_glucose,
                "schedule_type": "strict",
                "meal_times": [
                    schedule.scheduled_time.strftime("%H:%M")
                    for schedule in diabetic_schedules
                ],
                "portion_sizes": [
                    round(schedule.portion_size, 1) for schedule in diabetic_schedules
                ],
                "special_diet_updated": config.special_diet,
                "activated_at": dt_util.now().isoformat(),
            }

            _LOGGER.info(
                "Activated diabetic feeding mode for %s: %d meals/day, %d%% carb limit",
                dog_id,
                meal_frequency,
                carb_limit_percent,
            )

            if dog_id in self._dogs:
                self._dogs[dog_id]["diabetic_mode"] = True
                self._dogs[dog_id]["carb_limit_percent"] = carb_limit_percent
                self._dogs[dog_id]["meals_per_day"] = meal_frequency

            return result

    def _create_diabetic_meal_schedule(
        self, meal_frequency: int, daily_amount: float
    ) -> list[MealSchedule]:
        """Create optimized meal schedule for diabetic dogs.

        Args:
            meal_frequency: Number of meals per day
            daily_amount: Total daily food amount

        Returns:
            List of meal schedules optimized for diabetes management
        """
        # Diabetic dogs need evenly spaced meals
        meal_times = {
            3: [time(8, 0), time(14, 0), time(20, 0)],
            4: [time(7, 0), time(12, 0), time(17, 0), time(21, 0)],
            5: [time(7, 0), time(11, 0), time(15, 0), time(19, 0), time(22, 0)],
            6: [
                time(7, 0),
                time(10, 30),
                time(14, 0),
                time(17, 30),
                time(21, 0),
                time(23, 0),
            ],
        }

        times = meal_times.get(meal_frequency, meal_times[4])
        portion_size = daily_amount / meal_frequency

        schedules = []
        for i, meal_time in enumerate(times):
            meal_type = (
                MealType.BREAKFAST
                if i == 0
                else (MealType.DINNER if i == len(times) - 1 else MealType.LUNCH)
            )

            schedules.append(
                MealSchedule(
                    meal_type=meal_type,
                    scheduled_time=meal_time,
                    portion_size=round(portion_size, 1),
                    enabled=True,
                    reminder_enabled=True,
                    reminder_minutes_before=15,
                    auto_log=False,  # Manual logging for diabetes monitoring
                )
            )

        return schedules

    async def async_activate_emergency_feeding_mode(
        self,
        dog_id: str,
        emergency_type: str,
        duration_days: int = 3,
        portion_adjustment: float = 0.8,
    ) -> dict[str, Any]:
        """Activate emergency feeding mode for sick or recovering dogs.

        Args:
            dog_id: Dog identifier
            emergency_type: Type of emergency (illness, surgery_recovery, etc.)
            duration_days: How many days to maintain emergency mode
            portion_adjustment: Portion multiplier (0.5-1.2)

        Returns:
            Dictionary with activation results
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config:
                raise ValueError(f"No feeding configuration found for dog {dog_id}")

            # Validate parameters
            if not 0.5 <= portion_adjustment <= 1.2:
                raise ValueError("Portion adjustment must be between 0.5 and 1.2")

            valid_emergency_types = [
                "illness",
                "surgery_recovery",
                "digestive_upset",
                "medication_reaction",
            ]
            if emergency_type not in valid_emergency_types:
                raise ValueError(
                    f"Emergency type must be one of: {valid_emergency_types}"
                )

            # Cancel any existing restoration for this dog
            if dog_id in self._emergency_restore_tasks:
                self._emergency_restore_tasks[dog_id].cancel()
                self._emergency_restore_tasks.pop(dog_id, None)

            # Store original configuration for restoration
            original_config = {
                "daily_food_amount": config.daily_food_amount,
                "meals_per_day": config.meals_per_day,
                "schedule_type": config.schedule_type,
                "food_type": config.food_type,
            }

            # Adjust daily amount
            old_daily_amount = config.daily_food_amount
            config.daily_food_amount = round(old_daily_amount * portion_adjustment, 1)

            # Increase meal frequency for better digestion during recovery
            if emergency_type in ["illness", "digestive_upset", "medication_reaction"]:
                config.meals_per_day = min(config.meals_per_day + 1, 4)
                # Recommend wet food for easier digestion
                if emergency_type == "digestive_upset":
                    config.food_type = "wet_food"

            # Create gentle feeding schedule
            if emergency_type == "surgery_recovery":
                # Smaller, more frequent meals for post-surgery
                config.meals_per_day = min(config.meals_per_day + 2, 5)

            # Invalidate caches
            self._invalidate_cache(dog_id)

            result = {
                "status": "activated",
                "dog_id": dog_id,
                "emergency_type": emergency_type,
                "duration_days": duration_days,
                "portion_adjustment": portion_adjustment,
                "old_daily_amount": old_daily_amount,
                "new_daily_amount": config.daily_food_amount,
                "old_meals_per_day": original_config["meals_per_day"],
                "new_meals_per_day": config.meals_per_day,
                "food_type_recommendation": config.food_type,
                "original_config": original_config,
                "expires_at": (
                    dt_util.now() + timedelta(days=duration_days)
                ).isoformat(),
                "activated_at": dt_util.now().isoformat(),
            }

            emergency_state = {
                "active": True,
                "status": "active",
                "emergency_type": emergency_type,
                "portion_adjustment": portion_adjustment,
                "duration_days": duration_days,
                "activated_at": result["activated_at"],
                "expires_at": result["expires_at"],
                "food_type_recommendation": config.food_type,
            }

            self._active_emergencies[dog_id] = emergency_state
            result["emergency_state"] = dict(emergency_state)

            _LOGGER.info(
                "Activated emergency feeding mode for %s: %s for %d days (%.1f%% portions)",
                dog_id,
                emergency_type,
                duration_days,
                portion_adjustment * 100,
            )

            # Schedule automatic restoration
            async def _restore_normal_feeding() -> None:
                await asyncio.sleep(
                    duration_days * 24 * 3600
                )  # Convert days to seconds
                try:
                    await self._offload_blocking(
                        f"restore emergency feeding plan for {dog_id}",
                        self._apply_emergency_restoration,
                        config,
                        original_config,
                        dog_id,
                    )

                    _LOGGER.info(
                        "Restored normal feeding mode for %s after %d days",
                        dog_id,
                        duration_days,
                    )
                except Exception as err:
                    _LOGGER.error(
                        "Failed to restore normal feeding for %s: %s", dog_id, err
                    )

            async def _restore_wrapper() -> None:
                try:
                    await _restore_normal_feeding()
                    emergency_details = self._active_emergencies.get(dog_id)
                    if emergency_details:
                        emergency_details = dict(emergency_details)
                        emergency_details.update(
                            {
                                "active": False,
                                "status": "resolved",
                                "resolved_at": dt_util.utcnow().isoformat(),
                            }
                        )
                        self._active_emergencies[dog_id] = emergency_details
                finally:
                    self._emergency_restore_tasks.pop(dog_id, None)

            restore_task = asyncio.create_task(_restore_wrapper())
            self._emergency_restore_tasks[dog_id] = restore_task
            result["restoration_scheduled"] = True

            return result

    async def async_start_diet_transition(
        self,
        dog_id: str,
        new_food_type: str,
        transition_days: int = 7,
        gradual_increase_percent: int = 25,
    ) -> dict[str, Any]:
        """Start a gradual diet transition to prevent digestive upset.

        Args:
            dog_id: Dog identifier
            new_food_type: Target food type
            transition_days: Number of days for full transition
            gradual_increase_percent: Daily increase percentage of new food

        Returns:
            Dictionary with transition plan and results
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config:
                raise ValueError(f"No feeding configuration found for dog {dog_id}")

            # Validate parameters
            if not 3 <= transition_days <= 14:
                raise ValueError("Transition days must be between 3 and 14")
            if not 10 <= gradual_increase_percent <= 50:
                raise ValueError("Gradual increase must be between 10% and 50%")

            old_food_type = config.food_type
            if old_food_type == new_food_type:
                return {
                    "status": "no_change",
                    "message": f"Dog is already on {new_food_type} diet",
                }

            # Create transition schedule
            transition_schedule = self._create_transition_schedule(
                transition_days, gradual_increase_percent
            )

            # Store transition info in config
            transition_data: FeedingTransitionData = {
                "active": True,
                "start_date": dt_util.now().date().isoformat(),
                "old_food_type": old_food_type,
                "new_food_type": new_food_type,
                "transition_days": transition_days,
                "gradual_increase_percent": gradual_increase_percent,
                "schedule": transition_schedule,
                "current_day": 1,
            }

            # Add to health conditions temporarily
            if "diet_transition" not in config.health_conditions:
                config.health_conditions.append("diet_transition")

            # Store transition data (would normally be in a separate storage)
            config.transition_data = transition_data

            # Invalidate caches
            self._invalidate_cache(dog_id)

            result = {
                "status": "started",
                "dog_id": dog_id,
                "old_food_type": old_food_type,
                "new_food_type": new_food_type,
                "transition_days": transition_days,
                "gradual_increase_percent": gradual_increase_percent,
                "transition_schedule": transition_schedule,
                "expected_completion": (dt_util.now() + timedelta(days=transition_days))
                .date()
                .isoformat(),
                "started_at": dt_util.now().isoformat(),
            }

            _LOGGER.info(
                "Started diet transition for %s from %s to %s over %d days",
                dog_id,
                old_food_type,
                new_food_type,
                transition_days,
            )

            return result

    def _create_transition_schedule(
        self, transition_days: int, increase_percent: int
    ) -> list[dict[str, Any]]:
        """Create day-by-day transition schedule.

        Args:
            transition_days: Total days for transition
            increase_percent: Daily increase percentage

        Returns:
            List of daily transition ratios
        """
        schedule = []

        for day in range(1, transition_days + 1):
            if day == 1:
                new_food_percent = increase_percent
            elif day == transition_days:
                new_food_percent = 100
            else:
                # Gradual increase each day
                new_food_percent = min(100, day * increase_percent)

            old_food_percent = 100 - new_food_percent

            schedule.append(
                {
                    "day": day,
                    "old_food_percent": old_food_percent,
                    "new_food_percent": new_food_percent,
                    "date": (dt_util.now() + timedelta(days=day - 1))
                    .date()
                    .isoformat(),
                }
            )

        return schedule

    async def async_check_feeding_compliance(
        self,
        dog_id: str,
        days_to_check: int = 7,
        notify_on_issues: bool = True,
    ) -> FeedingComplianceResult:
        """Check feeding compliance against schedule and health requirements.

        Args:
            dog_id: Dog identifier
            days_to_check: Number of recent days to analyze
            notify_on_issues: Whether to create notifications for issues

        Returns:
            Dictionary with compliance analysis
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config:
                raise ValueError(f"No feeding configuration found for dog {dog_id}")

            feedings = self._feedings.get(dog_id, [])
            if not feedings:
                return FeedingComplianceNoData(
                    status="no_data",
                    message="No feeding history available",
                )

            # Get recent feedings
            since = dt_util.now() - timedelta(days=days_to_check)
            recent_feedings = [
                event for event in feedings if event.time > since and not event.skipped
            ]

            if not recent_feedings:
                return FeedingComplianceNoData(
                    status="no_recent_data",
                    message=f"No feeding data in last {days_to_check} days",
                )

            # Analyze compliance
            compliance_issues: list[ComplianceIssue] = []
            daily_accumulators: dict[str, _DailyComplianceAccumulator] = {}
            missed_meals: list[MissedMealEntry] = []

            # Group feedings by date
            for event in recent_feedings:
                date_str = event.time.date().isoformat()
                accumulator = daily_accumulators.get(date_str)
                if accumulator is None:
                    accumulator = _DailyComplianceAccumulator(date=date_str)
                    daily_accumulators[date_str] = accumulator

                accumulator.feedings.append(event)
                accumulator.total_amount += event.amount
                if event.meal_type:
                    accumulator.meal_types.add(event.meal_type.value)
                if event.scheduled:
                    accumulator.scheduled_feedings += 1

            # Check each day for compliance issues
            expected_daily_amount = config.daily_food_amount
            expected_meals_per_day = config.meals_per_day
            tolerance_percent = config.portion_tolerance

            for date_str, accumulator in daily_accumulators.items():
                day_issues: list[str] = []

                # Check daily amount
                amount_deviation = (
                    abs(accumulator.total_amount - expected_daily_amount)
                    / expected_daily_amount
                    * 100
                    if expected_daily_amount > 0
                    else 0.0
                )
                if amount_deviation > tolerance_percent:
                    if accumulator.total_amount < expected_daily_amount:
                        day_issues.append(
                            f"Underfed by {amount_deviation:.1f}% ({accumulator.total_amount:.0f}g vs {expected_daily_amount:.0f}g)"
                        )
                    else:
                        day_issues.append(
                            f"Overfed by {amount_deviation:.1f}% ({accumulator.total_amount:.0f}g vs {expected_daily_amount:.0f}g)"
                        )

                # Check meal frequency
                actual_meals = len(accumulator.feedings)
                if actual_meals < expected_meals_per_day:
                    day_issues.append(
                        f"Too few meals: {actual_meals} vs expected {expected_meals_per_day}"
                    )
                    missed_meals.append(
                        MissedMealEntry(
                            date=date_str,
                            expected=expected_meals_per_day,
                            actual=actual_meals,
                        )
                    )
                elif (
                    actual_meals > expected_meals_per_day + 2
                ):  # Allow some flexibility
                    day_issues.append(
                        f"Too many meals: {actual_meals} vs expected {expected_meals_per_day}"
                    )

                # Check schedule adherence if strict scheduling
                if config.schedule_type == FeedingScheduleType.STRICT:
                    expected_scheduled = len(
                        [s for s in config.get_active_schedules() if s.is_due_today()]
                    )
                    if accumulator.scheduled_feedings < expected_scheduled:
                        day_issues.append(
                            f"Missed scheduled feedings: {accumulator.scheduled_feedings} vs {expected_scheduled}"
                        )

                if day_issues:
                    severity = (
                        "high"
                        if any(
                            "Overfed" in issue or "Underfed" in issue
                            for issue in day_issues
                        )
                        else "medium"
                    )
                    compliance_issues.append(
                        ComplianceIssue(
                            date=date_str,
                            issues=day_issues,
                            severity=severity,
                        )
                    )

            # Calculate overall compliance score
            total_days = len(daily_accumulators)
            days_with_issues = len(compliance_issues)
            expected_feedings = expected_meals_per_day * total_days
            actual_feedings = sum(
                len(acc.feedings) for acc in daily_accumulators.values()
            )
            if expected_feedings > 0:
                compliance_rate = round((actual_feedings / expected_feedings) * 100, 1)
            else:
                compliance_rate = 100.0

            compliance_score = int(min(100, max(0, compliance_rate)))

            # Generate recommendations
            recommendations: list[str] = []
            if compliance_score < 80:
                recommendations.append("Consider setting up feeding reminders")
                recommendations.append("Review portion sizes and meal timing")
            if any(
                "Overfed" in entry or "Underfed" in entry
                for issue in compliance_issues
                for entry in issue["issues"]
            ):
                recommendations.append("Reduce portion sizes to prevent weight gain")
            if any(
                "schedule" in entry.lower()
                for issue in compliance_issues
                for entry in issue["issues"]
            ):
                recommendations.append("Enable automatic reminders for scheduled meals")

            daily_analysis_payload: dict[str, DailyComplianceTelemetry] = {
                date: {
                    "date": accumulator.date,
                    "feedings": [
                        cast(FeedingEventTelemetry, event.to_dict())
                        for event in accumulator.feedings
                    ],
                    "total_amount": accumulator.total_amount,
                    "meal_types": sorted(accumulator.meal_types),
                    "scheduled_feedings": accumulator.scheduled_feedings,
                }
                for date, accumulator in sorted(daily_accumulators.items())
            }

            average_daily_amount = (
                sum(acc.total_amount for acc in daily_accumulators.values())
                / total_days
                if total_days > 0
                else 0.0
            )
            average_meals_per_day = (
                sum(len(acc.feedings) for acc in daily_accumulators.values())
                / total_days
                if total_days > 0
                else 0.0
            )

            result: FeedingComplianceCompleted = {
                "status": "completed",
                "dog_id": dog_id,
                "compliance_score": compliance_score,
                "compliance_rate": compliance_rate,
                "days_analyzed": total_days,
                "days_with_issues": days_with_issues,
                "compliance_issues": compliance_issues,
                "missed_meals": missed_meals,
                "daily_analysis": daily_analysis_payload,
                "recommendations": recommendations,
                "summary": {
                    "average_daily_amount": average_daily_amount,
                    "average_meals_per_day": average_meals_per_day,
                    "expected_daily_amount": expected_daily_amount,
                    "expected_meals_per_day": expected_meals_per_day,
                },
                "checked_at": dt_util.now().isoformat(),
            }

            _LOGGER.info(
                "Feeding compliance check for %s: %d%% compliant over %d days",
                dog_id,
                compliance_score,
                total_days,
            )

            return result

    async def async_adjust_daily_portions(
        self,
        dog_id: str,
        adjustment_percent: int,
        reason: str | None = None,
        temporary: bool = False,
        duration_days: int | None = None,
    ) -> dict[str, Any]:
        """Adjust daily portions by a percentage.

        Args:
            dog_id: Dog identifier
            adjustment_percent: Percentage to adjust (-50 to +50)
            reason: Reason for adjustment
            temporary: Whether adjustment is temporary
            duration_days: Days to maintain adjustment (if temporary)

        Returns:
            Dictionary with adjustment results
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config:
                raise ValueError(f"No feeding configuration found for dog {dog_id}")

            # Validate adjustment range
            if not -50 <= adjustment_percent <= 50:
                raise ValueError("Adjustment percent must be between -50 and +50")

            # Store original amount for temporary adjustments
            original_amount = config.daily_food_amount

            # Calculate new amount
            adjustment_factor = 1.0 + (adjustment_percent / 100.0)
            new_amount = round(original_amount * adjustment_factor, 1)

            # Safety check - don't allow extremely small portions
            if new_amount < 50.0:  # Minimum 50g per day
                raise ValueError("Adjustment would result in dangerously low portions")

            # Update daily amount
            config.daily_food_amount = new_amount

            # Update meal schedules proportionally
            updated_schedules = 0
            for schedule in config.meal_schedules:
                old_portion = schedule.portion_size
                schedule.portion_size = round(old_portion * adjustment_factor, 1)
                updated_schedules += 1

            # Invalidate caches
            self._invalidate_cache(dog_id)

            result = {
                "status": "adjusted",
                "dog_id": dog_id,
                "adjustment_percent": adjustment_percent,
                "original_daily_amount": original_amount,
                "new_daily_amount": new_amount,
                "absolute_change_g": round(new_amount - original_amount, 1),
                "updated_schedules": updated_schedules,
                "reason": reason,
                "temporary": temporary,
                "duration_days": duration_days,
                "adjusted_at": dt_util.now().isoformat(),
            }

            _LOGGER.info(
                "Adjusted daily portions for %s by %+d%% (%.0fg -> %.0fg) - %s",
                dog_id,
                adjustment_percent,
                original_amount,
                new_amount,
                reason or "no reason given",
            )

            # Schedule reversion if temporary
            if temporary and duration_days:
                if existing_task := self._portion_reversion_tasks.pop(dog_id, None):
                    existing_task.cancel()

                async def _revert_adjustment() -> None:
                    try:
                        await asyncio.sleep(duration_days * 24 * 3600)
                        try:
                            # Restore original amount
                            config.daily_food_amount = original_amount

                            # Restore meal schedules
                            revert_factor = 1.0 / adjustment_factor
                            for schedule in config.meal_schedules:
                                schedule.portion_size = round(
                                    schedule.portion_size * revert_factor, 1
                                )

                            self._invalidate_cache(dog_id)

                            _LOGGER.info(
                                "Reverted portion adjustment for %s back to %.0fg after %d days",
                                dog_id,
                                original_amount,
                                duration_days,
                            )
                        except Exception as err:  # pragma: no cover - logging only
                            _LOGGER.error(
                                "Failed to revert portion adjustment for %s: %s",
                                dog_id,
                                err,
                            )
                    finally:
                        self._portion_reversion_tasks.pop(dog_id, None)

                revert_task = asyncio.create_task(_revert_adjustment())
                self._portion_reversion_tasks[dog_id] = revert_task
                result["reversion_scheduled"] = True
                result["reversion_date"] = (
                    dt_util.now() + timedelta(days=duration_days)
                ).isoformat()

            return result

    async def async_add_health_snack(
        self,
        dog_id: str,
        snack_type: str,
        amount: float,
        health_benefit: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Add a health-focused snack/supplement to feeding log.

        Args:
            dog_id: Dog identifier
            snack_type: Type of healthy snack
            amount: Amount in grams
            health_benefit: Specific health benefit category
            notes: Additional notes

        Returns:
            Dictionary with snack addition results
        """
        async with self._lock:
            config = self._configs.get(dog_id)
            if not config:
                raise ValueError(f"No feeding configuration found for dog {dog_id}")

            # Validate amount
            if amount <= 0 or amount > 100:  # Reasonable limit for snacks
                raise ValueError("Snack amount must be between 0 and 100 grams")

            # Build enhanced notes with health benefit info
            enhanced_notes = notes or ""
            if health_benefit:
                benefit_descriptions = {
                    "digestive": "Supports digestive health",
                    "dental": "Promotes dental health",
                    "joint": "Supports joint health",
                    "skin_coat": "Improves skin and coat health",
                    "immune": "Boosts immune system",
                    "calming": "Natural calming properties",
                }
                benefit_desc = benefit_descriptions.get(
                    health_benefit, f"Health benefit: {health_benefit}"
                )
                enhanced_notes = (
                    f"{benefit_desc}. {enhanced_notes}"
                    if enhanced_notes
                    else benefit_desc
                )

            # Add as feeding event
            feeding_event = await self.async_add_feeding(
                dog_id=dog_id,
                amount=amount,
                meal_type="snack",  # Use snack meal type
                notes=enhanced_notes,
                scheduled=False,  # Health snacks are typically unscheduled
            )

            # Track health snack in daily stats (don't count towards meal requirements)
            result = {
                "status": "added",
                "dog_id": dog_id,
                "snack_type": snack_type,
                "amount": amount,
                "health_benefit": health_benefit,
                "feeding_event_id": feeding_event.time.isoformat(),
                "notes": enhanced_notes,
                "added_at": dt_util.now().isoformat(),
            }

            _LOGGER.info(
                "Added health snack for %s: %.1fg %s (%s)",
                dog_id,
                amount,
                snack_type,
                health_benefit or "general health",
            )

            return result

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
