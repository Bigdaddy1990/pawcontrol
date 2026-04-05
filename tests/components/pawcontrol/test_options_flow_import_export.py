"""Coverage tests for import/export options flow mixin."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.options_flow_import_export import ImportExportOptionsMixin


class _FakeConfigEntries:
    """Capture config entry update calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def async_update_entry(self, entry: object, **kwargs: Any) -> None:
        self.calls.append({"entry": entry, **kwargs})


class _FakeHass:
    """Minimal Home Assistant stub with config entries manager."""

    def __init__(self) -> None:
        self.config_entries = _FakeConfigEntries()


class _FakeImportExportFlow(ImportExportOptionsMixin):
    """Host implementation used to exercise ``ImportExportOptionsMixin``."""

    def __init__(self) -> None:
        self.hass = _FakeHass()
        self._entry = type("Entry", (), {"data": {"existing": "value"}})()
        self._dogs: list[dict[str, Any]] = []
        self._current_dog: dict[str, Any] | None = {"dog_id": "selected"}
        self.invalidated_profile_caches = 0
        self.returned_options: dict[str, Any] = {}
        self.validation_error: FlowValidationError | None = None

    async def async_step_init(self) -> dict[str, Any]:
        return {"type": "menu", "step_id": "init"}

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: object,
        errors: dict[str, str] | None = None,
        description_placeholders: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
            "description_placeholders": dict(description_placeholders or {}),
        }

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": "create_entry", "title": title, "data": data}

    def _build_export_payload(self) -> dict[str, Any]:
        return {
            "version": 1,
            "created_at": "2026-04-05T00:00:00+00:00",
            "options": {"some": "value"},
            "dogs": [{"dog_id": "dog-1", "dog_name": "Milo"}],
        }

    def _validate_import_payload(self, payload: Any) -> dict[str, Any]:
        if self.validation_error is not None:
            raise self.validation_error
        assert isinstance(payload, Mapping)
        return {
            "version": payload.get("version", 1),
            "created_at": payload.get("created_at", "2026-04-05T00:00:00+00:00"),
            "options": payload.get("options", {}),
            "dogs": payload.get("dogs", []),
        }

    def _normalise_options_snapshot(self, options: dict[str, Any]) -> dict[str, Any]:
        return {"normalised": True, **options}

    def _invalidate_profile_caches(self) -> None:
        self.invalidated_profile_caches += 1


def test_import_export_menu_schema_defaults_to_export_action() -> None:
    """The menu schema should enforce action and keep export as default."""
    flow = _FakeImportExportFlow()

    schema = flow._get_import_export_menu_schema()

    assert schema({"action": "import"}) == {"action": "import"}
    assert schema({}) == {"action": "export"}


def test_import_export_import_schema_persists_default_payload() -> None:
    """The import schema should preserve the pre-filled payload value."""
    flow = _FakeImportExportFlow()

    schema = flow._get_import_export_import_schema("{\"cached\":true}")

    assert schema({}) == {"payload": "{\"cached\":true}"}


async def test_import_export_step_handles_initial_state_and_invalid_action() -> None:
    """Top-level step should show a form and reject unsupported actions."""
    flow = _FakeImportExportFlow()

    shown = await flow.async_step_import_export()
    assert shown["type"] == "form"
    assert shown["step_id"] == "import_export"
    assert "instructions" in shown["description_placeholders"]

    invalid = await flow.async_step_import_export({"action": "unsupported"})
    assert invalid["type"] == "form"
    assert invalid["errors"] == {"action": "invalid_action"}


async def test_import_export_step_routes_to_export_and_import_steps() -> None:
    """Selecting action should dispatch to export or import step handlers."""
    flow = _FakeImportExportFlow()

    exported = await flow.async_step_import_export({"action": "export"})
    assert exported["type"] == "form"
    assert exported["step_id"] == "import_export_export"

    imported = await flow.async_step_import_export({"action": "import"})
    assert imported["type"] == "form"
    assert imported["step_id"] == "import_export_import"


async def test_export_step_shows_payload_and_returns_to_init_after_submit() -> None:
    """Export step should display JSON and bounce back to init on submit."""
    flow = _FakeImportExportFlow()

    shown = await flow.async_step_import_export_export()
    assert shown["type"] == "form"
    assert shown["step_id"] == "import_export_export"
    assert shown["description_placeholders"]["generated_at"] == "2026-04-05T00:00:00+00:00"
    assert '"version": 1' in shown["description_placeholders"]["export_blob"]

    returned = await flow.async_step_import_export_export({"export_blob": "done"})
    assert returned == {"type": "menu", "step_id": "init"}


async def test_import_step_reports_payload_and_json_errors() -> None:
    """Import step should guard against empty and malformed payloads."""
    flow = _FakeImportExportFlow()

    empty_payload = await flow.async_step_import_export_import({"payload": "   "})
    assert empty_payload["type"] == "form"
    assert empty_payload["errors"] == {"payload": "invalid_payload"}

    invalid_json = await flow.async_step_import_export_import({"payload": "{"})
    assert invalid_json["type"] == "form"
    assert invalid_json["errors"] == {"payload": "invalid_json"}


async def test_import_step_maps_flow_validation_errors_to_form_errors() -> None:
    """Validation errors should be converted to Home Assistant form errors."""
    flow = _FakeImportExportFlow()
    flow.validation_error = FlowValidationError(
        field_errors={"payload": "invalid_payload"},
    )

    result = await flow.async_step_import_export_import(
        {
            "payload": '{"version": 1, "options": {}}',
        },
    )

    assert result["type"] == "form"
    assert result["errors"] == {"payload": "invalid_payload"}


async def test_import_step_persists_valid_payload_and_normalises_dogs() -> None:
    """Successful imports should normalise options, update entry data, and reset state."""
    flow = _FakeImportExportFlow()

    result = await flow.async_step_import_export_import(
        {
            "payload": (
                '{"version":1,"options":{"theme":"dark"},'
                '"dogs":["skip",{"dog_id":"dog-1","dog_name":"Milo"},'
                '{"dog_id":"","dog_name":"Broken"}]}'
            ),
        },
    )

    assert result["type"] == "create_entry"
    assert result["title"] == ""
    assert result["data"] == {"normalised": True, "theme": "dark"}

    assert flow.hass.config_entries.calls == [
        {
            "entry": flow._entry,
            "data": {
                "existing": "value",
                CONF_DOGS: [{"dog_id": "dog-1", "dog_name": "Milo"}],
            },
        },
    ]
    assert flow._dogs == [{"dog_id": "dog-1", "dog_name": "Milo"}]
    assert flow._current_dog is None
    assert flow.invalidated_profile_caches == 1


async def test_import_step_maps_base_validation_errors_when_no_field_errors() -> None:
    """Base validation errors should surface when no field-level errors exist."""
    flow = _FakeImportExportFlow()
    flow.validation_error = FlowValidationError(base_errors=["update_failed"])

    result = await flow.async_step_import_export_import({"payload": "{\"version\": 1}"})

    assert result["type"] == "form"
    assert result["errors"] == {"base": "update_failed"}
