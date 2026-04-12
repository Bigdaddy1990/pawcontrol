"""Tests for ``config_flow_main`` helpers and validation paths."""

from collections.abc import Mapping
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryNotReady
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.pawcontrol import config_flow_main
from custom_components.pawcontrol.config_flow_main import PawControlConfigFlow
from custom_components.pawcontrol.const import CONF_DOGS, DOMAIN
from custom_components.pawcontrol.exceptions import (
    ConfigurationError,
    FlowValidationError,
    PawControlSetupError,
    ValidationError,
)
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raised_error",
    [
        FlowValidationError(field_errors={"dog_name": "invalid_name"}),
        ValidationError("dog_name", constraint="invalid_name"),
    ],
)
async def test_validate_import_config_collects_dog_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
    raised_error: Exception,
) -> None:
    """Per-dog validation failures should be aggregated with position metadata."""
    flow = PawControlConfigFlow()

    def _raise_validation(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise raised_error

    monkeypatch.setattr(
        config_flow_main,
        "validate_dog_import_input",
        _raise_validation,
    )

    with pytest.raises(ValidationError, match="Dog validation failed at position 1"):
        await flow._validate_import_config_enhanced({CONF_DOGS: [{"dog_id": "buddy"}]})


@pytest.mark.asyncio
async def test_validate_import_config_requires_at_least_one_valid_dog() -> None:
    """Empty dog imports should raise a dedicated no-valid-dogs validation error."""
    flow = PawControlConfigFlow()

    with pytest.raises(
        ValidationError,
        match="No valid dogs found in import configuration",
    ):
        await flow._validate_import_config_enhanced({CONF_DOGS: []})


@pytest.mark.asyncio
async def test_validate_import_config_valid_path_keeps_warnings_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid imports with compatible profiles should not emit import warnings."""
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
        lambda profile, modules: True,
    )

    result = await flow._validate_import_config_enhanced({
        CONF_DOGS: [{"dog_id": "buddy", "dog_name": "Buddy"}],
        "entity_profile": "standard",
    })

    assert result["data"]["import_warnings"] == []
    assert result["data"]["entity_profile"] == "standard"


@pytest.mark.asyncio
async def test_validate_import_config_accepts_non_string_id_name_from_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validator output with non-string id/name should still be passed through safely."""
    flow = PawControlConfigFlow()

    def _validate_dog_import_input(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {
            DOG_ID_FIELD: 7,
            DOG_NAME_FIELD: None,
        }

    monkeypatch.setattr(
        config_flow_main,
        "validate_dog_import_input",
        _validate_dog_import_input,
    )
    monkeypatch.setattr(
        flow._entity_factory,
        "validate_profile_for_modules",
        lambda profile, modules: True,
    )

    result = await flow._validate_import_config_enhanced({
        CONF_DOGS: [{"any": "payload"}],
        "entity_profile": "standard",
    })

    assert result["data"]["dogs"][0][DOG_ID_FIELD] == 7
    assert result["data"]["dogs"][0][DOG_NAME_FIELD] is None


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


def test_abort_if_unique_id_mismatch_raises_for_mismatched_reauth_entry() -> None:
    """Reauth unique-id mismatch should raise ``ConfigEntryNotReady``."""
    flow = PawControlConfigFlow()
    flow.reauth_entry = MockConfigEntry(domain=DOMAIN, unique_id="entry-user", data={})
    flow.unique_id = "different-user"  # type: ignore[attr-defined]

    with pytest.raises(ConfigEntryNotReady, match="wrong_account"):
        flow._abort_if_unique_id_mismatch(reason="wrong_account")


def test_abort_if_unique_id_mismatch_noops_for_equal_or_missing_ids() -> None:
    """Missing or equal IDs should not interrupt the reauth flow."""
    flow = PawControlConfigFlow()

    flow.reauth_entry = MockConfigEntry(domain=DOMAIN, unique_id="entry-user", data={})
    flow.unique_id = "entry-user"  # type: ignore[attr-defined]
    flow._abort_if_unique_id_mismatch(reason="wrong_account")

    flow.reauth_entry = None
    flow._abort_if_unique_id_mismatch(reason="wrong_account")


@pytest.mark.asyncio
async def test_async_step_user_returns_form_when_name_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid integration names should keep the user on the initial form."""
    flow = PawControlConfigFlow()

    monkeypatch.setattr(flow, "async_set_unique_id", AsyncMock())
    monkeypatch.setattr(flow, "_abort_if_unique_id_configured", lambda **_kwargs: None)

    result = await flow.async_step_user({"name": ""})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"name": "integration_name_required"}


@pytest.mark.asyncio
async def test_async_step_import_creates_entry_from_validated_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Import step should create a config entry from validated data/options."""
    flow = PawControlConfigFlow()

    monkeypatch.setattr(flow, "async_set_unique_id", AsyncMock())
    monkeypatch.setattr(flow, "_abort_if_unique_id_configured", lambda **_kwargs: None)

    async def _validated(_config):
        return {"data": {"dogs": []}, "options": {"entity_profile": "standard"}}

    monkeypatch.setattr(flow, "_validate_import_config_enhanced", _validated)

    result = await flow.async_step_import({"dogs": []})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "PawControl (Imported)"
    assert result["data"] == {"dogs": []}
    assert result["options"] == {"entity_profile": "standard"}


@pytest.mark.asyncio
async def test_async_step_import_wraps_vol_invalid_in_config_entry_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Voluptuous import parsing failures should surface as config-entry errors."""
    flow = PawControlConfigFlow()

    monkeypatch.setattr(flow, "async_set_unique_id", AsyncMock())
    monkeypatch.setattr(flow, "_abort_if_unique_id_configured", lambda **_kwargs: None)

    async def _raise_invalid(_config):
        raise vol.Invalid("bad format")

    monkeypatch.setattr(flow, "_validate_import_config_enhanced", _raise_invalid)

    with pytest.raises(ConfigEntryNotReady, match="Invalid import configuration format"):
        await flow.async_step_import({"dogs": []})


@pytest.mark.asyncio
async def test_async_step_import_wraps_validation_error_in_config_entry_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation failures should propagate as typed config-entry errors."""
    flow = PawControlConfigFlow()

    monkeypatch.setattr(flow, "async_set_unique_id", AsyncMock())
    monkeypatch.setattr(flow, "_abort_if_unique_id_configured", lambda **_kwargs: None)

    async def _raise_validation(_config):
        raise ValidationError("invalid dogs")

    monkeypatch.setattr(flow, "_validate_import_config_enhanced", _raise_validation)

    with pytest.raises(
        ConfigEntryNotReady,
        match="Import validation failed: Validation failed for 'invalid dogs'",
    ):
        await flow.async_step_import({"dogs": []})


@pytest.mark.asyncio
async def test_validate_import_config_wrapper_delegates_to_enhanced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy wrapper should return the enhanced validator result unchanged."""
    flow = PawControlConfigFlow()
    expected = {"data": {"dogs": []}, "options": {"entity_profile": "standard"}}

    async def _validated(_config):
        return expected

    monkeypatch.setattr(flow, "_validate_import_config_enhanced", _validated)

    assert await flow._validate_import_config({"dogs": []}) == expected


@pytest.mark.asyncio
async def test_final_setup_shows_confirmation_form_when_no_input() -> None:
    """Final setup should present a confirmation form for empty input."""
    flow = PawControlConfigFlow()

    result = await flow.async_step_final_setup()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "final_setup"


@pytest.mark.asyncio
async def test_final_setup_requires_at_least_one_configured_dog() -> None:
    """Final setup should fail fast when no dogs were configured."""
    flow = PawControlConfigFlow()

    with pytest.raises(PawControlSetupError, match="No dogs configured"):
        await flow.async_step_final_setup({})


@pytest.mark.asyncio
async def test_final_setup_raises_when_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Final setup should surface comprehensive validation failures."""
    flow = PawControlConfigFlow()
    flow._dogs = [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]

    async def _validation_failure() -> Mapping[str, object]:
        return {
            "valid": False,
            "errors": ["Invalid dog configuration: buddy"],
            "estimated_entities": 0,
        }

    monkeypatch.setattr(flow, "_perform_comprehensive_validation", _validation_failure)

    with pytest.raises(PawControlSetupError, match="Invalid dog configuration"):
        await flow.async_step_final_setup({})


@pytest.mark.asyncio
async def test_final_setup_creates_entry_when_validation_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Final setup should create a config entry from the synthesized payloads."""
    flow = PawControlConfigFlow()
    flow._dogs = [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]
    flow._integration_name = "Paw Control"
    flow._entity_profile = "standard"

    async def _validation_success() -> Mapping[str, object]:
        return {"valid": True, "errors": [], "estimated_entities": 3}

    monkeypatch.setattr(flow, "_perform_comprehensive_validation", _validation_success)
    monkeypatch.setattr(flow, "_validate_profile_compatibility", lambda: True)
    monkeypatch.setattr(
        flow,
        "_build_config_entry_data",
        lambda: (
            {"name": "Paw Control", "dogs": flow._dogs},
            {"entity_profile": "standard"},
        ),
    )

    result = await flow.async_step_final_setup({})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Paw Control (Standard (≤12 entities))"
    assert result["data"]["dogs"][0][DOG_ID_FIELD] == "buddy"
    assert result["options"]["entity_profile"] == "standard"


@pytest.mark.asyncio
async def test_final_setup_wraps_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Final setup should re-raise build errors as ``PawControlSetupError``."""
    flow = PawControlConfigFlow()
    flow._dogs = [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]

    async def _validation_success() -> Mapping[str, object]:
        return {"valid": True, "errors": [], "estimated_entities": 3}

    monkeypatch.setattr(flow, "_perform_comprehensive_validation", _validation_success)
    monkeypatch.setattr(flow, "_validate_profile_compatibility", lambda: True)

    def _raise_failure() -> tuple[dict[str, object], dict[str, object]]:
        raise RuntimeError("boom")

    monkeypatch.setattr(flow, "_build_config_entry_data", _raise_failure)

    with pytest.raises(PawControlSetupError, match="Setup failed: boom"):
        await flow.async_step_final_setup({})
