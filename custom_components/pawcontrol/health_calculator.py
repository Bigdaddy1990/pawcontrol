"""Health metrics utilities for PawControl.

Provides body condition scoring, calorie calculations and weight management
recommendations for dogs.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
import logging
import re
from typing import TYPE_CHECKING, ClassVar, Literal, TypedDict

from homeassistant.util import dt as dt_util

from .types import (
  DietValidationResult,
  FeedingGoalSettings,
  FeedingHistoryAnalysis,
  FeedingHistoryEvent,
  FeedingHistoryStatus,
  HealthReport,
  WeatherConditionsPayload,
)
from .utils import ensure_local_datetime

# TYPE_CHECKING import for weather integration
if TYPE_CHECKING:
  from .weather_manager import WeatherConditions, WeatherHealthManager  # noqa: E111

_LOGGER = logging.getLogger(__name__)


class BodyConditionScore(Enum):
  """Body condition score classification (1-9 scale)."""  # noqa: E111

  EMACIATED = 1  # Severely underweight  # noqa: E111
  VERY_THIN = 2  # Underweight  # noqa: E111
  THIN = 3  # Slightly underweight  # noqa: E111
  UNDERWEIGHT = 4  # Below ideal  # noqa: E111
  IDEAL = 5  # Perfect weight  # noqa: E111
  OVERWEIGHT = 6  # Slightly above ideal  # noqa: E111
  HEAVY = 7  # Overweight  # noqa: E111
  OBESE = 8  # Significantly overweight  # noqa: E111
  SEVERELY_OBESE = 9  # Severely obese  # noqa: E111


class LifeStage(Enum):
  """Life stage classification for nutritional needs."""  # noqa: E111

  PUPPY = "puppy"  # 0-12 months  # noqa: E111
  YOUNG_ADULT = "young_adult"  # 1-2 years  # noqa: E111
  ADULT = "adult"  # 2-7 years  # noqa: E111
  SENIOR = "senior"  # 7-10 years  # noqa: E111
  GERIATRIC = "geriatric"  # 10+ years  # noqa: E111


class ActivityLevel(Enum):
  """Activity level classification."""  # noqa: E111

  VERY_LOW = "very_low"  # Inactive, elderly, sick  # noqa: E111
  LOW = "low"  # Light exercise, indoor  # noqa: E111
  MODERATE = "moderate"  # Regular walks  # noqa: E111
  HIGH = "high"  # Active, long walks  # noqa: E111
  VERY_HIGH = "very_high"  # Working, athletic dogs  # noqa: E111


class DietSafetyResult(TypedDict):
  """Structured information about calculated portion safety."""  # noqa: E111

  safe: bool  # noqa: E111
  warnings: list[str]  # noqa: E111
  recommendations: list[str]  # noqa: E111
  portion_per_kg: float  # noqa: E111


class DietInteractionDetails(TypedDict):
  """Detailed description of how special diets interact."""  # noqa: E111

  synergistic: list[tuple[str, str]]  # noqa: E111
  neutral: list[tuple[str, str]]  # noqa: E111
  caution: list[tuple[str, str]]  # noqa: E111
  conflicting: list[tuple[str, str]]  # noqa: E111
  recommendations: list[str]  # noqa: E111
  overall_complexity: int  # noqa: E111
  risk_level: Literal["low", "medium", "high"]  # noqa: E111


class FeedingHistoryDaySummary(TypedDict):
  """Internal summary bucket for daily feeding analysis."""  # noqa: E111

  calories: float  # noqa: E111
  meals: int  # noqa: E111


@dataclass(init=False)
class HealthMetrics:
  """Comprehensive health metrics for a dog.

  Attributes:
      breed: Standardized breed name (for example, "Golden Retriever").
          The value must be a non-empty human readable breed description
          and is leveraged by weather specific advice to tailor
          recommendations.
  """  # noqa: E111

  # Basic measurements  # noqa: E114
  current_weight: float  # noqa: E111
  age_months: int | None = None  # noqa: E111
  breed: str | None = field(  # noqa: E111
    default=None,
    metadata={
      "doc": (
        "Standardized breed name (e.g., 'Golden Retriever'). Used "
        "by downstream weather guidance for breed-specific "
        "recommendations."
      ),
    },
  )
  height_cm: float | None = None  # noqa: E111
  ideal_weight: float | None = None  # noqa: E111

  # Health assessments  # noqa: E114
  body_condition_score: BodyConditionScore | None = None  # noqa: E111
  activity_level: ActivityLevel | None = None  # noqa: E111
  life_stage: LifeStage | None = None  # noqa: E111

  # Health conditions  # noqa: E114
  health_conditions: list[str] = field(default_factory=list)  # noqa: E111
  medications: list[str] = field(default_factory=list)  # noqa: E111
  special_diet: list[str] = field(default_factory=list)  # noqa: E111

  # Calculated values  # noqa: E114
  daily_calorie_requirement: float | None = None  # noqa: E111
  portion_adjustment_factor: float = 1.0  # noqa: E111
  weight_goal: str | None = None  # "maintain", "lose", "gain"  # noqa: E111

  # NEW: Weather-related adjustments  # noqa: E114
  weather_conditions: WeatherConditionsPayload | None = None  # noqa: E111
  weather_health_score: int | None = None  # noqa: E111

  _BREED_ALLOWED_CHARACTERS = frozenset(" -'")  # noqa: E111

  def __init__(  # noqa: E111
    self,
    current_weight: float,
    ideal_weight: float | None = None,
    height_cm: float | None = None,
    age_months: int | None = None,
    breed: str | None = None,
    body_condition_score: BodyConditionScore | None = None,
    activity_level: ActivityLevel | None = None,
    life_stage: LifeStage | None = None,
    health_conditions: Iterable[str] | None = None,
    medications: Iterable[str] | None = None,
    special_diet: Iterable[str] | None = None,
    daily_calorie_requirement: float | None = None,
    portion_adjustment_factor: float = 1.0,
    weight_goal: str | None = None,
    weather_conditions: WeatherConditionsPayload | None = None,
    weather_health_score: int | None = None,
  ) -> None:
    """Create a calculator pre-populated with the dog's baseline metrics."""
    self.current_weight = current_weight
    self.ideal_weight = ideal_weight
    self.height_cm = height_cm
    self.age_months = age_months
    self.breed = self._validate_breed(breed)
    self.body_condition_score = body_condition_score
    self.activity_level = activity_level
    self.life_stage = life_stage
    self.health_conditions = (
      list(health_conditions) if health_conditions is not None else []
    )
    self.medications = list(medications) if medications is not None else []
    self.special_diet = (
      list(
        special_diet,
      )
      if special_diet is not None
      else []
    )
    self.daily_calorie_requirement = daily_calorie_requirement
    self.portion_adjustment_factor = portion_adjustment_factor
    self.weight_goal = weight_goal
    self.weather_conditions = weather_conditions
    self.weather_health_score = weather_health_score

  @classmethod  # noqa: E111
  def _validate_breed(cls, breed: str | None) -> str | None:  # noqa: E111
    """Validate and normalize the provided breed string."""

    if breed is None:
      return None  # noqa: E111
    if not isinstance(breed, str):
      raise TypeError("breed must be provided as a string")  # noqa: E111

    normalized = breed.strip()
    if not normalized:
      raise ValueError("breed must not be empty when provided")  # noqa: E111

    if len(normalized) < 2:
      raise ValueError("breed must contain at least two characters")  # noqa: E111

    if not all(
      char.isalpha() or char in cls._BREED_ALLOWED_CHARACTERS for char in normalized
    ):
      raise ValueError(  # noqa: E111
        "breed may only contain letters, spaces, apostrophes, or hyphens",
      )

    # Collapse repeated internal whitespace to a single space for consistency.
    return re.sub(r"\s+", " ", normalized)


class HealthCalculator:
  """Enhanced health calculator for comprehensive dog health metrics."""  # noqa: E111

  # Calorie requirements per kg by life stage (kcal/kg/day)  # noqa: E114
  BASE_CALORIE_REQUIREMENTS: ClassVar[dict[LifeStage, int]] = {  # noqa: E111
    LifeStage.PUPPY: 130,  # Growing puppies need more calories
    LifeStage.YOUNG_ADULT: 110,  # Active young adults
    LifeStage.ADULT: 95,  # Standard adult maintenance
    LifeStage.SENIOR: 85,  # Slower metabolism
    LifeStage.GERIATRIC: 75,  # Reduced activity and metabolism
  }

  # Activity level multipliers  # noqa: E114
  ACTIVITY_MULTIPLIERS: ClassVar[dict[ActivityLevel, float]] = {  # noqa: E111
    ActivityLevel.VERY_LOW: 0.8,  # Sedentary, sick, or elderly
    ActivityLevel.LOW: 0.9,  # Light activity
    ActivityLevel.MODERATE: 1.0,  # Baseline
    ActivityLevel.HIGH: 1.3,  # Very active
    ActivityLevel.VERY_HIGH: 1.6,  # Working or athletic dogs
  }

  # Body condition score adjustments for portion size  # noqa: E114
  BCS_ADJUSTMENTS: ClassVar[dict[BodyConditionScore, float]] = {  # noqa: E111
    BodyConditionScore.EMACIATED: 1.5,  # Increase portions significantly
    BodyConditionScore.VERY_THIN: 1.3,  # Increase portions
    BodyConditionScore.THIN: 1.15,  # Slight increase
    BodyConditionScore.UNDERWEIGHT: 1.05,  # Minor increase
    BodyConditionScore.IDEAL: 1.0,  # Maintain current
    BodyConditionScore.OVERWEIGHT: 0.9,  # Slight reduction
    BodyConditionScore.HEAVY: 0.8,  # Reduce portions
    BodyConditionScore.OBESE: 0.7,  # Significant reduction
    BodyConditionScore.SEVERELY_OBESE: 0.6,  # Major reduction
  }

  # Health condition adjustments  # noqa: E114
  HEALTH_CONDITION_ADJUSTMENTS: ClassVar[dict[str, float]] = {  # noqa: E111
    "diabetes": 0.9,  # Controlled portions
    "kidney_disease": 0.85,  # Reduced protein/phosphorus
    "heart_disease": 0.85,  # Weight management critical
    "arthritis": 0.9,  # Weight management for joints
    "thyroid_disorder": 0.8,  # Often affects metabolism
    "allergies": 1.0,  # No portion change, diet change
    "digestive_issues": 0.95,  # Smaller, more frequent meals
    "dental_problems": 1.0,  # Texture change, not portion
    "cancer": 1.1,  # May need more calories
    "liver_disease": 0.9,  # Controlled nutrition
  }

  @staticmethod  # noqa: E111
  def calculate_life_stage(age_months: int, breed_size: str = "medium") -> LifeStage:  # noqa: E111
    """Calculate life stage based on age and breed size.

    Args:
        age_months: Age in months
        breed_size: Size category (toy, small, medium, large, giant)

    Returns:
        Life stage classification
    """
    if age_months < 0:
      raise ValueError(  # noqa: E111
        "age_months must be greater than or equal to zero",
      )

    # Adjust adult/senior thresholds based on breed size
    size_adjustments = {
      # 10 months to adult, 8 years to senior
      "toy": {"adult": 10, "senior": 96},
      # 1 year to adult, 7 years to senior
      "small": {"adult": 12, "senior": 84},
      "medium": {
        "adult": 15,
        "senior": 84,
      },  # 15 months to adult, 7 years to senior
      "large": {
        "adult": 18,
        "senior": 72,
      },  # 18 months to adult, 6 years to senior
      # 2 years to adult, 5 years to senior
      "giant": {"adult": 24, "senior": 60},
    }

    thresholds = size_adjustments.get(
      breed_size,
      size_adjustments["medium"],
    )

    if age_months < thresholds["adult"]:
      return LifeStage.PUPPY  # noqa: E111
    if age_months < 24:
      return LifeStage.YOUNG_ADULT  # noqa: E111
    if age_months < thresholds["senior"]:
      return LifeStage.ADULT  # noqa: E111
    if age_months < 120:  # 10 years
      return LifeStage.SENIOR  # noqa: E111
    return LifeStage.GERIATRIC

  @staticmethod  # noqa: E111
  def calculate_bmi(weight: float, height_cm: float) -> float:  # noqa: E111
    """Calculate body mass index for a dog.

    Args:
        weight: Weight in kilograms
        height_cm: Height in centimeters

    Returns:
        BMI value
    """
    if height_cm <= 0:
      return 0.0  # noqa: E111
    return weight / ((height_cm / 100) ** 2)

  @staticmethod  # noqa: E111
  def estimate_body_condition_score(  # noqa: E111
    current_weight: float,
    ideal_weight: float | None = None,
    visual_assessment: int | None = None,
  ) -> BodyConditionScore:
    """Estimate body condition score from weight and visual assessment.

    Args:
        current_weight: Current weight in kg
        ideal_weight: Ideal weight in kg (if known)
        visual_assessment: Manual BCS assessment (1-9)

    Returns:
        Body condition score
    """
    if visual_assessment is not None:
      # Use provided assessment if available  # noqa: E114
      return BodyConditionScore(min(9, max(1, visual_assessment)))  # noqa: E111

    if ideal_weight is None or ideal_weight <= 0:
      # Default to ideal if no ideal weight provided  # noqa: E114
      return BodyConditionScore.IDEAL  # noqa: E111

    # Calculate based on weight deviation
    weight_ratio = current_weight / ideal_weight

    if weight_ratio < 0.7:
      return BodyConditionScore.EMACIATED  # noqa: E111
    if weight_ratio < 0.8:
      return BodyConditionScore.VERY_THIN  # noqa: E111
    if weight_ratio < 0.9:
      return BodyConditionScore.THIN  # noqa: E111
    if weight_ratio < 0.95:
      return BodyConditionScore.UNDERWEIGHT  # noqa: E111
    if weight_ratio <= 1.05:
      return BodyConditionScore.IDEAL  # noqa: E111
    if weight_ratio <= 1.15:
      return BodyConditionScore.OVERWEIGHT  # noqa: E111
    if weight_ratio <= 1.25:
      return BodyConditionScore.HEAVY  # noqa: E111
    if weight_ratio <= 1.4:
      return BodyConditionScore.OBESE  # noqa: E111
    return BodyConditionScore.SEVERELY_OBESE

  @staticmethod  # noqa: E111
  def calculate_daily_calories(  # noqa: E111
    weight: float,
    life_stage: LifeStage,
    activity_level: ActivityLevel,
    body_condition_score: BodyConditionScore | None = None,
    health_conditions: list[str] | None = None,
    spayed_neutered: bool = True,
  ) -> float:
    """Calculate daily calorie requirements.

    Args:
        weight: Current weight in kg
        life_stage: Life stage classification
        activity_level: Activity level
        body_condition_score: Current body condition
        health_conditions: List of health conditions
        spayed_neutered: Whether dog is spayed/neutered

    Returns:
        Daily calorie requirement
    """
    # Base calculation: RER (Resting Energy Requirement)
    # RER = 70 * (weight in kg)^0.75
    rer = 70 * (weight**0.75)

    # Get base multiplier for life stage
    base_multiplier = (
      HealthCalculator.BASE_CALORIE_REQUIREMENTS.get(life_stage, 95) / 95
    )  # Normalize to adult baseline

    # Apply activity level multiplier
    activity_multiplier = HealthCalculator.ACTIVITY_MULTIPLIERS.get(
      activity_level,
      1.0,
    )

    # Calculate base daily calories
    daily_calories = rer * base_multiplier * activity_multiplier

    # Adjust for spayed/neutered (typically 10% reduction)
    if spayed_neutered and life_stage in [LifeStage.ADULT, LifeStage.SENIOR]:
      daily_calories *= 0.9  # noqa: E111

    return round(daily_calories, 1)

  @staticmethod  # noqa: E111
  def calculate_portion_adjustment_factor(  # noqa: E111
    health_metrics: HealthMetrics,
    feeding_goals: FeedingGoalSettings | None = None,
    diet_validation: DietValidationResult | None = None,
  ) -> float:
    """Calculate comprehensive portion adjustment factor with diet validation.

    Args:
        health_metrics: Complete health metrics
        feeding_goals: Specific feeding goals (weight loss, etc.)
        diet_validation: Diet combination validation results

    Returns:
        Portion adjustment factor (1.0 = normal)
    """
    adjustment_factor = 1.0

    # Apply body condition score adjustment
    if health_metrics.body_condition_score:
      bcs_adjustment = HealthCalculator.BCS_ADJUSTMENTS.get(  # noqa: E111
        health_metrics.body_condition_score,
        1.0,
      )
      adjustment_factor *= bcs_adjustment  # noqa: E111

    # Apply health condition adjustments
    for condition in health_metrics.health_conditions:
      condition_adjustment = HealthCalculator.HEALTH_CONDITION_ADJUSTMENTS.get(  # noqa: E111
        condition.lower(),
        1.0,
      )
      adjustment_factor *= condition_adjustment  # noqa: E111

    # Apply special diet considerations
    diet_adjustments = {
      "weight_control": 0.85,  # Weight management formula
      "senior_formula": 0.95,  # Often lower calorie
      "puppy_formula": 1.15,  # Higher calorie density
      "low_fat": 0.9,  # Reduced calorie density
      "prescription": 0.9,  # Often therapeutic portions
      "high_protein": 1.05,  # May need slight increase
      "diabetic": 0.85,  # Controlled portions critical
      "kidney_support": 0.9,  # Reduced protein portions
      "sensitive_stomach": 0.95,  # Smaller, more frequent meals
    }

    for diet_type in health_metrics.special_diet:
      diet_adjustment = diet_adjustments.get(diet_type.lower(), 1.0)  # noqa: E111
      adjustment_factor *= diet_adjustment  # noqa: E111

    # Apply diet validation adjustments for conflicts/warnings
    if diet_validation:
      validation_adjustment = HealthCalculator.calculate_diet_validation_adjustment(  # noqa: E111
        diet_validation,
        health_metrics.special_diet,
      )
      adjustment_factor *= validation_adjustment  # noqa: E111

    # Apply feeding goals
    if feeding_goals:
      weight_goal = feeding_goals.get("weight_goal")  # noqa: E111
      if weight_goal == "lose":  # noqa: E111
        if health_metrics.life_stage == LifeStage.PUPPY:
          adjustment_factor *= 0.9  # gentler reduction for growth  # noqa: E111
        else:
          adjustment_factor *= 0.8  # 20% reduction for weight loss  # noqa: E111
      elif weight_goal == "gain":  # noqa: E111
        adjustment_factor *= 1.2  # 20% increase for weight gain

      # Time-based adjustments  # noqa: E114
      weight_loss_rate = feeding_goals.get(  # noqa: E111
        "weight_loss_rate",
        "moderate",
      )
      if weight_loss_rate == "aggressive" and weight_goal == "lose":  # noqa: E111
        adjustment_factor *= 0.9  # Additional 10% reduction
      elif weight_loss_rate == "gradual" and weight_goal == "lose":  # noqa: E111
        adjustment_factor *= 1.1  # Less aggressive reduction

    # Ensure reasonable bounds
    adjustment_factor = max(0.5, min(2.0, adjustment_factor))

    if health_metrics.life_stage == LifeStage.PUPPY:
      adjustment_factor = max(adjustment_factor, 0.85)  # noqa: E111

    return round(adjustment_factor, 2)

  @staticmethod  # noqa: E111
  def calculate_diet_validation_adjustment(  # noqa: E111
    diet_validation: DietValidationResult,
    special_diets: list[str],
  ) -> float:
    """Calculate portion adjustment based on diet validation results.

    This method applies conservative adjustments when diet conflicts
    or warnings are detected to ensure safe feeding practices.

    Args:
        diet_validation: Validation results from config flow
        special_diets: List of special diet requirements

    Returns:
        Adjustment factor for portion calculation (0.8-1.1)
    """
    adjustment = 1.0

    # Handle conflicts (more conservative adjustments)
    for conflict in diet_validation["conflicts"]:
      conflict_type = conflict["type"]  # noqa: E111

      if conflict_type == "age_conflict":  # noqa: E111
        # Age conflicts require veterinary guidance - use conservative portions
        adjustment *= 0.9
        _LOGGER.warning(
          "Age-based diet conflict detected: applying conservative 10%% portion reduction",  # noqa: E501
        )

    # Handle warnings (milder adjustments)
    for warning in diet_validation["warnings"]:
      warning_type = warning["type"]  # noqa: E111

      if warning_type == "multiple_prescription_warning":  # noqa: E111
        # Multiple prescription diets need careful portion control
        adjustment *= 0.95
        _LOGGER.info(
          "Multiple prescription diets: applying 5%% portion reduction for safety",
        )

      elif warning_type == "raw_medical_warning":  # noqa: E111
        # Raw diet with medical conditions - slightly conservative
        adjustment *= 0.95
        _LOGGER.info(
          "Raw diet with medical conditions: applying 5%% portion reduction",
        )

      elif warning_type == "weight_puppy_warning":  # noqa: E111
        # Weight control for puppies - less restrictive than adults
        adjustment *= 1.05  # Actually increase slightly for growing puppy
        _LOGGER.info(
          "Weight control for puppy: applying 5%% portion increase for growth",
        )

      elif warning_type == "hypoallergenic_warning":  # noqa: E111
        # Hypoallergenic with other diets - standard portions but monitor
        adjustment *= 0.98  # Very minor reduction for safety
        _LOGGER.info(
          "Hypoallergenic diet combination: minor portion adjustment for monitoring",
        )

      elif warning_type == "low_fat_activity_warning":  # noqa: E111
        # Low fat with joint support - may need calorie compensation
        adjustment *= 1.05  # Slight increase to compensate for low fat
        _LOGGER.info(
          "Low fat diet with joint support needs: applying 5%% portion increase",
        )

    # Additional adjustments based on total diet complexity
    total_diets = diet_validation["total_diets"]
    if total_diets >= 4:
      # Complex diet combinations need careful monitoring  # noqa: E114
      adjustment *= 0.97  # 3% reduction for very complex diets  # noqa: E111
      _LOGGER.info(  # noqa: E111
        "Complex diet combination (%d diets): applying 3%% portion reduction for safety",  # noqa: E501
        total_diets,
      )

    # Veterinary consultation recommendation adjustment
    if diet_validation["recommended_vet_consultation"]:
      # When vet consultation is recommended, use more conservative portions  # noqa: E114, E501
      adjustment *= 0.95  # noqa: E111
      _LOGGER.info(  # noqa: E111
        "Veterinary consultation recommended: applying 5%% conservative portion adjustment",  # noqa: E501
      )

    # Ensure reasonable bounds (more conservative than general adjustments)
    adjustment = max(0.8, min(1.1, adjustment))

    # Log the final adjustment if it's not neutral
    if adjustment != 1.0:
      _LOGGER.info(  # noqa: E111
        "Diet validation adjustment applied: %.2fx (%.0f%% of base portion)",
        adjustment,
        adjustment * 100,
      )

    return round(adjustment, 3)

  @staticmethod  # noqa: E111
  def validate_portion_safety(  # noqa: E111
    calculated_portion: float,
    dog_weight: float,
    life_stage: LifeStage,
    special_diets: list[str],
    diet_validation: DietValidationResult | None = None,
  ) -> DietSafetyResult:
    """Validate calculated portion for safety concerns.

    Args:
        calculated_portion: Calculated portion size in grams
        dog_weight: Dog weight in kg
        life_stage: Life stage of the dog
        special_diets: List of special diet requirements
        diet_validation: Optional diet validation results

    Returns:
        Dictionary with safety validation results
    """
    safety_result: DietSafetyResult = {
      "safe": True,
      "warnings": [],
      "recommendations": [],
      "portion_per_kg": round(calculated_portion / dog_weight, 1)
      if dog_weight > 0
      else 0.0,
    }

    # Check portion size relative to body weight
    if dog_weight > 0:
      portion_per_kg = calculated_portion / dog_weight  # noqa: E111

      # General safety thresholds (grams per kg body weight per meal)  # noqa: E114
      if life_stage == LifeStage.PUPPY:  # noqa: E111
        min_threshold, max_threshold = 15, 80  # Puppies need more food
      elif life_stage in [LifeStage.SENIOR, LifeStage.GERIATRIC]:  # noqa: E111
        min_threshold, max_threshold = 7, 40  # Seniors typically less
      else:  # noqa: E111
        min_threshold, max_threshold = 10, 50  # Adult dogs

      if portion_per_kg < min_threshold:  # noqa: E111
        safety_result["warnings"].append(
          f"Portion may be too small: {portion_per_kg:.1f}g/kg (minimum: {min_threshold}g/kg)",  # noqa: E501
        )
        safety_result["recommendations"].append(
          "Consider increasing portion size or adding additional meals",
        )

      elif portion_per_kg > max_threshold:  # noqa: E111
        safety_result["warnings"].append(
          f"Portion may be too large: {portion_per_kg:.1f}g/kg (maximum: {max_threshold}g/kg)",  # noqa: E501
        )
        safety_result["recommendations"].append(
          "Consider reducing portion size or splitting into smaller meals",
        )
        safety_result["safe"] = False

    # Special diet safety checks
    high_risk_diets = ["prescription", "diabetic", "kidney_support"]
    if any(diet in special_diets for diet in high_risk_diets):
      safety_result["recommendations"].append(  # noqa: E111
        "Prescription diet detected - verify portions with veterinarian",
      )

    # Diet validation safety checks
    if diet_validation:
      if diet_validation["conflicts"]:  # noqa: E111
        safety_result["warnings"].append(
          "Diet conflicts detected - extra monitoring recommended",
        )
        safety_result["safe"] = False

      if diet_validation["recommended_vet_consultation"]:  # noqa: E111
        safety_result["recommendations"].append(
          "Veterinary consultation recommended due to diet complexity",
        )

    return safety_result

  @staticmethod  # noqa: E111
  def get_diet_interaction_effects(  # noqa: E111
    special_diets: list[str],
  ) -> DietInteractionDetails:
    """Analyze potential interactions between special diets.

    Args:
        special_diets: List of special diet requirements

    Returns:
        Dictionary with interaction analysis
    """
    interactions: DietInteractionDetails = {
      "synergistic": [],  # Diets that work well together
      "neutral": [],  # Diets with no significant interaction
      "caution": [],  # Combinations requiring monitoring
      "conflicting": [],  # Combinations that may conflict
      "recommendations": [],
      "overall_complexity": 0,
      "risk_level": "low",
    }

    # Define interaction matrix
    synergistic_pairs = [
      ("senior_formula", "joint_support"),
      ("senior_formula", "low_fat"),
      ("weight_control", "low_fat"),
      ("dental_care", "senior_formula"),
      ("hypoallergenic", "sensitive_stomach"),
      ("grain_free", "hypoallergenic"),
    ]

    caution_pairs = [
      ("raw_diet", "prescription"),
      ("raw_diet", "kidney_support"),
      ("raw_diet", "diabetic"),
      ("organic", "prescription"),
      ("weight_control", "puppy_formula"),
    ]

    conflicting_pairs = [
      ("puppy_formula", "senior_formula"),
      ("low_fat", "puppy_formula"),  # Puppies need fat for development
    ]

    # Check for interactions
    diet_set = set(special_diets)

    for diet1, diet2 in synergistic_pairs:
      if diet1 in diet_set and diet2 in diet_set:  # noqa: E111
        interactions["synergistic"].append((diet1, diet2))

    for diet1, diet2 in caution_pairs:
      if diet1 in diet_set and diet2 in diet_set:  # noqa: E111
        interactions["caution"].append((diet1, diet2))

    for diet1, diet2 in conflicting_pairs:
      if diet1 in diet_set and diet2 in diet_set:  # noqa: E111
        interactions["conflicting"].append((diet1, diet2))

    # Add recommendations based on interactions
    recommendations: list[str] = []

    if interactions["synergistic"]:
      recommendations.append(  # noqa: E111
        f"Good diet combinations detected: {len(interactions['synergistic'])} synergistic pairs",  # noqa: E501
      )

    if interactions["caution"]:
      recommendations.append(  # noqa: E111
        f"Monitor carefully: {len(interactions['caution'])} combinations need attention",  # noqa: E501
      )

    if interactions["conflicting"]:
      recommendations.append(  # noqa: E111
        f"Conflicting diets detected: {len(interactions['conflicting'])} pairs need resolution",  # noqa: E501
      )

    interactions["recommendations"] = recommendations
    interactions["overall_complexity"] = len(special_diets)
    interactions["risk_level"] = (
      "high"
      if interactions["conflicting"]
      else "medium"
      if interactions["caution"]
      else "low"
    )

    return interactions

  @staticmethod  # noqa: E111
  def analyze_feeding_history(  # noqa: E111
    feeding_events: list[FeedingHistoryEvent],
    target_calories: float,
    food_calories_per_gram: float = 3.5,
  ) -> FeedingHistoryAnalysis:
    """Analyze feeding history for patterns and recommendations.

    Args:
        feeding_events: List of feeding events
        target_calories: Target daily calories
        food_calories_per_gram: Calories per gram of food

    Returns:
        Analysis results with recommendations
    """
    if not feeding_events:
      return FeedingHistoryAnalysis(  # noqa: E111
        status="no_data",
        recommendation="Start tracking feedings to analyze patterns",
      )

    # Calculate daily averages over last 7 days
    recent_days: dict[date, FeedingHistoryDaySummary] = {}
    now = dt_util.now()
    week_ago = now - timedelta(days=7)

    midpoint_adjustment = timedelta(hours=12)

    for event in feeding_events:
      event_time = ensure_local_datetime(event.get("time"))  # noqa: E111
      if event_time is None or event_time <= week_ago:  # noqa: E111
        continue

      delta = now - event_time  # noqa: E111
      if delta < timedelta(0):  # noqa: E111
        day_index = 0
      else:  # noqa: E111
        day_index = int(
          (delta + midpoint_adjustment).total_seconds() // 86400,
        )

      bucket_date = (now - timedelta(days=day_index)).date()  # noqa: E111
      if bucket_date not in recent_days:  # noqa: E111
        recent_days[bucket_date] = FeedingHistoryDaySummary(
          calories=0.0,
          meals=0,
        )

      amount = float(event.get("amount", 0))  # noqa: E111
      calories = amount * food_calories_per_gram  # noqa: E111
      day_summary = recent_days[bucket_date]  # noqa: E111
      day_summary["calories"] += calories  # noqa: E111
      day_summary["meals"] += 1  # noqa: E111

    if not recent_days:
      return FeedingHistoryAnalysis(  # noqa: E111
        status="insufficient_data",
        recommendation="Need at least one week of feeding data",
      )

    # Calculate averages
    avg_daily_calories = sum(day["calories"] for day in recent_days.values()) / len(
      recent_days,
    )
    avg_daily_meals = sum(day["meals"] for day in recent_days.values()) / len(
      recent_days,
    )

    # Calculate variance from target
    calorie_variance = (avg_daily_calories - target_calories) / target_calories * 100

    # Generate recommendations
    recommendations: list[str] = []
    status: FeedingHistoryStatus = "good"

    if calorie_variance > 20:
      status = "overfeeding"  # noqa: E111
      recommendations.append("Consider reducing portion sizes by 15-20%")  # noqa: E111
      recommendations.append("Increase exercise if possible")  # noqa: E111
    elif calorie_variance > 10:
      status = "slight_overfeeding"  # noqa: E111
      recommendations.append("Slightly reduce portion sizes by 5-10%")  # noqa: E111
    elif calorie_variance < -20:
      status = "underfeeding"  # noqa: E111
      recommendations.append("Increase portion sizes by 15-20%")  # noqa: E111
      recommendations.append("Consider more nutrient-dense food")  # noqa: E111
    elif calorie_variance < -10:
      status = "slight_underfeeding"  # noqa: E111
      recommendations.append("Slightly increase portion sizes by 5-10%")  # noqa: E111
    else:
      recommendations.append(  # noqa: E111
        "Feeding is well balanced, maintain current portions",
      )

    # Meal frequency recommendations
    if avg_daily_meals < 1.5:
      recommendations.append(  # noqa: E111
        "Consider splitting daily food into 2+ meals",
      )
    elif avg_daily_meals > 4:
      recommendations.append(  # noqa: E111
        "Consider consolidating into 2-3 larger meals",
      )

    return FeedingHistoryAnalysis(
      status=status,
      avg_daily_calories=round(avg_daily_calories, 1),
      target_calories=target_calories,
      calorie_variance_percent=round(calorie_variance, 1),
      avg_daily_meals=round(avg_daily_meals, 1),
      recommendations=recommendations,
      analysis_period_days=len(recent_days),
    )

  @staticmethod  # noqa: E111
  def calculate_ideal_weight_range(  # noqa: E111
    breed: str | None = None,
    height_cm: float | None = None,
    current_weight: float = 0,
    age_months: int | None = None,
  ) -> tuple[float, float]:
    """Calculate ideal weight range for a dog.

    Args:
        breed: Dog breed (if known)
        height_cm: Height in centimeters
        current_weight: Current weight in kg
        age_months: Age in months

    Returns:
        Tuple of (min_ideal_weight, max_ideal_weight)
    """
    # Breed-specific weight ranges (kg)
    breed_weights = {
      "chihuahua": (1.5, 3.0),
      "yorkshire_terrier": (2.0, 3.5),
      "beagle": (9.0, 11.0),
      "cocker_spaniel": (12.0, 16.0),
      "border_collie": (14.0, 20.0),
      "labrador": (25.0, 32.0),
      "golden_retriever": (25.0, 34.0),
      "german_shepherd": (22.0, 40.0),
      "great_dane": (50.0, 90.0),
      "saint_bernard": (64.0, 82.0),
    }

    if breed and breed.lower().replace(" ", "_") in breed_weights:
      return breed_weights[breed.lower().replace(" ", "_")]  # noqa: E111

    # Height-based estimation if available
    if height_cm and height_cm > 0:
      # Rough estimation: weight = height^2 * breed_factor  # noqa: E114
      # Breed factor varies by build type  # noqa: E114
      if height_cm < 25:  # Small dogs  # noqa: E111
        min_weight = (height_cm**1.8) * 0.002
        max_weight = (height_cm**1.8) * 0.003
      elif height_cm < 45:  # Medium dogs  # noqa: E111
        min_weight = (height_cm**1.8) * 0.0025
        max_weight = (height_cm**1.8) * 0.0035
      else:  # Large dogs  # noqa: E111
        min_weight = (height_cm**1.8) * 0.003
        max_weight = (height_cm**1.8) * 0.004

      return (round(min_weight, 1), round(max_weight, 1))  # noqa: E111

    # Fallback: assume current weight is close to ideal
    if current_weight > 0:
      min_weight = current_weight * 0.9  # noqa: E111
      max_weight = current_weight * 1.1  # noqa: E111
      return (round(min_weight, 1), round(max_weight, 1))  # noqa: E111

    # Default ranges by estimated size
    return (10.0, 30.0)  # Default medium dog range

  @staticmethod  # noqa: E111
  def generate_health_report(  # noqa: E111
    health_metrics: HealthMetrics,
    weather_conditions: WeatherConditions | None = None,
    weather_health_manager: WeatherHealthManager | None = None,
  ) -> HealthReport:
    """Generate a detailed health report with recommendations."""
    report: HealthReport = HealthReport(
      timestamp=dt_util.now().isoformat(),
      overall_status="good",
      recommendations=[],
      health_score=85,
      areas_of_concern=[],
      positive_indicators=[],
    )

    HealthCalculator._assess_weight(health_metrics, report)
    HealthCalculator._assess_body_condition(health_metrics, report)
    HealthCalculator._assess_health_conditions(health_metrics, report)
    HealthCalculator._assess_age(health_metrics, report)
    HealthCalculator._assess_activity(health_metrics, report)

    # NEW: Weather-based health assessment
    if weather_conditions and weather_health_manager:
      HealthCalculator._assess_weather_impact(  # noqa: E111
        health_metrics,
        weather_conditions,
        weather_health_manager,
        report,
      )

    HealthCalculator._finalize_status(report)

    return report

  @staticmethod  # noqa: E111
  def _assess_weight(health_metrics: HealthMetrics, report: HealthReport) -> None:  # noqa: E111
    if health_metrics.ideal_weight and health_metrics.current_weight:
      weight_ratio = health_metrics.current_weight / health_metrics.ideal_weight  # noqa: E111
      if weight_ratio < 0.85:  # noqa: E111
        report["areas_of_concern"].append("underweight")
        report["recommendations"].append(
          "Consult vet about weight gain plan",
        )
        report["health_score"] -= 15
      elif weight_ratio > 1.2:  # noqa: E111
        report["areas_of_concern"].append("overweight")
        report["recommendations"].append(
          "Implement weight management plan",
        )
        report["health_score"] -= 10
      else:  # noqa: E111
        report["positive_indicators"].append("healthy_weight")

  @staticmethod  # noqa: E111
  def _assess_body_condition(  # noqa: E111
    health_metrics: HealthMetrics,
    report: HealthReport,
  ) -> None:
    if not health_metrics.body_condition_score:
      return  # noqa: E111

    bcs = health_metrics.body_condition_score
    if bcs in [BodyConditionScore.EMACIATED, BodyConditionScore.VERY_THIN]:
      report["overall_status"] = "concerning"  # noqa: E111
      report["areas_of_concern"].append("severe_underweight")  # noqa: E111
      report["recommendations"].append(  # noqa: E111
        "Immediate veterinary consultation needed",
      )
      report["health_score"] -= 25  # noqa: E111
    elif bcs in [BodyConditionScore.OBESE, BodyConditionScore.SEVERELY_OBESE]:
      report["overall_status"] = "needs_attention"  # noqa: E111
      report["areas_of_concern"].append("obesity")  # noqa: E111
      report["recommendations"].append(  # noqa: E111
        "Urgent weight management required",
      )
      report["health_score"] -= 20  # noqa: E111
    elif bcs == BodyConditionScore.IDEAL:
      report["positive_indicators"].append("ideal_body_condition")  # noqa: E111

  @staticmethod  # noqa: E111
  def _assess_health_conditions(  # noqa: E111
    health_metrics: HealthMetrics,
    report: HealthReport,
  ) -> None:
    serious_conditions = {
      "diabetes",
      "heart_disease",
      "kidney_disease",
      "liver_disease",
      "cancer",
    }
    for condition in health_metrics.health_conditions:
      if condition.lower() in serious_conditions:  # noqa: E111
        report["overall_status"] = "managing_condition"
        report["areas_of_concern"].append(f"chronic_{condition}")
        report["recommendations"].append(
          f"Continue monitoring {condition} as prescribed",
        )
        report["health_score"] -= 15

  @staticmethod  # noqa: E111
  def _assess_age(health_metrics: HealthMetrics, report: HealthReport) -> None:  # noqa: E111
    if not health_metrics.age_months:
      return  # noqa: E111
    age_years = health_metrics.age_months / 12
    if age_years < 1:
      report["recommendations"].append(  # noqa: E111
        "Ensure puppy vaccination schedule is complete",
      )
      report["recommendations"].append(  # noqa: E111
        "Monitor growth rate and adjust portions accordingly",
      )
    elif age_years > 7:
      report["recommendations"].append(  # noqa: E111
        "Consider senior health screening",
      )
      report["recommendations"].append(  # noqa: E111
        "Monitor for age-related conditions",
      )

  @staticmethod  # noqa: E111
  def _assess_activity(health_metrics: HealthMetrics, report: HealthReport) -> None:  # noqa: E111
    if health_metrics.activity_level == ActivityLevel.VERY_LOW:
      report["recommendations"].append(  # noqa: E111
        "Gradually increase physical activity if health permits",
      )
    elif health_metrics.activity_level == ActivityLevel.VERY_HIGH:
      report["positive_indicators"].append("excellent_activity_level")  # noqa: E111

  @staticmethod  # noqa: E111
  def _finalize_status(report: HealthReport) -> None:  # noqa: E111
    score = report["health_score"]
    if score >= 90:
      report["overall_status"] = "excellent"  # noqa: E111
    elif score >= 75:
      report["overall_status"] = "good"  # noqa: E111
    elif score >= 60:
      report["overall_status"] = "needs_attention"  # noqa: E111
    else:
      report["overall_status"] = "concerning"  # noqa: E111

  @staticmethod  # noqa: E111
  def _assess_weather_impact(  # noqa: E111
    health_metrics: HealthMetrics,
    weather_conditions: WeatherConditions,
    weather_health_manager: WeatherHealthManager,
    report: HealthReport,
  ) -> None:
    """Assess weather impact on dog health and update report.

    Args:
        health_metrics: Dog health metrics
        weather_conditions: Current weather conditions
        weather_health_manager: Weather health manager instance
        report: Health report to update
    """
    # Get weather health score
    weather_score = weather_health_manager.get_weather_health_score()

    # Get active weather alerts
    active_alerts = weather_health_manager.get_active_alerts()

    # Assess overall weather impact
    if weather_score < 30:
      report["areas_of_concern"].append("dangerous_weather_conditions")  # noqa: E111
      report["health_score"] -= 25  # noqa: E111
      report["recommendations"].append(  # noqa: E111
        "Dangerous weather conditions - avoid outdoor activities",
      )
    elif weather_score < 50:
      report["areas_of_concern"].append("poor_weather_conditions")  # noqa: E111
      report["health_score"] -= 15  # noqa: E111
      report["recommendations"].append(  # noqa: E111
        "Poor weather conditions - limit outdoor exposure",
      )
    elif weather_score < 70:
      report["recommendations"].append(  # noqa: E111
        "Moderate weather concerns - take basic precautions",
      )
      report["health_score"] -= 5  # noqa: E111
    else:
      report["positive_indicators"].append(  # noqa: E111
        "favorable_weather_conditions",
      )

    # Add weather-specific recommendations
    if health_metrics.breed:
      weather_recommendations = weather_health_manager.get_recommendations_for_dog(  # noqa: E111
        dog_breed=health_metrics.breed,
        dog_age_months=health_metrics.age_months,
        health_conditions=health_metrics.health_conditions,
      )
      report["recommendations"].extend(  # noqa: E111
        weather_recommendations[:3],
      )  # Limit to 3 most important

    # Add alert-specific concerns
    for alert in active_alerts:
      if alert.severity.value in ["high", "extreme"]:  # noqa: E111
        report["areas_of_concern"].append(
          f"weather_{alert.alert_type.value}",
        )

    # Temperature-specific assessments for health conditions
    if weather_conditions.temperature_c is not None:
      temp = weather_conditions.temperature_c  # noqa: E111

      # Heat concerns for specific health conditions  # noqa: E114
      if temp > 25 and "heart_disease" in health_metrics.health_conditions:  # noqa: E111
        report["recommendations"].append(
          "Heart condition + hot weather: Avoid strenuous activity",
        )
        report["health_score"] -= 10

      # Cold concerns for arthritis  # noqa: E114
      if temp < 10 and "arthritis" in health_metrics.health_conditions:  # noqa: E111
        report["recommendations"].append(
          "Arthritis + cold weather: Ensure warm environment",
        )
        report["health_score"] -= 5

      # Respiratory concerns with humidity  # noqa: E114
      if (  # noqa: E111
        weather_conditions.humidity_percent
        and weather_conditions.humidity_percent > 80
        and any(
          condition in health_metrics.health_conditions
          for condition in ["respiratory", "breathing", "asthma"]
        )
      ):
        report["recommendations"].append(
          "Respiratory condition + high humidity: Monitor breathing closely",
        )
        report["health_score"] -= 10

  @staticmethod  # noqa: E111
  def calculate_weather_adjusted_activity_level(  # noqa: E111
    base_activity_level: ActivityLevel,
    weather_conditions: WeatherConditions | None = None,
    dog_breed: str | None = None,
    health_conditions: list[str] | None = None,
  ) -> ActivityLevel:
    """Calculate weather-adjusted activity level for more accurate calorie calculation.

    Args:
        base_activity_level: Base activity level without weather consideration
        weather_conditions: Current weather conditions
        dog_breed: Dog breed for breed-specific adjustments
        health_conditions: List of health conditions

    Returns:
        Weather-adjusted activity level
    """
    if not weather_conditions or not weather_conditions.is_valid:
      return base_activity_level  # noqa: E111

    # Start with base level
    adjusted_level = base_activity_level

    # Temperature-based adjustments
    if weather_conditions.temperature_c is not None:
      temp = weather_conditions.temperature_c  # noqa: E111

      # Hot weather reductions  # noqa: E114
      if temp > 35:  # Extreme heat  # noqa: E111
        if adjusted_level == ActivityLevel.VERY_HIGH:
          adjusted_level = ActivityLevel.LOW  # noqa: E111
        elif (
          adjusted_level == ActivityLevel.HIGH
          or adjusted_level == ActivityLevel.MODERATE
        ):
          adjusted_level = ActivityLevel.VERY_LOW  # noqa: E111
      elif temp > 30:  # High heat  # noqa: E111
        if adjusted_level == ActivityLevel.VERY_HIGH:
          adjusted_level = ActivityLevel.MODERATE  # noqa: E111
        elif adjusted_level == ActivityLevel.HIGH:
          adjusted_level = ActivityLevel.LOW  # noqa: E111

      # Cold weather considerations  # noqa: E114
      elif temp < -10:  # Extreme cold  # noqa: E111
        if adjusted_level in [ActivityLevel.HIGH, ActivityLevel.VERY_HIGH]:
          adjusted_level = ActivityLevel.MODERATE  # noqa: E111
      elif (  # noqa: E111
        temp < 0 and adjusted_level == ActivityLevel.VERY_HIGH
      ):  # High cold
        adjusted_level = ActivityLevel.HIGH

    # Breed-specific weather adjustments
    if dog_breed:
      breed_lower = dog_breed.lower()  # noqa: E111

      # Brachycephalic breeds more sensitive to heat/humidity  # noqa: E114
      if any(  # noqa: E111
        breed in breed_lower for breed in ["bulldog", "pug", "boxer", "boston"]
      ) and (
        (weather_conditions.temperature_c and weather_conditions.temperature_c > 25)
        or (
          weather_conditions.humidity_percent
          and weather_conditions.humidity_percent > 70
        )
      ):
        # Reduce activity by one level
        if adjusted_level == ActivityLevel.VERY_HIGH:
          adjusted_level = ActivityLevel.HIGH  # noqa: E111
        elif adjusted_level == ActivityLevel.HIGH:
          adjusted_level = ActivityLevel.MODERATE  # noqa: E111
        elif adjusted_level == ActivityLevel.MODERATE:
          adjusted_level = ActivityLevel.LOW  # noqa: E111

      # Cold-sensitive breeds  # noqa: E114
      if (  # noqa: E111
        any(breed in breed_lower for breed in ["chihuahua", "greyhound", "whippet"])
        and (weather_conditions.temperature_c and weather_conditions.temperature_c < 5)
        and adjusted_level in [ActivityLevel.HIGH, ActivityLevel.VERY_HIGH]
      ):
        adjusted_level = ActivityLevel.MODERATE

    # Health condition adjustments
    if health_conditions:
      for condition in health_conditions:  # noqa: E111
        condition_lower = condition.lower()

        # Heart conditions + heat
        if (
          "heart" in condition_lower
          and weather_conditions.temperature_c
          and weather_conditions.temperature_c > 25
        ) and adjusted_level in [ActivityLevel.HIGH, ActivityLevel.VERY_HIGH]:
          adjusted_level = ActivityLevel.MODERATE  # noqa: E111

        # Respiratory conditions + humidity
        if (
          any(
            resp in condition_lower for resp in ["respiratory", "breathing", "asthma"]
          )
          and weather_conditions.humidity_percent
          and weather_conditions.humidity_percent > 80
        ):
          if adjusted_level == ActivityLevel.VERY_HIGH:  # noqa: E111
            adjusted_level = ActivityLevel.HIGH
          elif adjusted_level == ActivityLevel.HIGH:  # noqa: E111
            adjusted_level = ActivityLevel.MODERATE

    return adjusted_level

  @staticmethod  # noqa: E111
  def calculate_weather_adjusted_portions(  # noqa: E111
    base_portion: float,
    weather_conditions: WeatherConditions | None = None,
    dog_breed: str | None = None,
    activity_level: ActivityLevel | None = None,
  ) -> float:
    """Calculate weather-adjusted portion sizes.

    Args:
        base_portion: Base portion size
        weather_conditions: Current weather conditions
        dog_breed: Dog breed
        activity_level: Current activity level

    Returns:
        Weather-adjusted portion size
    """
    if not weather_conditions or not weather_conditions.is_valid:
      return base_portion  # noqa: E111

    adjustment_factor = 1.0

    # Temperature-based adjustments
    if weather_conditions.temperature_c is not None:
      temp = weather_conditions.temperature_c  # noqa: E111

      # Hot weather - dogs may eat less  # noqa: E114
      if temp > 30:  # noqa: E111
        adjustment_factor *= 0.9  # 10% reduction in hot weather
      elif temp > 35:  # noqa: E111
        adjustment_factor *= 0.85  # 15% reduction in extreme heat

      # Cold weather - dogs may need more calories  # noqa: E114
      elif temp < 5:  # noqa: E111
        adjustment_factor *= 1.05  # 5% increase in cold weather
      elif temp < -5:  # noqa: E111
        adjustment_factor *= 1.1  # 10% increase in extreme cold

    # Activity level adjustments based on weather limitations
    if (
      activity_level in [ActivityLevel.VERY_LOW, ActivityLevel.LOW]
      and weather_conditions.temperature_c
      and (
        weather_conditions.temperature_c > 30 or weather_conditions.temperature_c < 0
      )
    ):
      # If activity is reduced due to weather, slightly reduce portions  # noqa: E114
      adjustment_factor *= (  # noqa: E111
        0.95  # 5% reduction for weather-limited activity
      )

    return round(base_portion * adjustment_factor, 1)

  @staticmethod  # noqa: E111
  def activity_score(steps: int, age: int) -> float:  # noqa: E111
    """Return activity score based on step count and age."""
    base = min(steps / 1000, 10)  # Cap at 10,000 steps for score
    age_adjustment = 1.0 if age < 8 else 0.8
    return round(base * age_adjustment * 10, 1)
