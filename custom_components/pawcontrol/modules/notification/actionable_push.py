from homeassistant.core import HomeAssistant, ServiceCall
import logging

_LOGGER = logging.getLogger(__name__)
DOMAIN = "pawcontrol"

from .utils import register_services

async def handle_send_notification(call: ServiceCall):
    hass: HomeAssistant = call.hass
    dog_name = call.data.get("dog_name")
    title = call.data.get("title", f"{dog_name}: Rückfrage")
    message = call.data.get("message", "War der Hund draußen?")
    target_devices = call.data.get("targets", [])
    person_ids = call.data.get("persons", [])

    notify_targets = set()

    # Dynamische Empfängerwahl basierend auf Anwesenheit
    for person_id in person_ids:
        person_entity = f"person.{person_id}"
        person_state = hass.states.get(person_entity)
        if person_state and person_state.state == "home":
            device_entity = f"input_text.notify_device_{person_id}"
            device_state = hass.states.get(device_entity)
            if device_state:
                notify_targets.add(device_state.state)

    notify_targets.update(target_devices)

    if not notify_targets:
        _LOGGER.warning("Keine gültigen Notify-Ziele gefunden")
        return

    actions = call.data.get("actions", [
        {"action": "yes", "title": "Ja"},
        {"action": "no", "title": "Nein"}
    ])
    data = {
        "actions": actions,
        "tag": f"{dog_name}_frage",
        "group": f"paw_control_{dog_name}",
        "clickAction": "/lovelace/pawcontrol"
    }

    for notify_target in notify_targets:
        await hass.services.async_call(
            "notify",
            notify_target,
            {
                "title": title,
                "message": message,
                "data": data
            },
            blocking=False,
        )

def setup_actionable_notifications(hass: HomeAssistant):
    register_services(hass, DOMAIN, {"send_notification": handle_send_notification})
