"""Tests for reauthentication helper logic."""

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol import config_flow_reauth
from custom_components.pawcontrol.config_flow_reauth import ReauthFlowMixin
from custom_components.pawcontrol.const import CONF_DOGS, CONF_MODULES
from custom_components.pawcontrol.types import DOG_ID_FIELD


class _Flow(ReauthFlowMixin):
    VERSION = 7

    def __init__(self, entry: MockConfigEntry) -> None:
        self.reauth_entry = entry
        self.context: dict[str, object] = {}
        self.hass = SimpleNamespace()

    def _normalise_string_list(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return [str(value) for value in values]

    def _normalise_entry_dogs(self, entry: MockConfigEntry) -> list[dict[str, Any]]:
        dogs = entry.data.get(CONF_DOGS, [])
        if isinstance(dogs, list):
            return [dict(dog) for dog in dogs if isinstance(dog, dict)]
        return []


@pytest.mark.parametrize(
    ("payload", "expected_count"),
    [
        ([{"id": "a"}, "bad", {"id": "b"}], 2),
        ("dogs", 0),
        (b"dogs", 0),
    ],
)
def test_count_dogs_ignores_non_mapping_items(
    payload: object, expected_count: int
) -> None:
    """Dog counters should only include mapping payload rows."""
    assert ReauthFlowMixin._count_dogs(payload) == expected_count


def test_render_reauth_health_status_renders_all_sections() -> None:
    """Rendered health text should include warnings, issues, and invalid modules."""
    flow = _Flow(MockConfigEntry(domain="pawcontrol", data={}, options={}))

    status = flow._render_reauth_health_status({
        "healthy": False,
        "validated_dogs": 1,
        "total_dogs": 3,
        "issues": ["missing id"],
        "warnings": ["profile fallback"],
        "invalid_modules": 2,
    })

    assert "attention required" in status
    assert "Validated dogs: 1/3" in status
    assert "Issues: missing id" in status
    assert "Warnings: profile fallback" in status
    assert "Modules needing review: 2" in status


def test_build_reauth_placeholders_uses_entry_defaults() -> None:
    """Placeholder payloads should use title, dog counts, and profile."""
    entry = MockConfigEntry(
        domain="pawcontrol",
        title="My Dogs",
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy"}, {DOG_ID_FIELD: "luna"}]},
        options={"entity_profile": 42},
    )
    flow = _Flow(entry)

    placeholders = flow._build_reauth_placeholders({
        "healthy": True,
        "validated_dogs": 2,
        "issues": [],
        "warnings": [],
    })

    assert placeholders["integration_name"] == "My Dogs"
    assert placeholders["dogs_count"] == "2"
    assert placeholders["current_profile"] == "42"
    assert "Status: healthy" in placeholders["health_status"]


@pytest.mark.asyncio
async def test_check_config_health_reports_duplicate_ids_and_module_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health checks should report duplicate IDs and malformed module payloads."""
    entry = MockConfigEntry(
        domain="pawcontrol",
        data={
            CONF_DOGS: [
                {DOG_ID_FIELD: "buddy", CONF_MODULES: {"feeding": True}},
                {DOG_ID_FIELD: "buddy", CONF_MODULES: {"walk": "yes"}},
            ]
        },
        options={"entity_profile": "invalid_profile"},
    )
    flow = _Flow(entry)

    monkeypatch.setattr(
        _Flow,
        "_is_dog_config_valid_for_reauth",
        staticmethod(lambda dog: True),
    )

    class _FakeFactory:
        def __init__(self, _hass: object) -> None:
            pass

        async def estimate_entity_count_async(
            self,
            _profile: str,
            _modules: Mapping[str, bool],
        ) -> int:
            return 150

    monkeypatch.setattr(config_flow_reauth, "EntityFactory", _FakeFactory)

    summary = await flow._check_config_health_enhanced(entry)

    assert summary["healthy"] is False
    assert "Duplicate dog IDs detected" in summary["issues"]
    assert any("invalid flag" in warning for warning in summary["warnings"])
    assert any("Invalid profile" in warning for warning in summary["warnings"])
    assert any("High entity count" in warning for warning in summary["warnings"])
    assert summary["invalid_modules"] == 1
    assert summary["estimated_entities"] == 300
