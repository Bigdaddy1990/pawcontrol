"""Coverage tests for final setup flow paths."""

from homeassistant.data_entry_flow import FlowResultType
import pytest

from custom_components.pawcontrol.config_flow_main import PawControlConfigFlow
from custom_components.pawcontrol.exceptions import PawControlSetupError
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD


@pytest.mark.asyncio
async def test_final_setup_shows_form_without_input() -> None:
    """Final setup should present an empty form on initial entry."""
    flow = PawControlConfigFlow()

    result = await flow.async_step_final_setup()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "final_setup"


@pytest.mark.asyncio
async def test_final_setup_raises_when_no_dogs() -> None:
    """Final setup should fail fast if no dogs were configured."""
    flow = PawControlConfigFlow()

    with pytest.raises(PawControlSetupError, match="No dogs configured"):
        await flow.async_step_final_setup({})


@pytest.mark.asyncio
async def test_final_setup_raises_when_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Final setup should surface comprehensive validation errors."""
    flow = PawControlConfigFlow()
    flow._dogs = [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]

    async def _invalid_validation() -> dict[str, object]:
        return {
            "valid": False,
            "errors": ["broken state"],
            "estimated_entities": 0,
        }

    monkeypatch.setattr(flow, "_perform_comprehensive_validation", _invalid_validation)

    with pytest.raises(PawControlSetupError, match="Setup validation failed"):
        await flow.async_step_final_setup({})


@pytest.mark.asyncio
async def test_final_setup_creates_entry_when_validation_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Final setup should create a config entry when checks pass."""
    flow = PawControlConfigFlow()
    flow._dogs = [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy", "modules": {}}]

    async def _valid_validation() -> dict[str, object]:
        return {
            "valid": True,
            "errors": [],
            "estimated_entities": 2,
        }

    monkeypatch.setattr(flow, "_perform_comprehensive_validation", _valid_validation)
    monkeypatch.setattr(flow, "_validate_profile_compatibility", lambda: True)

    result = await flow.async_step_final_setup({})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"].startswith("Paw Control")
    assert result["data"]["dogs"][0][DOG_ID_FIELD] == "buddy"


@pytest.mark.asyncio
async def test_perform_comprehensive_validation_collects_all_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Comprehensive validation should aggregate config, entity, and profile errors."""
    flow = PawControlConfigFlow()
    flow._dogs = [
        {DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"},
        {DOG_ID_FIELD: "max", DOG_NAME_FIELD: "Max"},
    ]
    flow._entity_profile = "not-a-profile"

    monkeypatch.setattr(flow, "_is_dog_config_valid_for_flow", lambda _dog: False)

    async def _estimated_entities() -> int:
        return 250

    monkeypatch.setattr(flow, "_estimate_total_entities_cached", _estimated_entities)

    result = await flow._perform_comprehensive_validation()

    assert result["valid"] is False
    assert "Invalid dog configuration: buddy" in result["errors"]
    assert "Invalid dog configuration: max" in result["errors"]
    assert "Too many estimated entities: 250" in result["errors"]
    assert "Invalid profile: not-a-profile" in result["errors"]
    assert result["estimated_entities"] == 250
