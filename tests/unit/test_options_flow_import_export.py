"""Tests for the options flow import/export mixin."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from homeassistant.data_entry_flow import FlowResultType

from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.options_flow_import_export import (
    ImportExportOptionsMixin,
)


@dataclass
class _Entry:
    data: dict[str, Any]


class _ConfigEntries:
    def __init__(self) -> None:
        self.updated: list[tuple[_Entry, dict[str, Any]]] = []

    def async_update_entry(self, entry: _Entry, *, data: dict[str, Any]) -> None:
        self.updated.append((entry, data))


class _Hass:
    def __init__(self) -> None:
        self.config_entries = _ConfigEntries()


class _ImportExportFlow(ImportExportOptionsMixin):
    def __init__(self) -> None:
        self._entry = _Entry(data={"existing": "value", CONF_DOGS: []})
        self._current_dog = {"id": "current"}
        self._dogs = [{"id": "old"}]
        self.hass = _Hass()
        self.cache_invalidated = False

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": FlowResultType.FORM, **kwargs}

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": FlowResultType.CREATE_ENTRY, "title": title, "data": data}

    async def async_step_init(self) -> dict[str, Any]:
        return {"type": FlowResultType.MENU, "step_id": "init"}

    def _build_export_payload(self) -> dict[str, Any]:
        return {"created_at": "2026-01-01T00:00:00+00:00", "dogs": self._dogs}

    def _validate_import_payload(self, payload: object) -> dict[str, Any]:
        assert isinstance(payload, dict)
        return {
            "options": payload["options"],
            "dogs": payload.get("dogs", []),
        }

    def _normalise_options_snapshot(self, payload: object) -> dict[str, Any]:
        assert isinstance(payload, dict)
        return {"normalised": payload}

    def _invalidate_profile_caches(self) -> None:
        self.cache_invalidated = True


async def test_import_export_menu_rejects_unknown_action() -> None:
    """Unknown actions should keep the user on the selector form."""
    flow = _ImportExportFlow()

    result = await flow.async_step_import_export({"action": "unknown"})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "import_export"
    assert result["errors"] == {"action": "invalid_action"}


async def test_import_export_menu_displays_selection_form() -> None:
    """The selector form should render before the user chooses an action."""
    flow = _ImportExportFlow()

    result = await flow.async_step_import_export()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "import_export"
    schema_dict = result["data_schema"].schema
    assert "action" in [key.schema for key in schema_dict]
    placeholders = result["description_placeholders"]
    assert "Create a JSON backup" in placeholders["instructions"]


async def test_import_export_menu_routes_to_export_and_import() -> None:
    """The selector action should dispatch to the requested step."""
    flow = _ImportExportFlow()

    export_result = await flow.async_step_import_export({"action": "export"})
    import_result = await flow.async_step_import_export({"action": "import"})

    assert export_result["step_id"] == "import_export_export"
    assert import_result["step_id"] == "import_export_import"


async def test_import_export_export_step_displays_payload_and_returns_to_init() -> None:
    """The export step should expose the payload and return to init on submit."""
    flow = _ImportExportFlow()

    result = await flow.async_step_import_export_export()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "import_export_export"
    placeholders = result["description_placeholders"]
    parsed_blob = json.loads(placeholders["export_blob"])
    assert parsed_blob == flow._build_export_payload()
    assert placeholders["generated_at"] == "2026-01-01T00:00:00+00:00"

    submitted = await flow.async_step_import_export_export({"ignored": True})
    assert submitted["type"] == FlowResultType.MENU
    assert submitted["step_id"] == "init"


async def test_import_payload_validation_errors_are_surfaced() -> None:
    """Import validation failures should map to per-field flow errors."""

    class _FailingValidationFlow(_ImportExportFlow):
        def _validate_import_payload(self, payload: object) -> dict[str, Any]:
            raise FlowValidationError(field_errors={"payload": "invalid_payload"})

    flow = _FailingValidationFlow()

    result = await flow.async_step_import_export_import(
        {"payload": '{"options": {"threshold": 3}}'}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"payload": "invalid_payload"}


async def test_import_payload_handles_blank_and_invalid_json() -> None:
    """Blank and invalid JSON payloads should produce dedicated error keys."""
    flow = _ImportExportFlow()

    blank = await flow.async_step_import_export_import({"payload": "   "})
    invalid = await flow.async_step_import_export_import({"payload": "{"})

    assert blank["errors"] == {"payload": "invalid_payload"}
    assert invalid["errors"] == {"payload": "invalid_json"}


async def test_import_payload_updates_entry_and_creates_options_entry(
    monkeypatch,
) -> None:
    """Valid payloads should update dogs and return a new options snapshot."""
    flow = _ImportExportFlow()

    monkeypatch.setattr(
        "custom_components.pawcontrol.options_flow_import_export.ensure_dog_config_data",
        lambda payload: payload,
    )

    result = await flow.async_step_import_export_import(
        {
            "payload": (
                '{"options": {"threshold": 3}, '
                '"dogs": [{"name": "Milo"}, "skip", {"name": "Luna"}]}'
            )
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {"normalised": {"threshold": 3}}
    assert flow.hass.config_entries.updated
    _entry, data = flow.hass.config_entries.updated[0]
    assert _entry is flow._entry
    assert data["existing"] == "value"
    assert data[CONF_DOGS] == [{"name": "Milo"}, {"name": "Luna"}]
    assert flow._dogs == [{"name": "Milo"}, {"name": "Luna"}]
    assert flow._current_dog is None
    assert flow.cache_invalidated is True
