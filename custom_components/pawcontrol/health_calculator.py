from __future__ import annotations


class HealthCalculator:
    def calculate_bmi(self, weight: float, height: float) -> float:
        if height <= 0:
            return 0.0
        return weight / ((height / 100) ** 2)

    def activity_score(self, steps: int, age: int) -> float:
        base = steps / 1000
        adjustment = 1.0 if age < 8 else 0.8
        return base * adjustment
