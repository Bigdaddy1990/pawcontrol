
from __future__ import annotations
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.components import logbook
from .const import DOMAIN

def async_describe_events(hass: HomeAssistant) -> None:
    logbook.async_describe_event(
        hass,
        DOMAIN,
        "pawcontrol_walk_started",
        describe_walk_started,
    )
    logbook.async_describe_event(
        hass,
        DOMAIN,
        "pawcontrol_walk_finished",
        describe_walk_finished,
    )
    logbook.async_describe_event(
        hass,
        DOMAIN,
        "pawcontrol_safe_zone_entered",
        describe_safe_zone_entered,
    )
    logbook.async_describe_event(
        hass,
        DOMAIN,
        "pawcontrol_safe_zone_left",
        describe_safe_zone_left,
    )

def _friendly(d: dict[str, Any]) -> str:
    dog = d.get("dog_id") or "dog"
    return f"Hund {dog}"

def describe_walk_started(event: dict[str, Any]) -> dict[str, str]:
    data = event.get("data") or {}
    return {"name": _friendly(data), "message": f"Spaziergang gestartet (Typ: {data.get('walk_type','normal')})"}

def describe_walk_finished(event: dict[str, Any]) -> dict[str, str]:
    data = event.get("data") or {}
    km = round((float(data.get("distance_m") or 0.0))/1000.0, 2)
    min_ = int((float(data.get("duration_s") or 0.0))/60.0)
    return {"name": _friendly(data), "message": f"Spaziergang beendet – {km} km in {min_} min"}

def describe_safe_zone_entered(event: dict[str, Any]) -> dict[str, str]:
    data = event.get("data") or {}
    return {"name": _friendly(data), "message": "Sicherheitszone betreten"}

def describe_safe_zone_left(event: dict[str, Any]) -> dict[str, str]:
    data = event.get("data") or {}
    return {"name": _friendly(data), "message": "Sicherheitszone verlassen"}
