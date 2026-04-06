"""Parametrized flow-path coverage for PawControl config and options flows."""

from collections.abc import Mapping
from unittest.mock import AsyncMock

from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol.config_flow_main import PawControlConfigFlow
from custom_components.pawcontrol.const import CONF_DOGS, CONF_NAME, DOMAIN
from custom_components.pawcontrol.exceptions import FlowValidationError, ValidationError
from custom_components.pawcontrol.options_flow_main import PawControlOptionsFlow
from custom_components.pawcontrol.types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_input", "expected_type", "expected_step", "expected_errors"),
    [
        (None, FlowResultType.FORM, "user", None),
        (
            {CONF_NAME: ""},
            FlowResultType.FORM,
            "user",
            {CONF_NAME: "integration_name_required"},
        ),
        ({CONF_NAME: "Family Dogs"}, FlowResultType.FORM, "add_dog", None),
    ],
)
async def test_user_step_input_matrix(
    user_input: Mapping[str, object] | None,
    expected_type: FlowResultType,
    expected_step: str,
    expected_errors: Mapping[str, str] | None,
) -> None:
    """The user step should cover initial, invalid, and successful form paths."""
    flow = PawControlConfigFlow()

    result = await flow.async_step_user(user_input)

    assert result["type"] == expected_type
    assert result["step_id"] == expected_step
    if expected_errors is None:
        assert "errors" not in result or not result["errors"]
    else:
        assert result["errors"] == expected_errors


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_errors"),
    [
        (
            FlowValidationError(field_errors={"dog_name": "invalid_dog_name"}),
            {"dog_name": "invalid_dog_name"},
        ),
        (RuntimeError("boom"), {"base": "unknown_error"}),
    ],
)
async def test_add_dog_validation_error_matrix(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_errors: Mapping[str, str],
) -> None:
    """Dog setup should map known and unknown validation failures to form errors."""
    flow = PawControlConfigFlow()

    async def _raise_error(_user_input):
        raise error

    monkeypatch.setattr(flow, "_validate_dog_input_cached", _raise_error)

    result = await flow.async_step_add_dog({
        DOG_ID_FIELD: "buddy",
        DOG_NAME_FIELD: "Buddy",
        "dog_weight": 8,
        "dog_age": 3,
    })

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_dog"
    assert result["errors"] == expected_errors


@pytest.mark.asyncio
async def test_duplicate_entry_paths_abort_with_already_configured(hass) -> None:
    """Both user and import sources should abort when the integration already exists."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)

    for source, data in (
        ("user", None),
        (
            "import",
            {
                CONF_DOGS: [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}],
            },
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": source},
            data=data,
        )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile_input", "expected_type", "expected_error"),
    [
        ("not-real", FlowResultType.FORM, {"base": "invalid_profile"}),
        ("standard", FlowResultType.FORM, {"base": "profile_unchanged"}),
        ("basic", FlowResultType.ABORT, None),
    ],
)
async def test_reconfigure_paths_and_updates(
    hass,
    monkeypatch: pytest.MonkeyPatch,
    profile_input: str,
    expected_type: FlowResultType,
    expected_error: Mapping[str, str] | None,
) -> None:
    """Reconfigure should return forms for invalid data and abort with exact updates."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: [
                {
                    DOG_ID_FIELD: "buddy",
                    DOG_NAME_FIELD: "Buddy",
                    DOG_MODULES_FIELD: {"gps": True},
                }
            ],
            "entity_profile": "standard",
        },
        options={"entity_profile": "standard"},
    )
    entry.add_to_hass(hass)

    flow = PawControlConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id}

    async def _placeholders(*_args, **_kwargs):
        return {"current_profile": "standard"}

    monkeypatch.setattr(flow, "_build_reconfigure_placeholders", _placeholders)
    monkeypatch.setattr(
        flow,
        "_extract_entry_dogs",
        lambda _entry: (
            [
                {
                    DOG_ID_FIELD: "buddy",
                    DOG_NAME_FIELD: "Buddy",
                    DOG_MODULES_FIELD: {"gps": True},
                }
            ],
            [],
        ),
    )
    monkeypatch.setattr(flow, "_resolve_entry_profile", lambda _entry: "standard")
    monkeypatch.setattr(
        flow, "_check_profile_compatibility", lambda *_: {"warnings": []}
    )
    monkeypatch.setattr(
        flow,
        "_check_config_health_enhanced",
        AsyncMock(return_value={"healthy": True, "issues": []}),
    )
    monkeypatch.setattr(
        flow, "_estimate_entities_for_reconfigure", AsyncMock(return_value=7)
    )
    monkeypatch.setattr(flow, "async_set_unique_id", AsyncMock())

    update_mock = AsyncMock(
        return_value={"type": FlowResultType.ABORT, "reason": "reconfigure_successful"}
    )
    monkeypatch.setattr(
        flow, "async_update_reload_and_abort", update_mock, raising=False
    )

    result = await flow.async_step_reconfigure({"entity_profile": profile_input})
    assert result["type"] == expected_type

    if expected_type == FlowResultType.FORM:
        assert result["step_id"] == "reconfigure"
        assert result["errors"] == expected_error
        update_mock.assert_not_awaited()
        return

    assert result["reason"] == "reconfigure_successful"
    update_call = update_mock.await_args.kwargs
    assert update_call["reason"] == "reconfigure_successful"
    assert update_call["data_updates"]["entity_profile"] == profile_input
    assert update_call["options_updates"]["entity_profile"] == profile_input
    assert update_call["options_updates"]["previous_profile"] == "standard"
    assert update_call["options_updates"]["reconfigure_telemetry"] == {
        "requested_profile": profile_input,
        "previous_profile": "standard",
        "dogs_count": 1,
        "estimated_entities": 7,
        "timestamp": update_call["options_updates"]["last_reconfigure"],
        "version": flow.VERSION,
        "health_summary": {"healthy": True, "issues": []},
        "valid_dogs": 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile_input", "expected_data"),
    [
        (
            "basic",
            {
                "entity_profile": "basic",
                "enable_analytics": True,
            },
        ),
        (
            "advanced",
            {
                "entity_profile": "advanced",
                "enable_analytics": True,
            },
        ),
    ],
)
async def test_options_update_profile_applies_exact_options(
    monkeypatch: pytest.MonkeyPatch,
    profile_input: str,
    expected_data: Mapping[str, object],
) -> None:
    """Options preview apply should persist exactly the normalized options payload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]},
        options={"entity_profile": "standard", "enable_analytics": True},
    )

    flow = PawControlOptionsFlow()
    flow.initialize_from_config_entry(entry)

    monkeypatch.setattr(
        flow,
        "_normalise_options_snapshot",
        lambda options: dict(options),
    )

    result = await flow.async_step_profile_preview({
        "profile": profile_input,
        "apply_profile": True,
    })

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == expected_data


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_input", "expected_type", "expected_reason", "expected_errors"),
    [
        (
            {"confirm": False},
            FlowResultType.FORM,
            None,
            {"base": "reauth_unsuccessful"},
        ),
        (
            {"confirm": True},
            FlowResultType.ABORT,
            "reauth_successful",
            None,
        ),
    ],
)
async def test_reauth_confirm_path_matrix_and_exact_update_payloads(
    monkeypatch: pytest.MonkeyPatch,
    user_input: Mapping[str, bool],
    expected_type: FlowResultType,
    expected_reason: str | None,
    expected_errors: Mapping[str, str] | None,
) -> None:
    """Reauth confirm should cover form/abort branches and persist exact updates."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]},
        options={"entity_profile": "standard"},
        unique_id=DOMAIN,
    )
    flow = PawControlConfigFlow()
    flow.reauth_entry = entry

    monkeypatch.setattr(flow, "async_set_unique_id", AsyncMock())
    monkeypatch.setattr(flow, "_abort_if_unique_id_mismatch", lambda **_kwargs: None)
    monkeypatch.setattr(
        flow,
        "_check_config_health_enhanced",
        AsyncMock(
            return_value={
                "healthy": True,
                "issues": [],
                "warnings": [],
                "validated_dogs": 1,
                "total_dogs": 1,
            }
        ),
    )

    expected_data_updates = {
        "reauth_timestamp": "2026-04-06T00:00:00+00:00",
        "reauth_version": flow.VERSION,
        "health_status": True,
        "health_validated_dogs": 1,
        "health_total_dogs": 1,
    }
    expected_options_updates = {
        "last_reauth": "2026-04-06T00:00:00+00:00",
        "reauth_health_issues": [],
        "reauth_health_warnings": [],
        "last_reauth_summary": "Status: healthy; Validated dogs: 1/1",
    }
    monkeypatch.setattr(
        flow,
        "_build_reauth_updates",
        lambda _summary: (expected_data_updates, expected_options_updates),
    )

    update_mock = AsyncMock(
        return_value={"type": FlowResultType.ABORT, "reason": "reauth_successful"}
    )
    monkeypatch.setattr(
        flow, "async_update_reload_and_abort", update_mock, raising=False
    )

    result = await flow.async_step_reauth_confirm(dict(user_input))
    assert result["type"] == expected_type

    if expected_type == FlowResultType.FORM:
        assert result["step_id"] == "reauth_confirm"
        assert result["errors"] == expected_errors
        update_mock.assert_not_awaited()
        return

    assert result["reason"] == expected_reason
    update_call = update_mock.await_args.kwargs
    assert update_call["data_updates"] == expected_data_updates
    assert update_call["options_updates"] == expected_options_updates


@pytest.mark.asyncio
async def test_import_validation_wraps_unexpected_validator_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected validator exceptions should map to ``ValidationError``."""
    flow = PawControlConfigFlow()

    def _raise_runtime(*_args, **_kwargs):
        raise RuntimeError("api offline")

    monkeypatch.setattr(
        "custom_components.pawcontrol.config_flow_main.validate_dog_import_input",
        _raise_runtime,
    )

    with pytest.raises(
        ValidationError, match="Import configuration validation failed: api offline"
    ):
        await flow._validate_import_config_enhanced({
            CONF_DOGS: [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}],
        })
