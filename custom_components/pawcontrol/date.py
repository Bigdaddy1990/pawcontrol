"""Date platform for Paw Control integration.

This module provides :class:`~homeassistant.components.date.DateEntity`
implementations that cover date-only workflows, complementing the
datetime entities by handling birth dates, adoption anniversaries, and
scheduled activities that do not require time components.

Metadata:
    Quality Scale: Platinum
    Home Assistant: 2025.8.2+
    Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import date
from typing import Any

from homeassistant.components.date import DateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_HEALTH,
    MODULE_WALK,
)
from .coordinator import PawControlCoordinator
from .exceptions import PawControlError, ValidationError
from .helpers import performance_monitor
from .runtime_data import get_runtime_data
from .utils import PawControlDeviceLinkMixin, async_call_add_entities

_LOGGER = logging.getLogger(__name__)

# Date helpers mutate coordinator-managed settings, so restrict concurrency to
# one update at a time for the ``parallel-updates`` quality scale rule.
PARALLEL_UPDATES = 1


async def _async_add_entities_in_batches(
    async_add_entities_func,
    entities: list[PawControlDateBase],
    batch_size: int = 12,
    delay_between_batches: float = 0.1,
) -> None:
    """Add date entities in small batches to prevent Entity Registry overload.

    The Entity Registry logs warnings when >200 messages occur rapidly.
    By batching entities and adding delays, we prevent registry overload.

    Args:
        async_add_entities_func: The actual async_add_entities callback
        entities: List of date entities to add
        batch_size: Number of entities per batch (default: 12)
        delay_between_batches: Seconds to wait between batches (default: 0.1s)
    """
    total_entities = len(entities)

    _LOGGER.debug(
        "Adding %d date entities in batches of %d to prevent Registry overload",
        total_entities,
        batch_size,
    )

    # Process entities in batches
    for i in range(0, total_entities, batch_size):
        batch = entities[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_entities + batch_size - 1) // batch_size

        _LOGGER.debug(
            "Processing date batch %d/%d with %d entities",
            batch_num,
            total_batches,
            len(batch),
        )

        # Add batch without update_before_add to reduce Registry load
        await async_call_add_entities(
            async_add_entities_func, batch, update_before_add=False
        )

        # Small delay between batches to prevent Registry flooding
        if i + batch_size < total_entities:  # No delay after last batch
            await asyncio.sleep(delay_between_batches)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control date platform with comprehensive entity creation.

    Creates date entities for each configured dog based on enabled modules.
    Date entities handle date-only scenarios without time components.

    Args:
        hass: Home Assistant instance
        entry: Config entry containing integration configuration
        async_add_entities: Callback to add entities to Home Assistant

    Raises:
        PawControlError: If setup fails due to configuration issues
    """
    _LOGGER.debug("Setting up Paw Control date platform for entry %s", entry.entry_id)

    try:
        # Retrieve runtime data from hass.data
        runtime_data = get_runtime_data(hass, entry)
        if runtime_data is None:
            _LOGGER.error("Runtime data missing for entry %s", entry.entry_id)
            return

        coordinator = runtime_data.coordinator
        dogs = runtime_data.dogs

        entities = []

        for dog in dogs:
            try:
                dog_id = dog[CONF_DOG_ID]
                dog_name = dog[CONF_DOG_NAME]
                modules = dog.get("modules", {})

                _LOGGER.debug(
                    "Creating date entities for dog %s (%s) with modules: %s",
                    dog_name,
                    dog_id,
                    list(modules.keys()),
                )

                # Core dog date entities (always created)
                entities.extend(
                    [
                        PawControlBirthdateDate(coordinator, dog_id, dog_name),
                        PawControlAdoptionDate(coordinator, dog_id, dog_name),
                    ]
                )

                # Health module date entities
                if modules.get(MODULE_HEALTH, False):
                    entities.extend(
                        [
                            PawControlLastVetVisitDate(coordinator, dog_id, dog_name),
                            PawControlNextVetAppointmentDate(
                                coordinator, dog_id, dog_name
                            ),
                            PawControlLastGroomingDate(coordinator, dog_id, dog_name),
                            PawControlNextGroomingDate(coordinator, dog_id, dog_name),
                            PawControlVaccinationDate(coordinator, dog_id, dog_name),
                            PawControlNextVaccinationDate(
                                coordinator, dog_id, dog_name
                            ),
                            PawControlDewormingDate(coordinator, dog_id, dog_name),
                            PawControlNextDewormingDate(coordinator, dog_id, dog_name),
                        ]
                    )

                # Feeding module date entities
                if modules.get(MODULE_FEEDING, False):
                    entities.extend(
                        [
                            PawControlDietStartDate(coordinator, dog_id, dog_name),
                            PawControlDietEndDate(coordinator, dog_id, dog_name),
                        ]
                    )

                # Walk/Training module date entities
                if modules.get(MODULE_WALK, False):
                    entities.extend(
                        [
                            PawControlTrainingStartDate(coordinator, dog_id, dog_name),
                            PawControlNextTrainingDate(coordinator, dog_id, dog_name),
                        ]
                    )

            except KeyError as err:
                _LOGGER.error("Missing required configuration for dog: %s", err)
                continue
            except Exception as err:
                _LOGGER.error(
                    "Error creating date entities for dog %s: %s",
                    dog.get(CONF_DOG_ID, "unknown"),
                    err,
                    exc_info=True,
                )
                continue

        # Add entities in smaller batches to prevent Entity Registry overload
        # With 48+ date entities (2 dogs), batching prevents Registry flooding
        await _async_add_entities_in_batches(
            async_add_entities, entities, batch_size=12
        )
        _LOGGER.info(
            "Successfully set up %d date entities for %d dogs using batched approach",
            len(entities),
            len(dogs),
        )

    except Exception as err:
        _LOGGER.error("Failed to setup date platform: %s", err, exc_info=True)
        raise PawControlError(
            "Date platform setup failed",
            "platform_setup_error",
        ) from err


class PawControlDateBase(
    PawControlDeviceLinkMixin,
    CoordinatorEntity[PawControlCoordinator],
    DateEntity,
    RestoreEntity,
):
    """Base class for Paw Control date entities.

    Provides common functionality for all date entities including state
    restoration, device association, and consistent attribute handling.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        date_type: str,
        icon: str = "mdi:calendar",
    ) -> None:
        """Initialize the date entity with comprehensive setup.

        Args:
            coordinator: Data update coordinator
            dog_id: Unique identifier for the dog
            dog_name: Display name for the dog
            date_type: Type identifier for the date entity
            icon: Material Design icon for the entity
        """
        super().__init__(coordinator)
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._date_type = date_type
        self._current_value: date | None = None
        self._active_update_token: object | None = None

        # Entity configuration with modern HA standards
        self._attr_unique_id = f"pawcontrol_{dog_id}_{date_type}"
        self._attr_name = f"{dog_name} {date_type.replace('_', ' ').title()}"
        self._attr_icon = icon

        self._attr_device_info = {
            "identifiers": {(DOMAIN, dog_id)},
            "name": dog_name,
            "manufacturer": "Paw Control",
            "model": "Smart Dog Management",
            "sw_version": "2025.8.2",
            "configuration_url": "https://github.com/BigDaddy1990/pawcontrol",
        }
        self._attr_suggested_area = f"Pet Area - {dog_name}"

    @property
    def native_value(self) -> date | None:
        """Return the current date value.

        Returns:
            Current date value or None if not set
        """
        return self._current_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for enhanced functionality.

        Returns:
            Dictionary of additional attributes for automations and templates
        """
        attributes = {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "date_type": self._date_type,
        }

        # Add calculated attributes for useful automations
        if self._current_value:
            today = dt_util.now().date()
            days_diff = (self._current_value - today).days

            attributes.update(
                {
                    "days_from_today": days_diff,
                    "is_past": days_diff < 0,
                    "is_today": days_diff == 0,
                    "is_future": days_diff > 0,
                    "iso_string": self._current_value.isoformat(),
                }
            )

            # Add age calculation for birthdate
            if self._date_type == "birthdate" and days_diff < 0:
                age_days = abs(days_diff)
                age_years = age_days / 365.25
                age_months = (age_days % 365.25) / 30.44

                attributes.update(
                    {
                        "age_days": age_days,
                        "age_years": round(age_years, 2),
                        "age_months": round(age_months, 1),
                    }
                )

        return attributes

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to Home Assistant.

        Handles state restoration and initial setup.
        """
        await super().async_added_to_hass()

        # Restore previous state with error handling
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable"):
            try:
                self._current_value = dt_util.parse_date(last_state.state)
                _LOGGER.debug(
                    "Restored %s for %s: %s",
                    self._date_type,
                    self._dog_name,
                    self._current_value,
                )
            except (ValueError, TypeError) as err:
                _LOGGER.warning(
                    "Failed to restore date state for %s: %s",
                    self.entity_id,
                    err,
                )
                self._current_value = None

    @performance_monitor(timeout=5.0)
    async def async_set_value(self, value: date) -> None:
        """Set new date value with validation and logging.

        Args:
            value: New date value to set

        Raises:
            ValidationError: If date value is invalid
        """
        # Validate date value early so we can return a consistent error message.
        if not isinstance(value, date):
            raise ValidationError(
                field="date_value",
                value=str(value),
                constraint="Value must be a date object",
            )

        previous_value = self._current_value
        update_token = object()
        self._active_update_token = update_token

        try:
            _LOGGER.debug(
                "Set %s for %s (%s) to %s",
                self._date_type,
                self._dog_name,
                self._dog_id,
                value,
            )

            # Call subclass-specific handling
            await self._async_handle_date_set(value)
        except Exception as err:
            if (
                self._active_update_token is update_token
                and self._current_value == previous_value
            ):
                self._current_value = previous_value
                self.async_write_ha_state()

            _LOGGER.error(
                "Error setting %s for %s: %s",
                self._date_type,
                self._dog_name,
                err,
                exc_info=True,
            )
            raise ValidationError(
                field="date_value",
                value=str(value),
                constraint=f"Failed to set date: {err}",
            ) from err
        else:
            self._current_value = value
            self.async_write_ha_state()

            _LOGGER.debug(
                "Set %s for %s (%s) to %s",
                self._date_type,
                self._dog_name,
                self._dog_id,
                value,
            )
        finally:
            if self._active_update_token is update_token:
                self._active_update_token = None

    async def _async_handle_date_set(self, value: date) -> None:
        """Handle date-specific logic when value is set.

        Subclasses can override this method to implement specific behavior
        when a date value is set.

        Args:
            value: The new date value that was set
        """
        # Default implementation does nothing
        pass

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        Updates entity state based on fresh data from the coordinator.
        """
        try:
            # Get dog-specific data from coordinator
            dog_data = self.coordinator.get_dog_data(self._dog_id)

            if dog_data:
                # Update entity state based on coordinator data
                updated_value = self._extract_date_from_dog_data(dog_data)

                if updated_value and updated_value != self._current_value:
                    self._current_value = updated_value
                    _LOGGER.debug(
                        "Updated %s for %s from coordinator: %s",
                        self._date_type,
                        self._dog_name,
                        updated_value,
                    )

        except Exception as err:
            _LOGGER.debug(
                "Error updating %s from coordinator: %s",
                self._date_type,
                err,
            )

        super()._handle_coordinator_update()

    def _extract_date_from_dog_data(self, dog_data: dict[str, Any]) -> date | None:
        """Extract date value from dog data.

        Subclasses should override this method to extract their specific
        date value from the dog data.

        Args:
            dog_data: Dictionary containing dog data from coordinator

        Returns:
            Extracted date value or None
        """
        return None


# Core Dog Date Entities


class PawControlBirthdateDate(PawControlDateBase):
    """Date entity for dog birthdate."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the birthdate entity."""
        super().__init__(coordinator, dog_id, dog_name, "birthdate", "mdi:cake")

    def _extract_date_from_dog_data(self, dog_data: dict[str, Any]) -> date | None:
        """Extract birthdate from dog data."""
        birthdate_str = dog_data.get("profile", {}).get("birthdate")
        if birthdate_str:
            with suppress(ValueError, TypeError):
                return dt_util.parse_date(birthdate_str)
        return None

    async def _async_handle_date_set(self, value: date) -> None:
        """Handle birthdate update - calculate and log age."""
        today = dt_util.now().date()
        age_years = (today - value).days / 365.25

        _LOGGER.info(
            "Updated birthdate for %s: %s (age: %.1f years)",
            self._dog_name,
            value,
            age_years,
        )

        # Update dog profile if data manager is available
        try:
            runtime_data = (
                get_runtime_data(self.hass, self.coordinator.config_entry)
                if self.hass
                else None
            )
            data_manager = getattr(runtime_data, "data_manager", None)
            if data_manager:
                await data_manager.async_update_dog_profile(
                    self._dog_id, {"birthdate": value.isoformat()}
                )
        except Exception as err:
            _LOGGER.debug("Could not update dog profile: %s", err)
            raise


class PawControlAdoptionDate(PawControlDateBase):
    """Date entity for adoption date."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the adoption date entity."""
        super().__init__(
            coordinator, dog_id, dog_name, "adoption_date", "mdi:home-heart"
        )

    def _extract_date_from_dog_data(self, dog_data: dict[str, Any]) -> date | None:
        """Extract adoption date from dog data."""
        adoption_date_str = dog_data.get("profile", {}).get("adoption_date")
        if adoption_date_str:
            with suppress(ValueError, TypeError):
                return dt_util.parse_date(adoption_date_str)
        return None

    async def _async_handle_date_set(self, value: date) -> None:
        """Handle adoption date update."""
        today = dt_util.now().date()
        days_since = (today - value).days

        _LOGGER.info(
            "Updated adoption date for %s: %s (%d days ago)",
            self._dog_name,
            value,
            days_since,
        )


# Health-related Date Entities


class PawControlLastVetVisitDate(PawControlDateBase):
    """Date entity for last vet visit."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the last vet visit date entity."""
        super().__init__(
            coordinator, dog_id, dog_name, "last_vet_visit", "mdi:medical-bag"
        )

    def _extract_date_from_dog_data(self, dog_data: dict[str, Any]) -> date | None:
        """Extract last vet visit date from dog data."""
        vet_visit_str = dog_data.get("health", {}).get("last_vet_visit")
        if vet_visit_str:
            with suppress(ValueError, TypeError):
                # Handle both date and datetime strings
                if parsed_dt := dt_util.parse_datetime(vet_visit_str):
                    return parsed_dt.date()

            with suppress(ValueError, TypeError):
                return dt_util.parse_date(vet_visit_str)
        return None

    async def _async_handle_date_set(self, value: date) -> None:
        """Handle vet visit date update - log health entry."""
        _LOGGER.info("Updated last vet visit for %s: %s", self._dog_name, value)

        # Log vet visit in health records
        try:
            await self.hass.services.async_call(
                DOMAIN,
                "log_health_data",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "note": f"Vet visit recorded for {value.strftime('%Y-%m-%d')}",
                    "health_status": "checked",
                },
            )
        except Exception as err:
            _LOGGER.debug("Could not log vet visit: %s", err)
            raise


class PawControlNextVetAppointmentDate(PawControlDateBase):
    """Date entity for next vet appointment."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the next vet appointment date entity."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "next_vet_appointment",
            "mdi:calendar-medical",
        )

    async def _async_handle_date_set(self, value: date) -> None:
        """Handle next vet appointment date update."""
        _LOGGER.info("Scheduled next vet appointment for %s: %s", self._dog_name, value)

        # Create reminder if close to appointment date
        today = dt_util.now().date()
        days_until = (value - today).days

        if 0 <= days_until <= 7:
            _LOGGER.info(
                "Vet appointment for %s is in %d days - consider setting up reminders",
                self._dog_name,
                days_until,
            )


class PawControlLastGroomingDate(PawControlDateBase):
    """Date entity for last grooming session."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the last grooming date entity."""
        super().__init__(
            coordinator, dog_id, dog_name, "last_grooming", "mdi:content-cut"
        )

    def _extract_date_from_dog_data(self, dog_data: dict[str, Any]) -> date | None:
        """Extract last grooming date from dog data."""
        grooming_str = dog_data.get("health", {}).get("last_grooming")
        if grooming_str:
            with suppress(ValueError, TypeError):
                if parsed_dt := dt_util.parse_datetime(grooming_str):
                    return parsed_dt.date()

            with suppress(ValueError, TypeError):
                return dt_util.parse_date(grooming_str)
        return None


class PawControlNextGroomingDate(PawControlDateBase):
    """Date entity for next grooming appointment."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the next grooming date entity."""
        super().__init__(
            coordinator, dog_id, dog_name, "next_grooming", "mdi:calendar-clock"
        )


class PawControlVaccinationDate(PawControlDateBase):
    """Date entity for vaccination dates."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the vaccination date entity."""
        super().__init__(
            coordinator, dog_id, dog_name, "vaccination_date", "mdi:needle"
        )

    async def _async_handle_date_set(self, value: date) -> None:
        """Handle vaccination date update - log health entry."""
        _LOGGER.info("Updated vaccination date for %s: %s", self._dog_name, value)

        # Log vaccination in health records
        try:
            await self.hass.services.async_call(
                DOMAIN,
                "log_health_data",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "note": f"Vaccination recorded for {value.strftime('%Y-%m-%d')}",
                    "health_status": "vaccinated",
                },
            )
        except Exception as err:
            _LOGGER.debug("Could not log vaccination: %s", err)
            raise


class PawControlNextVaccinationDate(PawControlDateBase):
    """Date entity for next vaccination due date."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the next vaccination date entity."""
        super().__init__(
            coordinator, dog_id, dog_name, "next_vaccination", "mdi:calendar-plus"
        )


class PawControlDewormingDate(PawControlDateBase):
    """Date entity for deworming dates."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the deworming date entity."""
        super().__init__(coordinator, dog_id, dog_name, "deworming_date", "mdi:pill")

    async def _async_handle_date_set(self, value: date) -> None:
        """Handle deworming date update - log health entry."""
        _LOGGER.info("Updated deworming date for %s: %s", self._dog_name, value)

        # Log deworming in health records
        try:
            await self.hass.services.async_call(
                DOMAIN,
                "log_health_data",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "note": f"Deworming treatment recorded for {value.strftime('%Y-%m-%d')}",
                    "health_status": "treated",
                },
            )
        except Exception as err:
            _LOGGER.debug("Could not log deworming: %s", err)
            raise


class PawControlNextDewormingDate(PawControlDateBase):
    """Date entity for next deworming due date."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the next deworming date entity."""
        super().__init__(
            coordinator, dog_id, dog_name, "next_deworming", "mdi:calendar-alert"
        )


# Feeding-related Date Entities


class PawControlDietStartDate(PawControlDateBase):
    """Date entity for diet start date."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the diet start date entity."""
        super().__init__(coordinator, dog_id, dog_name, "diet_start_date", "mdi:scale")

    async def _async_handle_date_set(self, value: date) -> None:
        """Handle diet start date update."""
        _LOGGER.info("Set diet start date for %s: %s", self._dog_name, value)


class PawControlDietEndDate(PawControlDateBase):
    """Date entity for diet end date."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the diet end date entity."""
        super().__init__(
            coordinator, dog_id, dog_name, "diet_end_date", "mdi:scale-off"
        )


# Training-related Date Entities


class PawControlTrainingStartDate(PawControlDateBase):
    """Date entity for training program start date."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the training start date entity."""
        super().__init__(
            coordinator, dog_id, dog_name, "training_start_date", "mdi:school"
        )


class PawControlNextTrainingDate(PawControlDateBase):
    """Date entity for next training session date."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the next training date entity."""
        super().__init__(
            coordinator, dog_id, dog_name, "next_training_date", "mdi:calendar-star"
        )

    async def _async_handle_date_set(self, value: date) -> None:
        """Handle next training date update."""
        today = dt_util.now().date()
        days_until = (value - today).days

        _LOGGER.info(
            "Scheduled next training session for %s: %s (%d days from today)",
            self._dog_name,
            value,
            days_until,
        )
