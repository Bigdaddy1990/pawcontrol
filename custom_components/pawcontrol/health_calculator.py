"""Enhanced health calculator for advanced portion calculation and health metrics.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+

Provides comprehensive health metrics for dogs including:
- Body condition scoring
- Calorie requirement calculations
- Age and activity-based adjustments
- Health condition considerations
- Weight management recommendations
- Diet validation integration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class BodyConditionScore(Enum):
    """Body condition score classification (1-9 scale)."""

    EMACIATED = 1  # Severely underweight
    VERY_THIN = 2  # Underweight
    THIN = 3  # Slightly underweight
    UNDERWEIGHT = 4  # Below ideal
    IDEAL = 5  # Perfect weight
    OVERWEIGHT = 6  # Slightly above ideal
    HEAVY = 7  # Overweight
    OBESE = 8  # Significantly overweight
    SEVERELY_OBESE = 9  # Severely obese


class LifeStage(Enum):
    """Life stage classification for nutritional needs."""

    PUPPY = "puppy"  # 0-12 months
    YOUNG_ADULT = "young_adult"  # 1-2 years
    ADULT = "adult"  # 2-7 years
    SENIOR = "senior"  # 7-10 years
    GERIATRIC = "geriatric"  # 10+ years


class ActivityLevel(Enum):
    """Activity level classification."""

    VERY_LOW = "very_low"  # Inactive, elderly, sick
    LOW = "low"  # Light exercise, indoor
    MODERATE = "moderate"  # Regular walks
    HIGH = "high"  # Active, long walks
    VERY_HIGH = "very_high"  # Working, athletic dogs


@dataclass
class HealthMetrics:
    """Comprehensive health metrics for a dog."""

    # Basic measurements
    current_weight: float
    ideal_weight: Optional[float] = None
    height_cm: Optional[float] = None
    age_months: Optional[int] = None

    # Health assessments
    body_condition_score: Optional[BodyConditionScore] = None
    activity_level: Optional[ActivityLevel] = None
    life_stage: Optional[LifeStage] = None

    # Health conditions
    health_conditions: List[str] = None
    medications: List[str] = None
    special_diet: List[str] = None

    # Calculated values
    daily_calorie_requirement: Optional[float] = None
    portion_adjustment_factor: float = 1.0
    weight_goal: Optional[str] = None  # "maintain", "lose", "gain"

    def __post_init__(self) -> None:
        """Initialize default values."""
        if self.health_conditions is None:
            self.health_conditions = []
        if self.medications is None:
            self.medications = []
        if self.special_diet is None:
            self.special_diet = []


class HealthCalculator:
    """Enhanced health calculator for comprehensive dog health metrics."""

    # Calorie requirements per kg by life stage (kcal/kg/day)
    BASE_CALORIE_REQUIREMENTS = {
        LifeStage.PUPPY: 130,  # Growing puppies need more calories
        LifeStage.YOUNG_ADULT: 110,  # Active young adults
        LifeStage.ADULT: 95,  # Standard adult maintenance
        LifeStage.SENIOR: 85,  # Slower metabolism
        LifeStage.GERIATRIC: 75,  # Reduced activity and metabolism
    }

    # Activity level multipliers
    ACTIVITY_MULTIPLIERS = {
        ActivityLevel.VERY_LOW: 0.8,  # Sedentary, sick, or elderly
        ActivityLevel.LOW: 0.9,  # Light activity
        ActivityLevel.MODERATE: 1.0,  # Baseline
        ActivityLevel.HIGH: 1.3,  # Very active
        ActivityLevel.VERY_HIGH: 1.6,  # Working or athletic dogs
    }

    # Body condition score adjustments for portion size
    BCS_ADJUSTMENTS = {
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

    # Health condition adjustments
    HEALTH_CONDITION_ADJUSTMENTS = {
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

    @staticmethod
    def calculate_life_stage(age_months: int, breed_size: str = "medium") -> LifeStage:
        """Calculate life stage based on age and breed size.

        Args:
            age_months: Age in months
            breed_size: Size category (toy, small, medium, large, giant)

        Returns:
            Life stage classification
        """
        if age_months < 0:
            return LifeStage.PUPPY

        # Adjust adult/senior thresholds based on breed size
        size_adjustments = {
            "toy": {"adult": 10, "senior": 96},  # 10 months to adult, 8 years to senior
            "small": {"adult": 12, "senior": 84},  # 1 year to adult, 7 years to senior
            "medium": {
                "adult": 15,
                "senior": 84,
            },  # 15 months to adult, 7 years to senior
            "large": {
                "adult": 18,
                "senior": 72,
            },  # 18 months to adult, 6 years to senior
            "giant": {"adult": 24, "senior": 60},  # 2 years to adult, 5 years to senior
        }

        thresholds = size_adjustments.get(breed_size, size_adjustments["medium"])

        if age_months < thresholds["adult"]:
            return LifeStage.PUPPY
        elif age_months < 24:
            return LifeStage.YOUNG_ADULT
        elif age_months < thresholds["senior"]:
            return LifeStage.ADULT
        elif age_months < 120:  # 10 years
            return LifeStage.SENIOR
        else:
            return LifeStage.GERIATRIC

    @staticmethod
    def calculate_bmi(weight: float, height_cm: float) -> float:
        """Calculate body mass index for a dog.

        Args:
            weight: Weight in kilograms
            height_cm: Height in centimeters

        Returns:
            BMI value
        """
        if height_cm <= 0:
            return 0.0
        return weight / ((height_cm / 100) ** 2)

    @staticmethod
    def estimate_body_condition_score(
        current_weight: float,
        ideal_weight: Optional[float] = None,
        visual_assessment: Optional[int] = None,
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
            # Use provided assessment if available
            return BodyConditionScore(min(9, max(1, visual_assessment)))

        if ideal_weight is None or ideal_weight <= 0:
            # Default to ideal if no ideal weight provided
            return BodyConditionScore.IDEAL

        # Calculate based on weight deviation
        weight_ratio = current_weight / ideal_weight

        if weight_ratio < 0.7:
            return BodyConditionScore.EMACIATED
        elif weight_ratio < 0.8:
            return BodyConditionScore.VERY_THIN
        elif weight_ratio < 0.9:
            return BodyConditionScore.THIN
        elif weight_ratio < 0.95:
            return BodyConditionScore.UNDERWEIGHT
        elif weight_ratio <= 1.05:
            return BodyConditionScore.IDEAL
        elif weight_ratio <= 1.15:
            return BodyConditionScore.OVERWEIGHT
        elif weight_ratio <= 1.25:
            return BodyConditionScore.HEAVY
        elif weight_ratio <= 1.4:
            return BodyConditionScore.OBESE
        else:
            return BodyConditionScore.SEVERELY_OBESE

    @staticmethod
    def calculate_daily_calories(
        weight: float,
        life_stage: LifeStage,
        activity_level: ActivityLevel,
        body_condition_score: Optional[BodyConditionScore] = None,
        health_conditions: Optional[List[str]] = None,
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
            activity_level, 1.0
        )

        # Calculate base daily calories
        daily_calories = rer * base_multiplier * activity_multiplier

        # Adjust for spayed/neutered (typically 10% reduction)
        if spayed_neutered and life_stage in [LifeStage.ADULT, LifeStage.SENIOR]:
            daily_calories *= 0.9

        # Apply body condition adjustments
        if body_condition_score:
            bcs_adjustment = HealthCalculator.BCS_ADJUSTMENTS.get(
                body_condition_score, 1.0
            )
            daily_calories *= bcs_adjustment

        # Apply health condition adjustments
        if health_conditions:
            for condition in health_conditions:
                adjustment = HealthCalculator.HEALTH_CONDITION_ADJUSTMENTS.get(
                    condition.lower(), 1.0
                )
                daily_calories *= adjustment

        return round(daily_calories, 1)

    @staticmethod
    def calculate_portion_adjustment_factor(
        health_metrics: HealthMetrics,
        feeding_goals: Optional[Dict[str, Any]] = None,
        diet_validation: Optional[Dict[str, Any]] = None,
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
            bcs_adjustment = HealthCalculator.BCS_ADJUSTMENTS.get(
                health_metrics.body_condition_score, 1.0
            )
            adjustment_factor *= bcs_adjustment

        # Apply health condition adjustments
        for condition in health_metrics.health_conditions:
            condition_adjustment = HealthCalculator.HEALTH_CONDITION_ADJUSTMENTS.get(
                condition.lower(), 1.0
            )
            adjustment_factor *= condition_adjustment

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
            diet_adjustment = diet_adjustments.get(diet_type.lower(), 1.0)
            adjustment_factor *= diet_adjustment

        # Apply diet validation adjustments for conflicts/warnings
        if diet_validation:
            validation_adjustment = (
                HealthCalculator.calculate_diet_validation_adjustment(
                    diet_validation, health_metrics.special_diet
                )
            )
            adjustment_factor *= validation_adjustment

        # Apply feeding goals
        if feeding_goals:
            weight_goal = feeding_goals.get("weight_goal")
            if weight_goal == "lose":
                adjustment_factor *= 0.8  # 20% reduction for weight loss
            elif weight_goal == "gain":
                adjustment_factor *= 1.2  # 20% increase for weight gain

            # Time-based adjustments
            weight_loss_rate = feeding_goals.get("weight_loss_rate", "moderate")
            if weight_loss_rate == "aggressive" and weight_goal == "lose":
                adjustment_factor *= 0.9  # Additional 10% reduction
            elif weight_loss_rate == "gradual" and weight_goal == "lose":
                adjustment_factor *= 1.1  # Less aggressive reduction

        # Ensure reasonable bounds
        adjustment_factor = max(0.5, min(2.0, adjustment_factor))

        return round(adjustment_factor, 2)

    @staticmethod
    def calculate_diet_validation_adjustment(
        diet_validation: Dict[str, Any], special_diets: List[str]
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
        conflicts = diet_validation.get("conflicts", [])
        for conflict in conflicts:
            conflict_type = conflict.get("type")

            if conflict_type == "age_conflict":
                # Age conflicts require veterinary guidance - use conservative portions
                adjustment *= 0.9
                _LOGGER.warning(
                    "Age-based diet conflict detected: applying conservative 10%% portion reduction"
                )

        # Handle warnings (milder adjustments)
        warnings = diet_validation.get("warnings", [])
        for warning in warnings:
            warning_type = warning.get("type")

            if warning_type == "multiple_prescription_warning":
                # Multiple prescription diets need careful portion control
                adjustment *= 0.95
                _LOGGER.info(
                    "Multiple prescription diets: applying 5%% portion reduction for safety"
                )

            elif warning_type == "raw_medical_warning":
                # Raw diet with medical conditions - slightly conservative
                adjustment *= 0.95
                _LOGGER.info(
                    "Raw diet with medical conditions: applying 5%% portion reduction"
                )

            elif warning_type == "weight_puppy_warning":
                # Weight control for puppies - less restrictive than adults
                adjustment *= 1.05  # Actually increase slightly for growing puppy
                _LOGGER.info(
                    "Weight control for puppy: applying 5%% portion increase for growth"
                )

            elif warning_type == "hypoallergenic_warning":
                # Hypoallergenic with other diets - standard portions but monitor
                adjustment *= 0.98  # Very minor reduction for safety
                _LOGGER.info(
                    "Hypoallergenic diet combination: minor portion adjustment for monitoring"
                )

            elif warning_type == "low_fat_activity_warning":
                # Low fat with joint support - may need calorie compensation
                adjustment *= 1.05  # Slight increase to compensate for low fat
                _LOGGER.info(
                    "Low fat diet with joint support needs: applying 5%% portion increase"
                )

        # Additional adjustments based on total diet complexity
        total_diets = diet_validation.get("total_diets", 0)
        if total_diets >= 4:
            # Complex diet combinations need careful monitoring
            adjustment *= 0.97  # 3% reduction for very complex diets
            _LOGGER.info(
                "Complex diet combination (%d diets): applying 3%% portion reduction for safety",
                total_diets,
            )

        # Veterinary consultation recommendation adjustment
        if diet_validation.get("recommended_vet_consultation", False):
            # When vet consultation is recommended, use more conservative portions
            adjustment *= 0.95
            _LOGGER.info(
                "Veterinary consultation recommended: applying 5%% conservative portion adjustment"
            )

        # Ensure reasonable bounds (more conservative than general adjustments)
        adjustment = max(0.8, min(1.1, adjustment))

        # Log the final adjustment if it's not neutral
        if adjustment != 1.0:
            _LOGGER.info(
                "Diet validation adjustment applied: %.2fx (%.0f%% of base portion)",
                adjustment,
                adjustment * 100,
            )

        return round(adjustment, 3)

    @staticmethod
    def validate_portion_safety(
        calculated_portion: float,
        dog_weight: float,
        life_stage: LifeStage,
        special_diets: List[str],
        diet_validation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
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
        safety_result = {
            "safe": True,
            "warnings": [],
            "recommendations": [],
            "portion_per_kg": round(calculated_portion / dog_weight, 1)
            if dog_weight > 0
            else 0,
        }

        # Check portion size relative to body weight
        if dog_weight > 0:
            portion_per_kg = calculated_portion / dog_weight

            # General safety thresholds (grams per kg body weight per meal)
            if life_stage == LifeStage.PUPPY:
                min_threshold, max_threshold = 15, 80  # Puppies need more food
            elif life_stage in [LifeStage.SENIOR, LifeStage.GERIATRIC]:
                min_threshold, max_threshold = 8, 40  # Seniors typically less
            else:
                min_threshold, max_threshold = 10, 50  # Adult dogs

            if portion_per_kg < min_threshold:
                safety_result["warnings"].append(
                    f"Portion may be too small: {portion_per_kg:.1f}g/kg (minimum: {min_threshold}g/kg)"
                )
                safety_result["recommendations"].append(
                    "Consider increasing portion size or adding additional meals"
                )

            elif portion_per_kg > max_threshold:
                safety_result["warnings"].append(
                    f"Portion may be too large: {portion_per_kg:.1f}g/kg (maximum: {max_threshold}g/kg)"
                )
                safety_result["recommendations"].append(
                    "Consider reducing portion size or splitting into smaller meals"
                )
                safety_result["safe"] = False

        # Special diet safety checks
        high_risk_diets = ["prescription", "diabetic", "kidney_support"]
        if any(diet in special_diets for diet in high_risk_diets):
            safety_result["recommendations"].append(
                "Prescription diet detected - verify portions with veterinarian"
            )

        # Diet validation safety checks
        if diet_validation:
            if diet_validation.get("conflicts"):
                safety_result["warnings"].append(
                    "Diet conflicts detected - extra monitoring recommended"
                )
                safety_result["safe"] = False

            if diet_validation.get("recommended_vet_consultation"):
                safety_result["recommendations"].append(
                    "Veterinary consultation recommended due to diet complexity"
                )

        return safety_result

    @staticmethod
    def get_diet_interaction_effects(special_diets: List[str]) -> Dict[str, Any]:
        """Analyze potential interactions between special diets.

        Args:
            special_diets: List of special diet requirements

        Returns:
            Dictionary with interaction analysis
        """
        interactions = {
            "synergistic": [],  # Diets that work well together
            "neutral": [],  # Diets with no significant interaction
            "caution": [],  # Combinations requiring monitoring
            "conflicting": [],  # Combinations that may conflict
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
            if diet1 in diet_set and diet2 in diet_set:
                interactions["synergistic"].append((diet1, diet2))

        for diet1, diet2 in caution_pairs:
            if diet1 in diet_set and diet2 in diet_set:
                interactions["caution"].append((diet1, diet2))

        for diet1, diet2 in conflicting_pairs:
            if diet1 in diet_set and diet2 in diet_set:
                interactions["conflicting"].append((diet1, diet2))

        # Add recommendations based on interactions
        recommendations = []

        if interactions["synergistic"]:
            recommendations.append(
                f"Good diet combinations detected: {len(interactions['synergistic'])} synergistic pairs"
            )

        if interactions["caution"]:
            recommendations.append(
                f"Monitor carefully: {len(interactions['caution'])} combinations need attention"
            )

        if interactions["conflicting"]:
            recommendations.append(
                f"Conflicting diets detected: {len(interactions['conflicting'])} pairs need resolution"
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

    @staticmethod
    def analyze_feeding_history(
        feeding_events: List[Dict[str, Any]],
        target_calories: float,
        food_calories_per_gram: float = 3.5,
    ) -> Dict[str, Any]:
        """Analyze feeding history for patterns and recommendations.

        Args:
            feeding_events: List of feeding events
            target_calories: Target daily calories
            food_calories_per_gram: Calories per gram of food

        Returns:
            Analysis results with recommendations
        """
        if not feeding_events:
            return {
                "status": "no_data",
                "recommendation": "Start tracking feedings to analyze patterns",
            }

        # Calculate daily averages over last 7 days
        recent_days = {}
        now = dt_util.now()
        week_ago = now - timedelta(days=7)

        for event in feeding_events:
            event_time = event.get("time")
            if isinstance(event_time, str):
                event_time = datetime.fromisoformat(event_time.replace("Z", "+00:00"))

            if event_time and event_time > week_ago:
                date_key = event_time.date()
                if date_key not in recent_days:
                    recent_days[date_key] = {"calories": 0, "meals": 0}

                # Calculate calories from amount
                amount = event.get("amount", 0)
                calories = amount * food_calories_per_gram
                recent_days[date_key]["calories"] += calories
                recent_days[date_key]["meals"] += 1

        if not recent_days:
            return {
                "status": "insufficient_data",
                "recommendation": "Need at least one week of feeding data",
            }

        # Calculate averages
        avg_daily_calories = sum(day["calories"] for day in recent_days.values()) / len(
            recent_days
        )
        avg_daily_meals = sum(day["meals"] for day in recent_days.values()) / len(
            recent_days
        )

        # Calculate variance from target
        calorie_variance = (
            (avg_daily_calories - target_calories) / target_calories * 100
        )

        # Generate recommendations
        recommendations = []
        status = "good"

        if calorie_variance > 20:
            status = "overfeeding"
            recommendations.append("Consider reducing portion sizes by 15-20%")
            recommendations.append("Increase exercise if possible")
        elif calorie_variance > 10:
            status = "slight_overfeeding"
            recommendations.append("Slightly reduce portion sizes by 5-10%")
        elif calorie_variance < -20:
            status = "underfeeding"
            recommendations.append("Increase portion sizes by 15-20%")
            recommendations.append("Consider more nutrient-dense food")
        elif calorie_variance < -10:
            status = "slight_underfeeding"
            recommendations.append("Slightly increase portion sizes by 5-10%")
        else:
            recommendations.append(
                "Feeding is well balanced, maintain current portions"
            )

        # Meal frequency recommendations
        if avg_daily_meals < 1.5:
            recommendations.append("Consider splitting daily food into 2+ meals")
        elif avg_daily_meals > 4:
            recommendations.append("Consider consolidating into 2-3 larger meals")

        return {
            "status": status,
            "avg_daily_calories": round(avg_daily_calories, 1),
            "target_calories": target_calories,
            "calorie_variance_percent": round(calorie_variance, 1),
            "avg_daily_meals": round(avg_daily_meals, 1),
            "recommendations": recommendations,
            "analysis_period_days": len(recent_days),
        }

    @staticmethod
    def calculate_ideal_weight_range(
        breed: Optional[str] = None,
        height_cm: Optional[float] = None,
        current_weight: float = 0,
        age_months: Optional[int] = None,
    ) -> Tuple[float, float]:
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
            return breed_weights[breed.lower().replace(" ", "_")]

        # Height-based estimation if available
        if height_cm and height_cm > 0:
            # Rough estimation: weight = height^2 * breed_factor
            # Breed factor varies by build type
            if height_cm < 25:  # Small dogs
                min_weight = (height_cm**1.8) * 0.002
                max_weight = (height_cm**1.8) * 0.003
            elif height_cm < 45:  # Medium dogs
                min_weight = (height_cm**1.8) * 0.0025
                max_weight = (height_cm**1.8) * 0.0035
            else:  # Large dogs
                min_weight = (height_cm**1.8) * 0.003
                max_weight = (height_cm**1.8) * 0.004

            return (round(min_weight, 1), round(max_weight, 1))

        # Fallback: assume current weight is close to ideal
        if current_weight > 0:
            min_weight = current_weight * 0.9
            max_weight = current_weight * 1.1
            return (round(min_weight, 1), round(max_weight, 1))

        # Default ranges by estimated size
        return (10.0, 30.0)  # Default medium dog range

    @classmethod
    def generate_health_report(cls, health_metrics: HealthMetrics) -> Dict[str, Any]:
        """Generate comprehensive health report with recommendations."""
        report = {
            "timestamp": dt_util.now().isoformat(),
            "overall_status": "good",
            "recommendations": [],
            "health_score": 85,  # Default good score
            "areas_of_concern": [],
            "positive_indicators": [],
        }

        cls._assess_weight(health_metrics, report)
        cls._assess_body_condition(health_metrics, report)
        cls._assess_health_conditions(health_metrics, report)
        cls._assess_age(health_metrics, report)
        cls._assess_activity(health_metrics, report)
        cls._finalize_status(report)

        return report

    @staticmethod
    def _assess_weight(health_metrics: HealthMetrics, report: Dict[str, Any]) -> None:
        if health_metrics.ideal_weight and health_metrics.current_weight:
            weight_ratio = health_metrics.current_weight / health_metrics.ideal_weight
            if weight_ratio < 0.85:
                report["areas_of_concern"].append("underweight")
                report["recommendations"].append("Consult vet about weight gain plan")
                report["health_score"] -= 15
            elif weight_ratio > 1.2:
                report["areas_of_concern"].append("overweight")
                report["recommendations"].append("Implement weight management plan")
                report["health_score"] -= 10
            else:
                report["positive_indicators"].append("healthy_weight")

    @staticmethod
    def _assess_body_condition(
        health_metrics: HealthMetrics, report: Dict[str, Any]
    ) -> None:
        if not health_metrics.body_condition_score:
            return

        bcs = health_metrics.body_condition_score
        if bcs in [BodyConditionScore.EMACIATED, BodyConditionScore.VERY_THIN]:
            report["overall_status"] = "concerning"
            report["areas_of_concern"].append("severe_underweight")
            report["recommendations"].append(
                "Immediate veterinary consultation needed",
            )
            report["health_score"] -= 25
        elif bcs in [BodyConditionScore.OBESE, BodyConditionScore.SEVERELY_OBESE]:
            report["overall_status"] = "needs_attention"
            report["areas_of_concern"].append("obesity")
            report["recommendations"].append("Urgent weight management required")
            report["health_score"] -= 20
        elif bcs == BodyConditionScore.IDEAL:
            report["positive_indicators"].append("ideal_body_condition")

    @staticmethod
    def _assess_health_conditions(
        health_metrics: HealthMetrics, report: Dict[str, Any]
    ) -> None:
        serious_conditions = {
            "diabetes",
            "heart_disease",
            "kidney_disease",
            "liver_disease",
            "cancer",
        }
        for condition in health_metrics.health_conditions:
            if condition.lower() in serious_conditions:
                report["overall_status"] = "managing_condition"
                report["areas_of_concern"].append(f"chronic_{condition}")
                report["recommendations"].append(
                    f"Continue monitoring {condition} as prescribed",
                )
                report["health_score"] -= 15

    @staticmethod
    def _assess_age(health_metrics: HealthMetrics, report: Dict[str, Any]) -> None:
        if not health_metrics.age_months:
            return
        age_years = health_metrics.age_months / 12
        if age_years < 1:
            report["recommendations"].append(
                "Ensure puppy vaccination schedule is complete",
            )
            report["recommendations"].append(
                "Monitor growth rate and adjust portions accordingly",
            )
        elif age_years > 7:
            report["recommendations"].append("Consider senior health screening")
            report["recommendations"].append("Monitor for age-related conditions")

    @staticmethod
    def _assess_activity(health_metrics: HealthMetrics, report: Dict[str, Any]) -> None:
        if health_metrics.activity_level == ActivityLevel.VERY_LOW:
            report["recommendations"].append(
                "Gradually increase physical activity if health permits",
            )
        elif health_metrics.activity_level == ActivityLevel.VERY_HIGH:
            report["positive_indicators"].append("excellent_activity_level")

    @staticmethod
    def _finalize_status(report: Dict[str, Any]) -> None:
        score = report["health_score"]
        if score >= 90:
            report["overall_status"] = "excellent"
        elif score >= 75:
            report["overall_status"] = "good"
        elif score >= 60:
            report["overall_status"] = "needs_attention"
        else:
            report["overall_status"] = "concerning"

    @staticmethod
    def activity_score(steps: int, age: int) -> float:
        """Return activity score based on step count and age."""
        base = min(steps / 1000, 10)  # Cap at 10,000 steps for score
        age_adjustment = 1.0 if age < 8 else 0.8
        return round(base * age_adjustment * 10, 1)
