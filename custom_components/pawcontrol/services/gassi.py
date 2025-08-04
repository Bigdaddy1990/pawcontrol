from homeassistant.core import HomeAssistant
from homeassistant.util.dt import now
from ..utils.helpers import make_id
import logging

_LOGGER = logging.getLogger(__name__)

async def handle_gassi_trigger(hass: HomeAssistant, dog_name: str) -> None:
    slug = dog_name.lower().replace(" ", "_")
    last_gassi_id = make_id("input_datetime", f"gassi_{slug}_last")
    active_id = make_id("input_boolean", f"gassi_{slug}_active")

    try:
        now_str = now().isoformat(timespec="seconds")
        hass.states.async_set(last_gassi_id, now_str)
        hass.states.async_set(active_id, False)
        _LOGGER.info(f"Gassi-Trigger empfangen für {dog_name}: Zeit aktualisiert.")
    except Exception as e:
        _LOGGER.warning(f"Gassi-Trigger für {dog_name} fehlgeschlagen: {e}")
