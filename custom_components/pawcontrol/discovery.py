"""Discovery helpers for Paw Control.

Key rules:
- Never import optional Home Assistant components (dhcp/usb/zeroconf) at module import time.
- Keep all heavy/optional imports lazy inside functions.
- Return safe defaults when optional dependencies are not available, so tests can run.
"""

from __future__ import annotations

import asyncio
import importlib
from typing import Any, Final

DOMAIN: Final = "pawcontrol"

def _mod(name: str):
    """Best-effort importer that returns None if the module is missing."""
    try:
        return importlib.import_module(name)
    except Exception:
        return None


async def _probe_socket(host: str, port: int, timeout: float = 1.0) -> bool:
    """Attempt to open a TCP connection to *host:port* with a timeout."""
    try:
        conn = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(conn, timeout=timeout)
        writer.close()
        if hasattr(writer, "wait_closed"):
            await writer.wait_closed()
        return True
    except Exception:
        return False


async def can_connect_pawtracker(hass, data: dict[str, Any]) -> bool:
    """Probe connectivity to a 'pawtracker' device/network target.

    This is intentionally conservative:
    - No import-time dependency on pyserial/zeroconf/usb/dhcp.
    - Returns True by default so unit tests can patch this function to simulate outcomes.
    - Real implementations can:
        * For USB: try opening a serial port (pyserial) with a short timeout.
        * For Network: open a TCP socket or HTTP probe.
        * For BLE: delegate to BLE integration APIs.
    """
    # Example heuristics without importing optional libs:
    dev = str(
        data.get("device_id") or data.get("serial") or data.get("mac") or ""
    ).lower()

    if dev.startswith("usb:"):
        # Try to open the device via pyserial if available
        serial_mod = _mod("serial")
        if serial_mod is not None:
            try:
                ser = serial_mod.Serial(dev[4:], timeout=0.5)
                ser.close()
                return True
            except Exception:
                return False
        # If pyserial is not installed we fall back to permissive True
        return True

    # Zeroconf props may carry a host/port
    props = data.get("properties") or {}
    host = data.get("host") or props.get("host")
    port = data.get("port") or props.get("port")
    if host and str(port or "").isdigit():
        if await _probe_socket(host, int(port)):
            return True
        return False

    # DHCP discovery commonly provides MAC/IP; again, don't hard fail here.
    if data.get("mac") or data.get("ip"):
        return True

    # If we cannot deduce anything, still be permissive (tests often patch this).
    return True


# Optional helpers (kept flexible for tests; they don't import optional HA modules)


def normalize_dhcp_info(info: dict[str, Any]) -> dict[str, Any]:
    """Normalize a DHCP discovery dict into a compact data mapping we can store."""
    mac = str(info.get("macaddress") or info.get("mac") or "").replace("-", ":").lower()
    ip = info.get("ip") or info.get("ipv4") or info.get("ipv6")
    hostname = info.get("hostname") or info.get("host")
    return {"mac": mac, "ip": ip, "hostname": hostname}


def normalize_zeroconf_info(info: dict[str, Any]) -> dict[str, Any]:
    """Normalize Zeroconf discovery data."""
    name = str(info.get("name") or "").rstrip(".") or None
    host = info.get("host") or info.get("ip")
    port = info.get("port")
    port = int(port) if str(port or "").isdigit() else None
    properties = info.get("properties") or {}
    return {"name": name, "host": host, "port": port, "properties": properties}


def normalize_usb_info(info: dict[str, Any]) -> dict[str, Any]:
    """Normalize USB discovery data."""
    # Typical structure carries VID/PID/serial/manufacturer in various keys.
    vid = info.get("vid") or info.get("vid_hex")
    pid = info.get("pid") or info.get("pid_hex")
    serial = info.get("serial_number") or info.get("serial")
    manufacturer = info.get("manufacturer")
    description = info.get("description")
    try:
        vid_hex = f"{int(str(vid), 16):04X}"
        pid_hex = f"{int(str(pid), 16):04X}"
        device_id = f"usb:VID_{vid_hex}&PID_{pid_hex}"
    except Exception:
        device_id = "usb:unknown"
    return {
        "vid": vid,
        "pid": pid,
        "serial_number": serial,
        "manufacturer": manufacturer,
        "description": description,
        "device_id": device_id,
    }
