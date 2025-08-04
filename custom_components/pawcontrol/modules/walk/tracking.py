"""Tracking-Funktionen für Gassi-Module von Paw Control."""
from datetime import UTC, datetime
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from ...helpers.services import call_service
from ...const import CONF_DOG_NAME

async def setup_walk_tracking(hass: HomeAssistant, entry: ConfigEntry) -> None:
    dog = entry.data[CONF_DOG_NAME]
    last_walk_id = f"sensor.{dog}_last_walk"
    hass.states.async_set(
        last_walk_id,
        datetime.now(UTC).isoformat(),
        {"friendly_name": f"{dog} Letzter Spaziergang"},
    )
    walk_counter_id = f"counter.{dog}_walks"
    if not hass.states.get(walk_counter_id):
        await call_service(hass, "counter", "create", {"name": f"{dog} Walks"})
