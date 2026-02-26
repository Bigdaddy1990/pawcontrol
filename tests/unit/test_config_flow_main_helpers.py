from __future__ import annotations

from collections.abc import Mapping

from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol.config_flow_main import (
    UNKNOWN_DISCOVERY_SOURCE,
    PawControlConfigFlow,
)


@pytest.fixture
def flow() -> PawControlConfigFlow:
    return PawControlConfigFlow()


def test_is_supported_device_matches_known_prefixes(flow: PawControlConfigFlow) -> None:
    assert flow._is_supported_device("tractive-123", {})
    assert flow._is_supported_device("Whistle-abc", {})
    assert not flow._is_supported_device("random-device", {})


def test_extract_device_id_uses_precedence_and_handles_none(
    flow: PawControlConfigFlow,
) -> None:
    assert flow._extract_device_id({"serial": "S-1", "device_id": "D-2"}) == "S-1"
    assert flow._extract_device_id({"serial": None, "device_id": "D-2"}) is None
    assert flow._extract_device_id({"mac": "AA:BB", "uuid": "u-1"}) == "AA:BB"
    assert flow._extract_device_id({}) is None


def test_normalise_discovery_metadata_normalizes_all_supported_fields(
    flow: PawControlConfigFlow,
) -> None:
    payload: Mapping[str, object] = {
        "source": "invalid_source",
        "hostname": "  paw-host  ",
        "host": "192.168.1.5",
        "port": " 8123 ",
        "properties": {
            "serial": 12,
            "mac": b"AA:BB:CC",
            "bad_bytes": b"\xff",
            "drop": None,
            "object": object(),
        },
        "service_uuids": ["  uuid-1  ", b"uuid-2", b"\xff", 123, None],
    }

    result = flow._normalise_discovery_metadata(payload)

    assert result["source"] == UNKNOWN_DISCOVERY_SOURCE
    assert result["hostname"] == "paw-host"
    assert result["port"] == 8123
    assert result["properties"]["serial"] == 12
    assert result["properties"]["mac"] == "AA:BB:CC"
    assert result["properties"]["bad_bytes"] == ""
    assert "drop" not in result["properties"]
    assert isinstance(result.get("last_seen"), str)
    assert result["service_uuids"] == ["uuid-1", "uuid-2", "123"]


def test_normalise_discovery_metadata_handles_integer_port_and_nonstr_fields(
    flow: PawControlConfigFlow,
) -> None:
    result = flow._normalise_discovery_metadata(
        {"source": "dhcp", "manufacturer": 77, "port": 443},
        include_last_seen=False,
    )

    assert result["source"] == "dhcp"
    assert result["manufacturer"] == "77"
    assert result["port"] == 443
    assert "last_seen" not in result


@pytest.mark.asyncio
async def test_async_get_entry_for_unique_id_without_id_returns_none(
    flow: PawControlConfigFlow,
) -> None:
    flow._unique_id = None
    assert await flow._async_get_entry_for_unique_id() is None


def test_strip_dynamic_discovery_fields_removes_last_seen(
    flow: PawControlConfigFlow,
) -> None:
    assert flow._strip_dynamic_discovery_fields(
        {"source": "dhcp", "last_seen": "now", "host": "1.1.1.1"},
    ) == {"source": "dhcp", "host": "1.1.1.1"}


def test_prepare_discovery_updates_sets_cached_info_and_optional_fields(
    flow: PawControlConfigFlow,
) -> None:
    updates, comparison = flow._prepare_discovery_updates(
        {
            "host": "10.0.0.1",
            "device": "eth0",
            "address": "AA:BB",
            "hostname": "paw",
        },
        source="dhcp",
    )

    assert updates["host"] == "10.0.0.1"
    assert updates["device"] == "eth0"
    assert updates["address"] == "AA:BB"
    assert "last_seen" in updates["discovery_info"]
    assert "last_seen" not in comparison
    assert flow._discovery_info["hostname"] == "paw"


def test_format_discovery_info_handles_sources(flow: PawControlConfigFlow) -> None:
    flow._discovery_info = {"source": "zeroconf", "hostname": "dev", "host": "1.2.3.4"}
    assert flow._format_discovery_info() == "Device: dev\nHost: 1.2.3.4"

    flow._discovery_info = {"source": "dhcp", "hostname": "dev", "ip": "1.2.3.5"}
    assert flow._format_discovery_info() == "Device: dev\nIP: 1.2.3.5"

    flow._discovery_info = {"source": "usb"}
    assert flow._format_discovery_info() == "Unknown device"


@pytest.mark.asyncio
async def test_async_get_entry_for_unique_id_direct_and_casefold_match(
    flow: PawControlConfigFlow,
) -> None:
    matching = MockConfigEntry(domain="pawcontrol", unique_id="PawControl")
    direct = MockConfigEntry(domain="pawcontrol", unique_id="pc")

    flow._unique_id = "pc"
    flow._async_current_entries = lambda: [matching, direct]  # type: ignore[assignment]
    assert await flow._async_get_entry_for_unique_id() is direct

    flow._unique_id = "pawcontrol"
    flow._async_current_entries = lambda: [matching]  # type: ignore[assignment]
    assert await flow._async_get_entry_for_unique_id() is matching


@pytest.mark.asyncio
async def test_async_get_entry_for_unique_id_awaitable_entries(
    flow: PawControlConfigFlow,
) -> None:
    entry = MockConfigEntry(domain="pawcontrol", unique_id="abc")

    async def _entries() -> list[MockConfigEntry]:
        return [entry]

    flow._unique_id = "abc"
    flow._async_current_entries = _entries  # type: ignore[assignment]
    assert await flow._async_get_entry_for_unique_id() is entry


@pytest.mark.asyncio
async def test_validate_dog_input_cached_reuses_recent_cached_result(
    flow: PawControlConfigFlow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def _validate(user_input: dict[str, object]) -> dict[str, object]:
        calls.append(user_input)
        return user_input

    flow._validate_dog_input_optimized = _validate  # type: ignore[assignment]
    dog_input = {"dog_id": "buddy", "dog_name": "Buddy", "dog_weight": 12}

    first = await flow._validate_dog_input_cached(dog_input)
    second = await flow._validate_dog_input_cached(dog_input)

    assert first == dog_input
    assert second == dog_input
    assert len(calls) == 1

    original_utcnow = dt_util.utcnow
    monkeypatch.setattr(dt_util, "utcnow", lambda: original_utcnow().replace(year=2099))
    third = await flow._validate_dog_input_cached(dog_input)
    assert third == dog_input
    assert len(calls) == 2


def test_discovery_update_required_detects_changes(flow: PawControlConfigFlow) -> None:
    entry = MockConfigEntry(
        domain="pawcontrol",
        data={"name": "Paw", "discovery_info": {"source": "dhcp", "host": "1.1.1.1"}},
    )

    same_updates = {
        "name": "Paw",
        "discovery_info": {"source": "dhcp", "host": "1.1.1.1", "last_seen": "later"},
    }
    comparison = {"source": "dhcp", "host": "1.1.1.1"}
    assert not flow._discovery_update_required(
        entry,
        updates=same_updates,
        comparison=comparison,
    )

    changed_updates = dict(same_updates)
    changed_updates["name"] = "Paw 2"
    assert flow._discovery_update_required(
        entry,
        updates=changed_updates,
        comparison=comparison,
    )


@pytest.mark.asyncio
async def test_handle_existing_discovery_entry_paths(
    flow: PawControlConfigFlow,
) -> None:
    entry = MockConfigEntry(domain="pawcontrol", unique_id="uid", data={"name": "paw"})

    async def _none() -> None:
        return None

    flow._async_get_entry_for_unique_id = _none  # type: ignore[assignment]
    flow._abort_if_unique_id_configured = lambda **kwargs: {
        "type": "abort",
        "reason": "already_configured",
        **kwargs,
    }  # type: ignore[assignment]
    result = await flow._handle_existing_discovery_entry(
        updates={"name": "paw"},
        comparison={},
        reload_on_update=False,
    )
    assert result["type"] == "abort"

    async def _entry() -> MockConfigEntry:
        return entry

    flow._async_get_entry_for_unique_id = _entry  # type: ignore[assignment]
    flow._discovery_update_required = lambda *args, **kwargs: False  # type: ignore[assignment]
    result = await flow._handle_existing_discovery_entry(
        updates={"name": "paw"},
        comparison={},
        reload_on_update=True,
    )
    assert result["reason"] == "already_configured"

    flow._discovery_update_required = lambda *args, **kwargs: True  # type: ignore[assignment]
    result = await flow._handle_existing_discovery_entry(
        updates={"name": "paw"},
        comparison={},
        reload_on_update=False,
    )
    assert result["reason"] == "already_configured"

    async def _update_reload_and_abort(*args, **kwargs):
        return {
            "type": "abort",
            "reason": kwargs["reason"],
            "data_updates": kwargs["data_updates"],
        }

    flow.async_update_reload_and_abort = _update_reload_and_abort  # type: ignore[assignment]
    result = await flow._handle_existing_discovery_entry(
        updates={"name": "paw2"},
        comparison={},
        reload_on_update=True,
    )
    assert result["data_updates"] == {"name": "paw2"}


def test_discovery_update_required_when_existing_discovery_missing_mapping(
    flow: PawControlConfigFlow,
) -> None:
    entry = MockConfigEntry(domain="pawcontrol", data={"discovery_info": "invalid"})
    assert flow._discovery_update_required(
        entry,
        updates={"discovery_info": {"source": "dhcp", "host": "1.1.1.1"}},
        comparison={"source": "dhcp", "host": "1.1.1.1"},
    )
