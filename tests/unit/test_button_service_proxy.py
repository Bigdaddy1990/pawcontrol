"""Tests for button platform service proxy helpers."""

from types import SimpleNamespace

from homeassistant.core import HomeAssistant
import pytest

from custom_components.pawcontrol.button import (
    PROFILE_BUTTON_LIMITS,
    ProfileAwareButtonFactory,
    _prepare_service_proxy,
    _resolve_profile_button_limit,
    _ServiceRegistryProxy,
)


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


def test_prepare_service_proxy_returns_existing_proxy_instance() -> None:
    """A pre-wrapped services proxy should be returned unchanged."""
    hass = HomeAssistant()
    proxy = _ServiceRegistryProxy(hass.services)
    hass.services = proxy
    hass.data["_pawcontrol_service_proxy"] = proxy

    assert _prepare_service_proxy(hass) is proxy


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


def test_resolve_profile_button_limit_uses_known_profile_and_fallback() -> None:
    """Known profiles should map to configured limits; unknowns use fallback."""
    assert (
        _resolve_profile_button_limit("advanced") == PROFILE_BUTTON_LIMITS["advanced"]
    )
    assert _resolve_profile_button_limit("custom_profile") == 6


@pytest.mark.parametrize(
    ("profile", "expected_min_feeding_types"),
    [
        ("basic", {"feed_now", "mark_fed"}),
        ("standard", {"feed_now", "mark_fed", "feed_breakfast", "feed_dinner"}),
        (
            "advanced",
            {
                "feed_now",
                "mark_fed",
                "feed_breakfast",
                "feed_dinner",
                "feed_lunch",
                "log_custom_feeding",
            },
        ),
    ],
)
def test_profile_factory_feeding_rules_follow_profile(
    profile: str,
    expected_min_feeding_types: set[str],
) -> None:
    """Feeding button rules should expand according to profile capability."""
    factory = ProfileAwareButtonFactory(SimpleNamespace(), profile=profile)

    feeding_rules = factory._get_feeding_button_rules()
    feeding_types = {rule["type"] for rule in feeding_rules}

    assert expected_min_feeding_types.issubset(feeding_types)


def test_profile_factory_caches_rules_for_supported_modules() -> None:
    """The factory should precompute button rules for each supported module."""
    factory = ProfileAwareButtonFactory(SimpleNamespace(), profile="gps_focus")

    assert set(factory._button_rules_cache.keys()) == {
        "feeding",
        "walk",
        "gps",
        "health",
        "garden",
    }
