"""Targeted coverage tests for health_enhancements.py — (0% → 22%+).

Covers: EnhancedHealthProfile, EnhancedHealthCalculator methods,
        DewormingRecord, DewormingType
"""

from datetime import UTC, datetime

import pytest

from custom_components.pawcontrol.health_enhancements import (
    DewormingRecord,
    DewormingType,
    EnhancedHealthCalculator,
    EnhancedHealthProfile,
)

# ─── EnhancedHealthProfile ────────────────────────────────────────────────────


@pytest.mark.unit
def test_enhanced_health_profile_minimal() -> None:
    profile = EnhancedHealthProfile(current_weight=22.0)
    assert profile.current_weight == pytest.approx(22.0)


@pytest.mark.unit
def test_enhanced_health_profile_with_ideal_weight() -> None:
    profile = EnhancedHealthProfile(current_weight=25.0, ideal_weight=23.0)
    assert profile.ideal_weight == pytest.approx(23.0)


@pytest.mark.unit
def test_enhanced_health_profile_bcs() -> None:
    profile = EnhancedHealthProfile(current_weight=20.0, body_condition_score=5)
    assert profile.body_condition_score == 5


@pytest.mark.unit
def test_enhanced_health_profile_empty_lists() -> None:
    profile = EnhancedHealthProfile(current_weight=18.0)
    assert isinstance(profile.vaccinations, list)
    assert isinstance(profile.dewormings, list)
    assert isinstance(profile.chronic_conditions, list)


# ─── DewormingRecord ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_deworming_record_init() -> None:
    record = DewormingRecord(
        treatment_type=DewormingType.BROAD_SPECTRUM,
        medication_name="Milbemax",
        date_given=datetime(2025, 1, 15, tzinfo=UTC),
        next_due_date=datetime(2025, 7, 15, tzinfo=UTC),
    )
    assert record.medication_name == "Milbemax"


@pytest.mark.unit
def test_deworming_type_values() -> None:
    assert DewormingType.BROAD_SPECTRUM is not None
    assert DewormingType.TAPEWORM is not None


# ─── EnhancedHealthCalculator ────────────────────────────────────────────────


@pytest.mark.unit
def test_enhanced_calculator_vaccination_schedule() -> None:
    schedule = EnhancedHealthCalculator.ADULT_VACCINATION_SCHEDULE
    assert isinstance(schedule, dict)
    assert len(schedule) > 0


@pytest.mark.unit
def test_enhanced_calculator_deworming_schedule() -> None:
    schedule = EnhancedHealthCalculator.ADULT_DEWORMING_SCHEDULE
    assert isinstance(schedule, dict)


@pytest.mark.unit
def test_generate_vaccination_schedule() -> None:
    birth = datetime(2022, 6, 1, tzinfo=UTC)
    result = EnhancedHealthCalculator.generate_vaccination_schedule(birth_date=birth)
    assert isinstance(result, list)


@pytest.mark.unit
def test_generate_deworming_schedule() -> None:
    birth = datetime(2022, 6, 1, tzinfo=UTC)
    result = EnhancedHealthCalculator.generate_deworming_schedule(birth_date=birth)
    assert isinstance(result, list)
