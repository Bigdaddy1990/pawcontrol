"""Coverage tests for enhanced health scheduling and status evaluation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pawcontrol import health_enhancements as health


@pytest.mark.parametrize(
    ("risk_factors", "expected_extra"),
    [
        ([], set()),
        (["boarding"], {health.VaccinationType.BORDETELLA}),
        (["tick_area"], {health.VaccinationType.LYME_DISEASE}),
        (
            ["boarding", "daycare", "tick_area"],
            {
                health.VaccinationType.BORDETELLA,
                health.VaccinationType.LYME_DISEASE,
            },
        ),
    ],
)
def test_generate_vaccination_schedule_tracks_age_and_risk(
    risk_factors: list[str],
    expected_extra: set[health.VaccinationType],
) -> None:
    """Puppy schedules should include overdue/due-soon doses and risk additions."""
    birth_date = datetime(2025, 10, 1, tzinfo=UTC)
    current_date = birth_date + timedelta(weeks=15)

    schedule = health.EnhancedHealthCalculator.generate_vaccination_schedule(
        birth_date,
        current_date=current_date,
        risk_factors=risk_factors,
    )

    statuses = {record.status for record in schedule}
    vaccine_types = {record.vaccine_type for record in schedule}

    assert health.HealthEventStatus.OVERDUE in statuses
    assert health.HealthEventStatus.DUE_SOON in statuses
    assert expected_extra.issubset(vaccine_types)


@pytest.mark.parametrize(
    ("age_months", "lifestyle_factors", "expected_flea_tick_count"),
    [
        (4, [], 0),
        (4, ["outdoor_frequent"], 4),
        (12, ["outdoor_frequent"], 4),
    ],
)
def test_generate_deworming_schedule_applies_lifestyle_adjustments(
    age_months: int,
    lifestyle_factors: list[str],
    expected_flea_tick_count: int,
) -> None:
    """Deworming schedules should adapt by age segment and lifestyle risk."""
    current_date = datetime(2026, 4, 1, tzinfo=UTC)
    birth_date = current_date - timedelta(days=30 * age_months)

    schedule = health.EnhancedHealthCalculator.generate_deworming_schedule(
        birth_date,
        current_date=current_date,
        lifestyle_factors=lifestyle_factors,
    )

    flea_tick_entries = [
        record
        for record in schedule
        if record.treatment_type is health.DewormingType.FLEA_TICK_PREVENTION
    ]

    assert len(flea_tick_entries) == expected_flea_tick_count
    assert any(
        record.treatment_type is health.DewormingType.HEARTWORM_PREVENTION
        for record in schedule
    )


def test_update_health_status_builds_alerts_upcoming_care_and_recommendations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health status should collect overdue items and near-term care reminders."""
    now = datetime(2026, 4, 1, 8, 0, tzinfo=UTC)
    monkeypatch.setattr(health.dt_util, "now", lambda: now)
    monkeypatch.setattr(
        health,
        "ensure_local_datetime",
        lambda value: datetime.fromisoformat(value) if "T" in str(value) else None,
    )

    profile = health.EnhancedHealthProfile(
        current_weight=20.5,
        vaccinations=[
            health.VaccinationRecord(
                vaccine_type=health.VaccinationType.RABIES,
                next_due_date=now - timedelta(days=3),
            ),
            health.VaccinationRecord(
                vaccine_type=health.VaccinationType.DHPP,
                next_due_date=now + timedelta(days=5),
            ),
        ],
        dewormings=[
            health.DewormingRecord(
                treatment_type=health.DewormingType.BROAD_SPECTRUM,
                next_due_date=now - timedelta(days=2),
            ),
            health.DewormingRecord(
                treatment_type=health.DewormingType.HEARTWORM_PREVENTION,
                next_due_date=now + timedelta(days=4),
            ),
        ],
        veterinary_appointments=[
            health.VeterinaryAppointment(
                appointment_date=now + timedelta(days=10),
                appointment_type="checkup",
                purpose="Routine exam",
            ),
        ],
        current_medications=[
            {"name": "Omega-3", "next_dose": (now + timedelta(hours=1)).isoformat()},
            {"name": "Invalid", "next_dose": "not-a-datetime"},
        ],
    )

    status = health.EnhancedHealthCalculator.update_health_status(profile)

    assert status["overall_score"] == 75
    assert {alert["type"] for alert in status["priority_alerts"]} == {
        "vaccination_overdue",
        "deworming_overdue",
        "medication_due",
    }
    assert {item["type"] for item in status["upcoming_care"]} == {
        "vaccination_due",
        "deworming_due",
        "vet_appointment",
    }
    assert status["recommendations"] == [
        "Schedule initial veterinary checkup to establish baseline health",
    ]


@pytest.mark.parametrize(
    ("age_months", "conditions", "expected_type", "expected_days"),
    [
        (8, [], "puppy_checkup", 30),
        (36, ["diabetes"], "diabetes_monitoring", 90),
        (120, ["kidney_disease"], "condition_monitoring", 120),
    ],
)
def test_calculate_next_appointment_recommendation_uses_age_and_conditions(
    monkeypatch: pytest.MonkeyPatch,
    age_months: int,
    conditions: list[str],
    expected_type: str,
    expected_days: int,
) -> None:
    """Appointment recommendation should switch cadence for chronic conditions."""
    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(health.dt_util, "now", lambda: now)
    monkeypatch.setattr(
        health,
        "ensure_local_datetime",
        lambda value: datetime.fromisoformat(value) if "T" in str(value) else None,
    )

    profile = health.EnhancedHealthProfile(
        current_weight=19.0,
        chronic_conditions=conditions,
        last_checkup_date=now,
    )

    recommendation = (
        health.EnhancedHealthCalculator.calculate_next_appointment_recommendation(
            profile,
            dog_age_months=age_months,
        )
    )

    assert recommendation["appointment_type"] == expected_type
    assert recommendation["days_until"] == expected_days
    assert recommendation["urgency"] == "normal"
