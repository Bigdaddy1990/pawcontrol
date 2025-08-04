"""Modul-Initialisierung für walk."""
from .tracking import setup_walk_tracking
from .automation import setup_walk_automations

async def async_setup(hass, entry):
    await setup_walk_tracking(hass, entry)
    await setup_walk_automations(hass, entry)
