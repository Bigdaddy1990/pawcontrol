"""Modul-Initialisierung für Benachrichtigungen."""
from .notification_handler import setup_notification_services
from .push import setup_push_services

async def async_setup(hass, entry):
    await setup_notification_services(hass, entry)
    await setup_push_services(hass)
