"""Push module for Paw Control – service, target handling, setup/teardown."""

from typing import Any, Optional

from .const import CONF_DOG_NAME, DOMAIN, SERVICE_SEND_NOTIFICATION
from .utils import register_services


async def send_notification(
    hass: Any,
    dog: str,
    helper_id: str,
    message: str,
    title: str,
    target: Optional[str] = None,
) -> None:
    """Send a notification if the helper is active.

    If ``target`` is provided, the ``notify`` service is used. Otherwise a
    persistent notification is created. Notifications are only sent when the
    ``input_boolean`` helper is in state ``on``.
    """

    helper_state = hass.states.get(helper_id)
    if not helper_state or getattr(helper_state, "state", None) != "on":
        return

    payload = {"message": f"{dog}: {message}", "title": title}
    if target:
        await hass.services.async_call("notify", target, payload, blocking=True)
    else:
        hass.components.persistent_notification.create(
            payload["message"], title=payload["title"]
        )


async def setup_push(hass, entry):
    """Register push service and helper for notifications."""
    dog = entry.data[CONF_DOG_NAME]
    helper_id = f"input_boolean.{dog}_push_active"

    # Create helper if it doesn't exist yet
    if not hass.states.get(helper_id):
        await hass.services.async_call(
            "input_boolean",
            "create",
            {"name": f"{dog} Push aktiviert", "entity_id": helper_id},
            blocking=True,
        )

    # Register service
    async def handle_send_notification(call):
        message = call.data.get("message", "Aktion erforderlich!")
        title = call.data.get("title", f"Paw Control: {dog}")
        target = call.data.get("target")
        await send_notification(hass, dog, helper_id, message, title, target)

    register_services(
        hass,
        DOMAIN,
        {SERVICE_SEND_NOTIFICATION: handle_send_notification},
    )


async def teardown_push(hass, entry):
    """Remove push service and associated helpers."""
    dog = entry.data[CONF_DOG_NAME]
    helper_id = f"input_boolean.{dog}_push_active"
    # Remove helper
    if hass.states.get(helper_id):
        await hass.services.async_call(
            "input_boolean",
            "remove",
            {"entity_id": helper_id},
            blocking=True,
        )
    # Deregister service
    if hass.services.has_service(DOMAIN, SERVICE_SEND_NOTIFICATION):
        hass.services.async_remove(DOMAIN, SERVICE_SEND_NOTIFICATION)


async def ensure_helpers(hass, opts):
    """Ensure that push helpers exist."""
    dog = opts[CONF_DOG_NAME]
    helper_id = f"input_boolean.{dog}_push_active"
    if not hass.states.get(helper_id):
        await hass.services.async_call(
            "input_boolean",
            "create",
            {"name": f"{dog} Push aktiviert", "entity_id": helper_id},
            blocking=True,
        )
