"""Tests for config flow discovery mixin helpers."""

from types import MappingProxyType, SimpleNamespace
from typing import Any

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.data_entry_flow import FlowResultType
import pytest

from custom_components.pawcontrol.config_flow_discovery import DiscoveryFlowMixin


class _DiscoveryFlowHarness(DiscoveryFlowMixin):
    """Harness covering discovery flow protocol handlers."""

    def __init__(self) -> None:
        self._discovery_info: dict[str, object] = {}
        self._unique_id: str | None = None
        self.supported = True
        self.existing_result: ConfigFlowResult | None = None
        self.prepared_payloads: list[tuple[dict[str, object], str]] = []
        self.abort_calls: list[dict[str, object]] = []
        self.set_unique_id_calls: list[str | None] = []
        self.add_dog_calls = 0

    def _is_supported_device(
        self, hostname: str, properties: dict[str, object]
    ) -> bool:
        return self.supported

    def _prepare_discovery_updates(
        self,
        payload: dict[str, object],
        *,
        source: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        self._discovery_info = dict(payload)
        self.prepared_payloads.append((dict(payload), source))
        return ({"payload": payload, "source": source}, payload)

    async def _handle_existing_discovery_entry(
        self,
        *,
        updates: dict[str, object],
        comparison: dict[str, object],
        reload_on_update: bool,
    ) -> ConfigFlowResult | None:
        return self.existing_result

    def _extract_device_id(self, properties: dict[str, object]) -> str | None:
        return "pawcontrol"

    def _abort_if_unique_id_configured(
        self,
        *,
        updates: dict[str, object] | None = None,
        reload_on_update: bool = False,
    ) -> ConfigFlowResult:
        self.abort_calls.append({
            "updates": updates,
            "reload_on_update": reload_on_update,
        })
        return {"type": FlowResultType.ABORT, "reason": "already_configured"}

    def _format_discovery_info(self) -> str:
        return "Tracker X"

    async def async_set_unique_id(self, unique_id: str | None = None) -> None:
        self._unique_id = unique_id
        self.set_unique_id_calls.append(unique_id)

    def async_abort(self, *, reason: str) -> ConfigFlowResult:
        return {"type": FlowResultType.ABORT, "reason": reason}

    def async_show_form(self, **kwargs: Any) -> ConfigFlowResult:
        return {
            "type": FlowResultType.FORM,
            "step_id": kwargs["step_id"],
            "description_placeholders": kwargs["description_placeholders"],
            "schema": kwargs["data_schema"],
        }

    async def async_step_add_dog(self) -> ConfigFlowResult:
        self.add_dog_calls += 1
        return {"type": FlowResultType.CREATE_ENTRY, "title": "PawControl"}


@pytest.mark.asyncio
async def test_zeroconf_unsupported_device_aborts() -> None:
    """Zeroconf path aborts when hostname/properties are unsupported."""
    flow = _DiscoveryFlowHarness()
    flow.supported = False

    result = await flow.async_step_zeroconf(
        SimpleNamespace(
            hostname="unknown.local",
            properties={"id": "x"},
            host="192.0.2.10",
            port=80,
            type="_pawcontrol._tcp.local.",
            name="PawControl",
        )
    )

    assert result == {"type": FlowResultType.ABORT, "reason": "not_supported"}
    assert flow.prepared_payloads == []


@pytest.mark.asyncio
async def test_dhcp_discovery_continues_to_confirmation_form() -> None:
    """DHCP discovery stores payload and routes to confirm form."""
    flow = _DiscoveryFlowHarness()

    result = await flow.async_step_dhcp(
        SimpleNamespace(hostname="paw.local", macaddress="AA:BB", ip="10.0.0.2")
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert flow.set_unique_id_calls == ["pawcontrol"]
    assert flow.prepared_payloads[0][1] == "dhcp"
    assert flow.prepared_payloads[0][0]["ip"] == "10.0.0.2"


@pytest.mark.asyncio
async def test_usb_existing_entry_result_short_circuits() -> None:
    """USB discovery returns existing entry handling when provided."""
    flow = _DiscoveryFlowHarness()
    flow.existing_result = {
        "type": FlowResultType.ABORT,
        "reason": "already_configured",
    }

    result = await flow.async_step_usb(
        SimpleNamespace(
            description="USB Tracker",
            serial_number="SN123",
            manufacturer="PawControl",
            vid=1234,
            pid=5678,
            device="/dev/ttyUSB0",
        )
    )

    assert result == {"type": FlowResultType.ABORT, "reason": "already_configured"}
    assert flow.prepared_payloads[0][0]["device"] == "/dev/ttyUSB0"


@pytest.mark.asyncio
async def test_bluetooth_discovery_confirm_accepts_and_adds_dog() -> None:
    """Confirm step proceeds to dog setup and keeps discovery updates."""
    flow = _DiscoveryFlowHarness()

    await flow.async_step_bluetooth(
        SimpleNamespace(name="PawTag", address="00:11", service_uuids=["abcd"])
    )
    flow._unique_id = "pawcontrol"

    result = await flow.async_step_discovery_confirm({"confirm": True})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert flow.add_dog_calls == 1
    assert flow.abort_calls == [
        {
            "updates": {"discovery_info": flow._discovery_info},
            "reload_on_update": True,
        }
    ]


@pytest.mark.asyncio
async def test_discovery_confirm_form_and_reject_branch() -> None:
    """Confirm step returns placeholders and supports explicit rejection."""
    flow = _DiscoveryFlowHarness()
    flow._discovery_info = {"source": "usb"}

    form_result = await flow.async_step_discovery_confirm()

    assert form_result["type"] == FlowResultType.FORM
    assert form_result["description_placeholders"] == MappingProxyType({
        "discovery_source": "usb",
        "device_info": "Tracker X",
    })

    reject_result = await flow.async_step_discovery_confirm({"confirm": False})
    assert reject_result == {
        "type": FlowResultType.ABORT,
        "reason": "discovery_rejected",
    }


@pytest.mark.asyncio
async def test_zeroconf_supported_device_includes_optional_metadata() -> None:
    """Zeroconf payload keeps optional fields before confirmation."""
    flow = _DiscoveryFlowHarness()

    result = await flow.async_step_zeroconf(
        SimpleNamespace(
            hostname="paw.local",
            properties={"id": "tracker"},
            host="192.0.2.11",
            port=8123,
            type="_pawcontrol._tcp.local.",
            name="PawControl Tracker",
        )
    )

    assert result["type"] == FlowResultType.FORM
    assert flow.prepared_payloads[0][1] == "zeroconf"
    assert flow.prepared_payloads[0][0]["port"] == 8123
    assert flow.prepared_payloads[0][0]["name"] == "PawControl Tracker"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("step", "payload"),
    [
        (
            "async_step_dhcp",
            SimpleNamespace(hostname="paw.local", macaddress="AA:BB", ip="10.0.0.2"),
        ),
        (
            "async_step_usb",
            SimpleNamespace(
                description="USB Tracker",
                serial_number="SN123",
                manufacturer="PawControl",
                vid=1234,
                pid=5678,
                device="/dev/ttyUSB0",
            ),
        ),
        (
            "async_step_bluetooth",
            SimpleNamespace(name="PawTag", address="00:11", service_uuids=["abcd"]),
        ),
    ],
)
async def test_discovery_steps_abort_for_unsupported_devices(
    step: str,
    payload: SimpleNamespace,
) -> None:
    """Every discovery transport aborts when support checks fail."""
    flow = _DiscoveryFlowHarness()
    flow.supported = False

    result = await getattr(flow, step)(payload)

    assert result == {"type": FlowResultType.ABORT, "reason": "not_supported"}
