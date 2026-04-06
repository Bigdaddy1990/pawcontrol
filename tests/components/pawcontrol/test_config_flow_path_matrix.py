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
async def test_reconfigure_paths_and_updates(
    hass, monkeypatch: pytest.MonkeyPatch
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

    invalid = await flow.async_step_reconfigure({"entity_profile": "not-real"})
    assert invalid["type"] == FlowResultType.FORM
    assert invalid["step_id"] == "reconfigure"
    assert invalid["errors"] == {"base": "invalid_profile"}

    unchanged = await flow.async_step_reconfigure({"entity_profile": "standard"})
    assert unchanged["type"] == FlowResultType.FORM
    assert unchanged["step_id"] == "reconfigure"
    assert unchanged["errors"] == {"base": "profile_unchanged"}

    success = await flow.async_step_reconfigure({"entity_profile": "basic"})
    assert success["type"] == FlowResultType.ABORT
    assert success["reason"] == "reconfigure_successful"

    update_call = update_mock.await_args.kwargs
    assert update_call["reason"] == "reconfigure_successful"
    assert update_call["data_updates"]["entity_profile"] == "basic"
    assert update_call["options_updates"]["entity_profile"] == "basic"
    assert update_call["options_updates"]["previous_profile"] == "standard"
    assert update_call["options_updates"]["reconfigure_telemetry"] == {
        "requested_profile": "basic",
        "previous_profile": "standard",
        "dogs_count": 1,
        "estimated_entities": 7,
        "timestamp": update_call["options_updates"]["last_reconfigure"],
        "version": flow.VERSION,
        "health_summary": {"healthy": True, "issues": []},
        "valid_dogs": 1,
    }


@pytest.mark.asyncio
async def test_options_update_profile_applies_exact_options(
    monkeypatch: pytest.MonkeyPatch,
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
        "profile": "basic",
        "apply_profile": True,
    })

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "entity_profile": "basic",
        "enable_analytics": True,
    }


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
