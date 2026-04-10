"""Tests for reauthentication helper logic."""

import builtins
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol import config_flow_reauth
from custom_components.pawcontrol.config_flow_reauth import ReauthFlowMixin
from custom_components.pawcontrol.const import CONF_DOGS, CONF_MODULES
from custom_components.pawcontrol.exceptions import (
    ConfigEntryAuthFailed,
    FlowValidationError,
    ValidationError,
)
from custom_components.pawcontrol.types import DOG_ID_FIELD


class _Flow(ReauthFlowMixin):
    VERSION = 7

    def __init__(self, entry: MockConfigEntry) -> None:
        self.reauth_entry = entry
        self.context: dict[str, object] = {}
        self.hass = SimpleNamespace()
        self.last_form: dict[str, Any] | None = None

    def _normalise_string_list(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return [str(value) for value in values]

    def _normalise_entry_dogs(self, entry: MockConfigEntry) -> list[dict[str, Any]]:
        dogs = entry.data.get(CONF_DOGS, [])
        if isinstance(dogs, list):
            return [dict(dog) for dog in dogs if isinstance(dog, dict)]
        return []

    def _abort_if_unique_id_mismatch(self, *, reason: str) -> None:
        self.context["abort_reason"] = reason

    async def async_set_unique_id(self, unique_id: str | None = None) -> None:
        self.context["unique_id"] = unique_id

    async def async_update_reload_and_abort(
        self,
        entry: MockConfigEntry,
        *,
        data_updates: Mapping[str, object] | None = None,
        options_updates: Mapping[str, object] | None = None,
        reason: str,
    ) -> dict[str, object]:
        return {
            "type": "abort",
            "entry": entry,
            "data_updates": dict(data_updates or {}),
            "options_updates": dict(options_updates or {}),
            "reason": reason,
        }

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: object,
        errors: dict[str, str] | None = None,
        description_placeholders: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        self.last_form = {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": dict(errors or {}),
            "description_placeholders": dict(description_placeholders or {}),
        }
        return self.last_form


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


def test_build_reauth_updates_uses_summary_fields() -> None:
    """Reauth updates should include timestamped health details."""
    entry = MockConfigEntry(domain="pawcontrol", data={}, options={})
    flow = _Flow(entry)

    data_updates, options_updates = flow._build_reauth_updates({
        "healthy": False,
        "validated_dogs": 1,
        "total_dogs": 4,
        "issues": ["missing modules"],
        "warnings": ["fallback profile"],
    })

    assert data_updates["reauth_timestamp"]
    assert data_updates["reauth_timestamp"] == options_updates["last_reauth"]
    assert data_updates["reauth_version"] == 7
    assert data_updates["health_status"] is False
    assert data_updates["health_validated_dogs"] == 1
    assert data_updates["health_total_dogs"] == 4
    assert options_updates["reauth_health_issues"] == ["missing modules"]
    assert options_updates["reauth_health_warnings"] == ["fallback profile"]
    assert "Status: attention required" in options_updates["last_reauth_summary"]


def test_is_dog_config_valid_for_reauth_delegates_to_payload_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reauth payload checks should delegate to the shared validator helper."""
    seen_payloads: list[Mapping[str, object]] = []

    def _fake_validator(dog_payload: Mapping[str, object]) -> bool:
        seen_payloads.append(dog_payload)
        return dog_payload.get(DOG_ID_FIELD) == "buddy"

    monkeypatch.setattr(
        config_flow_reauth,
        "is_dog_config_payload_valid",
        _fake_validator,
    )

    assert ReauthFlowMixin._is_dog_config_valid_for_reauth({DOG_ID_FIELD: "buddy"})
    assert not ReauthFlowMixin._is_dog_config_valid_for_reauth({DOG_ID_FIELD: "luna"})
    assert seen_payloads == [{DOG_ID_FIELD: "buddy"}, {DOG_ID_FIELD: "luna"}]


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


@pytest.mark.asyncio
async def test_validate_reauth_entry_enhanced_raises_for_dog_id_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dog identifier validation failures should abort reauth validation."""
    entry = MockConfigEntry(
        domain="pawcontrol",
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy"}]},
        options={},
    )
    flow = _Flow(entry)

    def _raise_dog_id_failure(
        _dog: Mapping[str, object],
        *,
        existing_ids: object,
        existing_names: object,
    ) -> None:
        raise FlowValidationError(field_errors={DOG_ID_FIELD: "missing"})

    monkeypatch.setattr(
        config_flow_reauth,
        "validate_dog_config_payload",
        _raise_dog_id_failure,
    )

    with pytest.raises(ValidationError, match="Dog payload invalid during reauth"):
        await flow._validate_reauth_entry_enhanced(entry)


@pytest.mark.asyncio
async def test_validate_reauth_entry_enhanced_raises_when_all_dogs_are_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If every dog payload is invalid, reauth should fail fast."""
    entry = MockConfigEntry(
        domain="pawcontrol",
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy"}, {DOG_ID_FIELD: "luna"}]},
        options={},
    )
    flow = _Flow(entry)

    def _raise_non_critical_failure(
        _dog: Mapping[str, object],
        *,
        existing_ids: object,
        existing_names: object,
    ) -> None:
        raise FlowValidationError(field_errors={"dog_name": "missing"})

    monkeypatch.setattr(
        config_flow_reauth,
        "validate_dog_config_payload",
        _raise_non_critical_failure,
    )

    with pytest.raises(ValidationError, match="All dog configurations are invalid"):
        await flow._validate_reauth_entry_enhanced(entry)


@pytest.mark.asyncio
async def test_validate_reauth_entry_enhanced_warns_for_invalid_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-standard profiles should only produce warnings during validation."""
    entry = MockConfigEntry(
        domain="pawcontrol",
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy"}]},
        options={"entity_profile": "unexpected"},
    )
    flow = _Flow(entry)

    monkeypatch.setattr(
        config_flow_reauth,
        "validate_dog_config_payload",
        lambda _dog, *, existing_ids, existing_names: None,
    )

    await flow._validate_reauth_entry_enhanced(entry)


@pytest.mark.asyncio
async def test_get_health_status_summary_safe_returns_rendered_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Healthy checks should render the summary status text."""
    entry = MockConfigEntry(domain="pawcontrol", data={CONF_DOGS: []}, options={})
    flow = _Flow(entry)

    async def _healthy(_entry: MockConfigEntry) -> dict[str, object]:
        return {
            "healthy": True,
            "issues": [],
            "warnings": [],
            "validated_dogs": 1,
            "total_dogs": 1,
        }

    monkeypatch.setattr(flow, "_check_config_health_enhanced", _healthy)

    assert "Status: healthy" in await flow._get_health_status_summary_safe(entry)


@pytest.mark.asyncio
async def test_async_step_reauth_confirm_returns_unsuccessful_error() -> None:
    """Declining confirmation should keep the user on the form."""
    entry = MockConfigEntry(domain="pawcontrol", data={CONF_DOGS: []}, options={})
    flow = _Flow(entry)

    result = await flow.async_step_reauth_confirm({"confirm": False})

    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "reauth_unsuccessful"}


@pytest.mark.asyncio
async def test_async_step_reauth_confirm_warns_when_summary_has_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unhealthy summaries should still allow reauth and emit issue details."""
    entry = MockConfigEntry(
        domain="pawcontrol",
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy"}]},
        options={},
    )
    flow = _Flow(entry)

    async def _unhealthy(_entry: MockConfigEntry) -> dict[str, object]:
        return {
            "healthy": False,
            "issues": ["duplicate ids"],
            "warnings": [],
            "validated_dogs": 0,
            "total_dogs": 1,
        }

    monkeypatch.setattr(flow, "_check_config_health_enhanced", _unhealthy)

    result = await flow.async_step_reauth_confirm({"confirm": True})

    assert result["type"] == "abort"
    assert result["data_updates"]["health_status"] is False
    assert result["options_updates"]["reauth_health_issues"] == ["duplicate ids"]


@pytest.mark.asyncio
async def test_async_step_reauth_confirm_uses_timeout_summary_fallback(
    monkeypatch: pytest.MonkeyPatch,
    assert_flow_abort_reason,
) -> None:
    """Timeout during health checks should still allow successful reauth updates."""
    entry = MockConfigEntry(
        domain="pawcontrol",
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy"}]},
        options={},
    )
    flow = _Flow(entry)

    async def _raise_timeout(_entry: MockConfigEntry) -> dict[str, object]:
        raise TimeoutError

    monkeypatch.setattr(flow, "_check_config_health_enhanced", _raise_timeout)

    result = await flow.async_step_reauth_confirm({"confirm": True})

    assert_flow_abort_reason(result, "reauth_successful")
    assert result["data_updates"]["health_total_dogs"] == 1
    assert result["options_updates"]["reauth_health_issues"] == ["Health check timeout"]


@pytest.mark.asyncio
async def test_async_step_reauth_confirm_timeout_shows_error_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeout in unique-id update should return the timeout form error."""
    entry = MockConfigEntry(domain="pawcontrol", data={CONF_DOGS: []}, options={})
    flow = _Flow(entry)

    async def _raise_timeout(unique_id: str | None = None) -> None:
        raise TimeoutError

    async def _health(_entry: MockConfigEntry) -> dict[str, object]:
        return {
            "healthy": True,
            "issues": [],
            "warnings": [],
            "validated_dogs": 0,
            "total_dogs": 0,
        }

    monkeypatch.setattr(flow, "async_set_unique_id", _raise_timeout)
    monkeypatch.setattr(flow, "_check_config_health_enhanced", _health)

    result = await flow.async_step_reauth_confirm({"confirm": True})

    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "reauth_timeout"}


@pytest.mark.asyncio
async def test_async_step_reauth_confirm_uses_display_fallback_when_summary_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Display summaries should fall back gracefully when health checks fail."""
    entry = MockConfigEntry(domain="pawcontrol", data={CONF_DOGS: []}, options={})
    flow = _Flow(entry)

    async def _raise_runtime_error(_entry: MockConfigEntry) -> dict[str, object]:
        raise RuntimeError("display boom")

    monkeypatch.setattr(flow, "_check_config_health_enhanced", _raise_runtime_error)

    result = await flow.async_step_reauth_confirm(None)

    assert result["type"] == "form"
    assert result["errors"] == {}
    placeholders = result["description_placeholders"]
    assert "Status check failed: display boom" in placeholders["health_status"]


@pytest.mark.asyncio
async def test_check_config_health_enhanced_handles_dog_id_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dog ID extraction errors should become warnings instead of hard failures."""
    entry = MockConfigEntry(
        domain="pawcontrol",
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy", CONF_MODULES: {}}]},
        options={},
    )
    flow = _Flow(entry)

    monkeypatch.setattr(
        builtins,
        "set",
        lambda _values: (_ for _ in ()).throw(RuntimeError("id boom")),
    )
    monkeypatch.setattr(
        _Flow,
        "_is_dog_config_valid_for_reauth",
        staticmethod(lambda _dog: True),
    )

    class _FakeFactory:
        def __init__(self, _hass: object) -> None:
            pass

        async def estimate_entity_count_async(
            self,
            _profile: str,
            _modules: Mapping[str, bool],
        ) -> int:
            return 1

    monkeypatch.setattr(config_flow_reauth, "EntityFactory", _FakeFactory)

    summary = await flow._check_config_health_enhanced(entry)

    assert any("Dog ID validation error" in warning for warning in summary["warnings"])


def test_build_reauth_placeholders_requires_reauth_entry() -> None:
    """Placeholder generation should fail when the flow has no reauth entry."""
    entry = MockConfigEntry(domain="pawcontrol", data={}, options={})
    flow = _Flow(entry)
    flow.reauth_entry = None

    with pytest.raises(ConfigEntryAuthFailed, match="No entry available"):
        flow._build_reauth_placeholders({
            "healthy": True,
            "validated_dogs": 0,
            "total_dogs": 0,
            "issues": [],
            "warnings": [],
        })


@pytest.mark.asyncio
async def test_async_step_reauth_raises_when_entry_missing() -> None:
    """Reauth should fail when the entry id cannot be resolved."""
    entry = MockConfigEntry(domain="pawcontrol", data={}, options={})
    flow = _Flow(entry)
    flow.context["entry_id"] = "missing"
    flow.hass.config_entries = SimpleNamespace(async_get_entry=lambda _: None)

    with pytest.raises(ConfigEntryAuthFailed, match="entry not found"):
        await flow.async_step_reauth({})


@pytest.mark.asyncio
async def test_async_step_reauth_wraps_validation_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation timeouts should surface as auth failures."""
    entry = MockConfigEntry(domain="pawcontrol", entry_id="abc", data={}, options={})
    flow = _Flow(entry)
    flow.context["entry_id"] = "abc"
    flow.hass.config_entries = SimpleNamespace(async_get_entry=lambda _: entry)

    async def _timeout(_entry: MockConfigEntry) -> None:
        raise TimeoutError

    monkeypatch.setattr(flow, "_validate_reauth_entry_enhanced", _timeout)

    with pytest.raises(ConfigEntryAuthFailed, match="validation timeout"):
        await flow.async_step_reauth({})


@pytest.mark.asyncio
async def test_async_step_reauth_wraps_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation errors should be converted to auth failures."""
    entry = MockConfigEntry(domain="pawcontrol", entry_id="abc", data={}, options={})
    flow = _Flow(entry)
    flow.context["entry_id"] = "abc"
    flow.hass.config_entries = SimpleNamespace(async_get_entry=lambda _: entry)

    async def _validation_error(_entry: MockConfigEntry) -> None:
        raise ValidationError("entry_dogs", constraint="invalid")

    monkeypatch.setattr(flow, "_validate_reauth_entry_enhanced", _validation_error)

    with pytest.raises(ConfigEntryAuthFailed, match="Entry validation failed"):
        await flow.async_step_reauth({})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("validation_error", "expected_fragment"),
    [
        (
            ValidationError("entry_dogs", constraint="invalid modules"),
            (
                "Entry validation failed: Validation failed for entry_dogs: "
                "invalid modules"
            ),
        ),
        (
            ValidationError("entry_dogs", constraint="missing id"),
            ("Entry validation failed: Validation failed for entry_dogs: missing id"),
        ),
    ],
)
async def test_async_step_reauth_wraps_validation_errors_with_reason_details(
    monkeypatch: pytest.MonkeyPatch,
    validation_error: ValidationError,
    expected_fragment: str,
) -> None:
    """Validation reasons should be preserved in the auth failure message."""
    entry = MockConfigEntry(domain="pawcontrol", entry_id="abc", data={}, options={})
    flow = _Flow(entry)
    flow.context["entry_id"] = "abc"
    flow.hass.config_entries = SimpleNamespace(async_get_entry=lambda _: entry)

    async def _raise_validation_error(_entry: MockConfigEntry) -> None:
        raise validation_error

    monkeypatch.setattr(
        flow,
        "_validate_reauth_entry_enhanced",
        _raise_validation_error,
    )

    with pytest.raises(ConfigEntryAuthFailed, match=expected_fragment):
        await flow.async_step_reauth({})


@pytest.mark.asyncio
async def test_async_step_reauth_wraps_unexpected_errors() -> None:
    """Unexpected errors should bubble as authentication failures."""
    entry = MockConfigEntry(domain="pawcontrol", entry_id="abc", data={}, options={})
    flow = _Flow(entry)
    flow.context["entry_id"] = "abc"
    flow.hass.config_entries = SimpleNamespace(async_get_entry=lambda _: entry)

    async def _confirm() -> dict[str, object]:
        raise RuntimeError("boom")

    flow.async_step_reauth_confirm = _confirm

    with pytest.raises(ConfigEntryAuthFailed, match="Reauthentication failed: boom"):
        await flow.async_step_reauth({})


@pytest.mark.asyncio
async def test_async_step_reauth_wraps_timeout_errors() -> None:
    """Timeouts at the top-level reauth step should map to auth failures."""
    entry = MockConfigEntry(domain="pawcontrol", entry_id="abc", data={}, options={})
    flow = _Flow(entry)
    flow.context["entry_id"] = "abc"

    def _raise_timeout(_entry_id: str) -> None:
        raise TimeoutError

    flow.hass.config_entries = SimpleNamespace(async_get_entry=_raise_timeout)

    with pytest.raises(ConfigEntryAuthFailed, match="Reauthentication timeout"):
        await flow.async_step_reauth({})


@pytest.mark.asyncio
async def test_async_step_reauth_confirm_missing_entry_raises_auth_failed() -> None:
    """Reauth confirmation requires an active config entry."""
    entry = MockConfigEntry(domain="pawcontrol", data={}, options={})
    flow = _Flow(entry)
    flow.reauth_entry = None

    with pytest.raises(ConfigEntryAuthFailed, match="No entry available"):
        await flow.async_step_reauth_confirm({"confirm": True})


@pytest.mark.asyncio
async def test_async_step_reauth_confirm_uses_error_summary_fallback(
    monkeypatch: pytest.MonkeyPatch,
    assert_flow_abort_reason,
) -> None:
    """Unexpected health-check failures should still succeed with fallback details."""
    entry = MockConfigEntry(
        domain="pawcontrol",
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy"}]},
        options={},
    )
    flow = _Flow(entry)

    async def _raise_runtime_error(_entry: MockConfigEntry) -> dict[str, object]:
        raise RuntimeError("health boom")

    monkeypatch.setattr(flow, "_check_config_health_enhanced", _raise_runtime_error)

    result = await flow.async_step_reauth_confirm({"confirm": True})

    assert_flow_abort_reason(result, "reauth_successful")
    assert result["options_updates"]["reauth_health_issues"] == [
        "Health check error: health boom"
    ]


@pytest.mark.asyncio
async def test_async_step_reauth_confirm_surfaces_reauth_failed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected confirmation errors should surface the generic reauth failure."""
    entry = MockConfigEntry(domain="pawcontrol", data={CONF_DOGS: []}, options={})
    flow = _Flow(entry)

    def _raise_abort(*, reason: str) -> None:
        raise RuntimeError(reason)

    async def _health(_entry: MockConfigEntry) -> dict[str, object]:
        return {
            "healthy": True,
            "issues": [],
            "warnings": [],
            "validated_dogs": 0,
            "total_dogs": 0,
        }

    monkeypatch.setattr(flow, "_abort_if_unique_id_mismatch", _raise_abort)
    monkeypatch.setattr(flow, "_check_config_health_enhanced", _health)

    result = await flow.async_step_reauth_confirm({"confirm": True})

    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "reauth_failed"}


@pytest.mark.asyncio
async def test_async_step_reauth_confirm_reraises_auth_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ConfigEntryAuthFailed should not be swallowed by generic handlers."""
    entry = MockConfigEntry(domain="pawcontrol", data={CONF_DOGS: []}, options={})
    flow = _Flow(entry)

    def _raise_auth_failed(*, reason: str) -> None:
        raise ConfigEntryAuthFailed(reason)

    monkeypatch.setattr(flow, "_abort_if_unique_id_mismatch", _raise_auth_failed)

    with pytest.raises(ConfigEntryAuthFailed, match="wrong_account"):
        await flow.async_step_reauth_confirm({"confirm": True})


@pytest.mark.parametrize(
    ("error_factory", "expected_summary"),
    [
        (
            lambda: TimeoutError(),
            "Health check timeout",
        ),
        (
            lambda: RuntimeError("boom"),
            "Health check failed: boom",
        ),
    ],
)
@pytest.mark.asyncio
async def test_get_health_status_summary_safe_error_paths(
    monkeypatch: pytest.MonkeyPatch,
    error_factory,
    expected_summary: str,
) -> None:
    """Health summary helper should normalize timeout/runtime exceptions."""
    entry = MockConfigEntry(domain="pawcontrol", data={CONF_DOGS: []}, options={})
    flow = _Flow(entry)

    async def _raise_error(_entry: MockConfigEntry) -> dict[str, object]:
        raise error_factory()

    monkeypatch.setattr(flow, "_check_config_health_enhanced", _raise_error)

    assert await flow._get_health_status_summary_safe(entry) == expected_summary


@pytest.mark.asyncio
async def test_async_step_reauth_confirm_builds_default_summary_when_none(
    monkeypatch: pytest.MonkeyPatch,
    assert_flow_abort_reason,
) -> None:
    """A None health payload should fall back to the zero-issue summary."""
    entry = MockConfigEntry(
        domain="pawcontrol",
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy"}]},
        options={},
    )
    flow = _Flow(entry)

    async def _return_none(_entry: MockConfigEntry) -> None:
        return None

    monkeypatch.setattr(flow, "_check_config_health_enhanced", _return_none)

    result = await flow.async_step_reauth_confirm({"confirm": True})

    assert_flow_abort_reason(result, "reauth_successful")
    assert result["data_updates"]["health_total_dogs"] == 1
    assert result["options_updates"]["reauth_health_issues"] == []


@pytest.mark.asyncio
async def test_check_config_health_handles_validation_and_estimation_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health checks should report warning details for runtime validation failures."""
    entry = MockConfigEntry(
        domain="pawcontrol",
        data={CONF_DOGS: [{CONF_MODULES: {"feeding": True}}]},
        options={"entity_profile": "standard"},
    )
    flow = _Flow(entry)

    def _raise_validation_error(_dog: Mapping[str, object]) -> bool:
        raise RuntimeError("bad dog")

    monkeypatch.setattr(
        flow, "_is_dog_config_valid_for_reauth", _raise_validation_error
    )

    class _ExplodingFactory:
        def __init__(self, _hass: object) -> None:
            pass

        async def estimate_entity_count_async(
            self,
            _profile: str,
            _modules: Mapping[str, bool],
        ) -> int:
            raise RuntimeError("factory boom")

    monkeypatch.setattr(config_flow_reauth, "EntityFactory", _ExplodingFactory)

    summary = await flow._check_config_health_enhanced(entry)

    assert any(
        "Dog config validation error" in warning for warning in summary["warnings"]
    )
    assert any(
        "Entity estimation failed: bad dog" in warning
        for warning in summary["warnings"]
    )


@pytest.mark.asyncio
async def test_check_config_health_enhanced_handles_invalid_dogs_and_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health checks should flag invalid configs and malformed modules payloads."""
    entry = MockConfigEntry(
        domain="pawcontrol",
        data={
            CONF_DOGS: [
                {DOG_ID_FIELD: "buddy", CONF_MODULES: ["bad"]},
            ]
        },
        options={"entity_profile": "standard"},
    )
    flow = _Flow(entry)

    monkeypatch.setattr(flow, "_is_dog_config_valid_for_reauth", lambda *_: False)

    summary = await flow._check_config_health_enhanced(entry)

    assert "Invalid dog config: buddy" in summary["issues"]
    assert "No valid dog configurations found" in summary["issues"]
    assert "Modules payload invalid for buddy" in summary["warnings"]


@pytest.mark.asyncio
async def test_validate_reauth_entry_enhanced_allows_invalid_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid profiles should only warn during reauth validation."""
    entry = MockConfigEntry(
        domain="pawcontrol",
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy", CONF_MODULES: {"feeding": True}}]},
        options={"entity_profile": "unsupported"},
    )
    flow = _Flow(entry)

    monkeypatch.setattr(
        config_flow_reauth,
        "validate_dog_config_payload",
        lambda *_args, **_kwargs: None,
    )

    await flow._validate_reauth_entry_enhanced(entry)


@pytest.mark.asyncio
async def test_async_step_reauth_confirm_logs_unhealthy_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unhealthy health summaries should still complete reauth."""
    entry = MockConfigEntry(domain="pawcontrol", data={CONF_DOGS: []}, options={})
    flow = _Flow(entry)

    async def _unhealthy(_entry: MockConfigEntry) -> dict[str, object]:
        return {
            "healthy": False,
            "issues": ["bad dog config"],
            "warnings": [],
            "validated_dogs": 0,
            "total_dogs": 0,
        }

    monkeypatch.setattr(flow, "_check_config_health_enhanced", _unhealthy)

    result = await flow.async_step_reauth_confirm({"confirm": True})

    assert result["type"] == "abort"
    assert result["data_updates"]["health_status"] is False


@pytest.mark.asyncio
async def test_async_step_reauth_confirm_uses_status_check_warning_on_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Display summary failures should fall back to status-check warnings."""
    entry = MockConfigEntry(domain="pawcontrol", data={CONF_DOGS: []}, options={})
    flow = _Flow(entry)

    async def _raise_summary_error(_entry: MockConfigEntry) -> dict[str, object]:
        raise RuntimeError("display boom")

    monkeypatch.setattr(flow, "_check_config_health_enhanced", _raise_summary_error)

    result = await flow.async_step_reauth_confirm({"confirm": False})

    assert result["step_id"] == "reauth_confirm"
    assert (
        "Status check failed: display boom"
        in result["description_placeholders"]["health_status"]
    )
