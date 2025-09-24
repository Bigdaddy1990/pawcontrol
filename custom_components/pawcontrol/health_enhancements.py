"""Enhanced Health Calculator with Vaccinations and Deworming Support.

ADDITIONS:
- Vaccination schedule tracking
- Deworming schedule management
- Medication reminders
- Health record timeline
- Veterinary appointment tracking

Quality Scale: Platinum++
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from homeassistant.util import dt as dt_util

from .utils import ensure_local_datetime

_LOGGER = logging.getLogger(__name__)


class VaccinationType(Enum):
    """Core vaccination types for dogs."""

    # Core vaccines (recommended for all dogs)
    RABIES = "rabies"
    DHPP = "dhpp"  # Distemper, Hepatitis, Parvovirus, Parainfluenza
    DISTEMPER = "distemper"
    PARVOVIRUS = "parvovirus"
    ADENOVIRUS = "adenovirus"
    PARAINFLUENZA = "parainfluenza"

    # Non-core vaccines (based on risk factors)
    BORDETELLA = "bordetella"  # Kennel cough
    LYME_DISEASE = "lyme_disease"
    CANINE_INFLUENZA = "canine_influenza"
    LEPTOSPIROSIS = "leptospirosis"
    CORONAVIRUS = "coronavirus"


class DewormingType(Enum):
    """Types of deworming treatments."""

    BROAD_SPECTRUM = "broad_spectrum"
    ROUNDWORM = "roundworm"
    HOOKWORM = "hookworm"
    WHIPWORM = "whipworm"
    TAPEWORM = "tapeworm"
    HEARTWORM_PREVENTION = "heartworm_prevention"
    FLEA_TICK_PREVENTION = "flea_tick_prevention"


class HealthEventStatus(Enum):
    """Status of health events."""

    OVERDUE = "overdue"
    DUE_SOON = "due_soon"  # Within 2 weeks
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    POSTPONED = "postponed"


@dataclass
class VaccinationRecord:
    """Complete vaccination record."""

    vaccine_type: VaccinationType
    date_given: datetime | None = None
    next_due_date: datetime | None = None
    veterinarian: str | None = None
    batch_number: str | None = None
    status: HealthEventStatus = HealthEventStatus.DUE_SOON
    notes: str = ""
    reminders_sent: int = 0

    def is_overdue(self) -> bool:
        """Check if vaccination is overdue."""
        if not self.next_due_date:
            return False
        return dt_util.now() > self.next_due_date

    def days_until_due(self) -> int | None:
        """Calculate days until next vaccination is due."""
        if not self.next_due_date:
            return None
        delta = self.next_due_date - dt_util.now()
        return delta.days


@dataclass
class DewormingRecord:
    """Complete deworming treatment record."""

    treatment_type: DewormingType
    date_given: datetime | None = None
    next_due_date: datetime | None = None
    medication_name: str | None = None
    dosage: str | None = None
    weight_at_treatment: float | None = None
    status: HealthEventStatus = HealthEventStatus.DUE_SOON
    notes: str = ""
    reminders_sent: int = 0

    def is_overdue(self) -> bool:
        """Check if deworming is overdue."""
        if not self.next_due_date:
            return False
        return dt_util.now() > self.next_due_date

    def days_until_due(self) -> int | None:
        """Calculate days until next treatment is due."""
        if not self.next_due_date:
            return None
        delta = self.next_due_date - dt_util.now()
        return delta.days


@dataclass
class VeterinaryAppointment:
    """Veterinary appointment tracking."""

    appointment_date: datetime
    appointment_type: str  # "checkup", "vaccination", "illness", "surgery"
    veterinarian: str | None = None
    clinic: str | None = None
    purpose: str = ""
    completed: bool = False
    notes: str = ""
    follow_up_needed: bool = False
    follow_up_date: datetime | None = None


@dataclass
class EnhancedHealthProfile:
    """Enhanced health profile with comprehensive medical tracking."""

    # Basic health metrics (from existing HealthMetrics)
    current_weight: float
    ideal_weight: float | None = None
    body_condition_score: int | None = None  # 1-9 scale

    # NEW: Vaccination tracking
    vaccinations: list[VaccinationRecord] = field(default_factory=list)
    vaccination_schedule: dict[str, timedelta] = field(default_factory=dict)

    # NEW: Deworming tracking
    dewormings: list[DewormingRecord] = field(default_factory=list)
    deworming_schedule: dict[str, timedelta] = field(default_factory=dict)

    # NEW: Veterinary care
    veterinary_appointments: list[VeterinaryAppointment] = field(default_factory=list)
    primary_veterinarian: str = ""
    emergency_contact: str = ""

    # NEW: Medication tracking
    current_medications: list[dict[str, Any]] = field(default_factory=list)
    medication_allergies: list[str] = field(default_factory=list)

    # NEW: Health conditions and history
    chronic_conditions: list[str] = field(default_factory=list)
    health_alerts: list[dict[str, Any]] = field(default_factory=list)
    last_checkup_date: datetime | None = None

    def get_overdue_vaccinations(self) -> list[VaccinationRecord]:
        """Get all overdue vaccinations."""
        return [v for v in self.vaccinations if v.is_overdue()]

    def get_due_soon_vaccinations(
        self, days_ahead: int = 14
    ) -> list[VaccinationRecord]:
        """Get vaccinations due within specified days."""
        return [
            v
            for v in self.vaccinations
            if v.days_until_due() is not None and 0 <= v.days_until_due() <= days_ahead
        ]

    def get_overdue_dewormings(self) -> list[DewormingRecord]:
        """Get all overdue deworming treatments."""
        return [d for d in self.dewormings if d.is_overdue()]

    def get_due_soon_dewormings(self, days_ahead: int = 14) -> list[DewormingRecord]:
        """Get dewormings due within specified days."""
        return [
            d
            for d in self.dewormings
            if d.days_until_due() is not None and 0 <= d.days_until_due() <= days_ahead
        ]


class EnhancedHealthCalculator:
    """Enhanced health calculator with comprehensive medical tracking."""

    # Standard vaccination schedules (in months)
    PUPPY_VACCINATION_SCHEDULE = {  # noqa: RUF012
        VaccinationType.DHPP: [6, 9, 12, 16],  # weeks for puppies
        VaccinationType.RABIES: [16, 68],  # 16 weeks initial, then yearly
        VaccinationType.BORDETELLA: [12, 16, 64],  # Optional but recommended
    }

    # Adult vaccination schedules (in months)
    ADULT_VACCINATION_SCHEDULE = {  # noqa: RUF012
        VaccinationType.DHPP: 36,  # Every 3 years after puppy series
        VaccinationType.RABIES: 12,  # Yearly or every 3 years depending on vaccine
        VaccinationType.BORDETELLA: 12,  # Yearly
        VaccinationType.LYME_DISEASE: 12,  # Yearly in endemic areas
    }

    # Deworming schedules by age and risk
    PUPPY_DEWORMING_SCHEDULE = {  # noqa: RUF012
        DewormingType.BROAD_SPECTRUM: timedelta(
            weeks=2
        ),  # Every 2 weeks until 6 months
        DewormingType.HEARTWORM_PREVENTION: timedelta(days=30),  # Monthly
    }

    ADULT_DEWORMING_SCHEDULE = {  # noqa: RUF012
        DewormingType.BROAD_SPECTRUM: timedelta(days=90),  # Every 3 months
        DewormingType.HEARTWORM_PREVENTION: timedelta(days=30),  # Monthly
        DewormingType.FLEA_TICK_PREVENTION: timedelta(days=30),  # Monthly
    }

    @staticmethod
    def generate_vaccination_schedule(
        birth_date: datetime,
        current_date: datetime | None = None,
        risk_factors: list[str] | None = None,
    ) -> list[VaccinationRecord]:
        """Generate complete vaccination schedule for a dog."""
        if current_date is None:
            current_date = dt_util.now()

        risk_factors = risk_factors or []
        age_weeks = (current_date - birth_date).days // 7

        schedule = []

        # Core vaccines for puppies
        if age_weeks < 52:  # Under 1 year
            for (
                vaccine_type,
                week_schedule,
            ) in EnhancedHealthCalculator.PUPPY_VACCINATION_SCHEDULE.items():
                for week in week_schedule:
                    due_date = birth_date + timedelta(weeks=week)
                    status = (
                        HealthEventStatus.OVERDUE
                        if due_date < current_date
                        else HealthEventStatus.DUE_SOON
                        if due_date <= current_date + timedelta(days=14)
                        else HealthEventStatus.SCHEDULED
                    )

                    schedule.append(
                        VaccinationRecord(
                            vaccine_type=vaccine_type,
                            next_due_date=due_date,
                            status=status,
                            notes=f"Puppy series - {week} weeks old",
                        )
                    )

        # Risk-based vaccines
        if "boarding" in risk_factors or "daycare" in risk_factors:
            # Bordetella more frequently
            next_bordetella = current_date + timedelta(days=365)
            schedule.append(
                VaccinationRecord(
                    vaccine_type=VaccinationType.BORDETELLA,
                    next_due_date=next_bordetella,
                    status=HealthEventStatus.SCHEDULED,
                    notes="High-risk environment",
                )
            )

        if "tick_area" in risk_factors:
            # Lyme disease vaccine
            next_lyme = current_date + timedelta(days=365)
            schedule.append(
                VaccinationRecord(
                    vaccine_type=VaccinationType.LYME_DISEASE,
                    next_due_date=next_lyme,
                    status=HealthEventStatus.SCHEDULED,
                    notes="Tick-endemic area",
                )
            )

        return schedule

    @staticmethod
    def generate_deworming_schedule(
        birth_date: datetime,
        current_date: datetime | None = None,
        lifestyle_factors: list[str] | None = None,
    ) -> list[DewormingRecord]:
        """Generate complete deworming schedule for a dog."""
        if current_date is None:
            current_date = dt_util.now()

        lifestyle_factors = lifestyle_factors or []
        age_months = (current_date - birth_date).days // 30

        schedule = []

        # Puppy deworming (more frequent)
        if age_months < 6:
            # Every 2 weeks until 6 months
            weeks_since_birth = (current_date - birth_date).days // 7
            for week in range(2, min(weeks_since_birth + 8, 26), 2):  # Every 2 weeks
                due_date = birth_date + timedelta(weeks=week)
                if due_date <= current_date + timedelta(days=60):  # Only next 2 months
                    schedule.append(
                        DewormingRecord(
                            treatment_type=DewormingType.BROAD_SPECTRUM,
                            next_due_date=due_date,
                            status=HealthEventStatus.SCHEDULED,
                            notes="Puppy deworming schedule",
                        )
                    )

        # Adult deworming schedule
        else:
            # Every 3 months for broad spectrum
            next_broad_spectrum = current_date + timedelta(days=90)
            schedule.append(
                DewormingRecord(
                    treatment_type=DewormingType.BROAD_SPECTRUM,
                    next_due_date=next_broad_spectrum,
                    status=HealthEventStatus.SCHEDULED,
                    notes="Adult maintenance deworming",
                )
            )

        # Monthly heartworm prevention (all ages)
        next_heartworm = current_date + timedelta(days=30)
        schedule.append(
            DewormingRecord(
                treatment_type=DewormingType.HEARTWORM_PREVENTION,
                next_due_date=next_heartworm,
                status=HealthEventStatus.SCHEDULED,
                notes="Monthly heartworm prevention",
            )
        )

        # Lifestyle-based adjustments
        if "outdoor_frequent" in lifestyle_factors:
            # More frequent broad spectrum
            for i in range(1, 5):  # Next 4 months
                due_date = current_date + timedelta(days=30 * i)
                schedule.append(
                    DewormingRecord(
                        treatment_type=DewormingType.FLEA_TICK_PREVENTION,
                        next_due_date=due_date,
                        status=HealthEventStatus.SCHEDULED,
                        notes="High outdoor exposure",
                    )
                )

        return schedule

    @staticmethod
    def update_health_status(health_profile: EnhancedHealthProfile) -> dict[str, Any]:
        """Update overall health status with comprehensive analysis."""
        current_date = dt_util.now()

        health_status = {
            "overall_score": 100,
            "priority_alerts": [],
            "upcoming_care": [],
            "recommendations": [],
            "last_updated": current_date.isoformat(),
        }

        # Check vaccination status
        overdue_vaccines = health_profile.get_overdue_vaccinations()
        due_soon_vaccines = health_profile.get_due_soon_vaccinations()

        if overdue_vaccines:
            health_status["overall_score"] -= len(overdue_vaccines) * 10
            for vaccine in overdue_vaccines:
                days_until_due = vaccine.days_until_due()
                if days_until_due is None:
                    _LOGGER.debug(
                        "Skipping overdue vaccination alert for %s because the next due date is unknown",
                        vaccine.vaccine_type,
                    )
                    continue

                message = (
                    f"{vaccine.vaccine_type.value.title()} vaccination is "
                    f"{abs(days_until_due)} days overdue"
                )
                health_status["priority_alerts"].append(
                    {
                        "type": "vaccination_overdue",
                        "message": message,
                        "severity": "high",
                        "action_required": True,
                    }
                )

        if due_soon_vaccines:
            for vaccine in due_soon_vaccines:
                days_until_due = vaccine.days_until_due()
                if days_until_due is None:
                    _LOGGER.debug(
                        "Skipping due-soon vaccination reminder for %s because the next due date is unknown",
                        vaccine.vaccine_type,
                    )
                    continue

                message = (
                    f"{vaccine.vaccine_type.value.title()} vaccination due in "
                    f"{days_until_due} days"
                )
                health_status["upcoming_care"].append(
                    {
                        "type": "vaccination_due",
                        "message": message,
                        "due_date": vaccine.next_due_date.isoformat()
                        if vaccine.next_due_date
                        else None,
                        "priority": "high",
                    }
                )

        # Check deworming status
        overdue_dewormings = health_profile.get_overdue_dewormings()
        due_soon_dewormings = health_profile.get_due_soon_dewormings()

        if overdue_dewormings:
            health_status["overall_score"] -= len(overdue_dewormings) * 5
            for deworming in overdue_dewormings:
                days_until_due = deworming.days_until_due()
                if days_until_due is None:
                    _LOGGER.debug(
                        "Skipping overdue deworming alert for %s because the next due date is unknown",
                        deworming.treatment_type,
                    )
                    continue

                treatment_name = deworming.treatment_type.value.replace(
                    "_", " "
                ).title()
                message = (
                    f"{treatment_name} treatment is {abs(days_until_due)} days overdue"
                )
                health_status["priority_alerts"].append(
                    {
                        "type": "deworming_overdue",
                        "message": message,
                        "severity": "medium",
                        "action_required": True,
                    }
                )

        if due_soon_dewormings:
            for deworming in due_soon_dewormings:
                days_until_due = deworming.days_until_due()
                if days_until_due is None:
                    _LOGGER.debug(
                        "Skipping due-soon deworming reminder for %s because the next due date is unknown",
                        deworming.treatment_type,
                    )
                    continue

                treatment_name = deworming.treatment_type.value.replace(
                    "_", " "
                ).title()
                message = f"{treatment_name} treatment due in {days_until_due} days"
                health_status["upcoming_care"].append(
                    {
                        "type": "deworming_due",
                        "message": message,
                        "due_date": deworming.next_due_date.isoformat()
                        if deworming.next_due_date
                        else None,
                        "priority": "medium",
                    }
                )

        # Check for upcoming veterinary appointments
        upcoming_appointments = [
            apt
            for apt in health_profile.veterinary_appointments
            if not apt.completed and apt.appointment_date > current_date
        ]

        for appointment in upcoming_appointments[:3]:  # Next 3 appointments
            days_until = (appointment.appointment_date - current_date).days
            health_status["upcoming_care"].append(
                {
                    "type": "vet_appointment",
                    "message": f"{appointment.appointment_type.title()} appointment in {days_until} days",
                    "due_date": appointment.appointment_date.isoformat(),
                    "priority": "medium",
                    "details": appointment.purpose,
                }
            )

        # Generate recommendations
        if health_profile.last_checkup_date:
            days_since_checkup = (current_date - health_profile.last_checkup_date).days
            if days_since_checkup > 365:
                health_status["recommendations"].append(
                    f"Annual checkup recommended - last visit was {days_since_checkup} days ago"
                )
                health_status["overall_score"] -= 5
        else:
            health_status["recommendations"].append(
                "Schedule initial veterinary checkup to establish baseline health"
            )
            health_status["overall_score"] -= 10

        # Medication reminders
        for medication in health_profile.current_medications:
            if not medication.get("next_dose"):
                continue

            next_dose = ensure_local_datetime(medication["next_dose"])
            if next_dose is None:
                continue

            if next_dose <= current_date + timedelta(hours=2):
                health_status["priority_alerts"].append(
                    {
                        "type": "medication_due",
                        "message": f"{medication['name']} dose due soon",
                        "severity": "high",
                        "action_required": True,
                    }
                )

        # Final score adjustment
        health_status["overall_score"] = max(
            0, min(100, health_status["overall_score"])
        )

        return health_status

    @staticmethod
    def calculate_next_appointment_recommendation(
        health_profile: EnhancedHealthProfile, dog_age_months: int
    ) -> dict[str, Any]:
        """Calculate when the next veterinary appointment should be scheduled."""
        current_date = dt_util.now()

        # Base recommendation frequencies by age
        if dog_age_months < 12:  # Puppy
            base_interval = timedelta(days=30)  # Monthly for puppies
            appointment_type = "puppy_checkup"
        elif dog_age_months < 84:  # Adult (under 7 years)
            base_interval = timedelta(days=365)  # Yearly for adults
            appointment_type = "annual_checkup"
        else:  # Senior
            base_interval = timedelta(days=180)  # Every 6 months for seniors
            appointment_type = "senior_checkup"

        # Adjust based on health conditions
        if health_profile.chronic_conditions:
            if "diabetes" in health_profile.chronic_conditions:
                base_interval = timedelta(days=90)  # Every 3 months
                appointment_type = "diabetes_monitoring"
            elif any(
                condition in ["heart_disease", "kidney_disease"]
                for condition in health_profile.chronic_conditions
            ):
                base_interval = timedelta(days=120)  # Every 4 months
                appointment_type = "condition_monitoring"

        # Check last checkup
        if health_profile.last_checkup_date:
            next_recommended = health_profile.last_checkup_date + base_interval
        else:
            next_recommended = current_date + timedelta(
                days=7
            )  # Schedule soon if never seen

        return {
            "next_appointment_date": next_recommended.isoformat(),
            "appointment_type": appointment_type,
            "reason": f"Based on age ({dog_age_months} months) and health conditions",
            "urgency": "high" if next_recommended < current_date else "normal",
            "days_until": (next_recommended - current_date).days,
        }
