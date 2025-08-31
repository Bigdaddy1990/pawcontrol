"""Health related helper calculations used by PawControl tests.

The implementation is intentionally small but documented so that unit tests
can validate behaviour without pulling in the full integration.
"""

from __future__ import annotations


class HealthCalculator:
    """Provide simple health metrics for dogs."""

    @staticmethod
    def calculate_bmi(weight: float, height_cm: float) -> float:
        """Calculate body mass index for a dog.

        Args:
            weight: Weight in kilograms.
            height_cm: Height in centimetres.
        """
        if height_cm <= 0:
            return 0.0
        return weight / ((height_cm / 100) ** 2)

    @staticmethod
    def activity_score(steps: int, age: int) -> float:
        """Return a crude activity score based on step count and age."""
        base = steps / 1000
        adjustment = 1.0 if age < 8 else 0.8
        return base * adjustment
