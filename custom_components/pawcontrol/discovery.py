"""Discovery configuration for Paw Control integration."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.components import dhcp, usb, zeroconf
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

# USB Discovery patterns for dog trackers
USB_DISCOVERY_INFO = [
    {
        "vid": "10C4",  # Silicon Labs
        "pid": "EA60",  # CP210x
        "description": "*pawtracker*",
        "manufacturer": "*PawControl*",
    },
    {
        "vid": "0403",  # FTDI
        "pid": "6001",  # FT232
        "description": "*dog*tracker*",
        "manufacturer": "*Smart*Pet*",
    },
]

# mDNS/Zeroconf discovery patterns
ZEROCONF_TYPE = "_pawcontrol._tcp.local."

# DHCP discovery patterns for network-enabled dog devices
DHCP_MATCHERS = [
    {
        "domain": "pawcontrol.local",
        "macaddress": "AA:BB:CC:*",
    },
    {
        "hostname": "pawtracker-*",
        "macaddress": "DC:A6:32:*",  # Raspberry Pi Foundation
    },
]


class PawControlDiscoveryFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle discovery flow for Paw Control."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize discovery flow."""
        self._discovered_device: dict[str, Any] = {}

    async def async_step_usb(self, discovery_info: usb.UsbServiceInfo) -> FlowResult:
        """Handle USB discovery."""
        await self.async_set_unique_id(
            f"{DOMAIN}_usb_{discovery_info.vid}_{discovery_info.pid}_{discovery_info.serial_number or 'unknown'}"
        )
        self._abort_if_unique_id_configured()

        self._discovered_device = {
            "type": "usb",
            "device": discovery_info.device,
            "description": discovery_info.description,
            "manufacturer": discovery_info.manufacturer,
            "serial": discovery_info.serial_number,
        }

        return await self.async_step_usb_confirm()

    async def async_step_usb_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm USB discovery."""
        if user_input is not None:
            # Continue with normal setup flow
            return await self.async_step_user()

        device_info = self._discovered_device
        return self.async_show_form(
            step_id="usb_confirm",
            description_placeholders={
                "device": device_info.get("description", "Unknown device"),
                "manufacturer": device_info.get("manufacturer", "Unknown"),
            },
        )

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle Zeroconf discovery."""
        host = discovery_info.host
        name = discovery_info.name.replace(f".{ZEROCONF_TYPE}", "")

        await self.async_set_unique_id(f"{DOMAIN}_mdns_{discovery_info.hostname}")
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._discovered_device = {
            "type": "zeroconf",
            CONF_HOST: host,
            CONF_NAME: name,
            "properties": discovery_info.properties,
        }

        self.context["title_placeholders"] = {
            "name": name,
        }

        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm Zeroconf discovery."""
        if user_input is not None:
            # Continue with normal setup flow
            return await self.async_step_user()

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={
                "name": self._discovered_device.get(CONF_NAME, "Unknown"),
                "host": self._discovered_device.get(CONF_HOST, "Unknown"),
            },
        )

    async def async_step_dhcp(
        self, discovery_info: dhcp.DhcpServiceInfo
    ) -> FlowResult:
        """Handle DHCP discovery."""
        await self.async_set_unique_id(
            f"{DOMAIN}_dhcp_{discovery_info.macaddress.replace(':', '')}"
        )
        self._abort_if_unique_id_configured()

        self._discovered_device = {
            "type": "dhcp",
            "ip": discovery_info.ip,
            "hostname": discovery_info.hostname,
            "macaddress": discovery_info.macaddress,
        }

        return await self.async_step_dhcp_confirm()

    async def async_step_dhcp_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm DHCP discovery."""
        if user_input is not None:
            # Continue with normal setup flow
            return await self.async_step_user()

        device_info = self._discovered_device
        return self.async_show_form(
            step_id="dhcp_confirm",
            description_placeholders={
                "hostname": device_info.get("hostname", "Unknown"),
                "ip": device_info.get("ip", "Unknown"),
            },
        )


def register_discovery() -> None:
    """Register discovery patterns with Home Assistant."""
    # This function would be called during integration setup
    # to register the discovery patterns
    pass
