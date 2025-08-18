"""Connectivity checks for Paw Control (minimal, HA-safe).

- No optional HA discovery (dhcp/usb/zeroconf).
- No heavy imports or blocking I/O.
- Deterministic True by default; tests can patch to simulate failures.
"""
from __future__ import annotations
from typing import Any
from homeassistant.core import HomeAssistant

async def can_connect_pawtracker(hass: HomeAssistant, data: dict[str, Any]) -> bool:
    """Return True if HA core is running; avoid any external dependencies.

    This intentionally does NOT probe network/USB/BLE. The integration
    assigns trackers via existing HA sensors/entities during setup.
    """
    return hasattr(hass, "bus") and hass.bus is not None
