"""Enhanced Health Calculator with Vaccinations and Deworming Support.

ADDITIONS:
- Vaccination schedule tracking
- Deworming schedule management
- Medication reminders
- Health record timeline
- Veterinary appointment tracking

Quality Scale: Platinum target++
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
from typing import ClassVar

from homeassistant.util import dt as dt_util

from .types import (
  HealthAlertEntry,
  HealthAlertList,
  HealthAppointmentRecommendation,
  HealthMedicationQueue,
  HealthStatusSnapshot,
  HealthUpcomingCareEntry,
  HealthUpcomingCareQueue,
)
from .utils import ensure_local_datetime

_LOGGER = logging.getLogger(__name__)


class VaccinationType(Enum):
  """Core vaccination types for dogs."""  # noqa: E111

  # Core vaccines (recommended for all dogs)  # noqa: E114
  RABIES = "rabies"  # noqa: E111
  DHPP = "dhpp"  # Distemper, Hepatitis, Parvovirus, Parainfluenza  # noqa: E111
  DISTEMPER = "distemper"  # noqa: E111
  PARVOVIRUS = "parvovirus"  # noqa: E111
  ADENOVIRUS = "adenovirus"  # noqa: E111
  PARAINFLUENZA = "parainfluenza"  # noqa: E111

  # Non-core vaccines (based on risk factors)  # noqa: E114
  BORDETELLA = "bordetella"  # Kennel cough  # noqa: E111
  LYME_DISEASE = "lyme_disease"  # noqa: E111
  CANINE_INFLUENZA = "canine_influenza"  # noqa: E111
  LEPTOSPIROSIS = "leptospirosis"  # noqa: E111
  CORONAVIRUS = "coronavirus"  # noqa: E111


class DewormingType(Enum):
  """Types of deworming treatments."""  # noqa: E111

  BROAD_SPECTRUM = "broad_spectrum"  # noqa: E111
  ROUNDWORM = "roundworm"  # noqa: E111
  HOOKWORM = "hookworm"  # noqa: E111
  WHIPWORM = "whipworm"  # noqa: E111
  TAPEWORM = "tapeworm"  # noqa: E111
  HEARTWORM_PREVENTION = "heartworm_prevention"  # noqa: E111
  FLEA_TICK_PREVENTION = "flea_tick_prevention"  # noqa: E111


class HealthEventStatus(Enum):
  """Status of health events."""  # noqa: E111

  OVERDUE = "overdue"  # noqa: E111
  DUE_SOON = "due_soon"  # Within 2 weeks  # noqa: E111
  SCHEDULED = "scheduled"  # noqa: E111
  COMPLETED = "completed"  # noqa: E111
  POSTPONED = "postponed"  # noqa: E111


@dataclass
class VaccinationRecord:
  """Complete vaccination record."""  # noqa: E111

  vaccine_type: VaccinationType  # noqa: E111
  date_given: datetime | None = None  # noqa: E111
  next_due_date: datetime | None = None  # noqa: E111
  veterinarian: str | None = None  # noqa: E111
  batch_number: str | None = None  # noqa: E111
  status: HealthEventStatus = HealthEventStatus.DUE_SOON  # noqa: E111
  notes: str = ""  # noqa: E111
  reminders_sent: int = 0  # noqa: E111

  def is_overdue(self) -> bool:  # noqa: E111
    """Check if vaccination is overdue."""
    if not self.next_due_date:
      return False  # noqa: E111
    return dt_util.now() > self.next_due_date

  def days_until_due(self) -> int | None:  # noqa: E111
    """Calculate days until next vaccination is due."""
    if not self.next_due_date:
      return None  # noqa: E111
    delta = self.next_due_date - dt_util.now()
    return delta.days


@dataclass
class DewormingRecord:
  """Complete deworming treatment record."""  # noqa: E111

  treatment_type: DewormingType  # noqa: E111
  date_given: datetime | None = None  # noqa: E111
  next_due_date: datetime | None = None  # noqa: E111
  medication_name: str | None = None  # noqa: E111
  dosage: str | None = None  # noqa: E111
  weight_at_treatment: float | None = None  # noqa: E111
  status: HealthEventStatus = HealthEventStatus.DUE_SOON  # noqa: E111
  notes: str = ""  # noqa: E111
  reminders_sent: int = 0  # noqa: E111

  def is_overdue(self) -> bool:  # noqa: E111
    """Check if deworming is overdue."""
    if not self.next_due_date:
      return False  # noqa: E111
    return dt_util.now() > self.next_due_date

  def days_until_due(self) -> int | None:  # noqa: E111
    """Calculate days until next treatment is due."""
    if not self.next_due_date:
      return None  # noqa: E111
    delta = self.next_due_date - dt_util.now()
    return delta.days


@dataclass
class VeterinaryAppointment:
  """Veterinary appointment tracking."""  # noqa: E111

  appointment_date: datetime  # noqa: E111
  appointment_type: str  # "checkup", "vaccination", "illness", "surgery"  # noqa: E111
  veterinarian: str | None = None  # noqa: E111
  clinic: str | None = None  # noqa: E111
  purpose: str = ""  # noqa: E111
  completed: bool = False  # noqa: E111
  notes: str = ""  # noqa: E111
  follow_up_needed: bool = False  # noqa: E111
  follow_up_date: datetime | None = None  # noqa: E111


@dataclass
class EnhancedHealthProfile:
  """Enhanced health profile with comprehensive medical tracking."""  # noqa: E111

  # Basic health metrics (from existing HealthMetrics)  # noqa: E114
  current_weight: float  # noqa: E111
  ideal_weight: float | None = None  # noqa: E111
  body_condition_score: int | None = None  # 1-9 scale  # noqa: E111

  # NEW: Vaccination tracking  # noqa: E114
  vaccinations: list[VaccinationRecord] = field(default_factory=list)  # noqa: E111
  vaccination_schedule: dict[str, timedelta] = field(default_factory=dict)  # noqa: E111

  # NEW: Deworming tracking  # noqa: E114
  dewormings: list[DewormingRecord] = field(default_factory=list)  # noqa: E111
  deworming_schedule: dict[str, timedelta] = field(default_factory=dict)  # noqa: E111

  # NEW: Veterinary care  # noqa: E114
  veterinary_appointments: list[VeterinaryAppointment] = field(  # noqa: E111
    default_factory=list,
  )
  primary_veterinarian: str = ""  # noqa: E111
  emergency_contact: str = ""  # noqa: E111

  # NEW: Medication tracking  # noqa: E114
  current_medications: HealthMedicationQueue = field(default_factory=list)  # noqa: E111
  medication_allergies: list[str] = field(default_factory=list)  # noqa: E111

  # NEW: Health conditions and history  # noqa: E114
  chronic_conditions: list[str] = field(default_factory=list)  # noqa: E111
  health_alerts: HealthAlertList = field(default_factory=list)  # noqa: E111
  last_checkup_date: datetime | None = None  # noqa: E111

  def get_overdue_vaccinations(self) -> list[VaccinationRecord]:  # noqa: E111
    """Get all overdue vaccinations."""
    return [v for v in self.vaccinations if v.is_overdue()]

  def get_due_soon_vaccinations(  # noqa: E111
    self,
    days_ahead: int = 14,
  ) -> list[VaccinationRecord]:
    """Get vaccinations due within specified days."""
    return [
      v
      for v in self.vaccinations
      if (due := v.days_until_due()) is not None and 0 <= due <= days_ahead
    ]

  def get_overdue_dewormings(self) -> list[DewormingRecord]:  # noqa: E111
    """Get all overdue deworming treatments."""
    return [d for d in self.dewormings if d.is_overdue()]

  def get_due_soon_dewormings(self, days_ahead: int = 14) -> list[DewormingRecord]:  # noqa: E111
    """Get dewormings due within specified days."""
    return [
      d
      for d in self.dewormings
      if (due := d.days_until_due()) is not None and 0 <= due <= days_ahead
    ]


class EnhancedHealthCalculator:
  """Enhanced health calculator with comprehensive medical tracking."""  # noqa: E111

  # Standard vaccination schedules (in months)  # noqa: E114
  PUPPY_VACCINATION_SCHEDULE: ClassVar[dict[VaccinationType, list[int]]] = {  # noqa: E111
    VaccinationType.DHPP: [6, 9, 12, 16],  # weeks for puppies
    VaccinationType.RABIES: [16, 68],  # 16 weeks initial, then yearly
    VaccinationType.BORDETELLA: [12, 16, 64],  # Optional but recommended
  }

  # Adult vaccination schedules (in months)  # noqa: E114
  ADULT_VACCINATION_SCHEDULE: ClassVar[dict[VaccinationType, int]] = {  # noqa: E111
    VaccinationType.DHPP: 36,  # Every 3 years after puppy series
    VaccinationType.RABIES: 12,  # Yearly or every 3 years depending on vaccine
    VaccinationType.BORDETELLA: 12,  # Yearly
    VaccinationType.LYME_DISEASE: 12,  # Yearly in endemic areas
  }

  # Deworming schedules by age and risk  # noqa: E114
  PUPPY_DEWORMING_SCHEDULE: ClassVar[dict[DewormingType, timedelta]] = {  # noqa: E111
    DewormingType.BROAD_SPECTRUM: timedelta(
      weeks=2,
    ),  # Every 2 weeks until 6 months
    DewormingType.HEARTWORM_PREVENTION: timedelta(days=30),  # Monthly
  }

  ADULT_DEWORMING_SCHEDULE: ClassVar[dict[DewormingType, timedelta]] = {  # noqa: E111
    DewormingType.BROAD_SPECTRUM: timedelta(days=90),  # Every 3 months
    DewormingType.HEARTWORM_PREVENTION: timedelta(days=30),  # Monthly
    DewormingType.FLEA_TICK_PREVENTION: timedelta(days=30),  # Monthly
  }

  @staticmethod  # noqa: E111
  def generate_vaccination_schedule(  # noqa: E111
    birth_date: datetime,
    current_date: datetime | None = None,
    risk_factors: list[str] | None = None,
  ) -> list[VaccinationRecord]:
    """Generate complete vaccination schedule for a dog."""
    if current_date is None:
      current_date = dt_util.now()  # noqa: E111

    risk_factors = risk_factors or []
    age_weeks = (current_date - birth_date).days // 7

    schedule = []

    # Core vaccines for puppies
    if age_weeks < 52:  # Under 1 year
      for (  # noqa: E111
        vaccine_type,
        week_schedule,
      ) in EnhancedHealthCalculator.PUPPY_VACCINATION_SCHEDULE.items():
        for week in week_schedule:
          due_date = birth_date + timedelta(weeks=week)  # noqa: E111
          status = (  # noqa: E111
            HealthEventStatus.OVERDUE
            if due_date < current_date
            else HealthEventStatus.DUE_SOON
            if due_date <= current_date + timedelta(days=14)
            else HealthEventStatus.SCHEDULED
          )

          schedule.append(  # noqa: E111
            VaccinationRecord(
              vaccine_type=vaccine_type,
              next_due_date=due_date,
              status=status,
              notes=f"Puppy series - {week} weeks old",
            ),
          )

    # Risk-based vaccines
    if "boarding" in risk_factors or "daycare" in risk_factors:
      # Bordetella more frequently  # noqa: E114
      next_bordetella = current_date + timedelta(days=365)  # noqa: E111
      schedule.append(  # noqa: E111
        VaccinationRecord(
          vaccine_type=VaccinationType.BORDETELLA,
          next_due_date=next_bordetella,
          status=HealthEventStatus.SCHEDULED,
          notes="High-risk environment",
        ),
      )

    if "tick_area" in risk_factors:
      # Lyme disease vaccine  # noqa: E114
      next_lyme = current_date + timedelta(days=365)  # noqa: E111
      schedule.append(  # noqa: E111
        VaccinationRecord(
          vaccine_type=VaccinationType.LYME_DISEASE,
          next_due_date=next_lyme,
          status=HealthEventStatus.SCHEDULED,
          notes="Tick-endemic area",
        ),
      )

    return schedule

  @staticmethod  # noqa: E111
  def generate_deworming_schedule(  # noqa: E111
    birth_date: datetime,
    current_date: datetime | None = None,
    lifestyle_factors: list[str] | None = None,
  ) -> list[DewormingRecord]:
    """Generate complete deworming schedule for a dog."""
    if current_date is None:
      current_date = dt_util.now()  # noqa: E111

    lifestyle_factors = lifestyle_factors or []
    age_months = (current_date - birth_date).days // 30

    schedule = []

    # Puppy deworming (more frequent)
    if age_months < 6:
      # Every 2 weeks until 6 months  # noqa: E114
      weeks_since_birth = (current_date - birth_date).days // 7  # noqa: E111
      for week in range(  # noqa: E111
        2, min(weeks_since_birth + 8, 26), 2
      ):  # Every 2 weeks
        due_date = birth_date + timedelta(weeks=week)
        # Only next 2 months
        if due_date <= current_date + timedelta(days=60):
          schedule.append(  # noqa: E111
            DewormingRecord(
              treatment_type=DewormingType.BROAD_SPECTRUM,
              next_due_date=due_date,
              status=HealthEventStatus.SCHEDULED,
              notes="Puppy deworming schedule",
            ),
          )

    # Adult deworming schedule
    else:
      # Every 3 months for broad spectrum  # noqa: E114
      next_broad_spectrum = current_date + timedelta(days=90)  # noqa: E111
      schedule.append(  # noqa: E111
        DewormingRecord(
          treatment_type=DewormingType.BROAD_SPECTRUM,
          next_due_date=next_broad_spectrum,
          status=HealthEventStatus.SCHEDULED,
          notes="Adult maintenance deworming",
        ),
      )

    # Monthly heartworm prevention (all ages)
    next_heartworm = current_date + timedelta(days=30)
    schedule.append(
      DewormingRecord(
        treatment_type=DewormingType.HEARTWORM_PREVENTION,
        next_due_date=next_heartworm,
        status=HealthEventStatus.SCHEDULED,
        notes="Monthly heartworm prevention",
      ),
    )

    # Lifestyle-based adjustments
    if "outdoor_frequent" in lifestyle_factors:
      # More frequent broad spectrum  # noqa: E114
      for i in range(1, 5):  # Next 4 months  # noqa: E111
        due_date = current_date + timedelta(days=30 * i)
        schedule.append(
          DewormingRecord(
            treatment_type=DewormingType.FLEA_TICK_PREVENTION,
            next_due_date=due_date,
            status=HealthEventStatus.SCHEDULED,
            notes="High outdoor exposure",
          ),
        )

    return schedule

  @staticmethod  # noqa: E111
  def update_health_status(  # noqa: E111
    health_profile: EnhancedHealthProfile,
  ) -> HealthStatusSnapshot:
    """Update overall health status with comprehensive analysis."""
    current_date = dt_util.now()

    priority_alerts: HealthAlertList = []
    upcoming_care: HealthUpcomingCareQueue = []
    recommendations: list[str] = []
    health_status: HealthStatusSnapshot = {
      "overall_score": 100,
      "priority_alerts": priority_alerts,
      "upcoming_care": upcoming_care,
      "recommendations": recommendations,
      "last_updated": current_date.isoformat(),
    }

    # Check vaccination status
    overdue_vaccines = health_profile.get_overdue_vaccinations()
    due_soon_vaccines = health_profile.get_due_soon_vaccinations()

    if overdue_vaccines:
      health_status["overall_score"] -= len(overdue_vaccines) * 10  # noqa: E111
      for vaccine in overdue_vaccines:  # noqa: E111
        days_until_due = vaccine.days_until_due()
        if days_until_due is None:
          _LOGGER.debug(  # noqa: E111
            "Skipping overdue vaccination alert for %s because the next due date is unknown",  # noqa: E501
            vaccine.vaccine_type,
          )
          continue  # noqa: E111

        message = (
          f"{vaccine.vaccine_type.value.title()} vaccination is "
          f"{abs(days_until_due)} days overdue"
        )
        overdue_vaccine_alert: HealthAlertEntry = {
          "type": "vaccination_overdue",
          "message": message,
          "severity": "high",
          "action_required": True,
        }
        priority_alerts.append(overdue_vaccine_alert)

    if due_soon_vaccines:
      for vaccine in due_soon_vaccines:  # noqa: E111
        days_until_due = vaccine.days_until_due()
        if days_until_due is None:
          _LOGGER.debug(  # noqa: E111
            "Skipping due-soon vaccination reminder for %s because the next due date is unknown",  # noqa: E501
            vaccine.vaccine_type,
          )
          continue  # noqa: E111

        message = (
          f"{vaccine.vaccine_type.value.title()} vaccination due in "
          f"{days_until_due} days"
        )
        vaccination_entry: HealthUpcomingCareEntry = {
          "type": "vaccination_due",
          "message": message,
          "due_date": vaccine.next_due_date.isoformat()
          if vaccine.next_due_date
          else None,
          "priority": "high",
        }
        upcoming_care.append(vaccination_entry)

    # Check deworming status
    overdue_dewormings = health_profile.get_overdue_dewormings()
    due_soon_dewormings = health_profile.get_due_soon_dewormings()

    if overdue_dewormings:
      health_status["overall_score"] -= len(overdue_dewormings) * 5  # noqa: E111
      for deworming in overdue_dewormings:  # noqa: E111
        days_until_due = deworming.days_until_due()
        if days_until_due is None:
          _LOGGER.debug(  # noqa: E111
            "Skipping overdue deworming alert for %s because the next due date is unknown",  # noqa: E501
            deworming.treatment_type,
          )
          continue  # noqa: E111

        treatment_name = deworming.treatment_type.value.replace(
          "_",
          " ",
        ).title()
        message = f"{treatment_name} treatment is {abs(days_until_due)} days overdue"
        overdue_deworming_alert: HealthAlertEntry = {
          "type": "deworming_overdue",
          "message": message,
          "severity": "medium",
          "action_required": True,
        }
        priority_alerts.append(overdue_deworming_alert)

    if due_soon_dewormings:
      for deworming in due_soon_dewormings:  # noqa: E111
        days_until_due = deworming.days_until_due()
        if days_until_due is None:
          _LOGGER.debug(  # noqa: E111
            "Skipping due-soon deworming reminder for %s because the next due date is unknown",  # noqa: E501
            deworming.treatment_type,
          )
          continue  # noqa: E111

        treatment_name = deworming.treatment_type.value.replace(
          "_",
          " ",
        ).title()
        message = f"{treatment_name} treatment due in {days_until_due} days"
        deworming_entry: HealthUpcomingCareEntry = {
          "type": "deworming_due",
          "message": message,
          "due_date": deworming.next_due_date.isoformat()
          if deworming.next_due_date
          else None,
          "priority": "medium",
        }
        upcoming_care.append(deworming_entry)

    # Check for upcoming veterinary appointments
    upcoming_appointments = [
      apt
      for apt in health_profile.veterinary_appointments
      if not apt.completed and apt.appointment_date > current_date
    ]

    for appointment in upcoming_appointments[:3]:  # Next 3 appointments
      days_until = (appointment.appointment_date - current_date).days  # noqa: E111
      upcoming_care.append(  # noqa: E111
        {
          "type": "vet_appointment",
          "message": (
            f"{appointment.appointment_type.title()} appointment in {days_until} days"
          ),
          "due_date": appointment.appointment_date.isoformat(),
          "priority": "medium",
          "details": appointment.purpose,
        },
      )

    # Generate recommendations
    if health_profile.last_checkup_date:
      days_since_checkup = (current_date - health_profile.last_checkup_date).days  # noqa: E111
      if days_since_checkup > 365:  # noqa: E111
        recommendations.append(
          f"Annual checkup recommended - last visit was {days_since_checkup} days ago",
        )
        health_status["overall_score"] -= 5
    else:
      recommendations.append(  # noqa: E111
        "Schedule initial veterinary checkup to establish baseline health",
      )
      health_status["overall_score"] -= 10  # noqa: E111

    # Medication reminders
    for medication in health_profile.current_medications:
      next_dose_value = medication.get("next_dose")  # noqa: E111
      if not next_dose_value:  # noqa: E111
        continue

      next_dose = ensure_local_datetime(next_dose_value)  # noqa: E111
      if next_dose is None:  # noqa: E111
        continue

      if next_dose <= current_date + timedelta(hours=2):  # noqa: E111
        medication_alert: HealthAlertEntry = {
          "type": "medication_due",
          "message": f"{medication['name']} dose due soon",
          "severity": "high",
          "action_required": True,
        }
        priority_alerts.append(medication_alert)

    # Final score adjustment
    health_status["overall_score"] = max(
      0,
      min(100, health_status["overall_score"]),
    )

    return health_status

  @staticmethod  # noqa: E111
  def calculate_next_appointment_recommendation(  # noqa: E111
    health_profile: EnhancedHealthProfile,
    dog_age_months: int,
  ) -> HealthAppointmentRecommendation:
    """Calculate when the next veterinary appointment should be scheduled."""
    current_date = dt_util.now()

    # Base recommendation frequencies by age
    if dog_age_months < 12:  # Puppy
      base_interval = timedelta(days=30)  # Monthly for puppies  # noqa: E111
      appointment_type = "puppy_checkup"  # noqa: E111
    elif dog_age_months < 84:  # Adult (under 7 years)
      base_interval = timedelta(days=365)  # Yearly for adults  # noqa: E111
      appointment_type = "annual_checkup"  # noqa: E111
    else:  # Senior
      base_interval = timedelta(days=180)  # Every 6 months for seniors  # noqa: E111
      appointment_type = "senior_checkup"  # noqa: E111

    # Adjust based on health conditions
    if health_profile.chronic_conditions:
      if "diabetes" in health_profile.chronic_conditions:  # noqa: E111
        base_interval = timedelta(days=90)  # Every 3 months
        appointment_type = "diabetes_monitoring"
      elif any(  # noqa: E111
        condition in ["heart_disease", "kidney_disease"]
        for condition in health_profile.chronic_conditions
      ):
        base_interval = timedelta(days=120)  # Every 4 months
        appointment_type = "condition_monitoring"

    # Check last checkup
    if health_profile.last_checkup_date:
      next_recommended = health_profile.last_checkup_date + base_interval  # noqa: E111
    else:
      next_recommended = current_date + timedelta(  # noqa: E111
        days=7,
      )  # Schedule soon if never seen

    recommendation: HealthAppointmentRecommendation = {
      "next_appointment_date": next_recommended.isoformat(),
      "appointment_type": appointment_type,
      "reason": f"Based on age ({dog_age_months} months) and health conditions",
      "urgency": "high" if next_recommended < current_date else "normal",
      "days_until": (next_recommended - current_date).days,
    }
    return recommendation
