"""Coverage-focused tests for import/export options mixin helpers."""

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.options_flow_import_export import (
    ImportExportOptionsMixin,
)
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD, JSONValue


class _ImportExportHost(ImportExportOptionsMixin):
    """Minimal host implementation for the import/export mixin."""

    def __init__(self) -> None:
        self._current_dog = {"dog_id": "buddy", "dog_name": "Buddy"}
        self._dogs = [cast(dict[str, str], self._current_dog)]
        self._entry = SimpleNamespace(
            data={CONF_DOGS: list(self._dogs), "existing": "value"},
        )
        self.hass = SimpleNamespace(
            config_entries=SimpleNamespace(async_update_entry=Mock()),
        )
        self.cache_invalidated = False
        self.last_form: dict[str, Any] | None = None
        self.last_created_entry: dict[str, Any] | None = None
        self._validated_payload: dict[str, Any] = {
            "options": {"entity_profile": "advanced"},
            "dogs": [{DOG_ID_FIELD: "milo", DOG_NAME_FIELD: "Milo"}],
        }

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        self.last_form = {"type": "form", **kwargs}
        return self.last_form

    def async_create_entry(
        self, *, title: str, data: dict[str, JSONValue]
    ) -> dict[str, Any]:
        self.last_created_entry = {
            "type": "create_entry",
            "title": title,
            "data": data,
        }
        return self.last_created_entry

    async def async_step_init(self) -> dict[str, str]:
        return {"type": "menu", "step_id": "init"}

    def _build_export_payload(self) -> dict[str, Any]:
        return {
            "version": 1,
            "created_at": "2026-03-20T00:00:00+00:00",
            "options": {"entity_profile": "default"},
            "dogs": list(self._dogs),
        }

    def _validate_import_payload(self, parsed: Any) -> dict[str, Any]:
        if parsed == "raise":
            raise FlowValidationError(field_errors={"payload": "invalid_payload"})
        return self._validated_payload

    def _normalise_options_snapshot(self, options: dict[str, Any]) -> dict[str, Any]:
        return {"normalised": True, **options}

    def _invalidate_profile_caches(self) -> None:
        self.cache_invalidated = True


@pytest.mark.asyncio
async def test_async_step_import_export_routes_actions_and_invalid_input() -> None:
    """The action menu should render and dispatch to import/export handlers."""
    host = _ImportExportHost()

    menu_result = await host.async_step_import_export()
    assert menu_result["type"] == "form"
    assert menu_result["step_id"] == "import_export"
    assert "instructions" in menu_result["description_placeholders"]

    export_result = await host.async_step_import_export({"action": "export"})
    assert export_result["step_id"] == "import_export_export"

    import_result = await host.async_step_import_export({"action": "import"})
    assert import_result["step_id"] == "import_export_import"

    invalid_result = await host.async_step_import_export({"action": "bad"})
    assert invalid_result["errors"] == {"action": "invalid_action"}


@pytest.mark.asyncio
async def test_async_step_import_export_export_handles_display_and_return_to_menu() -> (
    None
):
    """Export should render the JSON blob and return to init on confirmation."""
    host = _ImportExportHost()

    export_form = await host.async_step_import_export_export()
    assert export_form["type"] == "form"
    assert export_form["step_id"] == "import_export_export"
    payload = json.loads(export_form["description_placeholders"]["export_blob"])
    assert payload["version"] == 1
    assert export_form["description_placeholders"]["generated_at"] == (
        "2026-03-20T00:00:00+00:00"
    )

    assert await host.async_step_import_export_export({"export_blob": "ignored"}) == {
        "type": "menu",
        "step_id": "init",
    }


@pytest.mark.asyncio
async def test_async_step_import_export_import_reports_payload_errors() -> None:
    """Import should expose dedicated form errors for invalid payload shapes."""
    host = _ImportExportHost()

    empty_result = await host.async_step_import_export_import({"payload": "   "})
    assert empty_result["errors"] == {"payload": "invalid_payload"}

    invalid_json_result = await host.async_step_import_export_import({
        "payload": "{bad json"
    })
    assert invalid_json_result["errors"] == {"payload": "invalid_json"}

    flow_error_result = await host.async_step_import_export_import({
        "payload": json.dumps("raise")
    })
    assert flow_error_result["errors"] == {"payload": "invalid_payload"}


@pytest.mark.asyncio
async def test_import_updates_entry_and_filters_invalid_dogs() -> None:
    """A valid import should normalise options and ignore malformed dogs."""
    host = _ImportExportHost()
    host._validated_payload = {
        "options": {"entity_profile": "advanced"},
        "dogs": [
            {DOG_ID_FIELD: "milo", DOG_NAME_FIELD: "Milo"},
            "invalid",
            {DOG_NAME_FIELD: "Missing id"},
        ],
    }

    result = await host.async_step_import_export_import({
        "payload": json.dumps({"ok": True})
    })

    assert result["type"] == "create_entry"
    assert result["data"]["normalised"] is True
    assert host._dogs == [{DOG_ID_FIELD: "milo", DOG_NAME_FIELD: "Milo"}]
    assert host._current_dog is None
    assert host.cache_invalidated is True

    update_call = host.hass.config_entries.async_update_entry.call_args
    assert update_call is not None
    assert update_call.kwargs["data"][CONF_DOGS] == host._dogs
