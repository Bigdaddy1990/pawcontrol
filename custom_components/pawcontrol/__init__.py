from homeassistant.core import HomeAssistant
from .setup_hundesystem import SetupCoordinator

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    coordinator = SetupCoordinator(hass)
    hass.async_create_task(coordinator.async_setup())
    return True
