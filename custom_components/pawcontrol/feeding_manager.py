"""Feeding management with health-aware portions for PawControl."""

import asyncio
from collections.abc import Callable, Iterable, Mapping, Sequence
import contextlib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from functools import partial
import logging
from time import perf_counter
from typing import Any, Literal, NotRequired, Required, TypedDict, TypeVar, cast

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .types import (
  DietValidationResult,
  FeedingDailyStats,
  FeedingDietValidationSummary,
  FeedingEmergencyState,
  FeedingEventRecord,
  FeedingGoalSettings,
  FeedingHealthContext,
  FeedingHealthStatus,
  FeedingHealthSummary,
  FeedingHistoryAnalysis,
  FeedingHistoryEvent,
  FeedingManagerDogSetupPayload,
  FeedingMissedMeal,
  FeedingSnapshot,
  FeedingSnapshotCache,
  FeedingStatisticsCache,
  FeedingStatisticsSnapshot,
  HealthFeedingInsights,
  HealthMetricsOverride,
  HealthReport,
  JSONLikeMapping,
  JSONMapping,
  JSONMutableMapping,
)
from .utils import is_number

# Support running as standalone module in tests
try:  # pragma: no cover - fallback for direct test execution
  from .health_calculator import (  # noqa: E111
    ActivityLevel,
    DietSafetyResult,
    HealthCalculator,
    HealthMetrics,
    LifeStage,
  )
except ImportError:  # pragma: no cover
  from custom_components.pawcontrol.health_calculator import (  # noqa: E111
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
  """Meal type enumeration."""  # noqa: E111

  BREAKFAST = "breakfast"  # noqa: E111
  LUNCH = "lunch"  # noqa: E111
  DINNER = "dinner"  # noqa: E111
  SNACK = "snack"  # noqa: E111
  TREAT = "treat"  # noqa: E111
  SUPPLEMENT = "supplement"  # noqa: E111


class FeedingScheduleType(Enum):
  """Feeding schedule type enumeration."""  # noqa: E111

  FLEXIBLE = "flexible"  # noqa: E111
  STRICT = "strict"  # noqa: E111
  CUSTOM = "custom"  # noqa: E111


class FeedingMedicationData(TypedDict, total=False):
  """Optional medication context attached to scheduled feedings."""  # noqa: E111

  name: str  # noqa: E111
  dose: str  # noqa: E111
  time: str  # noqa: E111


class FeedingBatchEntry(TypedDict, total=False):
  """Batch-feeding payload accepted by ``async_batch_add_feedings``."""  # noqa: E111

  dog_id: Required[str]  # noqa: E111
  amount: float  # noqa: E111
  meal_type: str | None  # noqa: E111
  time: datetime | None  # noqa: E111
  timestamp: datetime | None  # noqa: E111
  notes: str | None  # noqa: E111
  feeder: str | None  # noqa: E111
  scheduled: bool  # noqa: E111
  with_medication: bool  # noqa: E111
  medication_name: str | None  # noqa: E111
  medication_dose: str | None  # noqa: E111
  medication_time: str | None  # noqa: E111


class FeedingAddParams(TypedDict, total=False):
  """Keyword parameters forwarded to ``async_add_feeding``."""  # noqa: E111

  amount: float  # noqa: E111
  meal_type: str | None  # noqa: E111
  time: datetime | None  # noqa: E111
  timestamp: datetime | None  # noqa: E111
  notes: str | None  # noqa: E111
  feeder: str | None  # noqa: E111
  scheduled: bool  # noqa: E111
  with_medication: bool  # noqa: E111
  medication_name: str | None  # noqa: E111
  medication_dose: str | None  # noqa: E111
  medication_time: str | None  # noqa: E111


class FeedingHealthUpdatePayload(TypedDict, total=False):
  """Incremental health-update payload consumed by the feeding manager."""  # noqa: E111

  weight: float | int  # noqa: E111
  ideal_weight: float | int  # noqa: E111
  age_months: int | float | None  # noqa: E111
  activity_level: str  # noqa: E111
  body_condition_score: float | int | None  # noqa: E111
  health_conditions: list[str]  # noqa: E111
  weight_goal: str  # noqa: E111


class FeedingDogMetadata(TypedDict, total=False):
  """Cached dog metadata maintained for compatibility with legacy helpers."""  # noqa: E111

  dog_id: Required[str]  # noqa: E111
  dog_name: str | None  # noqa: E111
  weight: float  # noqa: E111
  ideal_weight: float | None  # noqa: E111
  activity_level: str | None  # noqa: E111
  age_months: int | None  # noqa: E111
  breed: str | None  # noqa: E111
  breed_size: str  # noqa: E111
  weight_goal: str | None  # noqa: E111
  health_conditions: list[str]  # noqa: E111
  feeding_config: JSONMutableMapping | JSONMapping  # noqa: E111
  meals_per_day: int  # noqa: E111
  diabetic_mode: bool  # noqa: E111
  carb_limit_percent: int | None  # noqa: E111


class FeedingEmergencyConfigSnapshot(TypedDict):
  """Snapshot of configuration values adjusted during emergency feeding."""  # noqa: E111

  daily_food_amount: float  # noqa: E111
  meals_per_day: int  # noqa: E111
  schedule_type: FeedingScheduleType  # noqa: E111
  food_type: str  # noqa: E111


class FeedingSpecialDietInfo(TypedDict, total=False):
  """Structured special-diet metadata for dashboards and diagnostics."""  # noqa: E111

  has_special_diet: Required[bool]  # noqa: E111
  requirements: list[str]  # noqa: E111
  categories: dict[str, list[str]]  # noqa: E111
  total_requirements: int  # noqa: E111
  priority_level: Literal["high", "normal"]  # noqa: E111
  validation: DietValidationResult | None  # noqa: E111


class FeedingDietValidationStatus(TypedDict):
  """Diet-validation payload exported via ``async_get_diet_validation_status``."""  # noqa: E111

  validation_data: DietValidationResult  # noqa: E111
  summary: FeedingDietValidationSummary  # noqa: E111
  special_diets: list[str]  # noqa: E111
  last_updated: str  # noqa: E111


class FeedingPortionValidationSuccess(TypedDict):
  """Successful portion-validation payload."""  # noqa: E111

  portion: float  # noqa: E111
  meal_type: str  # noqa: E111
  safety_validation: DietSafetyResult  # noqa: E111
  diet_validation_summary: FeedingDietValidationSummary | None  # noqa: E111
  health_aware_calculation: bool  # noqa: E111
  config_id: str  # noqa: E111


class FeedingPortionValidationError(TypedDict):
  """Failed portion-validation payload."""  # noqa: E111

  error: str  # noqa: E111
  portion: float  # noqa: E111
  meal_type: NotRequired[str]  # noqa: E111


FeedingPortionValidationResult = (
  FeedingPortionValidationSuccess | FeedingPortionValidationError
)


class FeedingRecalculationResult(TypedDict, total=False):
  """Result payload returned by ``async_recalculate_health_portions``."""  # noqa: E111

  status: Required[str]  # noqa: E111
  dog_id: Required[str]  # noqa: E111
  new_portions: dict[str, float]  # noqa: E111
  total_daily_amount: float  # noqa: E111
  previous_daily_target: float  # noqa: E111
  updated_schedules: int  # noqa: E111
  health_metrics_used: dict[str, float | str | None]  # noqa: E111
  recalculated_at: str  # noqa: E111
  message: str  # noqa: E111


class FeedingActivityAdjustmentResult(TypedDict, total=False):
  """Result payload returned by ``async_adjust_calories_for_activity``."""  # noqa: E111

  status: Required[str]  # noqa: E111
  dog_id: Required[str]  # noqa: E111
  old_activity_level: str | None  # noqa: E111
  new_activity_level: str  # noqa: E111
  old_daily_calories: float | int | None  # noqa: E111
  new_daily_calories: float | int | None  # noqa: E111
  old_daily_amount_g: float  # noqa: E111
  new_daily_amount_g: float  # noqa: E111
  adjustment_percent: float  # noqa: E111
  temporary: bool  # noqa: E111
  duration_hours: int | None  # noqa: E111
  adjusted_at: str  # noqa: E111
  message: str  # noqa: E111
  reversion_scheduled: NotRequired[bool]  # noqa: E111


class FeedingDiabeticActivationResult(TypedDict, total=False):
  """Result payload returned by ``async_activate_diabetic_feeding_mode``."""  # noqa: E111

  status: Required[str]  # noqa: E111
  dog_id: Required[str]  # noqa: E111
  old_meals_per_day: int  # noqa: E111
  new_meals_per_day: int  # noqa: E111
  carb_limit_percent: int  # noqa: E111
  monitor_blood_glucose: bool  # noqa: E111
  schedule_type: str  # noqa: E111
  meal_times: list[str]  # noqa: E111
  portion_sizes: list[float]  # noqa: E111
  special_diet_updated: list[str]  # noqa: E111
  activated_at: str  # noqa: E111


class FeedingEmergencyActivationResult(TypedDict, total=False):
  """Result payload returned by ``async_activate_emergency_feeding_mode``."""  # noqa: E111

  status: Required[str]  # noqa: E111
  dog_id: Required[str]  # noqa: E111
  emergency_type: str  # noqa: E111
  duration_days: int  # noqa: E111
  portion_adjustment: float  # noqa: E111
  old_daily_amount: float  # noqa: E111
  new_daily_amount: float  # noqa: E111
  old_meals_per_day: int  # noqa: E111
  new_meals_per_day: int  # noqa: E111
  food_type_recommendation: str  # noqa: E111
  original_config: FeedingEmergencyConfigSnapshot  # noqa: E111
  expires_at: str  # noqa: E111
  activated_at: str  # noqa: E111
  emergency_state: FeedingEmergencyState  # noqa: E111
  restoration_scheduled: NotRequired[bool]  # noqa: E111


class FeedingTransitionResult(TypedDict, total=False):
  """Result payload returned by ``async_start_diet_transition``."""  # noqa: E111

  status: Required[str]  # noqa: E111
  dog_id: Required[str]  # noqa: E111
  old_food_type: str  # noqa: E111
  new_food_type: str  # noqa: E111
  transition_days: int  # noqa: E111
  gradual_increase_percent: int  # noqa: E111
  transition_schedule: list[FeedingTransitionScheduleEntry]  # noqa: E111
  expected_completion: str  # noqa: E111
  started_at: str  # noqa: E111
  message: str  # noqa: E111


class FeedingPortionAdjustmentResult(TypedDict, total=False):
  """Result payload returned by ``async_adjust_daily_portions``."""  # noqa: E111

  status: Required[str]  # noqa: E111
  dog_id: Required[str]  # noqa: E111
  adjustment_percent: int  # noqa: E111
  original_daily_amount: float  # noqa: E111
  new_daily_amount: float  # noqa: E111
  absolute_change_g: float  # noqa: E111
  updated_schedules: int  # noqa: E111
  reason: str | None  # noqa: E111
  temporary: bool  # noqa: E111
  duration_days: int | None  # noqa: E111
  adjusted_at: str  # noqa: E111
  reversion_scheduled: bool  # noqa: E111
  reversion_date: str  # noqa: E111


class FeedingHealthSnackResult(TypedDict, total=False):
  """Result payload returned by ``async_add_health_snack``."""  # noqa: E111

  status: Required[str]  # noqa: E111
  dog_id: Required[str]  # noqa: E111
  snack_type: str  # noqa: E111
  amount: float  # noqa: E111
  health_benefit: str | None  # noqa: E111
  feeding_event_id: str  # noqa: E111
  notes: str | None  # noqa: E111
  added_at: str  # noqa: E111


@dataclass(slots=True, frozen=True)
class FeedingEvent:
  """Immutable feeding event for better caching."""  # noqa: E111

  time: datetime  # noqa: E111
  amount: float  # noqa: E111
  meal_type: MealType | None = None  # noqa: E111
  portion_size: float | None = None  # noqa: E111
  food_type: str | None = None  # noqa: E111
  notes: str | None = None  # noqa: E111
  feeder: str | None = None  # noqa: E111
  scheduled: bool = False  # noqa: E111
  skipped: bool = False  # noqa: E111
  with_medication: bool = False  # noqa: E111
  medication_name: str | None = None  # noqa: E111
  medication_dose: str | None = None  # noqa: E111
  medication_time: str | None = None  # noqa: E111

  def to_dict(self) -> FeedingEventRecord:  # noqa: E111
    """Convert to dictionary for storage."""
    return FeedingEventRecord(
      time=self.time.isoformat(),
      amount=float(self.amount),
      meal_type=self.meal_type.value if self.meal_type else None,
      portion_size=self.portion_size,
      food_type=self.food_type,
      notes=self.notes,
      feeder=self.feeder,
      scheduled=self.scheduled,
      skipped=self.skipped,
      with_medication=self.with_medication,
      medication_name=self.medication_name,
      medication_dose=self.medication_dose,
      medication_time=self.medication_time,
    )


@dataclass(slots=True)
class _DailyComplianceAccumulator:
  """Internal accumulator for per-day compliance statistics."""  # noqa: E111

  date: str  # noqa: E111
  feedings: list[FeedingEvent] = field(default_factory=list)  # noqa: E111
  total_amount: float = 0.0  # noqa: E111
  meal_types: set[str] = field(default_factory=set)  # noqa: E111
  scheduled_feedings: int = 0  # noqa: E111


@dataclass(slots=True)
class MealSchedule:
  """Scheduled meal with configuration."""  # noqa: E111

  meal_type: MealType  # noqa: E111
  scheduled_time: time  # noqa: E111
  portion_size: float  # noqa: E111
  enabled: bool = True  # noqa: E111
  reminder_enabled: bool = True  # noqa: E111
  reminder_minutes_before: int = 15  # noqa: E111
  auto_log: bool = False  # noqa: E111
  days_of_week: list[int] | None = None  # noqa: E111

  def is_due_today(self) -> bool:  # noqa: E111
    """Check if meal is scheduled for today."""
    if not self.enabled:
      return False  # noqa: E111

    if self.days_of_week is None:
      return True  # noqa: E111

    today = dt_util.now().weekday()
    return today in self.days_of_week

  def get_next_feeding_time(self) -> datetime:  # noqa: E111
    """Get next scheduled feeding time."""
    now = dt_util.now()
    today = now.date()

    scheduled = datetime.combine(today, self.scheduled_time)
    scheduled = dt_util.as_local(scheduled)

    if scheduled <= now:
      scheduled += timedelta(days=1)  # noqa: E111

    if self.days_of_week is not None:
      while scheduled.weekday() not in self.days_of_week:  # noqa: E111
        scheduled += timedelta(days=1)

    return scheduled

  def get_reminder_time(self) -> datetime | None:  # noqa: E111
    """Get reminder time for this meal."""
    if not self.reminder_enabled:
      return None  # noqa: E111

    next_feeding = self.get_next_feeding_time()
    return next_feeding - timedelta(minutes=self.reminder_minutes_before)


def _normalise_health_override(
  data: JSONLikeMapping | None,
) -> HealthMetricsOverride | None:
  """Coerce arbitrary mappings into ``HealthMetricsOverride`` payloads."""  # noqa: E111

  if not data:  # noqa: E111
    return None

  override: HealthMetricsOverride = {}  # noqa: E111

  if (weight := data.get("weight")) is not None and isinstance(  # noqa: E111
    weight,
    int | float | str,
  ):
    override["weight"] = float(weight)

  if (ideal_weight := data.get("ideal_weight")) is not None and isinstance(  # noqa: E111
    ideal_weight,
    int | float | str,
  ):
    override["ideal_weight"] = float(ideal_weight)

  if (age_months := data.get("age_months")) is not None and isinstance(  # noqa: E111
    age_months,
    int | float | str,
  ):
    override["age_months"] = int(age_months)

  conditions = data.get("health_conditions")  # noqa: E111
  if isinstance(conditions, Sequence) and not isinstance(conditions, str | bytes):  # noqa: E111
    override["health_conditions"] = [
      condition for condition in conditions if isinstance(condition, str)
    ]

  return override or None  # noqa: E111


class FeedingTransitionScheduleEntry(TypedDict):
  """Daily transition ratios applied while changing diets."""  # noqa: E111

  day: int  # noqa: E111
  old_food_percent: int  # noqa: E111
  new_food_percent: int  # noqa: E111
  date: str  # noqa: E111


class FeedingTransitionData(TypedDict):
  """Telemetry describing an in-progress feeding transition."""  # noqa: E111

  active: bool  # noqa: E111
  start_date: str  # noqa: E111
  old_food_type: str  # noqa: E111
  new_food_type: str  # noqa: E111
  transition_days: int  # noqa: E111
  gradual_increase_percent: int  # noqa: E111
  schedule: list[FeedingTransitionScheduleEntry]  # noqa: E111
  current_day: int  # noqa: E111


class ComplianceIssue(TypedDict):
  """Structured compliance issue telemetry."""  # noqa: E111

  date: str  # noqa: E111
  issues: list[str]  # noqa: E111
  severity: str  # noqa: E111


class MissedMealEntry(TypedDict):
  """Metadata describing a missed scheduled meal."""  # noqa: E111

  date: str  # noqa: E111
  expected: int  # noqa: E111
  actual: int  # noqa: E111


class FeedingEventTelemetry(TypedDict, total=False):
  """Serialized telemetry describing a recorded feeding event."""  # noqa: E111

  time: str  # noqa: E111
  amount: float  # noqa: E111
  meal_type: str | None  # noqa: E111
  portion_size: float | None  # noqa: E111
  food_type: str | None  # noqa: E111
  notes: str | None  # noqa: E111
  feeder: str | None  # noqa: E111
  scheduled: bool  # noqa: E111
  skipped: bool  # noqa: E111
  with_medication: bool  # noqa: E111
  medication_name: str | None  # noqa: E111
  medication_dose: str | None  # noqa: E111
  medication_time: str | None  # noqa: E111


class DailyComplianceTelemetry(TypedDict):
  """Telemetry summarising compliance statistics for a day."""  # noqa: E111

  date: str  # noqa: E111
  feedings: list[FeedingEventTelemetry]  # noqa: E111
  total_amount: float  # noqa: E111
  meal_types: list[str]  # noqa: E111
  scheduled_feedings: int  # noqa: E111


class FeedingComplianceSummary(TypedDict):
  """Summary metrics for the compliance analysis window."""  # noqa: E111

  average_daily_amount: float  # noqa: E111
  average_meals_per_day: float  # noqa: E111
  expected_daily_amount: float  # noqa: E111
  expected_meals_per_day: int  # noqa: E111


class FeedingComplianceCompleted(TypedDict):
  """Successful compliance analysis payload."""  # noqa: E111

  status: Literal["completed"]  # noqa: E111
  dog_id: str  # noqa: E111
  compliance_score: int  # noqa: E111
  compliance_rate: float  # noqa: E111
  days_analyzed: int  # noqa: E111
  days_with_issues: int  # noqa: E111
  compliance_issues: list[ComplianceIssue]  # noqa: E111
  missed_meals: list[MissedMealEntry]  # noqa: E111
  daily_analysis: dict[str, DailyComplianceTelemetry]  # noqa: E111
  recommendations: list[str]  # noqa: E111
  summary: FeedingComplianceSummary  # noqa: E111
  checked_at: str  # noqa: E111


class FeedingComplianceNoData(TypedDict):
  """Compliance analysis result when insufficient telemetry exists."""  # noqa: E111

  status: Literal["no_data", "no_recent_data"]  # noqa: E111
  message: str  # noqa: E111


FeedingComplianceResult = FeedingComplianceCompleted | FeedingComplianceNoData


@dataclass
class FeedingConfig:
  """Enhanced feeding configuration with health integration."""  # noqa: E111

  dog_id: str  # noqa: E111
  meals_per_day: int = 2  # noqa: E111
  daily_food_amount: float = 500.0  # noqa: E111
  food_type: str = "dry_food"  # noqa: E111
  special_diet: list[str] = field(default_factory=list)  # noqa: E111
  schedule_type: FeedingScheduleType = FeedingScheduleType.FLEXIBLE  # noqa: E111
  meal_schedules: list[MealSchedule] = field(default_factory=list)  # noqa: E111
  treats_enabled: bool = True  # noqa: E111
  max_treats_per_day: int = 3  # noqa: E111
  water_tracking: bool = False  # noqa: E111
  calorie_tracking: bool = False  # noqa: E111
  calories_per_gram: float | None = None  # noqa: E111
  portion_calculation_enabled: bool = True  # noqa: E111
  medication_with_meals: bool = False  # noqa: E111
  portion_tolerance: int = 10  # percentage  # noqa: E111

  # Health integration fields  # noqa: E114
  health_aware_portions: bool = True  # noqa: E111
  dog_weight: float | None = None  # noqa: E111
  ideal_weight: float | None = None  # noqa: E111
  age_months: int | None = None  # noqa: E111
  breed_size: str = "medium"  # noqa: E111
  activity_level: str | None = None  # noqa: E111
  body_condition_score: int | None = None  # noqa: E111
  health_conditions: list[str] = field(default_factory=list)  # noqa: E111
  weight_goal: str | None = None  # "maintain", "lose", "gain"  # noqa: E111
  spayed_neutered: bool = True  # noqa: E111

  # Diet validation integration  # noqa: E114
  diet_validation: DietValidationResult | None = None  # noqa: E111
  transition_data: FeedingTransitionData | None = None  # noqa: E111

  def calculate_portion_size(  # noqa: E111
    self,
    meal_type: MealType | None = None,
    health_data: HealthMetricsOverride | None = None,
  ) -> float:
    """Calculate health-aware portion size with advanced algorithms.

    Args:
        meal_type: Optional meal type for specialized portion calculation
        health_data: Optional real-time health data override

    Returns:
        Calculated portion size in grams
    """
    if self.meals_per_day <= 0:
      return 0.0  # noqa: E111

    base_portion = self.daily_food_amount / self.meals_per_day

    if not self.portion_calculation_enabled:
      return base_portion  # noqa: E111

    # Health-aware calculation if enabled
    if self.health_aware_portions:
      try:  # noqa: E111
        health_portion = self._calculate_health_aware_portion(
          meal_type,
          health_data,
        )
        if health_portion > 0:
          return health_portion  # noqa: E111
      except Exception as err:  # noqa: E111
        _LOGGER.warning(
          "Health-aware calculation failed for %s: %s",
          self.dog_id,
          err,
        )

    # Fallback to basic meal-type calculation
    if not meal_type:
      return base_portion  # noqa: E111

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
      tolerance_factor = 1.0 + (self.portion_tolerance / 100.0)  # noqa: E111
      calculated_portion = min(  # noqa: E111
        calculated_portion * tolerance_factor,
        self.daily_food_amount * 0.6,
      )  # Max 60% in one meal

    return round(calculated_portion, 1)

  def _calculate_health_aware_portion(  # noqa: E111
    self,
    meal_type: MealType | None = None,
    health_data: HealthMetricsOverride | None = None,
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
      # No weight data - fall back to basic calculation  # noqa: E114
      return 0.0  # noqa: E111

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
    feeding_goals: FeedingGoalSettings = {}
    if self.weight_goal in {"maintain", "lose", "gain"}:
      feeding_goals["weight_goal"] = cast(  # noqa: E111
        Literal["maintain", "lose", "gain"],
        self.weight_goal,
      )
    if self.weight_goal == "lose":
      # Could be configurable  # noqa: E114
      feeding_goals["weight_loss_rate"] = "moderate"  # noqa: E111

    adjustment_factor = HealthCalculator.calculate_portion_adjustment_factor(
      health_metrics,
      feeding_goals if feeding_goals else None,
      self.diet_validation,
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
      meal_distribution = self._get_meal_distribution()  # noqa: E111
      meal_factor = meal_distribution.get(meal_type, 1.0)  # noqa: E111
      portion = base_portion * meal_factor  # noqa: E111
    else:
      portion = base_portion  # noqa: E111

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
      validation_summary = self._get_diet_validation_summary()  # noqa: E111
      if validation_summary.get("has_adjustments"):  # noqa: E111
        _LOGGER.info(
          "Diet validation adjustments applied to portion for %s: %s",
          self.dog_id,
          validation_summary["adjustment_info"],
        )

    return round(portion, 1)

  def _get_diet_validation_summary(self) -> FeedingDietValidationSummary:  # noqa: E111
    """Get summary of diet validation adjustments."""

    total_diets = len(self.special_diet or [])

    validation = self.diet_validation
    if not validation:
      return FeedingDietValidationSummary(  # noqa: E111
        has_adjustments=False,
        adjustment_info="No validation data",
        conflict_count=0,
        warning_count=0,
        vet_consultation_recommended=False,
        vet_consultation_state="not_needed",
        consultation_urgency="none",
        total_diets=total_diets,
        diet_validation_adjustment=1.0,
        percentage_adjustment=0.0,
        adjustment_direction="none",
        safety_factor="normal",
        compatibility_score=100,
        compatibility_level="excellent",
        conflicts=[],
        warnings=[],
      )

    conflicts = validation["conflicts"]
    warnings = validation["warnings"]
    total_diets = max(
      total_diets,
      int(
        validation["total_diets"] or total_diets,
      ),
    )

    try:
      validation_adjustment = HealthCalculator.calculate_diet_validation_adjustment(  # noqa: E111
        validation,
        self.special_diet,
      )
    except Exception as err:  # pragma: no cover - defensive logging
      _LOGGER.debug(  # noqa: E111
        "Failed to calculate diet validation adjustment for %s: %s",
        self.dog_id,
        err,
      )
      validation_adjustment = 1.0  # noqa: E111

    percentage_adjustment = round((validation_adjustment - 1.0) * 100.0, 1)

    if percentage_adjustment > 0.5:
      adjustment_direction = "increase"  # noqa: E111
    elif percentage_adjustment < -0.5:
      adjustment_direction = "decrease"  # noqa: E111
    else:
      adjustment_direction = "none"  # noqa: E111

    safety_factor = "conservative" if validation_adjustment < 1.0 else "normal"

    adjustments: list[str] = []
    if conflicts:
      adjustments.extend(  # noqa: E111
        [f"Conflict: {conflict['type']}" for conflict in conflicts],
      )
    if warnings:
      adjustments.extend(  # noqa: E111
        [f"Warning: {warning['type']}" for warning in warnings],
      )

    conflict_count = len(conflicts)
    warning_count = len(warnings)

    compatibility_score = 100
    compatibility_score -= conflict_count * 25
    compatibility_score -= min(warning_count * 10, 40)
    compatibility_score -= max(0, total_diets - 3) * 5
    compatibility_score = max(0, min(100, compatibility_score))

    if compatibility_score >= 85:
      compatibility_level = "excellent"  # noqa: E111
    elif compatibility_score >= 70:
      compatibility_level = "good"  # noqa: E111
    elif compatibility_score >= 55:
      compatibility_level = "acceptable"  # noqa: E111
    elif compatibility_score >= 40:
      compatibility_level = "concerning"  # noqa: E111
    else:
      compatibility_level = "poor"  # noqa: E111

    vet_recommended = bool(
      validation["recommended_vet_consultation"] or conflict_count > 0,
    )

    if conflict_count > 0:
      consultation_urgency = "high"  # noqa: E111
    elif warning_count >= 2 or total_diets >= 5:
      consultation_urgency = "medium"  # noqa: E111
    elif warning_count > 0 or total_diets >= 4:
      consultation_urgency = "low"  # noqa: E111
    else:
      consultation_urgency = "none"  # noqa: E111

    has_adjustments = (
      bool(adjustments)
      or abs(
        validation_adjustment - 1.0,
      )
      > 0.005
    )

    return FeedingDietValidationSummary(
      has_adjustments=has_adjustments,
      adjustment_info="; ".join(
        adjustments,
      )
      if adjustments
      else "No adjustments",
      conflict_count=conflict_count,
      warning_count=warning_count,
      vet_consultation_recommended=vet_recommended,
      vet_consultation_state="recommended" if vet_recommended else "not_needed",
      consultation_urgency=consultation_urgency,
      total_diets=total_diets,
      diet_validation_adjustment=round(validation_adjustment, 3),
      percentage_adjustment=percentage_adjustment,
      adjustment_direction=adjustment_direction,
      safety_factor=safety_factor,
      compatibility_score=compatibility_score,
      compatibility_level=compatibility_level,
      conflicts=cast(list[JSONMapping], conflicts),
      warnings=cast(list[JSONMapping], warnings),
    )

  def update_diet_validation(self, validation_data: DietValidationResult) -> None:  # noqa: E111
    """Update diet validation data and trigger portion recalculation.

    Args:
        validation_data: Diet validation results from config flow
    """
    self.diet_validation = validation_data

    # Log validation update
    validation_summary = self._get_diet_validation_summary()
    if validation_summary.get("has_adjustments"):
      _LOGGER.info(  # noqa: E111
        "Diet validation updated for %s: %s",
        self.dog_id,
        validation_summary["adjustment_info"],
      )

  def _build_health_metrics(  # noqa: E111
    self,
    override_data: HealthMetricsOverride | None = None,
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
      if (override_weight := override_data.get("weight")) is not None:  # noqa: E111
        current_weight = float(override_weight)
      if (override_ideal := override_data.get("ideal_weight")) is not None:  # noqa: E111
        ideal_weight = float(override_ideal)
      if (override_age := override_data.get("age_months")) is not None:  # noqa: E111
        age_months = int(override_age)
      additional_conditions = override_data.get("health_conditions")  # noqa: E111
      if additional_conditions:  # noqa: E111
        health_conditions.extend(additional_conditions)

    # Determine life stage
    life_stage = None
    if age_months is not None:
      try:  # noqa: E111
        life_stage = HealthCalculator.calculate_life_stage(
          age_months,
          self.breed_size,
        )
      except ValueError:  # noqa: E111
        _LOGGER.warning(
          "Received invalid age_months=%s for %s; skipping life stage determination",
          age_months,
          self.dog_id,
        )

    # Parse activity level
    activity_level = None
    if self.activity_level:
      try:  # noqa: E111
        activity_level = ActivityLevel(self.activity_level)
      except ValueError:  # noqa: E111
        _LOGGER.warning(
          "Invalid activity level: %s",
          self.activity_level,
        )

    # Parse body condition score
    body_condition_score = None
    if self.body_condition_score is not None:
      body_condition_score = HealthCalculator.estimate_body_condition_score(  # noqa: E111
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

  def _estimate_calories_per_gram(self) -> float:  # noqa: E111
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

  def _get_meal_distribution(self) -> dict[MealType, float]:  # noqa: E111
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

  def get_health_summary(self) -> FeedingHealthSummary:  # noqa: E111
    """Get summary of health-related feeding configuration."""

    health_metrics = self._build_health_metrics()

    # Calculate daily calorie requirement if possible
    daily_calories = None
    if health_metrics.current_weight:
      try:  # noqa: E111
        daily_calories = HealthCalculator.calculate_daily_calories(
          weight=health_metrics.current_weight,
          life_stage=health_metrics.life_stage or LifeStage.ADULT,
          activity_level=health_metrics.activity_level or ActivityLevel.MODERATE,
          body_condition_score=health_metrics.body_condition_score,
          health_conditions=health_metrics.health_conditions,
          spayed_neutered=self.spayed_neutered,
        )
      except Exception as err:  # noqa: E111
        _LOGGER.warning("Calorie calculation failed: %s", err)

    return FeedingHealthSummary(
      health_aware_enabled=self.health_aware_portions,
      current_weight=health_metrics.current_weight,
      ideal_weight=health_metrics.ideal_weight,
      life_stage=health_metrics.life_stage.value if health_metrics.life_stage else None,
      activity_level=health_metrics.activity_level.value
      if health_metrics.activity_level
      else None,
      body_condition_score=health_metrics.body_condition_score.value
      if health_metrics.body_condition_score
      else None,
      daily_calorie_requirement=daily_calories,
      calories_per_gram=self._estimate_calories_per_gram(),
      health_conditions=health_metrics.health_conditions,
      special_diet=health_metrics.special_diet,
      weight_goal=self.weight_goal,
      diet_validation_applied=self.diet_validation is not None,
    )

  def get_special_diet_info(self) -> FeedingSpecialDietInfo:  # noqa: E111
    """Get information about special diet requirements.

    Returns:
        Dictionary with special diet information
    """
    if not self.special_diet:
      return {"has_special_diet": False, "requirements": [], "validation": None}  # noqa: E111

    # Categorize special diet requirements
    health_related = [
      "diabetic",
      "kidney_support",
      "prescription",
      "low_fat",
    ]
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

    return FeedingSpecialDietInfo(
      has_special_diet=True,
      requirements=list(self.special_diet),
      categories={k: v for k, v in categorized.items() if v},
      total_requirements=len(self.special_diet),
      priority_level=(
        "high" if any(d in health_related for d in self.special_diet) else "normal"
      ),
      validation=self.diet_validation,
    )

  def get_active_schedules(self) -> list[MealSchedule]:  # noqa: E111
    """Get enabled meal schedules."""
    return [s for s in self.meal_schedules if s.enabled]

  def get_todays_schedules(self) -> list[MealSchedule]:  # noqa: E111
    """Get schedules due today."""
    return [s for s in self.meal_schedules if s.is_due_today()]


class FeedingManager:
  """Optimized feeding management with event-based reminders and caching."""  # noqa: E111

  _MAX_SINGLE_FEEDING_GRAMS = 5000.0  # noqa: E111

  def __init__(self, hass: HomeAssistant, max_history: int = 100) -> None:  # noqa: E111
    """Initialize with configurable history limit.

    Args:
        hass: Home Assistant instance
        max_history: Maximum feeding events to keep per dog
    """
    self.hass = hass
    self._feedings: dict[str, list[FeedingEvent]] = {}
    self._configs: dict[str, FeedingConfig] = {}
    # Historic FeedingManager implementations exposed ``_dogs`` as a cache
    # of per-dog metadata.  Several diagnostics and tests rely on that
    # attribute, so we continue to populate it even though the refactored
    # manager primarily works with FeedingConfig instances.
    self._dogs: dict[str, FeedingDogMetadata] = {}
    self._lock = asyncio.Lock()
    self._max_history = max_history

    # OPTIMIZATION: Event-based reminder system
    self._reminder_events: dict[str, asyncio.Event] = {}
    self._reminder_tasks: dict[str, asyncio.Task] = {}
    self._next_reminders: dict[str, datetime] = {}

    # Track emergency feeding modes for health-aware entities
    self._active_emergencies: dict[str, FeedingEmergencyState] = {}
    self._emergency_restore_tasks: dict[str, asyncio.Task] = {}

    # Track scheduled reversion tasks so we can cancel or clean them up
    self._activity_reversion_tasks: dict[str, asyncio.Task] = {}
    self._portion_reversion_tasks: dict[str, asyncio.Task] = {}

    # Async dependency audit instrumentation
    self._profile_threshold = 0.05

    # OPTIMIZATION: Feeding data cache
    self._data_cache: FeedingSnapshotCache = {}
    self._cache_time: dict[str, datetime] = {}
    self._cache_ttl = timedelta(seconds=10)

    # OPTIMIZATION: Statistics cache
    self._stats_cache: FeedingStatisticsCache = {}
    self._stats_cache_time: dict[str, datetime] = {}
    self._stats_cache_ttl = timedelta(minutes=5)

  async def _offload_blocking(  # noqa: E111
    self,
    description: str,
    func: Callable[..., T],
    *args: Any,
    **kwargs: Any,
  ) -> T:
    """Run *func* in a worker thread and emit async profiling logs."""

    start = perf_counter()
    if kwargs:
      func = partial(func, **kwargs)  # noqa: E111
    result = await self.hass.async_add_executor_job(func, *args)
    duration = perf_counter() - start
    if duration >= self._profile_threshold:
      _LOGGER.debug(  # noqa: E111
        "Async dependency audit: %s completed in %.3fs off the event loop",
        description,
        duration,
      )
    return result

  def _apply_emergency_restoration(  # noqa: E111
    self,
    config: FeedingConfig,
    original_config: FeedingEmergencyConfigSnapshot,
    dog_id: str,
  ) -> None:
    """Restore baseline feeding parameters after emergency mode."""

    config.daily_food_amount = original_config["daily_food_amount"]
    config.meals_per_day = original_config["meals_per_day"]
    config.schedule_type = original_config["schedule_type"]
    config.food_type = original_config["food_type"]

    self._invalidate_cache(dog_id)

  async def async_initialize(  # noqa: E111
    self,
    dogs: Sequence[FeedingManagerDogSetupPayload | JSONLikeMapping],
  ) -> None:
    """Initialize feeding configurations for dogs.

    Args:
        dogs: Sequence of dog configuration payloads
            compatible with ``FeedingManagerDogSetupPayload``
    """
    async with self._lock:
      # Reset caches so repeated initialisation (common in tests) does not  # noqa: E114
      # leak previous dog metadata or reminder tasks.  # noqa: E114
      for task in self._reminder_tasks.values():  # noqa: E111
        task.cancel()
      self._reminder_tasks.clear()  # noqa: E111
      self._reminder_events.clear()  # noqa: E111
      self._next_reminders.clear()  # noqa: E111
      self._feedings.clear()  # noqa: E111
      self._configs.clear()  # noqa: E111
      self._dogs.clear()  # noqa: E111
      self._data_cache.clear()  # noqa: E111
      self._cache_time.clear()  # noqa: E111
      self._stats_cache.clear()  # noqa: E111
      self._stats_cache_time.clear()  # noqa: E111

      batch_configs: dict[str, FeedingConfig] = {}  # noqa: E111
      batch_dogs: dict[str, FeedingDogMetadata] = {}  # noqa: E111

      for dog in dogs:  # noqa: E111
        dog_id_raw = dog.get("dog_id")
        if not isinstance(dog_id_raw, str) or not dog_id_raw:
          continue  # noqa: E111

        dog_id = dog_id_raw

        weight = dog.get("weight")
        if not isinstance(weight, int | float | str):
          raise ValueError(  # noqa: E111
            f"Invalid feeding configuration for {dog_id}: weight is required",
          )

        try:
          parsed_weight = float(weight)  # noqa: E111
        except ValueError:
          raise ValueError(  # noqa: E111
            f"Invalid feeding configuration for {dog_id}: weight is required",
          ) from None
        except TypeError:
          raise ValueError(  # noqa: E111
            f"Invalid feeding configuration for {dog_id}: weight is required",
          ) from None

        if parsed_weight <= 0:
          raise ValueError(  # noqa: E111
            f"Invalid feeding configuration for {dog_id}: weight is required",
          )

        feeding_config = cast(
          JSONMutableMapping,
          dict(
            cast(
              JSONLikeMapping,
              dog.get("feeding_config", {}),
            ),
          ),
        )
        config = await self._create_feeding_config(dog_id, feeding_config)

        config.dog_weight = parsed_weight
        if (ideal_weight := dog.get("ideal_weight")) is not None and isinstance(
          ideal_weight,
          int | float | str,
        ):
          try:  # noqa: E111
            config.ideal_weight = float(ideal_weight)
          except ValueError:  # pragma: no cover - defensive  # noqa: E111
            _LOGGER.debug(
              "Invalid ideal weight %s for %s; keeping existing value",
              ideal_weight,
              dog_id,
            )
          except TypeError:  # pragma: no cover - defensive  # noqa: E111
            _LOGGER.debug(
              "Invalid ideal weight %s for %s; keeping existing value",
              ideal_weight,
              dog_id,
            )
        if (age_months := dog.get("age_months")) is not None and isinstance(
          age_months,
          int | float | str,
        ):
          config.age_months = int(age_months)  # noqa: E111
        if (activity := dog.get("activity_level")) and isinstance(
          activity,
          str,
        ):
          config.activity_level = activity  # noqa: E111
        health_conditions = dog.get("health_conditions")
        if isinstance(health_conditions, Sequence) and not isinstance(
          health_conditions,
          str | bytes,
        ):
          config.health_conditions = [  # noqa: E111
            condition for condition in health_conditions if isinstance(condition, str)
          ]
        if isinstance(weight_goal := dog.get("weight_goal"), str):
          config.weight_goal = weight_goal  # noqa: E111
        if (special_diet := dog.get("special_diet")) is not None:
          config.special_diet = self._normalize_special_diet(  # noqa: E111
            special_diet,
          )

        self._feedings[dog_id] = []
        batch_configs[dog_id] = config

        batch_dogs[dog_id] = FeedingDogMetadata(
          dog_id=dog_id,
          dog_name=cast(str | None, dog.get("dog_name")),
          weight=parsed_weight,
          ideal_weight=config.ideal_weight,
          activity_level=config.activity_level or "moderate",
          age_months=config.age_months,
          breed=cast(str | None, dog.get("breed")),
          breed_size=config.breed_size,
          weight_goal=config.weight_goal,
          health_conditions=list(config.health_conditions),
          feeding_config=feeding_config,
          meals_per_day=config.meals_per_day,
          diabetic_mode=False,
          carb_limit_percent=None,
        )

      # OPTIMIZATION: Batch update configs  # noqa: E114
      self._configs.update(batch_configs)  # noqa: E111
      self._dogs.update(batch_dogs)  # noqa: E111

      # Setup reminders for all dogs with schedules  # noqa: E114
      for dog_id, config in batch_configs.items():  # noqa: E111
        if config.schedule_type != FeedingScheduleType.FLEXIBLE:
          await self._setup_reminder(dog_id)  # noqa: E111

  async def _create_feeding_config(  # noqa: E111
    self,
    dog_id: str,
    config_data: JSONLikeMapping,
  ) -> FeedingConfig:
    """Create enhanced feeding configuration with health integration."""
    special_diet = self._normalize_special_diet(
      config_data.get("special_diet", []),
    )

    meals_per_day_raw = config_data.get("meals_per_day", 2)
    meals_per_day = (
      int(meals_per_day_raw) if isinstance(meals_per_day_raw, int | float | str) else 2
    )

    daily_food_amount_raw = config_data.get("daily_food_amount", 500.0)
    daily_food_amount = (
      float(daily_food_amount_raw)
      if isinstance(daily_food_amount_raw, int | float | str)
      else 500.0
    )

    food_type_raw = config_data.get("food_type", "dry_food")
    food_type = (
      food_type_raw
      if isinstance(
        food_type_raw,
        str,
      )
      else "dry_food"
    )

    schedule_value = str(config_data.get("feeding_schedule", "flexible"))

    treats_enabled_raw = config_data.get("treats_enabled", True)
    treats_enabled = (
      treats_enabled_raw
      if isinstance(
        treats_enabled_raw,
        bool,
      )
      else True
    )

    water_tracking_raw = config_data.get("water_tracking", False)
    water_tracking = (
      water_tracking_raw
      if isinstance(
        water_tracking_raw,
        bool,
      )
      else False
    )

    calorie_tracking_raw = config_data.get("calorie_tracking", False)
    calorie_tracking = (
      calorie_tracking_raw
      if isinstance(
        calorie_tracking_raw,
        bool,
      )
      else False
    )

    portion_calculation_raw = config_data.get("portion_calculation", True)
    portion_calculation_enabled = (
      portion_calculation_raw if isinstance(portion_calculation_raw, bool) else True
    )

    medication_with_meals_raw = config_data.get(
      "medication_with_meals",
      False,
    )
    medication_with_meals = (
      medication_with_meals_raw
      if isinstance(medication_with_meals_raw, bool)
      else False
    )

    portion_tolerance_raw = config_data.get("portion_tolerance", 10)
    portion_tolerance = (
      int(portion_tolerance_raw)
      if isinstance(portion_tolerance_raw, int | float | str)
      else 10
    )

    health_aware_portions_raw = config_data.get(
      "health_aware_portions",
      True,
    )
    health_aware_portions = (
      health_aware_portions_raw if isinstance(health_aware_portions_raw, bool) else True
    )

    dog_weight_value = config_data.get("dog_weight")
    dog_weight = (
      float(dog_weight_value)
      if isinstance(dog_weight_value, int | float | str)
      else None
    )

    ideal_weight_value = config_data.get("ideal_weight")
    ideal_weight = (
      float(ideal_weight_value)
      if isinstance(ideal_weight_value, int | float | str)
      else None
    )

    age_months_value = config_data.get("age_months")
    age_months = (
      int(age_months_value) if isinstance(age_months_value, int | float | str) else None
    )

    breed_size_raw = config_data.get("breed_size", "medium")
    breed_size = (
      breed_size_raw
      if isinstance(
        breed_size_raw,
        str,
      )
      else "medium"
    )

    activity_level_raw = config_data.get("activity_level")
    activity_level = activity_level_raw if isinstance(activity_level_raw, str) else None

    body_condition_raw = config_data.get("body_condition_score")
    body_condition_score = (
      int(body_condition_raw)
      if isinstance(body_condition_raw, int | float | str)
      else None
    )

    health_conditions_raw = config_data.get("health_conditions", [])
    health_conditions = (
      [condition for condition in health_conditions_raw if isinstance(condition, str)]
      if isinstance(health_conditions_raw, Sequence)
      and not isinstance(health_conditions_raw, str | bytes)
      else []
    )

    weight_goal_raw = config_data.get("weight_goal")
    weight_goal = (
      weight_goal_raw
      if isinstance(
        weight_goal_raw,
        str,
      )
      else None
    )

    spayed_neutered_raw = config_data.get("spayed_neutered", True)
    spayed_neutered = (
      spayed_neutered_raw
      if isinstance(
        spayed_neutered_raw,
        bool,
      )
      else True
    )

    diet_validation_raw = config_data.get("diet_validation")
    diet_validation: DietValidationResult | None = None
    if isinstance(diet_validation_raw, Mapping):
      diet_validation = cast(  # noqa: E111
        DietValidationResult,
        {k: v for k, v in diet_validation_raw.items() if isinstance(k, str)},
      )

    config = FeedingConfig(
      dog_id=dog_id,
      meals_per_day=meals_per_day,
      daily_food_amount=daily_food_amount,
      food_type=food_type,
      special_diet=special_diet,
      schedule_type=FeedingScheduleType(schedule_value),
      treats_enabled=treats_enabled,
      water_tracking=water_tracking,
      calorie_tracking=calorie_tracking,
      portion_calculation_enabled=portion_calculation_enabled,
      medication_with_meals=medication_with_meals,
      portion_tolerance=portion_tolerance,
      # Health integration fields
      health_aware_portions=health_aware_portions,
      dog_weight=dog_weight,
      ideal_weight=ideal_weight,
      age_months=age_months,
      breed_size=breed_size,
      activity_level=activity_level,
      body_condition_score=body_condition_score,
      health_conditions=health_conditions,
      weight_goal=weight_goal,
      spayed_neutered=spayed_neutered,
      # Diet validation integration
      diet_validation=diet_validation,
    )

    meal_schedules = []
    portion_size = config.calculate_portion_size()

    # Parse meal times
    for meal_name, meal_enum in [
      ("breakfast_time", MealType.BREAKFAST),
      ("lunch_time", MealType.LUNCH),
      ("dinner_time", MealType.DINNER),
    ]:
      meal_time_raw = config_data.get(meal_name)  # noqa: E111
      if isinstance(meal_time_raw, str | time) and (  # noqa: E111
        parsed_time := self._parse_time(meal_time_raw)
      ):
        portion_size_raw = config_data.get(
          "portion_size",
          portion_size,
        )
        portion_size_value = (
          float(portion_size_raw)
          if isinstance(portion_size_raw, int | float | str)
          else portion_size
        )
        reminder_enabled_raw = config_data.get(
          "enable_reminders",
          True,
        )
        reminder_enabled = (
          reminder_enabled_raw if isinstance(reminder_enabled_raw, bool) else True
        )
        reminder_minutes_raw = config_data.get(
          "reminder_minutes_before",
          15,
        )
        reminder_minutes_before = (
          int(reminder_minutes_raw)
          if isinstance(reminder_minutes_raw, int | float | str)
          else 15
        )

        meal_schedules.append(
          MealSchedule(
            meal_type=meal_enum,
            scheduled_time=parsed_time,
            portion_size=portion_size_value,
            reminder_enabled=reminder_enabled,
            reminder_minutes_before=reminder_minutes_before,
          ),
        )

    # Parse snack times
    snack_times_raw = config_data.get("snack_times", [])
    if isinstance(snack_times_raw, Sequence) and not isinstance(
      snack_times_raw,
      str | bytes,
    ):
      for snack_time_str in snack_times_raw:  # noqa: E111
        if not isinstance(snack_time_str, str | time):
          continue  # noqa: E111
        if parsed_time := self._parse_time(snack_time_str):
          meal_schedules.append(  # noqa: E111
            MealSchedule(
              meal_type=MealType.SNACK,
              scheduled_time=parsed_time,
              portion_size=50.0,
              reminder_enabled=False,
            ),
          )

    config.meal_schedules = meal_schedules
    return config

  def _parse_time(self, time_str: str | time) -> time | None:  # noqa: E111
    """Parse time string to time object."""
    if isinstance(time_str, time):
      return time_str  # noqa: E111

    try:
      parts = time_str.split(":")  # noqa: E111
      if len(parts) == 2:  # noqa: E111
        return time(int(parts[0]), int(parts[1]))
      if len(parts) == 3:  # noqa: E111
        return time(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError, AttributeError:
      _LOGGER.warning("Failed to parse time: %s", time_str)  # noqa: E111

    return None

  def _normalize_special_diet(self, raw_value: Any) -> list[str]:  # noqa: E111
    """Normalize special diet configuration values into a list of strings."""

    if raw_value is None:
      return []  # noqa: E111

    if isinstance(raw_value, str):
      stripped_value = raw_value.strip()  # noqa: E111
      return [stripped_value] if stripped_value else []  # noqa: E111

    if isinstance(raw_value, Iterable) and not isinstance(raw_value, bytes | str):
      normalized: list[str] = []  # noqa: E111
      for item in raw_value:  # noqa: E111
        if not isinstance(item, str):
          _LOGGER.debug(  # noqa: E111
            "Ignoring non-string special diet entry for %s: %s",
            type(item).__name__,
            item,
          )
          continue  # noqa: E111

        stripped_item = item.strip()
        if stripped_item:
          normalized.append(stripped_item)  # noqa: E111

      return normalized  # noqa: E111

    _LOGGER.debug("Unsupported special diet format: %s", raw_value)
    return []

  def _require_config(self, dog_id: str) -> FeedingConfig:  # noqa: E111
    """Return the FeedingConfig for ``dog_id`` or raise KeyError."""

    config = self._configs.get(dog_id)
    if config is None:
      raise KeyError(dog_id)  # noqa: E111
    return config

  def _require_dog_record(self, dog_id: str) -> FeedingDogMetadata:  # noqa: E111
    """Return the cached dog metadata for ``dog_id``."""

    try:
      return self._dogs[dog_id]  # noqa: E111
    except KeyError as err:  # pragma: no cover - defensive
      raise KeyError(dog_id) from err  # noqa: E111

  def _calculate_rer(self, weight: float, *, adjusted: bool = True) -> float:  # noqa: E111
    """Calculate resting energy requirement for ``weight`` in kilograms."""

    if not is_number(weight):
      raise ValueError("Weight must be a number")  # noqa: E111

    weight_value = float(weight)
    if weight_value <= 0:
      raise ValueError("Weight must be greater than zero")  # noqa: E111

    effective_weight = (
      weight_value - 7 if adjusted and weight_value > 7 else weight_value
    )
    effective_weight = max(effective_weight, 0.1)

    return 70.0 * (effective_weight**0.75)

  def calculate_daily_calories(self, dog_id: str) -> float:  # noqa: E111
    """Return the daily calorie recommendation for ``dog_id``."""

    dog = self._require_dog_record(dog_id)
    config = self._require_config(dog_id)

    weight = dog.get("weight") or config.dog_weight
    if weight is None:
      raise ValueError("Dog weight is required for calorie calculation")  # noqa: E111

    weight_value = float(weight)
    target_weight = config.ideal_weight
    if config.weight_goal in {"lose", "gain"} and target_weight:
      with contextlib.suppress(TypeError, ValueError):  # noqa: E111
        weight_value = float(target_weight)

    age_months = dog.get("age_months") or config.age_months or 24
    breed_size = dog.get("breed_size") or config.breed_size or "medium"

    with contextlib.suppress(ValueError, TypeError):
      HealthCalculator.calculate_life_stage(int(age_months), breed_size)  # noqa: E111

    activity_source = (
      config.activity_level or dog.get("activity_level") or ActivityLevel.MODERATE.value
    )
    try:
      activity_level = ActivityLevel(activity_source)  # noqa: E111
    except ValueError:
      activity_level = ActivityLevel.MODERATE  # noqa: E111

    base_weight = weight_value
    adjusted_rer = True
    if config.weight_goal == "lose" and config.ideal_weight:
      try:  # noqa: E111
        base_weight = float(config.ideal_weight)
        adjusted_rer = False
      except ValueError:  # pragma: no cover - defensive  # noqa: E111
        base_weight = weight_value
      except TypeError:  # pragma: no cover - defensive  # noqa: E111
        base_weight = weight_value
    elif config.weight_goal == "gain" and config.ideal_weight:
      try:  # noqa: E111
        base_weight = float(config.ideal_weight)
      except ValueError:  # noqa: E111
        base_weight = weight_value
      except TypeError:  # noqa: E111
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

  def calculate_portion(self, dog_id: str, meal_type: str | None = None) -> float:  # noqa: E111
    """Return the suggested portion size for ``dog_id`` and ``meal_type``."""

    config = self._require_config(dog_id)

    daily_grams = float(config.daily_food_amount)
    dog_record = self._dogs.get(dog_id)
    meals_source = (
      dog_record.get(
        "meals_per_day",
      )
      if dog_record
      else config.meals_per_day
    )
    meals = max(1, int(meals_source or config.meals_per_day))
    portion = daily_grams / meals
    return round(portion, 1)

  async def _setup_reminder(self, dog_id: str) -> None:  # noqa: E111
    """Setup event-based reminder for a dog.

    OPTIMIZATION: Uses events instead of sleep loops.

    Args:
        dog_id: Dog identifier
    """
    # Cancel existing reminder
    if dog_id in self._reminder_tasks:
      self._reminder_tasks[dog_id].cancel()  # noqa: E111

    # Create event for reminder updates
    self._reminder_events[dog_id] = asyncio.Event()

    # Create reminder task
    self._reminder_tasks[dog_id] = asyncio.create_task(
      self._reminder_handler(dog_id),
    )

  async def _reminder_handler(self, dog_id: str) -> None:  # noqa: E111
    """Event-based reminder handler.

    OPTIMIZATION: Uses events to wake up instead of continuous sleeping.

    Args:
        dog_id: Dog identifier
    """
    event = self._reminder_events[dog_id]

    while True:
      try:  # noqa: E111
        config = self._configs.get(dog_id)
        if not config:
          break  # noqa: E111

        # Calculate next reminder
        next_reminder = await self._calculate_next_reminder(config)

        if next_reminder:
          self._next_reminders[dog_id] = next_reminder  # noqa: E111

          # Wait until reminder time or event signal  # noqa: E114
          now = dt_util.now()  # noqa: E111
          if next_reminder > now:  # noqa: E111
            wait_seconds = (next_reminder - now).total_seconds()

            # Wait for timeout or event signal
            try:
              await asyncio.wait_for(event.wait(), timeout=wait_seconds)  # noqa: E111
              # Event was set - recalculate  # noqa: E114
              event.clear()  # noqa: E111
              continue  # noqa: E111
            except TimeoutError:
              # Time to send reminder  # noqa: E114
              schedule = await self._get_reminder_schedule(  # noqa: E111
                config,
                next_reminder,
              )
              if schedule:  # noqa: E111
                _LOGGER.info(
                  "Feeding reminder for %s: %s in %d minutes",
                  dog_id,
                  schedule.meal_type.value,
                  schedule.reminder_minutes_before,
                )
        else:
          # No reminders - wait for event signal  # noqa: E114
          await event.wait()  # noqa: E111
          event.clear()  # noqa: E111

      except asyncio.CancelledError:  # noqa: E111
        break
      except Exception as err:  # noqa: E111
        _LOGGER.error(
          "Error in reminder handler for %s: %s",
          dog_id,
          err,
        )
        await asyncio.sleep(60)  # Error recovery

  async def _calculate_next_reminder(self, config: FeedingConfig) -> datetime | None:  # noqa: E111
    """Calculate next reminder time for a config.

    Args:
        config: Feeding configuration

    Returns:
        Next reminder datetime or None
    """
    next_reminder = None

    for schedule in config.get_todays_schedules():
      reminder_time = schedule.get_reminder_time()  # noqa: E111
      if (  # noqa: E111
        reminder_time
        and reminder_time > dt_util.now()
        and (next_reminder is None or reminder_time < next_reminder)
      ):
        next_reminder = reminder_time

    # If no reminders today, check tomorrow
    if next_reminder is None:
      tomorrow = dt_util.now() + timedelta(days=1)  # noqa: E111
      tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0)  # noqa: E111

      for schedule in config.get_active_schedules():  # noqa: E111
        reminder_time = schedule.get_reminder_time()
        if (
          reminder_time
          and reminder_time >= tomorrow_start
          and (next_reminder is None or reminder_time < next_reminder)
        ):
          next_reminder = reminder_time  # noqa: E111

    return next_reminder

  async def _get_reminder_schedule(  # noqa: E111
    self,
    config: FeedingConfig,
    reminder_time: datetime,
  ) -> MealSchedule | None:
    """Get schedule for a reminder time.

    Args:
        config: Feeding configuration
        reminder_time: Reminder datetime

    Returns:
        Meal schedule or None
    """
    for schedule in config.get_active_schedules():
      if schedule.get_reminder_time() == reminder_time:  # noqa: E111
        return schedule
    return None

  async def async_add_feeding(  # noqa: E111
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
      raise ValueError("Feeding amount must be a numeric value in grams")  # noqa: E111

    amount_value = float(amount)
    if not (0 < amount_value <= self._MAX_SINGLE_FEEDING_GRAMS):
      raise ValueError(  # noqa: E111
        f"Feeding amount must be between 0 and {self._MAX_SINGLE_FEEDING_GRAMS} grams",
      )

    if timestamp is not None:
      time = timestamp  # noqa: E111

    async with self._lock:
      if dog_id not in self._configs:  # noqa: E111
        raise KeyError(dog_id)

      event_time = time or dt_util.now()  # noqa: E111
      if event_time.tzinfo is None:  # noqa: E111
        event_time = dt_util.as_local(dt_util.as_utc(event_time))
      else:  # noqa: E111
        event_time = dt_util.as_local(event_time)

      meal_type_enum = None  # noqa: E111
      is_medication_meal = False  # noqa: E111
      if meal_type:  # noqa: E111
        normalized_meal = meal_type.lower()
        try:
          meal_type_enum = MealType(normalized_meal)  # noqa: E111
        except ValueError:
          if normalized_meal == "medication":  # noqa: E111
            is_medication_meal = True
          else:  # noqa: E111
            _LOGGER.warning("Invalid meal type: %s", meal_type)

      if is_medication_meal and not with_medication:  # noqa: E111
        with_medication = True

      config = self._configs.get(dog_id)  # noqa: E111
      portion_size = None  # noqa: E111

      if config and meal_type_enum:  # noqa: E111
        # Use health-aware portion calculation if enabled
        if config.portion_calculation_enabled:
          portion_size = config.calculate_portion_size(  # noqa: E111
            meal_type_enum,
            health_data=None,  # Could pass real-time health data here
          )
        else:
          # Fall back to schedule-based portion size  # noqa: E114
          for schedule in config.meal_schedules:  # noqa: E111
            if schedule.meal_type == meal_type_enum:
              portion_size = schedule.portion_size  # noqa: E111
              break  # noqa: E111

      event = FeedingEvent(  # noqa: E111
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

      self._feedings.setdefault(dog_id, []).append(event)  # noqa: E111

      # OPTIMIZATION: Maintain history limit  # noqa: E114
      if len(self._feedings[dog_id]) > self._max_history:  # noqa: E111
        self._feedings[dog_id] = self._feedings[dog_id][-self._max_history :]

      # Invalidate caches  # noqa: E114
      self._invalidate_cache(dog_id)  # noqa: E111

      # Signal reminder update if scheduled feeding  # noqa: E114
      if scheduled and dog_id in self._reminder_events:  # noqa: E111
        self._reminder_events[dog_id].set()

      return event  # noqa: E111

  async def async_add_feeding_with_medication(  # noqa: E111
    self,
    dog_id: str,
    amount: float,
    meal_type: str,
    medication_data: FeedingMedicationData | None = None,
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
      # If medication linking is disabled, just record normal feeding  # noqa: E114
      return await self.async_add_feeding(  # noqa: E111
        dog_id=dog_id,
        amount=amount,
        meal_type=meal_type,
        time=time,
        notes=notes,
        feeder=feeder,
        scheduled=True,
        with_medication=True,
        medication_name=medication_data.get("name") if medication_data else None,
        medication_dose=medication_data.get("dose") if medication_data else None,
        medication_time=medication_data.get("time") if medication_data else None,
      )

    # Combine feeding notes with medication info
    combined_notes = notes or ""
    if medication_data:
      med_name = medication_data.get("name", "Unknown")  # noqa: E111
      med_dose = medication_data.get("dose", "")  # noqa: E111
      med_time = medication_data.get("time", "with meal")  # noqa: E111

      med_note = f"Medication: {med_name}"  # noqa: E111
      if med_dose:  # noqa: E111
        med_note += f" ({med_dose})"
      if med_time != "with meal":  # noqa: E111
        med_note += f" at {med_time}"

      combined_notes = f"{combined_notes}\n{med_note}" if combined_notes else med_note  # noqa: E111

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
      medication_name=medication_data.get(
        "name",
      )
      if medication_data
      else None,
      medication_dose=medication_data.get(
        "dose",
      )
      if medication_data
      else None,
      medication_time=medication_data.get(
        "time",
      )
      if medication_data
      else None,
    )

  async def async_batch_add_feedings(  # noqa: E111
    self,
    feedings: Sequence[FeedingBatchEntry],
  ) -> list[FeedingEvent]:
    """OPTIMIZATION: Add multiple feeding events at once.

    Args:
        feedings: List of feeding data dictionaries

    Returns:
        List of created FeedingEvents
    """
    events = []

    async with self._lock:
      for raw_data in feedings:  # noqa: E111
        batch_payload = dict(raw_data)
        dog_id = cast(str, batch_payload.pop("dog_id"))
        params = cast(FeedingAddParams, batch_payload)
        event = await self.async_add_feeding(dog_id, **params)
        events.append(event)

    return events

  async def async_get_feedings(  # noqa: E111
    self,
    dog_id: str,
    since: datetime | None = None,
  ) -> list[FeedingEvent]:
    """Return feeding history for a dog.

    Args:
        dog_id: Dog identifier
        since: Optional datetime filter

    Returns:
        List of feeding events
    """
    async with self._lock:
      feedings = self._feedings.get(dog_id, [])  # noqa: E111

      if since:  # noqa: E111
        # OPTIMIZATION: Binary search for efficiency with large lists
        left, right = 0, len(feedings)
        while left < right:
          mid = (left + right) // 2  # noqa: E111
          if feedings[mid].time < since:  # noqa: E111
            left = mid + 1
          else:  # noqa: E111
            right = mid
        feedings = feedings[left:]

      return list(feedings)  # noqa: E111

  async def async_get_feeding_data(self, dog_id: str) -> FeedingSnapshot:  # noqa: E111
    """Get comprehensive feeding data with caching.

    OPTIMIZATION: Caches feeding data for 10 seconds.

    Args:
        dog_id: Dog identifier

    Returns:
        Dictionary with feeding statistics
    """
    async with self._lock:
      if dog_id not in self._configs and dog_id not in self._feedings:  # noqa: E111
        empty_snapshot = self._empty_feeding_data(None)
        self._data_cache[dog_id] = empty_snapshot
        self._cache_time[dog_id] = dt_util.now()
        return empty_snapshot

      # Check cache  # noqa: E114
      if dog_id in self._data_cache:  # noqa: E111
        cache_time = self._cache_time.get(dog_id)
        if cache_time and (dt_util.now() - cache_time) < self._cache_ttl:
          return self._data_cache[dog_id]  # noqa: E111

      # Calculate feeding data  # noqa: E114
      data = self._build_feeding_snapshot(dog_id)  # noqa: E111

      # Cache result  # noqa: E114
      self._data_cache[dog_id] = data  # noqa: E111
      self._cache_time[dog_id] = dt_util.now()  # noqa: E111

      return data  # noqa: E111

  def get_feeding_data(self, dog_id: str) -> FeedingSnapshot:  # noqa: E111
    """Synchronously return the feeding snapshot for ``dog_id``.

    Legacy tests and diagnostics relied on a synchronous accessor.  The
    helper reuses the async cache but falls back to building the snapshot
    inline when the cached value has expired.
    """

    if dog_id not in self._configs and dog_id not in self._feedings:
      snapshot = self._empty_feeding_data(None)  # noqa: E111
      self._data_cache[dog_id] = snapshot  # noqa: E111
      self._cache_time[dog_id] = dt_util.now()  # noqa: E111
      return snapshot  # noqa: E111

    cache_time = self._cache_time.get(dog_id)
    if cache_time and (dt_util.now() - cache_time) < self._cache_ttl:
      cached = self._data_cache.get(dog_id)  # noqa: E111
      if cached is not None:  # noqa: E111
        return cached

    data = self._build_feeding_snapshot(dog_id)
    self._data_cache[dog_id] = data
    self._cache_time[dog_id] = dt_util.now()
    return data

  def get_daily_stats(self, dog_id: str) -> FeedingDailyStats:  # noqa: E111
    """Return today's feeding statistics for the given dog."""

    data = self.get_feeding_data(dog_id)
    stats = data.get(
      "daily_stats",
      {
        "total_fed_today": 0.0,
        "meals_today": 0,
        "remaining_calories": None,
      },
    )
    total_fed_raw = stats.get("total_fed_today", 0.0)
    total_fed_today = (
      float(total_fed_raw) if isinstance(total_fed_raw, int | float | str) else 0.0
    )

    meals_today_raw = stats.get("meals_today", 0)
    meals_today = (
      int(meals_today_raw) if isinstance(meals_today_raw, int | float | str) else 0
    )

    remaining_calories_raw = stats.get("remaining_calories")
    remaining_calories = (
      float(remaining_calories_raw)
      if isinstance(remaining_calories_raw, int | float | str)
      else None
    )

    return FeedingDailyStats(
      total_fed_today=total_fed_today,
      meals_today=meals_today,
      remaining_calories=remaining_calories,
    )

  def get_feeding_config(self, dog_id: str) -> FeedingConfig | None:  # noqa: E111
    """Return feeding configuration for a dog if available."""

    return self._configs.get(dog_id)

  def get_active_emergency(self, dog_id: str) -> FeedingEmergencyState | None:  # noqa: E111
    """Return active or most recent emergency feeding state for a dog."""

    emergency = self._active_emergencies.get(dog_id)
    if not emergency:
      return None  # noqa: E111

    return FeedingEmergencyState(**emergency)

  def _build_feeding_snapshot(self, dog_id: str) -> FeedingSnapshot:  # noqa: E111
    """Calculate feeding data without cache."""

    feedings = self._feedings.get(dog_id, [])
    config = self._configs.get(dog_id)

    if not feedings:
      return self._empty_feeding_data(config)  # noqa: E111

    now = dt_util.now()
    today = now.date()

    feedings_today: dict[str, int] = {}
    daily_amount = 0.0
    last_feeding: FeedingEvent | None = None

    for event in reversed(feedings):
      if event.time.date() == today and not event.skipped:  # noqa: E111
        meal = event.meal_type.value if event.meal_type else "unknown"
        feedings_today[meal] = feedings_today.get(meal, 0) + 1
        daily_amount += float(event.amount)

      if last_feeding is None and not event.skipped:  # noqa: E111
        last_feeding = event

    last_hours: float | None = None
    if last_feeding:
      last_hours = (now - last_feeding.time).total_seconds() / 3600  # noqa: E111

    adherence = 100
    missed_feedings: list[FeedingMissedMeal] = []

    if config and config.schedule_type != FeedingScheduleType.FLEXIBLE:
      todays_schedules = config.get_todays_schedules()  # noqa: E111
      expected = len(todays_schedules)  # noqa: E111
      if expected > 0:  # noqa: E111
        for schedule in todays_schedules:
          scheduled_datetime = dt_util.as_local(  # noqa: E111
            datetime.combine(today, schedule.scheduled_time),
          )
          if (  # noqa: E111
            scheduled_datetime <= now and schedule.meal_type.value not in feedings_today
          ):
            missed_feedings.append(
              FeedingMissedMeal(
                meal_type=schedule.meal_type.value,
                scheduled_time=scheduled_datetime.isoformat(),
              ),
            )

        completed = expected - len(missed_feedings)
        adherence = (
          int(
            (completed / expected) * 100,
          )
          if expected
          else 100
        )

    next_feeding: datetime | None = None
    next_type: str | None = None
    if config:
      for schedule in config.get_active_schedules():  # noqa: E111
        candidate = schedule.get_next_feeding_time()
        if next_feeding is None or candidate < next_feeding:
          next_feeding = candidate  # noqa: E111
          next_type = schedule.meal_type.value  # noqa: E111

    daily_amount_target = (
      float(
        config.daily_food_amount,
      )
      if config
      else 500.0
    )
    daily_amount_percentage = (
      int((daily_amount / daily_amount_target) * 100) if daily_amount_target > 0 else 0
    )

    health_summary: FeedingHealthSummary | None = None
    calories_per_gram: float | None = None
    if config:
      health_summary = config.get_health_summary()  # noqa: E111
      calories_per_gram = health_summary.get("calories_per_gram")  # noqa: E111
      if calories_per_gram is None:  # noqa: E111
        calories_per_gram = config._estimate_calories_per_gram()

    daily_calorie_target: float | None = None
    if health_summary:
      daily_calorie_target = cast(  # noqa: E111
        float | None,
        health_summary.get("daily_calorie_requirement"),
      )
    if daily_calorie_target is None and config and calories_per_gram is not None:
      daily_calorie_target = round(  # noqa: E111
        float(config.daily_food_amount) * float(calories_per_gram),
        1,
      )

    total_calories_today: float | None = None
    calorie_goal_progress: float | None = None
    if calories_per_gram is not None and daily_amount:
      total_calories_today = round(  # noqa: E111
        daily_amount * float(calories_per_gram),
        1,
      )
      if daily_calorie_target:  # noqa: E111
        try:
          progress = (total_calories_today / daily_calorie_target) * 100  # noqa: E111
        except TypeError, ZeroDivisionError:
          calorie_goal_progress = 0.0  # noqa: E111
        else:
          calorie_goal_progress = round(min(progress, 150.0), 1)  # noqa: E111

    portion_adjustment: float | None = None
    if config:
      try:  # noqa: E111
        health_metrics = config._build_health_metrics()
        feeding_goals: FeedingGoalSettings = {}
        if config.weight_goal in {"maintain", "lose", "gain"}:
          feeding_goals["weight_goal"] = cast(  # noqa: E111
            Literal["maintain", "lose", "gain"],
            config.weight_goal,
          )
        portion_adjustment = HealthCalculator.calculate_portion_adjustment_factor(
          health_metrics,
          feeding_goals if feeding_goals else None,
          config.diet_validation,
        )
      except Exception as err:  # noqa: E111
        _LOGGER.debug(
          "Failed to calculate portion adjustment factor for %s: %s",
          dog_id,
          err,
        )

    diet_summary: FeedingDietValidationSummary | None = None
    if config and config.diet_validation:
      diet_summary = config._get_diet_validation_summary()  # noqa: E111

    health_conditions: list[str] = []
    if health_summary:
      health_conditions = list(  # noqa: E111
        health_summary.get("health_conditions", []),
      )
    if config and config.health_conditions:
      seen: set[str] = set(health_conditions)  # noqa: E111
      for condition in config.health_conditions:  # noqa: E111
        if condition not in seen:
          health_conditions.append(condition)  # noqa: E111
          seen.add(condition)  # noqa: E111

    daily_activity_level: str | None = None
    if health_summary and health_summary.get("activity_level"):
      daily_activity_level = cast(  # noqa: E111
        str | None,
        health_summary.get("activity_level"),
      )

    weight_goal_progress: float | None = None
    if config and health_summary:
      current_weight = health_summary.get("current_weight")  # noqa: E111
      ideal_weight = health_summary.get("ideal_weight")  # noqa: E111
      if is_number(current_weight) and is_number(ideal_weight):  # noqa: E111
        current = float(current_weight)
        ideal = float(ideal_weight)
        try:
          if config.weight_goal == "lose":  # noqa: E111
            ratio = ideal / current if current else 0
            weight_goal_progress = max(
              0.0,
              min(ratio * 100, 100.0),
            )
          elif config.weight_goal == "gain":  # noqa: E111
            ratio = current / ideal if ideal else 0
            weight_goal_progress = max(
              0.0,
              min(ratio * 100, 100.0),
            )
          else:  # noqa: E111
            diff = abs(current - ideal)
            weight_goal_progress = max(
              0.0,
              min(100.0, 100.0 - (diff / max(ideal, 1.0)) * 100.0),
            )
        except TypeError, ZeroDivisionError:
          weight_goal_progress = None  # noqa: E111

    emergency_mode: FeedingEmergencyState | None = None
    health_emergency = False
    emergency_state = self._active_emergencies.get(dog_id)
    if emergency_state:
      emergency_copy = cast(FeedingEmergencyState, dict(emergency_state))  # noqa: E111
      expires_at = emergency_copy.get("expires_at")  # noqa: E111
      if expires_at:  # noqa: E111
        expires_dt = dt_util.parse_datetime(expires_at)
        if expires_dt and expires_dt < dt_util.utcnow():
          emergency_copy["active"] = False  # noqa: E111
          emergency_copy["status"] = emergency_copy.get(  # noqa: E111
            "status",
            "resolved",
          )
      health_emergency = bool(emergency_copy.get("active", True))  # noqa: E111
      emergency_mode = emergency_copy  # noqa: E111

    meals_today = sum(feedings_today.values())
    remaining_calories: float | None = None
    if daily_calorie_target is not None and total_calories_today is not None:
      remaining_calories = max(  # noqa: E111
        0.0,
        daily_calorie_target - total_calories_today,
      )
    elif calories_per_gram is not None:
      try:  # noqa: E111
        target_calories = daily_amount_target * float(calories_per_gram)
        consumed_calories = daily_amount * float(calories_per_gram)
        remaining_calories = max(
          0.0,
          target_calories - consumed_calories,
        )
      except ValueError:  # pragma: no cover - defensive  # noqa: E111
        remaining_calories = None
      except TypeError:  # pragma: no cover - defensive  # noqa: E111
        remaining_calories = None

    daily_stats = FeedingDailyStats(
      total_fed_today=round(daily_amount, 1),
      meals_today=meals_today,
      remaining_calories=round(remaining_calories, 1)
      if remaining_calories is not None
      else None,
    )

    health_status: FeedingHealthStatus = "insufficient_data"
    if health_emergency:
      health_status = "emergency"  # noqa: E111
    elif total_calories_today is not None and daily_calorie_target:
      try:  # noqa: E111
        ratio = total_calories_today / daily_calorie_target
      except TypeError, ZeroDivisionError:  # noqa: E111
        health_status = "unknown"
      else:  # noqa: E111
        if ratio < 0.85:
          health_status = "underfed"  # noqa: E111
        elif ratio > 1.15:
          health_status = "overfed"  # noqa: E111
        else:
          health_status = "on_track"  # noqa: E111
    elif portion_adjustment is not None:
      health_status = "monitoring"  # noqa: E111

    snapshot: FeedingSnapshot = FeedingSnapshot(
      status="ready",
      last_feeding=last_feeding.time.isoformat() if last_feeding else None,
      last_feeding_type=(
        last_feeding.meal_type.value
        if last_feeding and last_feeding.meal_type
        else None
      ),
      last_feeding_hours=last_hours,
      last_feeding_amount=last_feeding.amount if last_feeding else None,
      feedings_today=dict(feedings_today),
      total_feedings_today=meals_today,
      daily_amount_consumed=round(daily_amount, 1),
      daily_amount_target=daily_amount_target,
      daily_target=daily_amount_target,
      daily_amount_percentage=daily_amount_percentage,
      schedule_adherence=adherence,
      next_feeding=next_feeding.isoformat() if next_feeding else None,
      next_feeding_type=next_type,
      missed_feedings=missed_feedings,
      feedings=[event.to_dict() for event in feedings],
      daily_stats=daily_stats,
      medication_with_meals=bool(
        config.medication_with_meals if config else False,
      ),
      health_aware_feeding=bool(
        config.health_aware_portions if config else False,
      ),
      weight_goal=config.weight_goal if config else None,
      emergency_mode=emergency_mode,
      health_emergency=health_emergency,
      health_feeding_status=health_status,
    )

    if config:
      snapshot["config"] = {  # noqa: E111
        "meals_per_day": config.meals_per_day,
        "food_type": config.food_type,
        "schedule_type": config.schedule_type.value,
      }

    if calories_per_gram is not None:
      snapshot["calories_per_gram"] = round(float(calories_per_gram), 2)  # noqa: E111
    if daily_calorie_target is not None:
      snapshot["daily_calorie_target"] = daily_calorie_target  # noqa: E111
    if total_calories_today is not None:
      snapshot["total_calories_today"] = total_calories_today  # noqa: E111
    if calorie_goal_progress is not None:
      snapshot["calorie_goal_progress"] = calorie_goal_progress  # noqa: E111
    if portion_adjustment is not None:
      snapshot["portion_adjustment_factor"] = portion_adjustment  # noqa: E111
    snapshot["diet_validation_summary"] = diet_summary

    if health_conditions:
      snapshot["health_conditions"] = health_conditions  # noqa: E111
    if daily_activity_level is not None:
      snapshot["daily_activity_level"] = daily_activity_level  # noqa: E111
    if health_summary is not None and (
      portion_adjustment is not None or daily_activity_level is not None
    ):
      snapshot["health_summary"] = health_summary  # noqa: E111
    if weight_goal_progress is not None:
      snapshot["weight_goal_progress"] = round(weight_goal_progress, 1)  # noqa: E111

    return snapshot

  def _empty_feeding_data(self, config: FeedingConfig | None) -> FeedingSnapshot:  # noqa: E111
    """Generate an empty feeding snapshot structure."""

    calories_per_gram = config._estimate_calories_per_gram() if config else None
    daily_amount_target = (
      float(
        config.daily_food_amount,
      )
      if config
      else 500.0
    )

    remaining_calories: float | None = None
    daily_calorie_target: float | None = None
    if calories_per_gram is not None:
      daily_calorie_target = round(  # noqa: E111
        daily_amount_target * float(calories_per_gram),
        1,
      )
      remaining_calories = daily_calorie_target  # noqa: E111

    snapshot: FeedingSnapshot = FeedingSnapshot(
      status="no_data",
      last_feeding=None,
      last_feeding_type=None,
      last_feeding_hours=None,
      last_feeding_amount=None,
      feedings_today={},
      total_feedings_today=0,
      daily_amount_consumed=0.0,
      daily_amount_target=daily_amount_target,
      daily_target=daily_amount_target,
      daily_amount_percentage=0,
      schedule_adherence=100,
      next_feeding=None,
      next_feeding_type=None,
      missed_feedings=[],
      feedings=[],
      daily_stats=FeedingDailyStats(
        total_fed_today=0.0,
        meals_today=0,
        remaining_calories=round(remaining_calories, 1)
        if remaining_calories is not None
        else None,
      ),
      medication_with_meals=bool(
        config.medication_with_meals if config else False,
      ),
      health_aware_feeding=bool(
        config.health_aware_portions if config else False,
      ),
      weight_goal=config.weight_goal if config else None,
      emergency_mode=None,
      health_emergency=False,
      health_feeding_status="insufficient_data",
    )

    if config and config.health_conditions:
      snapshot["health_conditions"] = list(config.health_conditions)  # noqa: E111
    snapshot["diet_validation_summary"] = None
    snapshot["daily_activity_level"] = None

    if calories_per_gram is not None:
      snapshot["calories_per_gram"] = round(float(calories_per_gram), 2)  # noqa: E111
    if daily_calorie_target is not None:
      snapshot["daily_calorie_target"] = daily_calorie_target  # noqa: E111
      snapshot["total_calories_today"] = 0.0  # noqa: E111

    return snapshot

  def _invalidate_cache(self, dog_id: str) -> None:  # noqa: E111
    """Invalidate caches for a dog.

    Args:
        dog_id: Dog identifier
    """
    self._data_cache.pop(dog_id, None)
    self._cache_time.pop(dog_id, None)

    # Clear stats cache entries
    keys_to_remove = [key for key in self._stats_cache if key.startswith(f"{dog_id}_")]
    for key in keys_to_remove:
      self._stats_cache.pop(key, None)  # noqa: E111
      self._stats_cache_time.pop(key, None)  # noqa: E111

  async def async_update_config(  # noqa: E111
    self,
    dog_id: str,
    config_data: JSONLikeMapping,
  ) -> None:
    """Update feeding configuration for a dog.

    Args:
        dog_id: Dog identifier
        config_data: New configuration data
    """
    async with self._lock:
      config = await self._create_feeding_config(dog_id, config_data)  # noqa: E111
      self._configs[dog_id] = config  # noqa: E111

      dog_record = self._dogs.get(dog_id)  # noqa: E111
      if dog_record is not None:  # noqa: E111
        if (weight := dog_record.get("weight")) is not None:
          with contextlib.suppress(TypeError, ValueError):  # noqa: E111
            config.dog_weight = float(weight)
        if (ideal_weight := dog_record.get("ideal_weight")) is not None:
          with contextlib.suppress(TypeError, ValueError):  # noqa: E111
            config.ideal_weight = float(ideal_weight)

        dog_record.update(
          {
            "activity_level": config.activity_level or dog_record.get("activity_level"),
            "breed_size": config.breed_size,
            "weight_goal": config.weight_goal,
            "health_conditions": list(config.health_conditions),
            "meals_per_day": config.meals_per_day,
          },
        )

      # Invalidate caches  # noqa: E114
      self._invalidate_cache(dog_id)  # noqa: E111

      await self._refresh_reminder_schedule(dog_id, config)  # noqa: E111

  async def async_refresh_reminder(self, dog_id: str) -> None:  # noqa: E111
    """Refresh reminder scheduling for ``dog_id``."""
    async with self._lock:
      config = self._configs.get(dog_id)  # noqa: E111
      if config is None:  # noqa: E111
        return
      await self._refresh_reminder_schedule(dog_id, config)  # noqa: E111

  async def _refresh_reminder_schedule(  # noqa: E111
    self,
    dog_id: str,
    config: FeedingConfig,
  ) -> None:
    """Update reminder tasks for ``dog_id`` based on ``config``."""
    # Update reminders
    if config.schedule_type != FeedingScheduleType.FLEXIBLE:
      await self._setup_reminder(dog_id)  # noqa: E111
    elif dog_id in self._reminder_tasks:
      self._reminder_tasks[dog_id].cancel()  # noqa: E111
      del self._reminder_tasks[dog_id]  # noqa: E111
      del self._reminder_events[dog_id]  # noqa: E111
      self._next_reminders.pop(dog_id, None)  # noqa: E111

    # Signal reminder update
    if dog_id in self._reminder_events:
      self._reminder_events[dog_id].set()  # noqa: E111

  async def async_get_statistics(  # noqa: E111
    self,
    dog_id: str,
    days: int = 30,
  ) -> FeedingStatisticsSnapshot:
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
      # Check cache  # noqa: E114
      if cache_key in self._stats_cache:  # noqa: E111
        cache_time = self._stats_cache_time.get(cache_key)
        if cache_time and (dt_util.now() - cache_time) < self._stats_cache_ttl:
          return self._stats_cache[cache_key]  # noqa: E111

      # Calculate statistics  # noqa: E114
      stats = await self._calculate_statistics(dog_id, days)  # noqa: E111

      # Cache result  # noqa: E114
      self._stats_cache[cache_key] = stats  # noqa: E111
      self._stats_cache_time[cache_key] = dt_util.now()  # noqa: E111

      return stats  # noqa: E111

  async def _calculate_statistics(  # noqa: E111
    self,
    dog_id: str,
    days: int,
  ) -> FeedingStatisticsSnapshot:
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
      mid = (left + right) // 2  # noqa: E111
      if feedings[mid].time < since:  # noqa: E111
        left = mid + 1
      else:  # noqa: E111
        right = mid

    recent_feedings = feedings[left:]

    if not recent_feedings:
      return FeedingStatisticsSnapshot(  # noqa: E111
        period_days=days,
        total_feedings=0,
        average_daily_feedings=0,
        average_daily_amount=0,
        most_common_meal=None,
        schedule_adherence=100,
        daily_target_met_percentage=(
          int(0 / config.daily_food_amount * 100)
          if config and config.daily_food_amount > 0
          else 0
        ),
      )

    # OPTIMIZATION: Single pass aggregation
    daily_counts: dict[date, int] = {}
    daily_amounts: dict[date, float] = {}
    meal_counts: dict[str, int] = {}

    for feeding in recent_feedings:
      if feeding.skipped:  # noqa: E111
        continue

      date = feeding.time.date()  # noqa: E111
      daily_counts[date] = daily_counts.get(date, 0) + 1  # noqa: E111
      daily_amounts[date] = daily_amounts.get(date, 0.0) + feeding.amount  # noqa: E111

      if feeding.meal_type:  # noqa: E111
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
      max(meal_counts.items(), key=lambda item: item[1])[0] if meal_counts else None
    )

    # Calculate adherence
    adherence = 100
    if config and config.schedule_type != FeedingScheduleType.FLEXIBLE:
      expected_daily = len(config.get_active_schedules())  # noqa: E111
      if expected_daily > 0:  # noqa: E111
        adherence = min(
          100,
          int((avg_daily_feedings / expected_daily) * 100),
        )

    return FeedingStatisticsSnapshot(
      period_days=days,
      total_feedings=len([f for f in recent_feedings if not f.skipped]),
      average_daily_feedings=round(avg_daily_feedings, 1),
      average_daily_amount=round(avg_daily_amount, 1),
      most_common_meal=most_common_meal,
      schedule_adherence=adherence,
      daily_target_met_percentage=(
        int(avg_daily_amount / config.daily_food_amount * 100)
        if config and config.daily_food_amount > 0
        else 0
      ),
    )

  async def async_get_reminders(self) -> dict[str, datetime]:  # noqa: E111
    """Get all next reminder times.

    Returns:
        Dictionary mapping dog_id to next reminder time
    """
    async with self._lock:
      return dict(self._next_reminders)  # noqa: E111

  async def async_calculate_health_aware_portion(  # noqa: E111
    self,
    dog_id: str,
    meal_type: str,
    health_data: JSONLikeMapping | None = None,
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
      config = self._configs.get(dog_id)  # noqa: E111
      if not config or not config.health_aware_portions:  # noqa: E111
        return None

      try:  # noqa: E111
        meal_type_enum = MealType(meal_type)
        return config.calculate_portion_size(
          meal_type_enum,
          _normalise_health_override(health_data),
        )
      except (ValueError, Exception) as err:  # noqa: E111
        _LOGGER.warning(
          "Health-aware portion calculation failed for %s: %s",
          dog_id,
          err,
        )
        return None

  async def async_analyze_feeding_health(  # noqa: E111
    self,
    dog_id: str,
    days: int = 7,
  ) -> FeedingHistoryAnalysis:
    """Analyze feeding patterns from health perspective.

    Args:
        dog_id: Dog identifier
        days: Number of days to analyze

    Returns:
        Health analysis of feeding patterns
    """
    async with self._lock:
      config = self._configs.get(dog_id)  # noqa: E111
      feedings = self._feedings.get(dog_id, [])  # noqa: E111

      if not config or not feedings:  # noqa: E111
        return FeedingHistoryAnalysis(
          status="insufficient_data",
          message="Need feeding configuration and history",
        )

      # Get recent feeding events  # noqa: E114
      since = dt_util.now() - timedelta(days=days)  # noqa: E111
      recent_events: list[FeedingHistoryEvent] = []  # noqa: E111
      for event in feedings:  # noqa: E111
        if event.time <= since or event.skipped:
          continue  # noqa: E111
        recent_events.append(
          FeedingHistoryEvent(
            time=event.time,
            amount=float(event.amount),
            meal_type=event.meal_type.value if event.meal_type else None,
          ),
        )

      if not recent_events:  # noqa: E111
        return FeedingHistoryAnalysis(
          status="no_recent_data",
          message=f"No feeding data in last {days} days",
        )

      # Get health summary for target calories  # noqa: E114
      health_summary = config.get_health_summary()  # noqa: E111
      target_calories = health_summary.get("daily_calorie_requirement")  # noqa: E111

      if not target_calories:  # noqa: E111
        return FeedingHistoryAnalysis(
          status="no_health_data",
          message="Insufficient health data for analysis",
        )

      # Use health calculator to analyze patterns  # noqa: E114
      calories_per_gram = health_summary.get("calories_per_gram", 3.5)  # noqa: E111

      analysis = HealthCalculator.analyze_feeding_history(  # noqa: E111
        recent_events,
        target_calories,
        calories_per_gram,
      )

      # Add health-specific recommendations  # noqa: E114
      health_context: FeedingHealthContext = {}  # noqa: E111
      if config.weight_goal is not None:  # noqa: E111
        health_context["weight_goal"] = config.weight_goal
      if (bcs := health_summary.get("body_condition_score")) is not None:  # noqa: E111
        health_context["body_condition_score"] = bcs
      if (life_stage := health_summary.get("life_stage")) is not None:  # noqa: E111
        health_context["life_stage"] = life_stage
      if (activity := health_summary.get("activity_level")) is not None:  # noqa: E111
        health_context["activity_level"] = activity
      if (conditions := health_summary.get("health_conditions")) is not None:  # noqa: E111
        health_context["health_conditions"] = cast(
          list[str],
          conditions,
        )
      if (diet := health_summary.get("special_diet")) is not None:  # noqa: E111
        health_context["special_diet"] = diet
      if health_context:  # noqa: E111
        analysis["health_context"] = health_context

      return analysis  # noqa: E111

  async def async_generate_health_report(self, dog_id: str) -> HealthReport | None:  # noqa: E111
    """Generate comprehensive health report for a dog.

    Args:
        dog_id: Dog identifier

    Returns:
        Health report or None if insufficient data
    """
    async with self._lock:
      config = self._configs.get(dog_id)  # noqa: E111
      if not config or not config.health_aware_portions:  # noqa: E111
        return None

      try:  # noqa: E111
        # Build health metrics
        health_metrics = config._build_health_metrics()

        # Generate health report
        report = HealthCalculator.generate_health_report(
          health_metrics,
        )

        # Add feeding-specific insights
        health_summary = config.get_health_summary()
        feeding_goal_settings: FeedingGoalSettings = {}
        if config.weight_goal in {"maintain", "lose", "gain"}:
          feeding_goal_settings["weight_goal"] = cast(  # noqa: E111
            Literal["maintain", "lose", "gain"],
            config.weight_goal,
          )

        portion_adjustment = HealthCalculator.calculate_portion_adjustment_factor(
          health_metrics,
          feeding_goal_settings if feeding_goal_settings else None,
          config.diet_validation,
        )

        feeding_insights: HealthFeedingInsights = HealthFeedingInsights(
          daily_calorie_target=cast(
            float | None,
            health_summary.get(
              "daily_calorie_requirement",
            ),
          ),
          portion_adjustment_factor=portion_adjustment,
          recommended_meals_per_day=self._recommend_meal_frequency(
            health_metrics,
          ),
          food_type_recommendation=self._recommend_food_type(
            health_metrics,
          ),
        )
        report["feeding_insights"] = feeding_insights

        # Add recent feeding analysis
        feeding_analysis = await self.async_analyze_feeding_health(dog_id, 14)
        if feeding_analysis.get("status") == "good":
          report["recent_feeding_performance"] = feeding_analysis  # noqa: E111

        return report

      except Exception as err:  # noqa: E111
        _LOGGER.error(
          "Health report generation failed for %s: %s",
          dog_id,
          err,
        )
        return None

  def _recommend_meal_frequency(self, health_metrics: HealthMetrics) -> int:  # noqa: E111
    """Recommend optimal meal frequency based on health metrics.

    Args:
        health_metrics: Health metrics for the dog

    Returns:
        Recommended number of meals per day
    """
    # Base recommendation on life stage and health conditions
    if health_metrics.life_stage == LifeStage.PUPPY:
      if health_metrics.age_months and health_metrics.age_months < 6:  # noqa: E111
        return 4  # Very young puppies need frequent meals
      return 3  # Older puppies  # noqa: E111

    # Check for health conditions requiring frequent meals
    frequent_meal_conditions = [
      "diabetes",
      "digestive_issues",
      "hypoglycemia",
    ]
    if any(
      condition in health_metrics.health_conditions
      for condition in frequent_meal_conditions
    ):
      return 3  # noqa: E111

    # Senior dogs often benefit from smaller, frequent meals
    if health_metrics.life_stage in [LifeStage.SENIOR, LifeStage.GERIATRIC]:
      return 3  # noqa: E111

    # Default for healthy adult dogs
    return 2

  def _recommend_food_type(self, health_metrics: HealthMetrics) -> str:  # noqa: E111
    """Recommend food type based on health metrics.

    Args:
        health_metrics: Health metrics for the dog

    Returns:
        Recommended food type
    """
    # Check for specific health conditions
    if "kidney_disease" in health_metrics.health_conditions:
      return "prescription"  # Requires prescription diet  # noqa: E111

    if "diabetes" in health_metrics.health_conditions:
      return "prescription"  # Requires controlled diet  # noqa: E111

    if "digestive_issues" in health_metrics.health_conditions:
      return "wet_food"  # Easier to digest  # noqa: E111

    # Age-based recommendations
    if health_metrics.life_stage == LifeStage.PUPPY:
      return "puppy_formula"  # noqa: E111

    if (
      health_metrics.life_stage in [LifeStage.SENIOR, LifeStage.GERIATRIC]
      and health_metrics.activity_level == ActivityLevel.VERY_LOW
    ):
      return "senior_formula"  # noqa: E111

    # Weight management
    if (
      health_metrics.body_condition_score
      and health_metrics.body_condition_score.value >= 7
    ):
      return "weight_control"  # noqa: E111

    # Default recommendation
    return "dry_food"

  async def async_update_health_data(  # noqa: E111
    self,
    dog_id: str,
    health_data: FeedingHealthUpdatePayload,
  ) -> bool:
    """Update health data for a dog and recalculate portions.

    Args:
        dog_id: Dog identifier
        health_data: Updated health information

    Returns:
        True if update successful
    """
    async with self._lock:
      config = self._configs.get(dog_id)  # noqa: E111
      if not config:  # noqa: E111
        return False

      try:  # noqa: E111
        # Update health-related fields
        if "weight" in health_data:
          config.dog_weight = health_data["weight"]  # noqa: E111
        if "ideal_weight" in health_data:
          config.ideal_weight = health_data["ideal_weight"]  # noqa: E111
        if "age_months" in health_data:
          age_months_value = health_data["age_months"]  # noqa: E111
          config.age_months = (  # noqa: E111
            int(age_months_value) if age_months_value is not None else None
          )
        if "activity_level" in health_data:
          config.activity_level = health_data["activity_level"]  # noqa: E111
        if "body_condition_score" in health_data:
          body_condition_value = health_data["body_condition_score"]  # noqa: E111
          config.body_condition_score = (  # noqa: E111
            int(body_condition_value) if body_condition_value is not None else None
          )
        if "health_conditions" in health_data:
          config.health_conditions = health_data["health_conditions"]  # noqa: E111
        if "weight_goal" in health_data:
          config.weight_goal = health_data["weight_goal"]  # noqa: E111

        # Invalidate caches to force recalculation
        self._invalidate_cache(dog_id)

        _LOGGER.info("Updated health data for dog %s", dog_id)
        return True

      except Exception as err:  # noqa: E111
        _LOGGER.error(
          "Failed to update health data for %s: %s",
          dog_id,
          err,
        )
        return False

  async def async_update_diet_validation(  # noqa: E111
    self,
    dog_id: str,
    validation_data: DietValidationResult,
  ) -> bool:
    """Update diet validation data for a dog.

    Args:
        dog_id: Dog identifier
        validation_data: Diet validation results from config flow

    Returns:
        True if update successful
    """
    async with self._lock:
      config = self._configs.get(dog_id)  # noqa: E111
      if not config:  # noqa: E111
        _LOGGER.warning("No config found for dog %s", dog_id)
        return False

      try:  # noqa: E111
        # Update diet validation in config
        config.update_diet_validation(validation_data)

        # Invalidate caches to force recalculation
        self._invalidate_cache(dog_id)

        _LOGGER.info(
          "Updated diet validation for dog %s: %d conflicts, %d warnings",
          dog_id,
          len(validation_data["conflicts"]),
          len(validation_data["warnings"]),
        )
        return True

      except Exception as err:  # noqa: E111
        _LOGGER.error(
          "Failed to update diet validation for %s: %s",
          dog_id,
          err,
        )
        return False

  async def async_get_diet_validation_status(  # noqa: E111
    self,
    dog_id: str,
  ) -> FeedingDietValidationStatus | None:
    """Get current diet validation status for a dog.

    Args:
        dog_id: Dog identifier

    Returns:
        Diet validation status or None if not available
    """
    async with self._lock:
      config = self._configs.get(dog_id)  # noqa: E111
      if not config or not config.diet_validation:  # noqa: E111
        return None

      return FeedingDietValidationStatus(  # noqa: E111
        validation_data=config.diet_validation,
        summary=config._get_diet_validation_summary(),
        special_diets=list(config.special_diet),
        last_updated=dt_util.now().isoformat(),
      )

  async def async_validate_portion_with_diet(  # noqa: E111
    self,
    dog_id: str,
    meal_type: str,
    override_health_data: JSONLikeMapping | None = None,
  ) -> FeedingPortionValidationResult:
    """Calculate portion with diet validation and safety checks.

    Args:
        dog_id: Dog identifier
        meal_type: Type of meal
        override_health_data: Optional real-time health data

    Returns:
        Dictionary with portion calculation and validation results
    """
    async with self._lock:
      config = self._configs.get(dog_id)  # noqa: E111
      if not config:  # noqa: E111
        return FeedingPortionValidationError(
          error="No configuration found",
          portion=0.0,
        )

      try:  # noqa: E111
        # Calculate health-aware portion
        meal_type_enum = MealType(meal_type)
        portion = config.calculate_portion_size(
          meal_type_enum,
          _normalise_health_override(
            override_health_data,
          ),
        )

        # Growth safeguard for puppies
        base_unadjusted = config.daily_food_amount / config.meals_per_day
        health_metrics = config._build_health_metrics(
          _normalise_health_override(override_health_data),
        )
        if health_metrics.life_stage == LifeStage.PUPPY:
          portion = max(  # noqa: E111
            portion,
            base_unadjusted * PUPPY_PORTION_SAFEGUARD_FACTOR,
          )
        elif (
          health_metrics.life_stage
          in (
            LifeStage.SENIOR,
            LifeStage.GERIATRIC,
          )
          and config.dog_weight
          and config.dog_weight <= 10
        ):
          portion = max(portion, 7 * config.dog_weight)  # noqa: E111

        # Validate portion safety with diet considerations
        safety_result: DietSafetyResult
        if config.dog_weight and portion > 0:
          safety_result = HealthCalculator.validate_portion_safety(  # noqa: E111
            calculated_portion=portion,
            dog_weight=config.dog_weight,
            life_stage=HealthCalculator.calculate_life_stage(
              config.age_months or 24,
              config.breed_size,
            ),
            special_diets=config.special_diet,
            diet_validation=config.diet_validation,
          )
        else:
          safety_result = {  # noqa: E111
            "safe": True,
            "warnings": [],
            "recommendations": [],
            "portion_per_kg": 0.0,
          }

        # Include diet validation info
        validation_summary = (
          config._get_diet_validation_summary() if config.diet_validation else None
        )

        return FeedingPortionValidationSuccess(
          portion=portion,
          meal_type=meal_type,
          safety_validation=safety_result,
          diet_validation_summary=validation_summary,
          health_aware_calculation=config.health_aware_portions,
          config_id=dog_id,
        )

      except Exception as err:  # noqa: E111
        _LOGGER.error(
          "Portion validation failed for %s: %s",
          dog_id,
          err,
        )
        return FeedingPortionValidationError(
          error=str(err),
          portion=0.0,
          meal_type=meal_type,
        )

  async def async_recalculate_health_portions(  # noqa: E111
    self,
    dog_id: str,
    force_recalculation: bool = False,
    update_feeding_schedule: bool = True,
  ) -> FeedingRecalculationResult:
    """Recalculate health-aware portions and optionally update feeding schedule.

    Args:
        dog_id: Dog identifier
        force_recalculation: Force recalculation even if recent
        update_feeding_schedule: Whether to update meal schedules with new portions

    Returns:
        Dictionary with recalculation results
    """
    async with self._lock:
      config = self._configs.get(dog_id)  # noqa: E111
      if not config:  # noqa: E111
        raise ValueError(
          f"No feeding configuration found for dog {dog_id}",
        )

      if not config.health_aware_portions:  # noqa: E111
        return FeedingRecalculationResult(
          status="disabled",
          dog_id=dog_id,
          new_portions={},
          total_daily_amount=0.0,
          previous_daily_target=config.daily_food_amount,
          updated_schedules=0,
          health_metrics_used={},
          recalculated_at=dt_util.now().isoformat(),
          message="Health-aware portions are disabled for this dog",
        )

      # Build current health metrics  # noqa: E114
      health_metrics = await self._offload_blocking(  # noqa: E111
        f"build health metrics for {dog_id}",
        config._build_health_metrics,
      )

      if not health_metrics.current_weight:  # noqa: E111
        return FeedingRecalculationResult(
          status="insufficient_data",
          dog_id=dog_id,
          new_portions={},
          total_daily_amount=0.0,
          previous_daily_target=config.daily_food_amount,
          updated_schedules=0,
          health_metrics_used={},
          recalculated_at=dt_util.now().isoformat(),
          message="Weight data required for health-aware portion calculation",
        )

      # Calculate new portions for all meal types  # noqa: E114
      new_portions = {}  # noqa: E111
      total_daily_calculated = 0.0  # noqa: E111

      for meal_type in [  # noqa: E111
        MealType.BREAKFAST,
        MealType.LUNCH,
        MealType.DINNER,
        MealType.SNACK,
      ]:
        portion = config.calculate_portion_size(meal_type)
        new_portions[meal_type.value] = portion

        if meal_type != MealType.SNACK:  # Don't count snacks in daily total
          total_daily_calculated += portion  # noqa: E111

      # Update meal schedules if requested  # noqa: E114
      updated_schedules = 0  # noqa: E111
      if update_feeding_schedule and config.meal_schedules:  # noqa: E111
        for schedule in config.meal_schedules:
          if schedule.meal_type in new_portions:  # noqa: E111
            old_portion = schedule.portion_size
            schedule.portion_size = new_portions[schedule.meal_type.value]
            if abs(old_portion - schedule.portion_size) > 1.0:  # Significant change
              updated_schedules += 1  # noqa: E111

      # Invalidate caches  # noqa: E114
      self._invalidate_cache(dog_id)  # noqa: E111

      result = FeedingRecalculationResult(  # noqa: E111
        status="success",
        dog_id=dog_id,
        new_portions=new_portions,
        total_daily_amount=round(total_daily_calculated, 1),
        previous_daily_target=config.daily_food_amount,
        updated_schedules=updated_schedules,
        health_metrics_used={
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
        recalculated_at=dt_util.now().isoformat(),
      )

      _LOGGER.info(  # noqa: E111
        "Recalculated health portions for %s: %s",
        dog_id,
        {k: v for k, v in new_portions.items() if k != "snack"},
      )

      return result  # noqa: E111

  async def async_adjust_calories_for_activity(  # noqa: E111
    self,
    dog_id: str,
    activity_level: str,
    duration_hours: int | None = None,
    temporary: bool = True,
  ) -> FeedingActivityAdjustmentResult:
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
      config = self._configs.get(dog_id)  # noqa: E111
      if not config:  # noqa: E111
        raise ValueError(
          f"No feeding configuration found for dog {dog_id}",
        )

      try:  # noqa: E111
        from .health_calculator import ActivityLevel

        activity_enum = ActivityLevel(activity_level)
      except (ImportError, ValueError) as err:  # noqa: E111
        raise ValueError(
          f"Invalid activity level '{activity_level}'",
        ) from err

      # Store original activity level if temporary  # noqa: E114
      original_activity = config.activity_level  # noqa: E111

      # Update activity level  # noqa: E114
      config.activity_level = activity_level  # noqa: E111

      # Recalculate portions with new activity level  # noqa: E114
      health_metrics = await self._offload_blocking(  # noqa: E111
        f"build health metrics for {dog_id}",
        config._build_health_metrics,
      )

      if not health_metrics.current_weight:  # noqa: E111
        return FeedingActivityAdjustmentResult(
          status="insufficient_data",
          dog_id=dog_id,
          old_activity_level=original_activity,
          new_activity_level=activity_level,
          old_daily_calories=None,
          new_daily_calories=None,
          old_daily_amount_g=config.daily_food_amount,
          new_daily_amount_g=config.daily_food_amount,
          adjustment_percent=0.0,
          temporary=temporary,
          duration_hours=duration_hours,
          adjusted_at=dt_util.now().isoformat(),
          message="Weight data required for calorie adjustment",
        )

      # Calculate new daily calorie requirement  # noqa: E114
      try:  # noqa: E111
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
      except ImportError as err:  # noqa: E111
        raise ValueError("Health calculator not available") from err

      # Convert calories to food amount  # noqa: E114
      calories_per_gram = await self._offload_blocking(  # noqa: E111
        f"estimate calories per gram for {dog_id}",
        config._estimate_calories_per_gram,
      )
      new_daily_amount = new_daily_calories / calories_per_gram  # noqa: E111

      # Update daily food amount  # noqa: E114
      old_daily_amount = config.daily_food_amount  # noqa: E111
      config.daily_food_amount = round(new_daily_amount, 1)  # noqa: E111

      # Invalidate caches  # noqa: E114
      self._invalidate_cache(dog_id)  # noqa: E111

      result = FeedingActivityAdjustmentResult(  # noqa: E111
        status="success",
        dog_id=dog_id,
        old_activity_level=original_activity,
        new_activity_level=activity_level,
        old_daily_calories=round(
          old_daily_amount * calories_per_gram,
          0,
        ),
        new_daily_calories=round(new_daily_calories, 0),
        old_daily_amount_g=old_daily_amount,
        new_daily_amount_g=config.daily_food_amount,
        adjustment_percent=round(
          ((config.daily_food_amount - old_daily_amount) / old_daily_amount) * 100,
          1,
        ),
        temporary=temporary,
        duration_hours=duration_hours,
        adjusted_at=dt_util.now().isoformat(),
      )

      _LOGGER.info(  # noqa: E111
        "Adjusted calories for %s: %s activity level, %.0fg daily (was %.0fg)",
        dog_id,
        activity_level,
        config.daily_food_amount,
        old_daily_amount,
      )

      # Schedule reversion if temporary  # noqa: E114
      if temporary and duration_hours and original_activity:  # noqa: E111
        if existing_task := self._activity_reversion_tasks.pop(dog_id, None):
          existing_task.cancel()  # noqa: E111

        async def _revert_activity() -> None:
          try:  # noqa: E111
            await asyncio.sleep(duration_hours * 3600)
            try:
              await self.async_adjust_calories_for_activity(  # noqa: E111
                dog_id,
                original_activity,
                None,
                False,
              )
              _LOGGER.info(  # noqa: E111
                "Reverted activity level for %s back to %s",
                dog_id,
                original_activity,
              )
            except Exception as err:  # pragma: no cover - logging only
              _LOGGER.error(  # noqa: E111
                "Failed to revert activity level for %s: %s",
                dog_id,
                err,
              )
          finally:  # noqa: E111
            self._activity_reversion_tasks.pop(dog_id, None)

        revert_task = asyncio.create_task(_revert_activity())
        self._activity_reversion_tasks[dog_id] = revert_task
        result["reversion_scheduled"] = True

      return result  # noqa: E111

  async def async_activate_diabetic_feeding_mode(  # noqa: E111
    self,
    dog_id: str,
    meal_frequency: int = 4,
    carb_limit_percent: int = 20,
    monitor_blood_glucose: bool = True,
  ) -> FeedingDiabeticActivationResult:
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
      config = self._configs.get(dog_id)  # noqa: E111
      if not config:  # noqa: E111
        raise ValueError(
          f"No feeding configuration found for dog {dog_id}",
        )

      # Validate parameters  # noqa: E114
      if not 3 <= meal_frequency <= 6:  # noqa: E111
        raise ValueError("Meal frequency must be between 3 and 6")
      if not 5 <= carb_limit_percent <= 30:  # noqa: E111
        raise ValueError("Carb limit must be between 5% and 30%")

      # Add diabetes to health conditions if not present  # noqa: E114
      if "diabetes" not in config.health_conditions:  # noqa: E111
        config.health_conditions.append("diabetes")

      # Update special diet requirements  # noqa: E114
      if "diabetic" not in config.special_diet:  # noqa: E111
        config.special_diet.append("diabetic")
      if "low_carb" not in config.special_diet:  # noqa: E111
        config.special_diet.append("low_carb")

      # Update feeding configuration  # noqa: E114
      old_meals_per_day = config.meals_per_day  # noqa: E111
      config.meals_per_day = meal_frequency  # noqa: E111

      # Create diabetic feeding schedule  # noqa: E114
      diabetic_schedules = self._create_diabetic_meal_schedule(  # noqa: E111
        meal_frequency,
        config.daily_food_amount,
      )

      # Replace existing schedules with diabetic schedule  # noqa: E114
      config.meal_schedules = diabetic_schedules  # noqa: E111

      # Enable strict scheduling for diabetes management  # noqa: E114
      config.schedule_type = FeedingScheduleType.STRICT  # noqa: E111

      # Invalidate caches  # noqa: E114
      self._invalidate_cache(dog_id)  # noqa: E111

      # Setup reminders if needed  # noqa: E114
      await self._setup_reminder(dog_id)  # noqa: E111

      result = FeedingDiabeticActivationResult(  # noqa: E111
        status="activated",
        dog_id=dog_id,
        old_meals_per_day=old_meals_per_day,
        new_meals_per_day=meal_frequency,
        carb_limit_percent=carb_limit_percent,
        monitor_blood_glucose=monitor_blood_glucose,
        schedule_type="strict",
        meal_times=[
          schedule.scheduled_time.strftime("%H:%M") for schedule in diabetic_schedules
        ],
        portion_sizes=[
          round(schedule.portion_size, 1) for schedule in diabetic_schedules
        ],
        special_diet_updated=list(config.special_diet),
        activated_at=dt_util.now().isoformat(),
      )

      _LOGGER.info(  # noqa: E111
        "Activated diabetic feeding mode for %s: %d meals/day, %d%% carb limit",
        dog_id,
        meal_frequency,
        carb_limit_percent,
      )

      if dog_id in self._dogs:  # noqa: E111
        self._dogs[dog_id]["diabetic_mode"] = True
        self._dogs[dog_id]["carb_limit_percent"] = carb_limit_percent
        self._dogs[dog_id]["meals_per_day"] = meal_frequency

      return result  # noqa: E111

  def _create_diabetic_meal_schedule(  # noqa: E111
    self,
    meal_frequency: int,
    daily_amount: float,
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
      meal_type = (  # noqa: E111
        MealType.BREAKFAST
        if i == 0
        else (MealType.DINNER if i == len(times) - 1 else MealType.LUNCH)
      )

      schedules.append(  # noqa: E111
        MealSchedule(
          meal_type=meal_type,
          scheduled_time=meal_time,
          portion_size=round(portion_size, 1),
          enabled=True,
          reminder_enabled=True,
          reminder_minutes_before=15,
          auto_log=False,  # Manual logging for diabetes monitoring
        ),
      )

    return schedules

  async def async_activate_emergency_feeding_mode(  # noqa: E111
    self,
    dog_id: str,
    emergency_type: str,
    duration_days: int = 3,
    portion_adjustment: float = 0.8,
  ) -> FeedingEmergencyActivationResult:
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
      config = self._configs.get(dog_id)  # noqa: E111
      if not config:  # noqa: E111
        raise ValueError(
          f"No feeding configuration found for dog {dog_id}",
        )

      # Validate parameters  # noqa: E114
      if not 0.5 <= portion_adjustment <= 1.2:  # noqa: E111
        raise ValueError(
          "Portion adjustment must be between 0.5 and 1.2",
        )

      valid_emergency_types = [  # noqa: E111
        "illness",
        "surgery_recovery",
        "digestive_upset",
        "medication_reaction",
      ]
      if emergency_type not in valid_emergency_types:  # noqa: E111
        raise ValueError(
          f"Emergency type must be one of: {valid_emergency_types}",
        )

      # Cancel any existing restoration for this dog  # noqa: E114
      if dog_id in self._emergency_restore_tasks:  # noqa: E111
        self._emergency_restore_tasks[dog_id].cancel()
        self._emergency_restore_tasks.pop(dog_id, None)

      # Store original configuration for restoration  # noqa: E114
      original_config = FeedingEmergencyConfigSnapshot(  # noqa: E111
        daily_food_amount=config.daily_food_amount,
        meals_per_day=config.meals_per_day,
        schedule_type=config.schedule_type,
        food_type=config.food_type,
      )

      # Adjust daily amount  # noqa: E114
      old_daily_amount = config.daily_food_amount  # noqa: E111
      config.daily_food_amount = round(  # noqa: E111
        old_daily_amount * portion_adjustment,
        1,
      )

      # Increase meal frequency for better digestion during recovery  # noqa: E114
      if emergency_type in ["illness", "digestive_upset", "medication_reaction"]:  # noqa: E111
        config.meals_per_day = min(config.meals_per_day + 1, 4)
        # Recommend wet food for easier digestion
        if emergency_type == "digestive_upset":
          config.food_type = "wet_food"  # noqa: E111

      # Create gentle feeding schedule  # noqa: E114
      if emergency_type == "surgery_recovery":  # noqa: E111
        # Smaller, more frequent meals for post-surgery
        config.meals_per_day = min(config.meals_per_day + 2, 5)

      # Invalidate caches  # noqa: E114
      self._invalidate_cache(dog_id)  # noqa: E111

      activated_at_dt = dt_util.now()  # noqa: E111
      expires_at_dt = activated_at_dt + timedelta(days=duration_days)  # noqa: E111

      result = FeedingEmergencyActivationResult(  # noqa: E111
        status="activated",
        dog_id=dog_id,
        emergency_type=emergency_type,
        duration_days=duration_days,
        portion_adjustment=portion_adjustment,
        old_daily_amount=old_daily_amount,
        new_daily_amount=config.daily_food_amount,
        old_meals_per_day=original_config["meals_per_day"],
        new_meals_per_day=config.meals_per_day,
        food_type_recommendation=config.food_type,
        original_config=original_config,
        expires_at=expires_at_dt.isoformat(),
        activated_at=activated_at_dt.isoformat(),
        emergency_state=FeedingEmergencyState(
          active=True,
          status="active",
          emergency_type=emergency_type,
          portion_adjustment=portion_adjustment,
          duration_days=duration_days,
          activated_at=activated_at_dt.isoformat(),
          expires_at=expires_at_dt.isoformat(),
          food_type_recommendation=config.food_type,
        ),
      )

      self._active_emergencies[dog_id] = result["emergency_state"]  # noqa: E111

      _LOGGER.info(  # noqa: E111
        "Activated emergency feeding mode for %s: %s for %d days (%.1f%% portions)",
        dog_id,
        emergency_type,
        duration_days,
        portion_adjustment * 100,
      )

      # Schedule automatic restoration  # noqa: E114
      async def _restore_normal_feeding() -> None:  # noqa: E111
        await asyncio.sleep(
          duration_days * 24 * 3600,
        )  # Convert days to seconds
        try:
          self._apply_emergency_restoration(  # noqa: E111
            config,
            original_config,
            dog_id,
          )

          _LOGGER.info(  # noqa: E111
            "Restored normal feeding mode for %s after %d days",
            dog_id,
            duration_days,
          )
        except Exception as err:
          _LOGGER.error(  # noqa: E111
            "Failed to restore normal feeding for %s: %s",
            dog_id,
            err,
          )

      async def _restore_wrapper() -> None:  # noqa: E111
        try:
          await _restore_normal_feeding()  # noqa: E111
          emergency_details = self._active_emergencies.get(dog_id)  # noqa: E111
          if emergency_details:  # noqa: E111
            emergency_details["active"] = False
            emergency_details["status"] = emergency_details.get(
              "status",
              "resolved",
            )
            emergency_details["resolved_at"] = dt_util.utcnow().isoformat()
        finally:
          self._emergency_restore_tasks.pop(dog_id, None)  # noqa: E111

      restore_task = asyncio.create_task(_restore_wrapper())  # noqa: E111
      self._emergency_restore_tasks[dog_id] = restore_task  # noqa: E111
      result["restoration_scheduled"] = True  # noqa: E111

      return result  # noqa: E111

  async def async_start_diet_transition(  # noqa: E111
    self,
    dog_id: str,
    new_food_type: str,
    transition_days: int = 7,
    gradual_increase_percent: int = 25,
  ) -> FeedingTransitionResult:
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
      config = self._configs.get(dog_id)  # noqa: E111
      if not config:  # noqa: E111
        raise ValueError(
          f"No feeding configuration found for dog {dog_id}",
        )

      # Validate parameters  # noqa: E114
      if not 3 <= transition_days <= 14:  # noqa: E111
        raise ValueError("Transition days must be between 3 and 14")
      if not 10 <= gradual_increase_percent <= 50:  # noqa: E111
        raise ValueError(
          "Gradual increase must be between 10% and 50%",
        )

      old_food_type = config.food_type  # noqa: E111
      if old_food_type == new_food_type:  # noqa: E111
        now = dt_util.now()
        return FeedingTransitionResult(
          status="no_change",
          dog_id=dog_id,
          old_food_type=old_food_type,
          new_food_type=new_food_type,
          transition_days=transition_days,
          gradual_increase_percent=gradual_increase_percent,
          transition_schedule=[],
          expected_completion=now.date().isoformat(),
          started_at=now.isoformat(),
          message=f"Dog is already on {new_food_type} diet",
        )

      # Create transition schedule  # noqa: E114
      transition_schedule = self._create_transition_schedule(  # noqa: E111
        transition_days,
        gradual_increase_percent,
      )

      # Store transition info in config  # noqa: E114
      transition_data: FeedingTransitionData = {  # noqa: E111
        "active": True,
        "start_date": dt_util.now().date().isoformat(),
        "old_food_type": old_food_type,
        "new_food_type": new_food_type,
        "transition_days": transition_days,
        "gradual_increase_percent": gradual_increase_percent,
        "schedule": transition_schedule,
        "current_day": 1,
      }

      # Add to health conditions temporarily  # noqa: E114
      if "diet_transition" not in config.health_conditions:  # noqa: E111
        config.health_conditions.append("diet_transition")

      # Store transition data (would normally be in a separate storage)  # noqa: E114
      config.transition_data = transition_data  # noqa: E111

      # Invalidate caches  # noqa: E114
      self._invalidate_cache(dog_id)  # noqa: E111

      started_at = dt_util.now()  # noqa: E111
      expected_completion = (started_at + timedelta(days=transition_days)).date()  # noqa: E111

      result = FeedingTransitionResult(  # noqa: E111
        status="started",
        dog_id=dog_id,
        old_food_type=old_food_type,
        new_food_type=new_food_type,
        transition_days=transition_days,
        gradual_increase_percent=gradual_increase_percent,
        transition_schedule=transition_schedule,
        expected_completion=expected_completion.isoformat(),
        started_at=started_at.isoformat(),
      )

      _LOGGER.info(  # noqa: E111
        "Started diet transition for %s from %s to %s over %d days",
        dog_id,
        old_food_type,
        new_food_type,
        transition_days,
      )

      return result  # noqa: E111

  def _create_transition_schedule(  # noqa: E111
    self,
    transition_days: int,
    increase_percent: int,
  ) -> list[FeedingTransitionScheduleEntry]:
    """Create day-by-day transition schedule.

    Args:
        transition_days: Total days for transition
        increase_percent: Daily increase percentage

    Returns:
        List of daily transition ratios
    """
    schedule: list[FeedingTransitionScheduleEntry] = []

    for day in range(1, transition_days + 1):
      if day == 1:  # noqa: E111
        new_food_percent = increase_percent
      elif day == transition_days:  # noqa: E111
        new_food_percent = 100
      else:  # noqa: E111
        # Gradual increase each day
        new_food_percent = min(100, day * increase_percent)

      old_food_percent = 100 - new_food_percent  # noqa: E111

      schedule.append(  # noqa: E111
        FeedingTransitionScheduleEntry(
          day=day,
          old_food_percent=old_food_percent,
          new_food_percent=new_food_percent,
          date=(dt_util.now() + timedelta(days=day - 1)).date().isoformat(),
        ),
      )

    return schedule

  async def async_check_feeding_compliance(  # noqa: E111
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
      config = self._configs.get(dog_id)  # noqa: E111
      if not config:  # noqa: E111
        raise ValueError(
          f"No feeding configuration found for dog {dog_id}",
        )

      feedings = self._feedings.get(dog_id, [])  # noqa: E111
      if not feedings:  # noqa: E111
        return FeedingComplianceNoData(
          status="no_data",
          message="No feeding history available",
        )

      # Get recent feedings  # noqa: E114
      since = dt_util.now() - timedelta(days=days_to_check)  # noqa: E111
      recent_feedings = [  # noqa: E111
        event for event in feedings if event.time > since and not event.skipped
      ]

      if not recent_feedings:  # noqa: E111
        return FeedingComplianceNoData(
          status="no_recent_data",
          message=f"No feeding data in last {days_to_check} days",
        )

      # Analyze compliance  # noqa: E114
      compliance_issues: list[ComplianceIssue] = []  # noqa: E111
      daily_accumulators: dict[str, _DailyComplianceAccumulator] = {}  # noqa: E111
      missed_meals: list[MissedMealEntry] = []  # noqa: E111

      # Group feedings by date  # noqa: E114
      for event in recent_feedings:  # noqa: E111
        date_str = event.time.date().isoformat()
        accumulator = daily_accumulators.get(date_str)
        if accumulator is None:
          accumulator = _DailyComplianceAccumulator(date=date_str)  # noqa: E111
          daily_accumulators[date_str] = accumulator  # noqa: E111

        accumulator.feedings.append(event)
        accumulator.total_amount += event.amount
        if event.meal_type:
          accumulator.meal_types.add(event.meal_type.value)  # noqa: E111
        if event.scheduled:
          accumulator.scheduled_feedings += 1  # noqa: E111

      # Check each day for compliance issues  # noqa: E114
      expected_daily_amount = config.daily_food_amount  # noqa: E111
      expected_meals_per_day = config.meals_per_day  # noqa: E111
      tolerance_percent = config.portion_tolerance  # noqa: E111

      for date_str, accumulator in daily_accumulators.items():  # noqa: E111
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
          if accumulator.total_amount < expected_daily_amount:  # noqa: E111
            day_issues.append(
              f"Underfed by {amount_deviation:.1f}% ({accumulator.total_amount:.0f}g vs {expected_daily_amount:.0f}g)",  # noqa: E501
            )
          else:  # noqa: E111
            day_issues.append(
              f"Overfed by {amount_deviation:.1f}% ({accumulator.total_amount:.0f}g vs {expected_daily_amount:.0f}g)",  # noqa: E501
            )

        # Check meal frequency
        actual_meals = len(accumulator.feedings)
        if actual_meals < expected_meals_per_day:
          day_issues.append(  # noqa: E111
            f"Too few meals: {actual_meals} vs expected {expected_meals_per_day}",
          )
          missed_meals.append(  # noqa: E111
            MissedMealEntry(
              date=date_str,
              expected=expected_meals_per_day,
              actual=actual_meals,
            ),
          )
        elif actual_meals > expected_meals_per_day + 2:  # Allow some flexibility
          day_issues.append(  # noqa: E111
            f"Too many meals: {actual_meals} vs expected {expected_meals_per_day}",
          )

        # Check schedule adherence if strict scheduling
        if config.schedule_type == FeedingScheduleType.STRICT:
          expected_scheduled = len(  # noqa: E111
            [s for s in config.get_active_schedules() if s.is_due_today()],
          )
          if accumulator.scheduled_feedings < expected_scheduled:  # noqa: E111
            day_issues.append(
              f"Missed scheduled feedings: {accumulator.scheduled_feedings} vs {expected_scheduled}",  # noqa: E501
            )

        if day_issues:
          severity = (  # noqa: E111
            "high"
            if any("Overfed" in issue or "Underfed" in issue for issue in day_issues)
            else "medium"
          )
          compliance_issues.append(  # noqa: E111
            ComplianceIssue(
              date=date_str,
              issues=day_issues,
              severity=severity,
            ),
          )

      # Calculate overall compliance score  # noqa: E114
      total_days = len(daily_accumulators)  # noqa: E111
      days_with_issues = len(compliance_issues)  # noqa: E111
      expected_feedings = expected_meals_per_day * total_days  # noqa: E111
      actual_feedings = sum(len(acc.feedings) for acc in daily_accumulators.values())  # noqa: E111
      if expected_feedings > 0:  # noqa: E111
        compliance_rate = round(
          (actual_feedings / expected_feedings) * 100,
          1,
        )
      else:  # noqa: E111
        compliance_rate = 100.0

      compliance_score = int(min(100, max(0, compliance_rate)))  # noqa: E111

      # Generate recommendations  # noqa: E114
      recommendations: list[str] = []  # noqa: E111
      if compliance_score < 80:  # noqa: E111
        recommendations.append("Consider setting up feeding reminders")
        recommendations.append("Review portion sizes and meal timing")
      if any(  # noqa: E111
        "Overfed" in entry or "Underfed" in entry
        for issue in compliance_issues
        for entry in issue["issues"]
      ):
        recommendations.append(
          "Reduce portion sizes to prevent weight gain",
        )
      if any(  # noqa: E111
        "schedule" in entry.lower()
        for issue in compliance_issues
        for entry in issue["issues"]
      ):
        recommendations.append(
          "Enable automatic reminders for scheduled meals",
        )

      daily_analysis_payload: dict[str, DailyComplianceTelemetry] = {  # noqa: E111
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

      average_daily_amount = (  # noqa: E111
        sum(acc.total_amount for acc in daily_accumulators.values()) / total_days
        if total_days > 0
        else 0.0
      )
      average_meals_per_day = (  # noqa: E111
        sum(len(acc.feedings) for acc in daily_accumulators.values()) / total_days
        if total_days > 0
        else 0.0
      )

      result: FeedingComplianceCompleted = {  # noqa: E111
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

      _LOGGER.info(  # noqa: E111
        "Feeding compliance check for %s: %d%% compliant over %d days",
        dog_id,
        compliance_score,
        total_days,
      )

      return result  # noqa: E111

  async def async_adjust_daily_portions(  # noqa: E111
    self,
    dog_id: str,
    adjustment_percent: int,
    reason: str | None = None,
    temporary: bool = False,
    duration_days: int | None = None,
  ) -> FeedingPortionAdjustmentResult:
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
      config = self._configs.get(dog_id)  # noqa: E111
      if not config:  # noqa: E111
        raise ValueError(
          f"No feeding configuration found for dog {dog_id}",
        )

      # Validate adjustment range  # noqa: E114
      if not -50 <= adjustment_percent <= 50:  # noqa: E111
        raise ValueError(
          "Adjustment percent must be between -50 and +50",
        )

      # Store original amount for temporary adjustments  # noqa: E114
      original_amount = config.daily_food_amount  # noqa: E111

      # Calculate new amount  # noqa: E114
      adjustment_factor = 1.0 + (adjustment_percent / 100.0)  # noqa: E111
      new_amount = round(original_amount * adjustment_factor, 1)  # noqa: E111

      # Safety check - don't allow extremely small portions  # noqa: E114
      if new_amount < 50.0:  # Minimum 50g per day  # noqa: E111
        raise ValueError(
          "Adjustment would result in dangerously low portions",
        )

      # Update daily amount  # noqa: E114
      config.daily_food_amount = new_amount  # noqa: E111

      # Update meal schedules proportionally  # noqa: E114
      updated_schedules = 0  # noqa: E111
      for schedule in config.meal_schedules:  # noqa: E111
        old_portion = schedule.portion_size
        schedule.portion_size = round(
          old_portion * adjustment_factor,
          1,
        )
        updated_schedules += 1

      # Invalidate caches  # noqa: E114
      self._invalidate_cache(dog_id)  # noqa: E111

      result = FeedingPortionAdjustmentResult(  # noqa: E111
        status="adjusted",
        dog_id=dog_id,
        adjustment_percent=adjustment_percent,
        original_daily_amount=original_amount,
        new_daily_amount=new_amount,
        absolute_change_g=round(new_amount - original_amount, 1),
        updated_schedules=updated_schedules,
        reason=reason,
        temporary=temporary,
        duration_days=duration_days,
        adjusted_at=dt_util.now().isoformat(),
      )

      _LOGGER.info(  # noqa: E111
        "Adjusted daily portions for %s by %+d%% (%.0fg -> %.0fg) - %s",
        dog_id,
        adjustment_percent,
        original_amount,
        new_amount,
        reason or "no reason given",
      )

      # Schedule reversion if temporary  # noqa: E114
      if temporary and duration_days:  # noqa: E111
        if existing_task := self._portion_reversion_tasks.pop(dog_id, None):
          existing_task.cancel()  # noqa: E111

        async def _revert_adjustment() -> None:
          try:  # noqa: E111
            await asyncio.sleep(duration_days * 24 * 3600)
            try:
              # Restore original amount  # noqa: E114
              config.daily_food_amount = original_amount  # noqa: E111

              # Restore meal schedules  # noqa: E114
              revert_factor = 1.0 / adjustment_factor  # noqa: E111
              for schedule in config.meal_schedules:  # noqa: E111
                schedule.portion_size = round(
                  schedule.portion_size * revert_factor,
                  1,
                )

              self._invalidate_cache(dog_id)  # noqa: E111

              _LOGGER.info(  # noqa: E111
                "Reverted portion adjustment for %s back to %.0fg after %d days",
                dog_id,
                original_amount,
                duration_days,
              )
            except Exception as err:  # pragma: no cover - logging only
              _LOGGER.error(  # noqa: E111
                "Failed to revert portion adjustment for %s: %s",
                dog_id,
                err,
              )
          finally:  # noqa: E111
            self._portion_reversion_tasks.pop(dog_id, None)

        revert_task = asyncio.create_task(_revert_adjustment())
        self._portion_reversion_tasks[dog_id] = revert_task
        result["reversion_scheduled"] = True
        result["reversion_date"] = (
          dt_util.now() + timedelta(days=duration_days)
        ).isoformat()

      return result  # noqa: E111

  async def async_add_health_snack(  # noqa: E111
    self,
    dog_id: str,
    snack_type: str,
    amount: float,
    health_benefit: str | None = None,
    notes: str | None = None,
  ) -> FeedingHealthSnackResult:
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
      config = self._configs.get(dog_id)  # noqa: E111
      if not config:  # noqa: E111
        raise ValueError(
          f"No feeding configuration found for dog {dog_id}",
        )

      # Validate amount  # noqa: E114
      if amount <= 0 or amount > 100:  # Reasonable limit for snacks  # noqa: E111
        raise ValueError(
          "Snack amount must be between 0 and 100 grams",
        )

      # Build enhanced notes with health benefit info  # noqa: E114
      enhanced_notes = notes or ""  # noqa: E111
      if health_benefit:  # noqa: E111
        benefit_descriptions = {
          "digestive": "Supports digestive health",
          "dental": "Promotes dental health",
          "joint": "Supports joint health",
          "skin_coat": "Improves skin and coat health",
          "immune": "Boosts immune system",
          "calming": "Natural calming properties",
        }
        benefit_desc = benefit_descriptions.get(
          health_benefit,
          f"Health benefit: {health_benefit}",
        )
        enhanced_notes = (
          f"{benefit_desc}. {enhanced_notes}" if enhanced_notes else benefit_desc
        )

      # Add as feeding event  # noqa: E114
      feeding_event = await self.async_add_feeding(  # noqa: E111
        dog_id=dog_id,
        amount=amount,
        meal_type="snack",  # Use snack meal type
        notes=enhanced_notes,
        scheduled=False,  # Health snacks are typically unscheduled
      )

      # Track health snack in daily stats (don't count towards meal requirements)  # noqa: E114, E501
      result = FeedingHealthSnackResult(  # noqa: E111
        status="added",
        dog_id=dog_id,
        snack_type=snack_type,
        amount=amount,
        health_benefit=health_benefit,
        feeding_event_id=feeding_event.time.isoformat(),
        notes=enhanced_notes,
        added_at=dt_util.now().isoformat(),
      )

      _LOGGER.info(  # noqa: E111
        "Added health snack for %s: %.1fg %s (%s)",
        dog_id,
        amount,
        snack_type,
        health_benefit or "general health",
      )

      return result  # noqa: E111

  async def async_shutdown(self) -> None:  # noqa: E111
    """Clean shutdown of feeding manager."""
    # Cancel all reminder tasks
    for task in self._reminder_tasks.values():
      task.cancel()  # noqa: E111

    if self._reminder_tasks:
      await asyncio.gather(*self._reminder_tasks.values(), return_exceptions=True)  # noqa: E111

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
