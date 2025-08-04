from homeassistant.core import HomeAssistant
from ..utils.helpers import make_id
import logging

_LOGGER = logging.getLogger(__name__)

async def send_notification(hass: HomeAssistant, dog_name: str, message: str, actions: list = None) -> None:
    try:
        # Config abrufen
        notify_config_state = hass.states.get("input_text.pawcontrol_setup_notifications_config")
        import json
        config = json.loads(notify_config_state.state) if notify_config_state else {}
        if not config.get("active", False):
            return

        targets = config.get("devices", [])
        fallback = config.get("fallback_device", "notify.notify")

        if not targets:
            targets = [fallback]

        # Daten vorbereiten
        data = {"message": message, "title": f"PawControl – {dog_name}"}
        if actions:
            data["data"] = {
                "actions": actions
            }

        for target in targets:
            try:
                await hass.services.async_call(
                    domain=target.split(".")[0],
                    service=target.split(".")[1],
                    service_data=data,
                    blocking=False
                )
            except Exception as e:
                _LOGGER.warning(f"Fehler beim Senden an {target}: {e}")

    except Exception as e:
        _LOGGER.error(f"Notification-Fehler: {e}")
