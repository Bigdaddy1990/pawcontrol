"""Advanced feeding management for PawControl with schedule support.

This module provides comprehensive feeding management including meal schedules,
portion tracking, reminders, and intelligent feeding recommendations.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class MealType(Enum):
    """Meal type enumeration."""
    
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    TREAT = "treat"
    SUPPLEMENT = "supplement"


class FeedingScheduleType(Enum):
    """Feeding schedule type enumeration."""
    
    FLEXIBLE = "flexible"
    STRICT = "strict"
    CUSTOM = "custom"


@dataclass(slots=True)
class FeedingEvent:
    """Represent a single feeding event with enhanced metadata."""
    
    time: datetime
    amount: float
    meal_type: Optional[MealType] = None
    portion_size: Optional[float] = None
    food_type: Optional[str] = None
    notes: Optional[str] = None
    feeder: Optional[str] = None  # Who fed the dog
    scheduled: bool = False  # Was this a scheduled feeding
    skipped: bool = False  # Was this feeding skipped
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "time": self.time.isoformat(),
            "amount": self.amount,
            "meal_type": self.meal_type.value if self.meal_type else None,
            "portion_size": self.portion_size,
            "food_type": self.food_type,
            "notes": self.notes,
            "feeder": self.feeder,
            "scheduled": self.scheduled,
            "skipped": self.skipped,
        }


@dataclass(slots=True)
class MealSchedule:
    """Represent a scheduled meal time with configuration."""
    
    meal_type: MealType
    scheduled_time: time
    portion_size: float
    enabled: bool = True
    reminder_enabled: bool = True
    reminder_minutes_before: int = 15
    auto_log: bool = False  # Automatically log feeding at scheduled time
    days_of_week: Optional[List[int]] = None  # 0=Monday, 6=Sunday; None=every day
    
    def is_due_today(self) -> bool:
        """Check if this meal is scheduled for today."""
        if not self.enabled:
            return False
        
        if self.days_of_week is None:
            return True
        
        today = datetime.now().weekday()
        return today in self.days_of_week
    
    def get_next_feeding_time(self) -> datetime:
        """Get the next scheduled feeding time."""
        now = dt_util.now()
        today = now.date()
        
        # Create datetime for today's scheduled time
        scheduled = datetime.combine(today, self.scheduled_time)
        scheduled = dt_util.as_local(scheduled)
        
        # If already passed today, get tomorrow's time
        if scheduled <= now:
            scheduled += timedelta(days=1)
        
        # Check days of week if configured
        if self.days_of_week is not None:
            while scheduled.weekday() not in self.days_of_week:
                scheduled += timedelta(days=1)
        
        return scheduled
    
    def get_reminder_time(self) -> Optional[datetime]:
        """Get the reminder time for this meal."""
        if not self.reminder_enabled:
            return None
        
        next_feeding = self.get_next_feeding_time()
        return next_feeding - timedelta(minutes=self.reminder_minutes_before)


@dataclass
class FeedingConfig:
    """Complete feeding configuration for a dog."""
    
    dog_id: str
    meals_per_day: int = 2
    daily_food_amount: float = 500.0  # grams
    food_type: str = "dry_food"
    schedule_type: FeedingScheduleType = FeedingScheduleType.FLEXIBLE
    meal_schedules: List[MealSchedule] = field(default_factory=list)
    treats_enabled: bool = True
    max_treats_per_day: int = 3
    water_tracking: bool = False
    calorie_tracking: bool = False
    calories_per_gram: Optional[float] = None
    
    def calculate_portion_size(self) -> float:
        """Calculate standard portion size based on meals per day."""
        if self.meals_per_day <= 0:
            return 0
        return self.daily_food_amount / self.meals_per_day
    
    def get_active_schedules(self) -> List[MealSchedule]:
        """Get only enabled meal schedules."""
        return [s for s in self.meal_schedules if s.enabled]
    
    def get_todays_schedules(self) -> List[MealSchedule]:
        """Get schedules that are due today."""
        return [s for s in self.meal_schedules if s.is_due_today()]


class FeedingManager:
    """Advanced feeding management with schedule support."""
    
    def __init__(self) -> None:
        """Initialize feeding manager."""
        self._feedings: Dict[str, List[FeedingEvent]] = {}
        self._configs: Dict[str, FeedingConfig] = {}
        self._reminders: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        
    async def async_initialize(self, dogs: List[Dict[str, Any]]) -> None:
        """Initialize feeding configurations for dogs.
        
        Args:
            dogs: List of dog configurations
        """
        async with self._lock:
            for dog in dogs:
                dog_id = dog.get("dog_id")
                if not dog_id:
                    continue
                
                # Create feeding config from dog data
                feeding_config = dog.get("feeding_config", {})
                config = await self._create_feeding_config(dog_id, feeding_config)
                self._configs[dog_id] = config
                
                # Setup scheduled reminders if enabled
                if config.schedule_type != FeedingScheduleType.FLEXIBLE:
                    await self._setup_reminders(dog_id)
    
    async def _create_feeding_config(
        self, dog_id: str, config_data: Dict[str, Any]
    ) -> FeedingConfig:
        """Create feeding configuration from data.
        
        Args:
            dog_id: Dog identifier
            config_data: Configuration data
            
        Returns:
            FeedingConfig instance
        """
        config = FeedingConfig(
            dog_id=dog_id,
            meals_per_day=config_data.get("meals_per_day", 2),
            daily_food_amount=config_data.get("daily_food_amount", 500.0),
            food_type=config_data.get("food_type", "dry_food"),
            schedule_type=FeedingScheduleType(
                config_data.get("feeding_schedule", "flexible")
            ),
            treats_enabled=config_data.get("treats_enabled", True),
            water_tracking=config_data.get("water_tracking", False),
            calorie_tracking=config_data.get("calorie_tracking", False),
        )
        
        # Create meal schedules from configuration
        meal_schedules = []
        
        # Breakfast
        if config_data.get("breakfast_time"):
            breakfast_time = self._parse_time(config_data["breakfast_time"])
            if breakfast_time:
                meal_schedules.append(
                    MealSchedule(
                        meal_type=MealType.BREAKFAST,
                        scheduled_time=breakfast_time,
                        portion_size=config_data.get("portion_size", config.calculate_portion_size()),
                        reminder_enabled=config_data.get("enable_reminders", True),
                        reminder_minutes_before=config_data.get("reminder_minutes_before", 15),
                    )
                )
        
        # Lunch
        if config_data.get("lunch_time"):
            lunch_time = self._parse_time(config_data["lunch_time"])
            if lunch_time:
                meal_schedules.append(
                    MealSchedule(
                        meal_type=MealType.LUNCH,
                        scheduled_time=lunch_time,
                        portion_size=config_data.get("portion_size", config.calculate_portion_size()),
                        reminder_enabled=config_data.get("enable_reminders", True),
                        reminder_minutes_before=config_data.get("reminder_minutes_before", 15),
                    )
                )
        
        # Dinner
        if config_data.get("dinner_time"):
            dinner_time = self._parse_time(config_data["dinner_time"])
            if dinner_time:
                meal_schedules.append(
                    MealSchedule(
                        meal_type=MealType.DINNER,
                        scheduled_time=dinner_time,
                        portion_size=config_data.get("portion_size", config.calculate_portion_size()),
                        reminder_enabled=config_data.get("enable_reminders", True),
                        reminder_minutes_before=config_data.get("reminder_minutes_before", 15),
                    )
                )
        
        # Snack times
        snack_times = config_data.get("snack_times", [])
        for snack_time_str in snack_times:
            snack_time = self._parse_time(snack_time_str)
            if snack_time:
                meal_schedules.append(
                    MealSchedule(
                        meal_type=MealType.SNACK,
                        scheduled_time=snack_time,
                        portion_size=50.0,  # Default snack portion
                        reminder_enabled=False,  # No reminders for snacks by default
                    )
                )
        
        config.meal_schedules = meal_schedules
        return config
    
    def _parse_time(self, time_str: str) -> Optional[time]:
        """Parse time string to time object.
        
        Args:
            time_str: Time string (HH:MM:SS or HH:MM)
            
        Returns:
            Parsed time or None
        """
        try:
            if isinstance(time_str, time):
                return time_str
            
            parts = time_str.split(":")
            if len(parts) == 2:
                return time(int(parts[0]), int(parts[1]))
            elif len(parts) == 3:
                return time(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, AttributeError):
            _LOGGER.warning("Failed to parse time: %s", time_str)
        
        return None
    
    async def _setup_reminders(self, dog_id: str) -> None:
        """Setup feeding reminders for a dog.
        
        Args:
            dog_id: Dog identifier
        """
        # Cancel existing reminders
        if dog_id in self._reminders:
            self._reminders[dog_id].cancel()
        
        # Create reminder task
        self._reminders[dog_id] = asyncio.create_task(
            self._reminder_loop(dog_id)
        )
    
    async def _reminder_loop(self, dog_id: str) -> None:
        """Reminder loop for a dog.
        
        Args:
            dog_id: Dog identifier
        """
        while True:
            try:
                config = self._configs.get(dog_id)
                if not config:
                    break
                
                # Find next reminder time
                next_reminder = None
                next_schedule = None
                
                for schedule in config.get_todays_schedules():
                    reminder_time = schedule.get_reminder_time()
                    if reminder_time and (next_reminder is None or reminder_time < next_reminder):
                        next_reminder = reminder_time
                        next_schedule = schedule
                
                if next_reminder:
                    # Wait until reminder time
                    now = dt_util.now()
                    if next_reminder > now:
                        wait_seconds = (next_reminder - now).total_seconds()
                        await asyncio.sleep(wait_seconds)
                        
                        # Send reminder (this would integrate with notification system)
                        _LOGGER.info(
                            "Feeding reminder for %s: %s in %d minutes",
                            dog_id,
                            next_schedule.meal_type.value,
                            next_schedule.reminder_minutes_before
                        )
                else:
                    # No more reminders today, wait until tomorrow
                    tomorrow = dt_util.now() + timedelta(days=1)
                    tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0)
                    wait_seconds = (tomorrow_start - dt_util.now()).total_seconds()
                    await asyncio.sleep(wait_seconds)
                    
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in reminder loop for %s: %s", dog_id, err)
                await asyncio.sleep(300)  # Retry in 5 minutes
    
    async def async_add_feeding(
        self,
        dog_id: str,
        amount: float,
        meal_type: Optional[str] = None,
        time: Optional[datetime] = None,
        notes: Optional[str] = None,
        feeder: Optional[str] = None,
        scheduled: bool = False,
    ) -> FeedingEvent:
        """Record a feeding event for a dog.
        
        Args:
            dog_id: Identifier of the dog
            amount: Amount of food provided in grams
            meal_type: Type of meal
            time: Optional timestamp (uses current time if not provided)
            notes: Optional notes about the feeding
            feeder: Who fed the dog
            scheduled: Whether this was a scheduled feeding
            
        Returns:
            Created FeedingEvent
        """
        async with self._lock:
            # Parse meal type
            meal_type_enum = None
            if meal_type:
                try:
                    meal_type_enum = MealType(meal_type)
                except ValueError:
                    _LOGGER.warning("Invalid meal type: %s", meal_type)
            
            # Get config for portion size
            config = self._configs.get(dog_id)
            portion_size = None
            if config and meal_type_enum:
                for schedule in config.meal_schedules:
                    if schedule.meal_type == meal_type_enum:
                        portion_size = schedule.portion_size
                        break
            
            event = FeedingEvent(
                time=time or dt_util.now(),
                amount=amount,
                meal_type=meal_type_enum,
                portion_size=portion_size,
                food_type=config.food_type if config else None,
                notes=notes,
                feeder=feeder,
                scheduled=scheduled,
            )
            
            self._feedings.setdefault(dog_id, []).append(event)
            
            # Maintain size limit (keep last 100 feedings)
            if len(self._feedings[dog_id]) > 100:
                self._feedings[dog_id] = self._feedings[dog_id][-100:]
            
            return event
    
    async def async_skip_feeding(
        self,
        dog_id: str,
        meal_type: str,
        reason: Optional[str] = None
    ) -> FeedingEvent:
        """Record a skipped feeding.
        
        Args:
            dog_id: Identifier of the dog
            meal_type: Type of meal skipped
            reason: Reason for skipping
            
        Returns:
            Created FeedingEvent with skipped flag
        """
        async with self._lock:
            meal_type_enum = None
            try:
                meal_type_enum = MealType(meal_type)
            except ValueError:
                _LOGGER.warning("Invalid meal type: %s", meal_type)
            
            event = FeedingEvent(
                time=dt_util.now(),
                amount=0,
                meal_type=meal_type_enum,
                notes=reason,
                scheduled=True,
                skipped=True,
            )
            
            self._feedings.setdefault(dog_id, []).append(event)
            
            return event
    
    async def async_get_feedings(
        self,
        dog_id: str,
        since: Optional[datetime] = None
    ) -> List[FeedingEvent]:
        """Return feeding history for a dog.
        
        Args:
            dog_id: Dog identifier
            since: Optional datetime to filter feedings since
            
        Returns:
            List of feeding events
        """
        async with self._lock:
            feedings = self._feedings.get(dog_id, [])
            
            if since:
                feedings = [f for f in feedings if f.time >= since]
            
            return list(feedings)
    
    async def async_get_feeding_data(self, dog_id: str) -> dict[str, Any]:
        """Return comprehensive feeding data with schedule adherence.
        
        Args:
            dog_id: Dog identifier
            
        Returns:
            Dictionary with feeding statistics and schedule info
        """
        async with self._lock:
            feedings = self._feedings.get(dog_id, [])
            config = self._configs.get(dog_id)
            
            if not feedings:
                return {
                    "last_feeding": None,
                    "feedings_today": {},
                    "total_feedings_today": 0,
                    "daily_amount_consumed": 0,
                    "daily_amount_target": config.daily_food_amount if config else 500,
                    "schedule_adherence": 100,
                    "next_feeding": None,
                    "missed_feedings": [],
                }
            
            now = dt_util.now()
            today = now.date()
            
            # Analyze today's feedings
            feedings_today: Dict[str, int] = {}
            daily_amount = 0.0
            scheduled_feedings = []
            actual_feedings = []
            
            for event in feedings:
                if event.time.date() != today:
                    continue
                
                if not event.skipped:
                    meal = event.meal_type.value if event.meal_type else "unknown"
                    feedings_today[meal] = feedings_today.get(meal, 0) + 1
                    daily_amount += event.amount
                    
                    if event.scheduled:
                        scheduled_feedings.append(event)
                    actual_feedings.append(event)
            
            # Find last feeding
            last_event = None
            for event in reversed(feedings):
                if not event.skipped:
                    last_event = event
                    break
            
            last_time = last_event.time if last_event else None
            last_hours = ((now - last_time).total_seconds() / 3600) if last_time else None
            
            # Calculate schedule adherence
            adherence = 100
            missed_feedings = []
            
            if config and config.schedule_type != FeedingScheduleType.FLEXIBLE:
                todays_schedules = config.get_todays_schedules()
                expected = len(todays_schedules)
                
                # Check which scheduled feedings were completed
                for schedule in todays_schedules:
                    scheduled_datetime = datetime.combine(today, schedule.scheduled_time)
                    scheduled_datetime = dt_util.as_local(scheduled_datetime)
                    
                    if scheduled_datetime <= now:
                        # Should have been fed by now
                        fed = False
                        for event in actual_feedings:
                            if event.meal_type == schedule.meal_type:
                                # Check if feeding was within 1 hour of scheduled time
                                time_diff = abs((event.time - scheduled_datetime).total_seconds())
                                if time_diff <= 3600:  # Within 1 hour
                                    fed = True
                                    break
                        
                        if not fed:
                            missed_feedings.append({
                                "meal_type": schedule.meal_type.value,
                                "scheduled_time": scheduled_datetime.isoformat(),
                            })
                
                if expected > 0:
                    completed = expected - len(missed_feedings)
                    adherence = int((completed / expected) * 100)
            
            # Find next feeding
            next_feeding = None
            if config:
                for schedule in config.get_active_schedules():
                    next_time = schedule.get_next_feeding_time()
                    if next_feeding is None or next_time < next_feeding:
                        next_feeding = next_time
            
            return {
                "last_feeding": last_time.isoformat() if last_time else None,
                "last_feeding_type": last_event.meal_type.value if last_event and last_event.meal_type else None,
                "last_feeding_hours": last_hours,
                "last_feeding_amount": last_event.amount if last_event else None,
                "feedings_today": feedings_today,
                "total_feedings_today": sum(feedings_today.values()),
                "daily_amount_consumed": daily_amount,
                "daily_amount_target": config.daily_food_amount if config else 500,
                "daily_amount_percentage": int((daily_amount / config.daily_food_amount * 100)) if config and config.daily_food_amount > 0 else 0,
                "schedule_adherence": adherence,
                "next_feeding": next_feeding.isoformat() if next_feeding else None,
                "next_feeding_type": self._get_next_feeding_type(config, next_feeding) if config and next_feeding else None,
                "missed_feedings": missed_feedings,
                "config": {
                    "meals_per_day": config.meals_per_day if config else 2,
                    "food_type": config.food_type if config else "dry_food",
                    "schedule_type": config.schedule_type.value if config else "flexible",
                } if config else None,
            }
    
    def _get_next_feeding_type(
        self,
        config: FeedingConfig,
        next_feeding_time: datetime
    ) -> Optional[str]:
        """Get the meal type for the next feeding.
        
        Args:
            config: Feeding configuration
            next_feeding_time: Next feeding datetime
            
        Returns:
            Meal type string or None
        """
        for schedule in config.get_active_schedules():
            if schedule.get_next_feeding_time() == next_feeding_time:
                return schedule.meal_type.value
        return None
    
    async def async_update_config(
        self,
        dog_id: str,
        config_data: Dict[str, Any]
    ) -> None:
        """Update feeding configuration for a dog.
        
        Args:
            dog_id: Dog identifier
            config_data: New configuration data
        """
        async with self._lock:
            config = await self._create_feeding_config(dog_id, config_data)
            self._configs[dog_id] = config
            
            # Restart reminders if needed
            if config.schedule_type != FeedingScheduleType.FLEXIBLE:
                await self._setup_reminders(dog_id)
            elif dog_id in self._reminders:
                self._reminders[dog_id].cancel()
                del self._reminders[dog_id]
    
    async def async_get_statistics(
        self,
        dog_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get feeding statistics for a dog.
        
        Args:
            dog_id: Dog identifier
            days: Number of days to analyze
            
        Returns:
            Dictionary with feeding statistics
        """
        async with self._lock:
            feedings = self._feedings.get(dog_id, [])
            config = self._configs.get(dog_id)
            
            since = dt_util.now() - timedelta(days=days)
            recent_feedings = [f for f in feedings if f.time >= since]
            
            if not recent_feedings:
                return {
                    "period_days": days,
                    "total_feedings": 0,
                    "average_daily_feedings": 0,
                    "average_daily_amount": 0,
                    "most_common_meal": None,
                    "schedule_adherence": 100,
                }
            
            # Calculate statistics
            daily_counts = {}
            daily_amounts = {}
            meal_counts = {}
            
            for feeding in recent_feedings:
                if feeding.skipped:
                    continue
                
                date = feeding.time.date()
                daily_counts[date] = daily_counts.get(date, 0) + 1
                daily_amounts[date] = daily_amounts.get(date, 0.0) + feeding.amount
                
                if feeding.meal_type:
                    meal = feeding.meal_type.value
                    meal_counts[meal] = meal_counts.get(meal, 0) + 1
            
            # Find most common meal
            most_common_meal = None
            if meal_counts:
                most_common_meal = max(meal_counts, key=meal_counts.get)
            
            # Calculate averages
            avg_daily_feedings = sum(daily_counts.values()) / len(daily_counts) if daily_counts else 0
            avg_daily_amount = sum(daily_amounts.values()) / len(daily_amounts) if daily_amounts else 0
            
            # Calculate schedule adherence
            adherence = 100
            if config and config.schedule_type != FeedingScheduleType.FLEXIBLE:
                expected_daily = len(config.get_active_schedules())
                if expected_daily > 0:
                    adherence = int((avg_daily_feedings / expected_daily) * 100)
            
            return {
                "period_days": days,
                "total_feedings": len(recent_feedings),
                "average_daily_feedings": round(avg_daily_feedings, 1),
                "average_daily_amount": round(avg_daily_amount, 1),
                "most_common_meal": most_common_meal,
                "schedule_adherence": adherence,
                "daily_target_met_percentage": int((avg_daily_amount / config.daily_food_amount * 100)) if config and config.daily_food_amount > 0 else 0,
            }
    
    async def async_shutdown(self) -> None:
        """Shutdown feeding manager and cancel reminders."""
        # Cancel all reminder tasks
        for task in self._reminders.values():
            task.cancel()
        
        # Wait for tasks to complete
        if self._reminders:
            await asyncio.gather(*self._reminders.values(), return_exceptions=True)
        
        self._reminders.clear()
        self._feedings.clear()
        self._configs.clear()
