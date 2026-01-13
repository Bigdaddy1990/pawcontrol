"""Discovery steps for the PawControl config flow."""
from __future__ import annotations

import logging
from typing import Any
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.usb import UsbServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .types import ConfigFlowDiscoveryData
from .types import ConfigFlowDiscoveryProperties
from .types import DiscoveryConfirmInput
from .types import freeze_placeholders

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
else:  # pragma: no cover - only used for typing
    BluetoothServiceInfoBleak = Any

_LOGGER = logging.getLogger(__name__)


class DiscoveryFlowMixin:
    """Mixin that provides HA discovery steps for the config flow."""

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo,
    ) -> ConfigFlowResult:
        """Handle Zeroconf discovery."""

        _LOGGER.debug('Zeroconf discovery: %s', discovery_info)

        hostname = discovery_info.hostname or ''
        properties_raw = discovery_info.properties or {}
        properties: ConfigFlowDiscoveryProperties = dict(properties_raw)

        if not self._is_supported_device(hostname, properties):
            return self.async_abort(reason='not_supported')

        discovery_payload: ConfigFlowDiscoveryData = {
            'source': 'zeroconf',
            'hostname': hostname,
            'host': discovery_info.host or '',
            'properties': properties,
        }

        if discovery_info.port is not None:
            discovery_payload['port'] = int(discovery_info.port)
        if discovery_info.type:
            discovery_payload['type'] = discovery_info.type
        if discovery_info.name:
            discovery_payload['name'] = discovery_info.name

        updates, comparison = self._prepare_discovery_updates(
            discovery_payload, source='zeroconf',
        )

        device_id = self._extract_device_id(properties)
        if device_id:
            await self.async_set_unique_id(device_id)
            result = await self._handle_existing_discovery_entry(
                updates=updates,
                comparison=comparison,
                reload_on_update=True,
            )
            if result is not None:
                return result

        return await self.async_step_discovery_confirm()

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo,
    ) -> ConfigFlowResult:
        """Handle DHCP discovery."""

        _LOGGER.debug('DHCP discovery: %s', discovery_info)

        hostname = discovery_info.hostname or ''
        macaddress = discovery_info.macaddress or ''

        if not self._is_supported_device(hostname, {'mac': macaddress}):
            return self.async_abort(reason='not_supported')

        dhcp_payload: ConfigFlowDiscoveryData = {
            'source': 'dhcp',
            'hostname': hostname,
            'macaddress': macaddress,
        }
        if discovery_info.ip:
            dhcp_payload['ip'] = discovery_info.ip

        updates, comparison = self._prepare_discovery_updates(
            dhcp_payload, source='dhcp',
        )

        await self.async_set_unique_id(macaddress)
        result = await self._handle_existing_discovery_entry(
            updates=updates,
            comparison=comparison,
            reload_on_update=True,
        )
        if result is not None:
            return result

        return await self.async_step_discovery_confirm()

    async def async_step_usb(self, discovery_info: UsbServiceInfo) -> ConfigFlowResult:
        """Handle USB discovery for supported trackers."""

        _LOGGER.debug('USB discovery: %s', discovery_info)

        description = discovery_info.description or ''
        serial_number = discovery_info.serial_number or ''
        hostname_hint = description or serial_number
        properties: ConfigFlowDiscoveryProperties = {
            'serial': serial_number,
            'vid': discovery_info.vid,
            'pid': discovery_info.pid,
            'manufacturer': discovery_info.manufacturer,
            'description': description,
        }

        if not self._is_supported_device(hostname_hint, properties):
            return self.async_abort(reason='not_supported')

        usb_payload: ConfigFlowDiscoveryData = {
            'source': 'usb',
            'description': description,
            'manufacturer': discovery_info.manufacturer or '',
            'vid': str(discovery_info.vid) if discovery_info.vid is not None else '',
            'pid': str(discovery_info.pid) if discovery_info.pid is not None else '',
            'serial_number': serial_number,
        }
        if discovery_info.device:
            usb_payload['device'] = discovery_info.device

        updates, comparison = self._prepare_discovery_updates(
            usb_payload, source='usb',
        )

        unique_id = serial_number or f"{discovery_info.vid}:{discovery_info.pid}"
        if unique_id:
            await self.async_set_unique_id(unique_id)
            result = await self._handle_existing_discovery_entry(
                updates=updates,
                comparison=comparison,
                reload_on_update=True,
            )
            if result is not None:
                return result

        return await self.async_step_discovery_confirm()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak,
    ) -> ConfigFlowResult:
        """Handle Bluetooth discovery for supported trackers."""

        _LOGGER.debug('Bluetooth discovery: %s', discovery_info)

        name = getattr(discovery_info, 'name', '') or ''
        address = getattr(discovery_info, 'address', '') or ''
        service_uuids = list(
            getattr(discovery_info, 'service_uuids', []) or [],
        )

        hostname_hint = name or address
        properties: ConfigFlowDiscoveryProperties = {
            'address': address,
            'service_uuids': service_uuids,
            'name': name,
        }

        if not self._is_supported_device(hostname_hint, properties):
            return self.async_abort(reason='not_supported')

        bluetooth_payload: ConfigFlowDiscoveryData = {
            'source': 'bluetooth',
            'name': name,
            'address': address,
            'service_uuids': service_uuids,
        }

        updates, comparison = self._prepare_discovery_updates(
            bluetooth_payload, source='bluetooth',
        )

        if address:
            await self.async_set_unique_id(address)
            result = await self._handle_existing_discovery_entry(
                updates=updates,
                comparison=comparison,
                reload_on_update=True,
            )
            if result is not None:
                return result

        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: DiscoveryConfirmInput | None = None,
    ) -> ConfigFlowResult:
        """Confirm discovered device setup."""

        if user_input is not None:
            if user_input.get('confirm', False):
                return await self.async_step_add_dog()
            return self.async_abort(reason='discovery_rejected')

        discovery_source = self._discovery_info.get('source', 'unknown')
        device_info = self._format_discovery_info()

        return self.async_show_form(
            step_id='discovery_confirm',
            data_schema=vol.Schema(
                {vol.Required('confirm', default=True): cv.boolean},
            ),
            description_placeholders=dict(
                freeze_placeholders(
                    {
                        'discovery_source': discovery_source,
                        'device_info': device_info,
                    },
                ),
            ),
        )
