"""Unit tests for health enhancement telemetry typing."""

from datetime import timedelta

from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.health_enhancements import (
    DewormingRecord,
    DewormingType,
    EnhancedHealthCalculator,
    EnhancedHealthProfile,
    HealthEventStatus,
    VaccinationRecord,
    VaccinationType,
    VeterinaryAppointment,
)


def test_update_health_status_generates_typed_entries() -> None:
    """Health status snapshots should expose fully typed telemetry."""
    now = dt_util.now()
    profile = EnhancedHealthProfile(
        current_weight=22.5,
        vaccinations=[
            VaccinationRecord(
                vaccine_type=VaccinationType.RABIES,
                next_due_date=now - timedelta(days=3),
            ),
            VaccinationRecord(
                vaccine_type=VaccinationType.DHPP,
                next_due_date=now + timedelta(days=5),
            ),
        ],
        dewormings=[
            DewormingRecord(
                treatment_type=DewormingType.HEARTWORM_PREVENTION,
                next_due_date=now + timedelta(days=10),
            ),
        ],
        current_medications=[
            {
                "name": "Carprofen",
                "next_dose": (now + timedelta(minutes=45)).isoformat(),
                "dosage": "25mg",
                "with_meals": True,
            }
        ],
        last_checkup_date=now - timedelta(days=400),
    )

    snapshot = EnhancedHealthCalculator.update_health_status(profile)

    assert snapshot["overall_score"] < 100
    assert isinstance(snapshot["last_updated"], str)

    alerts = snapshot["priority_alerts"]
    assert alerts, "Expected at least one priority alert"
    for alert in alerts:
        assert alert["type"] in {"vaccination_overdue", "medication_due"}
        assert isinstance(alert["message"], str)
        assert isinstance(alert["action_required"], bool)

    upcoming = snapshot["upcoming_care"]
    assert any(entry["type"] == "vaccination_due" for entry in upcoming)
    assert all("priority" in entry for entry in upcoming)

    recommendations = snapshot["recommendations"]
    assert any("Annual checkup" in rec for rec in recommendations)


def test_calculate_next_appointment_recommendation_structured() -> None:
    """Appointment recommendations should map to the typed contract."""
    now = dt_util.now()
    profile = EnhancedHealthProfile(
        current_weight=18.2,
        chronic_conditions=["diabetes"],
        last_checkup_date=now - timedelta(days=200),
    )

    recommendation = EnhancedHealthCalculator.calculate_next_appointment_recommendation(
        profile, dog_age_months=96
    )

    assert recommendation["appointment_type"] == "diabetes_monitoring"
    assert recommendation["urgency"] in {"high", "normal"}
    assert "health conditions" in recommendation["reason"]
    assert isinstance(recommendation["next_appointment_date"], str)


def test_generate_vaccination_schedule_marks_puppy_and_risk_based_entries() -> None:
    """Puppy schedules should include age-based and risk-based vaccinations."""
    current_date = dt_util.now()
    birth_date = current_date - timedelta(weeks=10)

    schedule = EnhancedHealthCalculator.generate_vaccination_schedule(
        birth_date,
        current_date=current_date,
        risk_factors=["boarding", "tick_area"],
    )

    assert any(
        record.vaccine_type is VaccinationType.DHPP
        and record.status is HealthEventStatus.OVERDUE
        for record in schedule
    )
    assert any(
        record.vaccine_type is VaccinationType.DHPP
        and record.status is HealthEventStatus.DUE_SOON
        for record in schedule
    )
    assert any(
        record.vaccine_type is VaccinationType.RABIES
        and record.status is HealthEventStatus.SCHEDULED
        for record in schedule
    )
    assert any(
        record.vaccine_type is VaccinationType.BORDETELLA
        and record.notes == "High-risk environment"
        for record in schedule
    )
    assert any(
        record.vaccine_type is VaccinationType.LYME_DISEASE
        and record.notes == "Tick-endemic area"
        for record in schedule
    )


def test_generate_deworming_schedule_covers_puppy_and_adult_paths() -> None:
    """Deworming schedules should adapt to age and lifestyle."""
    current_date = dt_util.now()

    puppy_schedule = EnhancedHealthCalculator.generate_deworming_schedule(
        current_date - timedelta(days=120),
        current_date=current_date,
        lifestyle_factors=["outdoor_frequent"],
    )
    adult_schedule = EnhancedHealthCalculator.generate_deworming_schedule(
        current_date - timedelta(days=365),
        current_date=current_date,
    )

    assert any(
        record.treatment_type is DewormingType.BROAD_SPECTRUM
        and record.notes == "Puppy deworming schedule"
        for record in puppy_schedule
    )
    assert (
        sum(
            record.treatment_type is DewormingType.FLEA_TICK_PREVENTION
            for record in puppy_schedule
        )
        == 4
    )
    assert any(
        record.treatment_type is DewormingType.HEARTWORM_PREVENTION
        for record in puppy_schedule
    )
    assert any(
        record.treatment_type is DewormingType.BROAD_SPECTRUM
        and record.notes == "Adult maintenance deworming"
        for record in adult_schedule
    )


def test_update_health_status_handles_deworming_appointments_and_initial_checkup(
    monkeypatch,
) -> None:
    """Health status should include deworming alerts, appointments, and defaults."""
    now = dt_util.now()

    def _safe_ensure_local_datetime(value: object):
        if value == "invalid":
            return None
        return dt_util.parse_datetime(value) if isinstance(value, str) else None

    monkeypatch.setattr(
        "custom_components.pawcontrol.health_enhancements.ensure_local_datetime",
        _safe_ensure_local_datetime,
    )

    profile = EnhancedHealthProfile(
        current_weight=30.0,
        vaccinations=[
            VaccinationRecord(
                vaccine_type=VaccinationType.RABIES,
                next_due_date=now - timedelta(days=120),
            )
            for _ in range(8)
        ],
        dewormings=[
            DewormingRecord(
                treatment_type=DewormingType.BROAD_SPECTRUM,
                next_due_date=now - timedelta(days=4),
            ),
            DewormingRecord(
                treatment_type=DewormingType.HEARTWORM_PREVENTION,
                next_due_date=now + timedelta(days=3),
            ),
        ],
        veterinary_appointments=[
            VeterinaryAppointment(
                appointment_date=now + timedelta(days=2),
                appointment_type="checkup",
                purpose="Follow-up",
            ),
            VeterinaryAppointment(
                appointment_date=now + timedelta(days=5),
                appointment_type="surgery",
                completed=True,
                purpose="Completed visit",
            ),
        ],
        current_medications=[
            {"name": "Skipped missing dose"},
            {"name": "Skipped invalid dose", "next_dose": "invalid"},
        ],
    )

    snapshot = EnhancedHealthCalculator.update_health_status(profile)

    assert snapshot["overall_score"] == 5
    assert any(
        alert["type"] == "deworming_overdue" for alert in snapshot["priority_alerts"]
    )
    assert any(entry["type"] == "deworming_due" for entry in snapshot["upcoming_care"])
    assert any(
        entry["type"] == "vet_appointment" and entry["details"] == "Follow-up"
        for entry in snapshot["upcoming_care"]
    )
    assert snapshot["recommendations"] == [
        "Schedule initial veterinary checkup to establish baseline health"
    ]


def test_record_helpers_and_condition_monitoring_recommendations() -> None:
    """Record helpers should handle missing dates and chronic-condition intervals."""
    vaccination = VaccinationRecord(vaccine_type=VaccinationType.DHPP)
    deworming = DewormingRecord(treatment_type=DewormingType.HOOKWORM)

    assert vaccination.is_overdue() is False
    assert vaccination.days_until_due() is None
    assert deworming.is_overdue() is False
    assert deworming.days_until_due() is None

    recommendation = EnhancedHealthCalculator.calculate_next_appointment_recommendation(
        EnhancedHealthProfile(
            current_weight=24.0,
            chronic_conditions=["heart_disease"],
        ),
        dog_age_months=48,
    )

    assert recommendation["appointment_type"] == "condition_monitoring"
    assert recommendation["urgency"] == "normal"
    assert 6 <= recommendation["days_until"] <= 7
