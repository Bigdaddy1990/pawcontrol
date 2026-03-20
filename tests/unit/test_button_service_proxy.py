"""Tests for button platform service proxy helpers."""

from types import SimpleNamespace

from homeassistant.core import HomeAssistant
import pytest

from custom_components.pawcontrol.button import (
    _prepare_service_proxy,
    _ServiceRegistryProxy,
)
from tests.helpers.homeassistant_test_stubs import ServiceCall, ServiceRegistry


@pytest.mark.asyncio
async def test_service_registry_proxy_forwards_calls_and_attributes() -> None:
    """The proxy should forward service calls and attribute access."""
    calls: list[tuple[str, str, dict[str, object] | None, bool, object | None]] = []

    class RegistryDouble:
        custom_marker = "pawcontrol"

        async def async_call(
            self,
            domain: str,
            service: str,
            service_data: dict[str, object] | None = None,
            blocking: bool = False,
            context: object | None = None,
        ) -> None:
            calls.append((domain, service, service_data, blocking, context))

    proxy = _ServiceRegistryProxy(RegistryDouble())

    await proxy.async_call(
        "notify",
        "send",
        {"message": "Coverage"},
        blocking=True,
    )

    assert proxy.custom_marker == "pawcontrol"
    assert calls == [("notify", "send", {"message": "Coverage"}, True, None)]


def test_prepare_service_proxy_wraps_and_reuses_service_registry() -> None:
    """Preparing services should wrap Home Assistant's registry once."""
    hass = HomeAssistant()
    registry = hass.services

    proxy = _prepare_service_proxy(hass)

    assert isinstance(proxy, _ServiceRegistryProxy)
    assert proxy is hass.services
    assert hass.data["_pawcontrol_service_proxy"] is proxy

    hass.services = registry
    reused_proxy = _prepare_service_proxy(hass)

    assert reused_proxy is proxy
    assert hass.services is proxy


def test_prepare_service_proxy_preserves_service_like_protocol_instance() -> None:
    """Objects matching the service protocol should be returned unchanged."""

    class CustomServices:
        async def async_call(
            self,
            domain: str,
            service: str,
            service_data: dict[str, object] | None = None,
            blocking: bool = False,
            context: object | None = None,
        ) -> None:
            return None

    services = CustomServices()
    hass = SimpleNamespace(data={}, services=services)

    assert _prepare_service_proxy(hass) is services
    assert hass.data == {}
    assert hass.services is services


@pytest.mark.parametrize(
    "hass",
    [
        SimpleNamespace(data={}),
        SimpleNamespace(data={}, services=None),
        SimpleNamespace(data={}, services=object()),
    ],
)
def test_prepare_service_proxy_returns_none_for_missing_or_invalid_services(
    hass: object,
) -> None:
    """Unsupported service surfaces should be ignored safely."""
    assert _prepare_service_proxy(hass) is None
