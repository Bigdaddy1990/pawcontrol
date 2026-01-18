"""Unit tests for health enhancement telemetry typing."""

from __future__ import annotations

from datetime import timedelta

from custom_components.pawcontrol.health_enhancements import (
  DewormingRecord,
  DewormingType,
  EnhancedHealthCalculator,
  EnhancedHealthProfile,
  VaccinationRecord,
  VaccinationType,
)
from homeassistant.util import dt as dt_util


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
