"""Unit tests for health enhancement telemetry typing."""

from datetime import timedelta

from homeassistant.util import dt as dt_util

import custom_components.pawcontrol.health_enhancements as health_enhancements
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


def test_generate_deworming_schedule_skips_far_future_puppy_dates(
    monkeypatch,
) -> None:
    """Future puppy deworming dates beyond the horizon should be ignored."""
    current_date = dt_util.now()
    birth_date = current_date - timedelta(weeks=2)

    original_timedelta = health_enhancements.timedelta

    def _patched_timedelta(*args, **kwargs):
        if kwargs.get("days") == 60:
            return original_timedelta(days=1)
        return original_timedelta(*args, **kwargs)

    monkeypatch.setattr(health_enhancements, "timedelta", _patched_timedelta)

    schedule = EnhancedHealthCalculator.generate_deworming_schedule(
        birth_date=birth_date,
        current_date=current_date,
    )

    broad_spectrum = [
        record
        for record in schedule
        if record.treatment_type is DewormingType.BROAD_SPECTRUM
    ]
    assert len(broad_spectrum) == 1


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


def test_update_health_status_skips_unknown_due_dates_and_non_urgent_medications(
    monkeypatch,
) -> None:
    """Unknown due dates should not create alerts and far doses should be ignored."""
    now = dt_util.now()
    profile = EnhancedHealthProfile(
        current_weight=20.0,
        current_medications=[
            {"name": "Tomorrow", "next_dose": (now + timedelta(days=1)).isoformat()}
        ],
        last_checkup_date=now - timedelta(days=30),
    )
    unknown_vaccine = VaccinationRecord(
        vaccine_type=VaccinationType.RABIES,
        next_due_date=None,
    )
    unknown_deworming = DewormingRecord(
        treatment_type=DewormingType.BROAD_SPECTRUM,
        next_due_date=None,
    )

    monkeypatch.setattr(
        profile,
        "get_overdue_vaccinations",
        lambda: [unknown_vaccine],
    )
    monkeypatch.setattr(
        profile,
        "get_due_soon_vaccinations",
        lambda: [unknown_vaccine],
    )
    monkeypatch.setattr(
        profile,
        "get_overdue_dewormings",
        lambda: [unknown_deworming],
    )
    monkeypatch.setattr(
        profile,
        "get_due_soon_dewormings",
        lambda: [unknown_deworming],
    )

    snapshot = EnhancedHealthCalculator.update_health_status(profile)

    assert snapshot["overall_score"] == 85
    assert snapshot["priority_alerts"] == []
    assert snapshot["upcoming_care"] == []
    assert snapshot["recommendations"] == []


def test_update_health_status_handles_no_due_soon_dewormings_branch() -> None:
    """Empty due-soon dewormings should skip reminder generation safely."""
    now = dt_util.now()
    profile = EnhancedHealthProfile(
        current_weight=22.0,
        dewormings=[
            DewormingRecord(
                treatment_type=DewormingType.BROAD_SPECTRUM,
                next_due_date=now - timedelta(days=5),
            )
        ],
        veterinary_appointments=[
            VeterinaryAppointment(
                appointment_date=now + timedelta(days=2),
                appointment_type="checkup",
                purpose="Follow-up",
            )
        ],
    )

    snapshot = EnhancedHealthCalculator.update_health_status(profile)

    assert any(alert["type"] == "deworming_overdue" for alert in snapshot["priority_alerts"])
    assert any(item["type"] == "vet_appointment" for item in snapshot["upcoming_care"])
    assert not any(item["type"] == "deworming_due" for item in snapshot["upcoming_care"])


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


def test_calculate_next_appointment_recommendation_keeps_age_default_for_unmatched_conditions() -> None:
    """Non-matching chronic conditions should keep the age-based interval."""
    now = dt_util.now()
    recommendation = EnhancedHealthCalculator.calculate_next_appointment_recommendation(
        EnhancedHealthProfile(
            current_weight=24.0,
            chronic_conditions=["skin_allergy"],
            last_checkup_date=now,
        ),
        dog_age_months=48,
    )

    assert recommendation["appointment_type"] == "annual_checkup"
    assert recommendation["urgency"] == "normal"
    assert 364 <= recommendation["days_until"] <= 365


def test_calculate_next_appointment_recommendation_covers_age_branches() -> None:
    """Appointment recommendations should adjust for puppy, adult, and senior dogs."""
    puppy_profile = EnhancedHealthProfile(current_weight=5.0)
    adult_profile = EnhancedHealthProfile(current_weight=20.0)
    senior_profile = EnhancedHealthProfile(
        current_weight=16.0,
        chronic_conditions=["kidney_disease"],
    )

    puppy = EnhancedHealthCalculator.calculate_next_appointment_recommendation(
        puppy_profile, dog_age_months=6
    )
    adult = EnhancedHealthCalculator.calculate_next_appointment_recommendation(
        adult_profile, dog_age_months=36
    )
    senior = EnhancedHealthCalculator.calculate_next_appointment_recommendation(
        senior_profile, dog_age_months=120
    )

    assert puppy["appointment_type"] == "puppy_checkup"
    assert 0 <= puppy["days_until"] <= 7
    assert adult["appointment_type"] == "annual_checkup"
    assert 0 <= adult["days_until"] <= 7
    assert senior["appointment_type"] == "condition_monitoring"
    assert 0 <= senior["days_until"] <= 7


def test_generate_vaccination_schedule_for_adult_without_risk_factors_is_empty() -> (
    None
):
    """Adult dogs without risk factors should not receive puppy-series entries.

    The puppy schedule should be skipped once the dog is older than one year.
    """
    current_date = dt_util.now()

    schedule = EnhancedHealthCalculator.generate_vaccination_schedule(
        current_date - timedelta(days=500),
        current_date=current_date,
        risk_factors=None,
    )

    assert schedule == []
