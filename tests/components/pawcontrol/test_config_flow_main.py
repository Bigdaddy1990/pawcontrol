"""Tests for ``config_flow_main`` helpers and validation paths."""

from __future__ import annotations

from collections.abc import Mapping

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol import config_flow_main
from custom_components.pawcontrol.config_flow_main import PawControlConfigFlow
from custom_components.pawcontrol.const import CONF_DOGS, DOMAIN
from custom_components.pawcontrol.exceptions import ConfigurationError, ValidationError
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD


@pytest.mark.asyncio
async def test_validate_import_config_rejects_non_list_dogs() -> None:
    """Import validation should reject non-list dog payloads."""
    flow = PawControlConfigFlow()

    with pytest.raises(ConfigurationError, match="Dogs configuration must be a list"):
        await flow._validate_import_config_enhanced({CONF_DOGS: "bad"})


@pytest.mark.asyncio
async def test_validate_import_config_collects_invalid_dog_errors() -> None:
    """Import validation should include position-specific errors for bad rows."""
    flow = PawControlConfigFlow()

    with pytest.raises(
        ValidationError, match="Dog entry at position 1 must be a mapping"
    ):
        await flow._validate_import_config_enhanced({CONF_DOGS: ["bad-entry"]})


@pytest.mark.asyncio
async def test_validate_import_config_uses_profile_fallback_and_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Import validation should fallback unsupported profiles and preserve warnings."""
    flow = PawControlConfigFlow()

    def _validate_dog_import_input(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
        }

    monkeypatch.setattr(
        config_flow_main,
        "validate_dog_import_input",
        _validate_dog_import_input,
    )
    monkeypatch.setattr(
        flow._entity_factory,
        "validate_profile_for_modules",
        lambda profile, modules: False,
    )

    result = await flow._validate_import_config_enhanced({
        CONF_DOGS: [{"any": "payload"}],
        "entity_profile": "invalid-profile",
        "dashboard_enabled": 0,
        "dashboard_auto_create": 1,
    })

    assert result["data"]["entity_profile"] == "standard"
    warnings = result["data"]["import_warnings"]
    assert any("Invalid profile" in warning for warning in warnings)
    assert any("may not be optimal" in warning for warning in warnings)
    assert result["options"]["dashboard_enabled"] is False
    assert result["options"]["dashboard_auto_create"] is True


def test_normalise_discovery_metadata_normalises_fields() -> None:
    """Discovery metadata should be normalized and cast to serializable types."""
    flow = PawControlConfigFlow()

    class _Stringify:
        def __str__(self) -> str:
            return "custom-value"

    payload = {
        "source": "INVALID",
        "hostname": "  tracker-1  ",
        "ip": 127001,
        "port": " 8123 ",
        "properties": {
            "serial": b"abc",
            "bad-bytes": b"\xff",
            "skip": None,
            "custom": _Stringify(),
        },
        "service_uuids": ["  uuid-1  ", b"uuid-2", 7, None],
    }

    normalized = flow._normalise_discovery_metadata(payload)

    assert normalized["source"] == "unknown"
    assert normalized["hostname"] == "tracker-1"
    assert normalized["ip"] == "127001"
    assert normalized["port"] == 8123
    assert normalized["properties"] == {
        "serial": "abc",
        "bad-bytes": "",
        "custom": "custom-value",
    }
    assert normalized["service_uuids"] == ["uuid-1", "uuid-2", "7"]


@pytest.mark.asyncio
async def test_async_get_entry_for_unique_id_matches_casefold(
    hass,
) -> None:
    """Unique ID matching should fall back to case-insensitive comparison."""
    flow = PawControlConfigFlow()
    flow.hass = hass
    flow._unique_id = "PAWCONTROL"

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="pawcontrol",
        data={},
        state=ConfigEntryState.LOADED,
    )

    flow._async_current_entries = lambda: []  # type: ignore[method-assign]
    assert await flow._async_get_entry_for_unique_id() is None

    monkey_entries: list[MockConfigEntry] = [entry]
    flow._async_current_entries = lambda: monkey_entries  # type: ignore[method-assign]

    assert await flow._async_get_entry_for_unique_id() is entry


@pytest.mark.asyncio
async def test_handle_existing_discovery_entry_aborts_without_reload(
    hass,
) -> None:
    """Existing discovery entries should abort when reloads are disabled."""
    flow = PawControlConfigFlow()
    flow.hass = hass
    flow._unique_id = DOMAIN

    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"host": "1.1.1.1"})
    flow._async_current_entries = lambda: [entry]  # type: ignore[method-assign]

    result = await flow._handle_existing_discovery_entry(
        updates={"host": "2.2.2.2", "discovery_info": {"source": "dhcp"}},
        comparison={"source": "dhcp"},
        reload_on_update=False,
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


def test_discovery_update_required_ignores_only_last_seen() -> None:
    """Discovery updates should ignore purely dynamic timestamp changes."""
    flow = PawControlConfigFlow()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "discovery_info": {"source": "dhcp", "host": "1.1.1.1"},
            "host": "1.1.1.1",
        },
    )

    assert (
        flow._discovery_update_required(
            entry,
            updates={
                "discovery_info": {
                    "source": "dhcp",
                    "host": "1.1.1.1",
                    "last_seen": "new-timestamp",
                }
            },
            comparison={"source": "dhcp", "host": "1.1.1.1"},
        )
        is False
    )

    assert (
        flow._discovery_update_required(
            entry,
            updates={"host": "2.2.2.2"},
            comparison={},
        )
        is True
    )


def test_prepare_discovery_updates_tracks_host_device_and_address() -> None:
    """Prepared discovery updates should expose selected top-level fields."""
    flow = PawControlConfigFlow()

    updates, comparison = flow._prepare_discovery_updates(
        {
            "ip": "10.0.0.5",
            "device": "tracker",
            "address": "AA:BB",
        },
        source="dhcp",
    )

    assert "last_seen" not in comparison
    assert updates["host"] == "10.0.0.5"
    assert updates["device"] == "tracker"
    assert updates["address"] == "AA:BB"
    assert flow._discovery_info["source"] == "dhcp"


def test_format_discovery_info_handles_known_and_unknown_sources() -> None:
    """Discovery info formatting should return source-specific summaries."""
    flow = PawControlConfigFlow()

    flow._discovery_info = {"source": "zeroconf", "hostname": "paw", "host": "1.1.1.1"}
    assert flow._format_discovery_info() == "Device: paw\nHost: 1.1.1.1"

    flow._discovery_info = {"source": "dhcp", "hostname": "paw", "ip": "2.2.2.2"}
    assert flow._format_discovery_info() == "Device: paw\nIP: 2.2.2.2"

    flow._discovery_info = {"source": "usb"}
    assert flow._format_discovery_info() == "Unknown device"


def test_device_helpers_cover_supported_patterns_and_id_extraction() -> None:
    """Device helper methods should classify hostnames and extract IDs."""
    flow = PawControlConfigFlow()

    assert flow._is_supported_device("tractive-123", {}) is True
    assert flow._is_supported_device("unsupported-host", {}) is False
    assert flow._extract_device_id({"serial": "abc"}) == "abc"
    assert flow._extract_device_id({"device_id": 12}) == "12"
    assert flow._extract_device_id({"uuid": None}) is None
    assert flow._extract_device_id({}) is None


def test_string_list_normalisation_and_module_aggregation() -> None:
    """List normalisation should trim values and aggregate enabled modules."""
    flow = PawControlConfigFlow()

    assert flow._normalise_string_list(["  gps  ", "", 10, None]) == ["gps", "10"]

    flow._dogs = [
        {"modules": {"gps": True, "health": False}},
        {"modules": {"health": True}},
    ]
    modules = flow._aggregate_enabled_modules()
    assert modules["gps"] is True
    assert modules["health"] is True
    assert modules["feeding"] is False
