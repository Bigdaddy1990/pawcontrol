"""Tests for the options flow import/export mixin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.data_entry_flow import FlowResultType

from custom_components.pawcontrol.const import CONF_DOGS
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
