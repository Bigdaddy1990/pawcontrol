"""Setup- und Registrierungsmodul für Paw Control."""
from .installation_manager import setup_installation
from .setup_verifier import verify_installation
from .module_registry import register_modules

async def async_setup(hass, entry):
    await setup_installation(hass, entry)
    await verify_installation(hass)
    register_modules(hass)
