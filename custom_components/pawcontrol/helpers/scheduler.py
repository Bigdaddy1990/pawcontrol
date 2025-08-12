
"""Scheduler for Paw Control (daily reset of 'today' counters)."""
from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change

_LOGGER = logging.getLogger(__name__)

class PawScheduler:
    def __init__(self, hass: HomeAssistant, reset_time: str = "23:59:00", domain: str | None = None, entry=None):
        self.hass = hass
        self.reset_time = reset_time or "23:59:00"
        self.domain = domain or "pawcontrol"
        self.entry = entry

    async def async_setup(self) -> None:
        try:
            hh, mm, ss = [int(x) for x in (self.reset_time or "23:59:00").split(":")]
        except Exception:
            hh, mm, ss = 23, 59, 0
        async_track_time_change(self.hass, self._on_daily_reset, hour=hh, minute=mm, second=ss)

    async def _on_daily_reset(self, now) -> None:
        try:
            opts = (self.entry.options or {}) if self.entry else {}
            dogs = opts.get("dogs") or []
            for d in dogs:
                dog = d.get("dog_id") or d.get("name")
                if not dog:
                    continue
                # Distance / time today
                self.hass.states.async_set(f"sensor.{self.domain}_{dog}_walk_distance_today", 0.0, {"unit_of_measurement": "m"})
                self.hass.states.async_set(f"sensor.{self.domain}_{dog}_walk_time_today", 0, {"unit_of_measurement": "s"})
                # Safe zone diagnostics
                self.hass.states.async_set(f"sensor.{self.domain}_{dog}_time_in_safe_zone_today", 0, {"unit_of_measurement": "s"})
                self.hass.states.async_set(f"sensor.{self.domain}_{dog}_safe_zone_enters_today", 0)
                self.hass.states.async_set(f"sensor.{self.domain}_{dog}_safe_zone_leaves_today", 0)
            _LOGGER.debug("PawScheduler daily reset executed at %s for %d dogs", now, len(dogs))
        except Exception as exc:
            _LOGGER.debug("PawScheduler reset error: %s", exc)
