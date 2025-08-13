"""Scheduler for Paw Control integration."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import datetime, time, timedelta
from typing import Any, Dict, Iterator, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOGS,
    CONF_RESET_TIME,
    DEFAULT_RESET_TIME,
    DOMAIN,
    EVENT_DAILY_RESET,
    MODULE_FEEDING,
    MODULE_GROOMING,
    MODULE_MEDICATION,
    MODULE_WALK,
)

_LOGGER = logging.getLogger(__name__)


class PawControlScheduler:
    """Manage scheduled tasks for Paw Control."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize scheduler."""
        self.hass = hass
        self.entry = entry
        self.runtime_data = entry.runtime_data
        self._scheduled_tasks: dict[str, CALLBACK_TYPE] = {}
        self._reminder_tasks: dict[str, CALLBACK_TYPE] = {}

    def _iter_dogs_with_module(self, module: str) -> Iterable[tuple[str, str]]:
        """Yield dog ID and name for dogs with the given module enabled."""
        for dog in self.entry.options.get(CONF_DOGS, []):
            dog_id = dog.get(CONF_DOG_ID)
            if not dog_id:
                continue
            modules = dog.get(CONF_DOG_MODULES, {})
            if modules.get(module, False):
                yield dog_id, dog.get("name", dog_id)

    async def setup(self) -> None:
        """Set up all scheduled tasks."""
        _LOGGER.info("Setting up scheduled tasks")

        # Setup daily reset
        await self._setup_daily_reset()

        # Setup daily report (if configured)
        await self._setup_daily_report()

        # Setup feeding reminders
        await self._setup_feeding_reminders()

        # Setup walk reminders
        await self._setup_walk_reminders()

        # Setup medication reminders
        await self._setup_medication_reminders()

        # Setup grooming reminders
        await self._setup_grooming_reminders()

    async def cleanup(self) -> None:
        """Clean up all scheduled tasks."""
        _LOGGER.info("Cleaning up scheduled tasks")

        # Cancel all scheduled tasks
        for task_id, cancel_callback in self._scheduled_tasks.items():
            if cancel_callback:
                cancel_callback()
                _LOGGER.debug(f"Cancelled scheduled task: {task_id}")

        self._scheduled_tasks.clear()

        # Cancel all reminder tasks
        for task_id, cancel_callback in self._reminder_tasks.items():
            if cancel_callback:
                cancel_callback()
                _LOGGER.debug(f"Cancelled reminder task: {task_id}")

        self._reminder_tasks.clear()

    def _iter_dogs_with_module(
        self, module: str
    ) -> Iterator[tuple[str, Dict[str, Any]]]:
        """Yield dogs that have a specific module enabled."""
        dogs = self.entry.options.get(CONF_DOGS, [])
        for dog in dogs:
            dog_id = dog.get(CONF_DOG_ID)
            if not dog_id:
                continue
            modules = dog.get(CONF_DOG_MODULES, {})
            if modules.get(module, False):
                yield dog_id, dog

    async def _setup_daily_reset(self) -> None:
        """Set up daily reset task."""
        reset_time_str = self.entry.options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME)

        try:
            reset_time = time.fromisoformat(reset_time_str)

            @callback
            def daily_reset_callback(now):
                """Execute daily reset."""
                _LOGGER.info("Executing daily reset")
                self.hass.bus.async_fire(EVENT_DAILY_RESET)

                # Call the service
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        DOMAIN,
                        "daily_reset",
                        {},
                        blocking=False,
                    )
                )

            # Schedule daily reset
            cancel = async_track_time_change(
                self.hass,
                daily_reset_callback,
                hour=reset_time.hour,
                minute=reset_time.minute,
                second=reset_time.second,
            )

            self._scheduled_tasks["daily_reset"] = cancel
            _LOGGER.info(f"Daily reset scheduled for {reset_time_str}")

        except ValueError as err:
            _LOGGER.error(f"Invalid reset time configuration: {err}")

    async def _setup_daily_report(self) -> None:
        """Set up daily report generation."""
        # Check if export is configured
        export_path = self.entry.options.get("export_path")
        if not export_path:
            return

        # Schedule report 5 minutes before daily reset
        reset_time_str = self.entry.options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME)

        try:
            reset_time = time.fromisoformat(reset_time_str)
            # Use Home Assistant's timezone-aware time for scheduling
            now = dt_util.now()
            report_time = (
                datetime.combine(now.date(), reset_time) - timedelta(minutes=5)
            ).time()

            @callback
            def daily_report_callback(now):
                """Generate daily report."""
                _LOGGER.info("Generating daily report")

                self.hass.async_create_task(
                    self.hass.services.async_call(
                        DOMAIN,
                        "generate_report",
                        {
                            "scope": "daily",
                            "target": "file",
                            "format": self.entry.options.get("export_format", "csv"),
                        },
                        blocking=False,
                    )
                )

            # Schedule daily report
            cancel = async_track_time_change(
                self.hass,
                daily_report_callback,
                hour=report_time.hour,
                minute=report_time.minute,
                second=0,
            )

            self._scheduled_tasks["daily_report"] = cancel
            _LOGGER.info(f"Daily report scheduled for {report_time.strftime('%H:%M')}")

        except ValueError as err:
            _LOGGER.error(f"Invalid report time configuration: {err}")

    async def _setup_feeding_reminders(self) -> None:
        """Set up feeding reminder schedules."""
        for dog_id, dog_name in self._iter_dogs_with_module(MODULE_FEEDING):
            # Default feeding times
            feeding_schedule = {
                "breakfast": "07:00:00",
                "lunch": "12:00:00",
                "dinner": "18:00:00",
            }

            for meal_type, meal_time_str in feeding_schedule.items():
                try:
                    meal_time = time.fromisoformat(meal_time_str)

                    @callback
                    def feeding_reminder_callback(
                        now, dog_id=dog_id, dog_name=dog_name, meal=meal_type
                    ):
                        """Send feeding reminder."""
                        _LOGGER.info(f"Feeding reminder for {dog_id} - {meal}")

                        # Get notification router
                        router = self.runtime_data.notification_router

                        if router:
                            self.hass.async_create_task(
                                router.send_reminder(
                                    "feeding", dog_id, dog_name, {"meal_type": meal}
                                )
                            )

                    # Schedule feeding reminder
                    cancel = async_track_time_change(
                        self.hass,
                        feeding_reminder_callback,
                        hour=meal_time.hour,
                        minute=meal_time.minute,
                        second=0,
                    )

                    task_id = f"feeding_{dog_id}_{meal_type}"
                    self._reminder_tasks[task_id] = cancel
                    _LOGGER.debug(
                        f"Feeding reminder scheduled: {task_id} at {meal_time_str}"
                    )

                except ValueError as err:
                    _LOGGER.error(f"Invalid feeding time for {meal_type}: {err}")

    async def _setup_walk_reminders(self) -> None:
        """Set up walk reminder checks."""
        for dog_id, dog_name in self._iter_dogs_with_module(MODULE_WALK):

            @callback
            def walk_check_callback(now, dog_id=dog_id, dog_name=dog_name):
                """Check if dog needs walk reminder."""
                coordinator = self.runtime_data.coordinator

                dog_data = coordinator.get_dog_data(dog_id)
                if dog_data.get("walk", {}).get("needs_walk", False):
                    _LOGGER.info(f"Walk needed for {dog_id}")

                    # Send reminder
                    router = self.runtime_data.notification_router

                    if router:
                        self.hass.async_create_task(
                            router.send_reminder("walk", dog_id, dog_name)
                        )

            # Check every hour
            cancel = async_track_time_interval(
                self.hass,
                walk_check_callback,
                timedelta(hours=1),
            )

            task_id = f"walk_check_{dog_id}"
            self._reminder_tasks[task_id] = cancel
            _LOGGER.debug(f"Walk check scheduled: {task_id}")

    async def _setup_medication_reminders(self) -> None:
        """Set up medication reminder schedules."""
        for dog_id, dog_name in self._iter_dogs_with_module(MODULE_MEDICATION):
            # Get medication schedule from config (if available)
            # For now, use default times
            medication_times = ["08:00:00", "20:00:00"]

            for med_time_str in medication_times:
                try:
                    med_time = time.fromisoformat(med_time_str)

                    @callback
                    def medication_reminder_callback(
                        now, dog_id=dog_id, dog_name=dog_name
                    ):
                        """Send medication reminder."""
                        _LOGGER.info(f"Medication reminder for {dog_id}")

                        router = self.runtime_data.notification_router

                        if router:
                            self.hass.async_create_task(
                                router.send_reminder(
                                    "medication",
                                    dog_id,
                                    dog_name,
                                    {"medication": "scheduled medication"},
                                )
                            )

                    # Schedule medication reminder
                    cancel = async_track_time_change(
                        self.hass,
                        medication_reminder_callback,
                        hour=med_time.hour,
                        minute=med_time.minute,
                        second=0,
                    )

                    task_id = f"medication_{dog_id}_{med_time_str.replace(':', '')}"
                    self._reminder_tasks[task_id] = cancel
                    _LOGGER.debug(
                        f"Medication reminder scheduled: {task_id} at {med_time_str}"
                    )

                except ValueError as err:
                    _LOGGER.error(f"Invalid medication time: {err}")

    async def _setup_grooming_reminders(self) -> None:
        """Set up grooming reminder checks."""
        for dog_id, dog_name in self._iter_dogs_with_module(MODULE_GROOMING):

            @callback
            def grooming_check_callback(now, dog_id=dog_id, dog_name=dog_name):
                """Check if dog needs grooming reminder."""
                coordinator = self.runtime_data.coordinator

                dog_data = coordinator.get_dog_data(dog_id)
                if dog_data.get("grooming", {}).get("needs_grooming", False):
                    _LOGGER.info(f"Grooming needed for {dog_id}")

                    # Send reminder
                    router = self.runtime_data.notification_router

                    if router:
                        self.hass.async_create_task(
                            router.send_reminder("grooming", dog_id, dog_name)
                        )

            # Check daily at 09:00
            cancel = async_track_time_change(
                self.hass,
                grooming_check_callback,
                hour=9,
                minute=0,
                second=0,
            )

            task_id = f"grooming_check_{dog_id}"
            self._reminder_tasks[task_id] = cancel
            _LOGGER.debug(f"Grooming check scheduled: {task_id}")

    def schedule_delayed_task(
        self,
        callback: Callable,
        delay_seconds: int,
        task_id: Optional[str] = None,
    ) -> None:
        """Schedule a delayed task."""

        @callback
        def delayed_callback(now):
            """Execute delayed task."""
            callback()

            # Remove from tracked tasks
            if task_id and task_id in self._scheduled_tasks:
                del self._scheduled_tasks[task_id]

        cancel = async_call_later(
            self.hass,
            delay_seconds,
            delayed_callback,
        )

        if task_id:
            # Cancel existing task if present
            if task_id in self._scheduled_tasks:
                old_cancel = self._scheduled_tasks[task_id]
                if old_cancel:
                    old_cancel()

            self._scheduled_tasks[task_id] = cancel


async def setup_schedulers(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up all schedulers for the integration."""
    scheduler = PawControlScheduler(hass, entry)
    await scheduler.setup()

    # Store scheduler instance on runtime data
    entry.runtime_data.scheduler = scheduler


async def cleanup_schedulers(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up all schedulers for the integration."""
    scheduler = entry.runtime_data.scheduler
    if scheduler:
        await scheduler.cleanup()
        entry.runtime_data.scheduler = None
