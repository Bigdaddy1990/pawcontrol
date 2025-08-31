"""Discovery support for PawControl."""
from __future__ import annotations
from typing import Any

DISCOVERY_SOURCES = {
    "usb": {"vid": "1234", "pid": "abcd"},
    "zeroconf": {"service": "_pawcontrol._tcp.local."},
    "dhcp": {"mac": "00:11:22:33:44"},
}

async def async_get_discovered_devices(hass: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for source, data in DISCOVERY_SOURCES.items():
        results.append({"source": source, "data": data})
    return results
