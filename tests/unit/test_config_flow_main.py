"""Focused regression tests for config_flow_main helper logic."""

from collections.abc import Mapping
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock

from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryNotReady
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.pawcontrol import config_flow_main
from custom_components.pawcontrol.config_flow_main import (
    _LIST_REMOVE_DIRECTIVE,
    PawControlConfigFlow,
)
from custom_components.pawcontrol.const import (
    CONF_DOG_OPTIONS,
    CONF_DOGS,
    CONF_MODULES,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.exceptions import FlowValidationError, ValidationError
from custom_components.pawcontrol.types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
)
from custom_components.pawcontrol.validation import InputCoercionError


def test_format_local_timestamp_handles_invalid_input() -> None:
    """Timestamp formatter should keep graceful fallbacks for bad input."""
    flow = PawControlConfigFlow()

    assert flow._format_local_timestamp(None) == "Never reconfigured"
    assert flow._format_local_timestamp("not-a-date") == "not-a-date"


def test_format_local_timestamp_formats_iso_utc() -> None:
    """Valid ISO timestamps are converted into a stable formatted string."""
    flow = PawControlConfigFlow()

    formatted = flow._format_local_timestamp("2025-01-05T12:30:00Z")

    assert formatted.startswith("2025-01-05 12:30:00")
    assert formatted != "2025-01-05T12:30:00Z"


def test_merge_sequence_values_honors_remove_directive_and_deduplicates() -> None:
    """Sequence merging supports remove directives and de-dup append semantics."""
    flow = PawControlConfigFlow()

    assert flow._merge_sequence_values(["a", "b"], [_LIST_REMOVE_DIRECTIVE]) == []

    merged = flow._merge_sequence_values(["a", "b"], ["b", "c"])
    assert merged == ["b", "c", "a"]


def test_merge_nested_mapping_merges_collections_without_mutation() -> None:
    """Nested mapping merge should deeply merge while preserving source payloads."""
    flow = PawControlConfigFlow()

    base: Mapping[str, object] = {
        "settings": {"a": 1, "tags": ["one"]},
        "keep": True,
    }
    override: Mapping[str, object] = {
        "settings": {"b": 2, "tags": ["two"]},
        "keep": None,
    }

    merged = flow._merge_nested_mapping(base, override)

    assert merged == {
        "settings": {"a": 1, "b": 2, "tags": ["two", "one"]},
        "keep": True,
    }
    assert base == {"settings": {"a": 1, "tags": ["one"]}, "keep": True}


def test_merge_dog_entry_records_module_and_rename_notes() -> None:
    """Merging an existing dog should append module and rename note text."""
    flow = PawControlConfigFlow()
    merged = {
        "buddy": {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            DOG_MODULES_FIELD: {MODULE_FEEDING: False},
        },
    }
    notes: list[str] = []

    flow._merge_dog_entry(
        merged,
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy Prime",
            DOG_MODULES_FIELD: {MODULE_FEEDING: True},
        },
        notes,
        source="options_dog_options",
    )

    assert merged["buddy"][DOG_NAME_FIELD] == "Buddy Prime"
    assert merged["buddy"][DOG_MODULES_FIELD][MODULE_FEEDING] is True
    assert any("enabled feeding" in note for note in notes)
    assert any("renamed this dog" in note for note in notes)


def test_merge_dog_entry_baseline_add_does_not_emit_note() -> None:
    """Baseline config-entry payload should initialize dogs without merge notes."""
    flow = PawControlConfigFlow()
    merged: dict[str, dict[str, object]] = {}
    notes: list[str] = []

    flow._merge_dog_entry(
        merged,
        {DOG_ID_FIELD: "luna", DOG_NAME_FIELD: "Luna"},
        notes,
        source="config_entry_data",
    )

    assert merged["luna"][DOG_NAME_FIELD] == "Luna"
    assert notes == []


def test_build_dog_candidate_handles_legacy_module_payload() -> None:
    """Legacy module list payloads are normalized into toggle mappings."""
    flow = PawControlConfigFlow()

    candidate = flow._build_dog_candidate(
        {
            "id": "  Buddy  ",
            DOG_NAME_FIELD: "  ",
            CONF_MODULES: [
                MODULE_GPS,
                {"module": MODULE_FEEDING, "enabled": "no"},
                {"key": MODULE_FEEDING, "value": 1},
            ],
        },
        preserve_empty_name=True,
    )

    assert candidate is not None
    assert candidate[DOG_ID_FIELD] == "buddy"
    assert candidate[DOG_NAME_FIELD] == "  "
    assert candidate[CONF_MODULES] == {MODULE_GPS: True, MODULE_FEEDING: True}


def test_normalise_dogs_payload_accepts_mapping_fallback_identifier() -> None:
    """Dog payload mappings can use dictionary keys as fallback identifiers."""
    flow = PawControlConfigFlow()

    dogs = flow._normalise_dogs_payload({
        "dog-alpha": {DOG_NAME_FIELD: "Alpha"},
        "dog-beta": {"uniqueId": "Beta-ID", DOG_NAME_FIELD: "Beta"},
        "skip": "invalid",
    })

    assert dogs == [
        {DOG_NAME_FIELD: "Alpha", DOG_ID_FIELD: "dog-alpha"},
        {"uniqueId": "Beta-ID", DOG_NAME_FIELD: "Beta", DOG_ID_FIELD: "beta-id"},
    ]


def test_normalise_discovery_metadata_covers_sparse_collections() -> None:
    """Discovery normalization should ignore empty/invalid collection payloads."""
    flow = PawControlConfigFlow()

    normalized = flow._normalise_discovery_metadata(
        {
            "source": "dhcp",
            "port": 8123,
            "properties": {"skip": None},
            "service_uuids": ["   ", None],
        },
        include_last_seen=False,
    )
    assert normalized["port"] == 8123
    assert "properties" not in normalized
    assert "service_uuids" not in normalized

    decode_fallback = flow._normalise_discovery_metadata(
        {"service_uuids": [b"\xff"]},
        include_last_seen=False,
    )
    assert "service_uuids" not in decode_fallback


@pytest.mark.asyncio
async def test_async_get_entry_for_unique_id_handles_missing_and_awaitable() -> None:
    """Unique-id lookup should handle missing IDs and awaitable entry providers."""
    flow = PawControlConfigFlow()
    flow._async_current_entries = lambda: []  # type: ignore[method-assign]

    flow._unique_id = None  # type: ignore[attr-defined]
    assert await flow._async_get_entry_for_unique_id() is None

    flow._unique_id = 123  # type: ignore[attr-defined]
    assert await flow._async_get_entry_for_unique_id() is None

    entry = MockConfigEntry(domain=DOMAIN, unique_id="pawcontrol", data={})
    flow._unique_id = "pawcontrol"  # type: ignore[attr-defined]

    async def _entries() -> list[MockConfigEntry]:
        return [entry]

    flow._async_current_entries = lambda: _entries()  # type: ignore[method-assign]
    assert await flow._async_get_entry_for_unique_id() is entry


@pytest.mark.asyncio
async def test_handle_existing_discovery_entry_uses_abort_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discovery handling should use unique-id abort helper when no entry is found."""
    flow = PawControlConfigFlow()
    monkeypatch.setattr(
        flow,
        "_async_get_entry_for_unique_id",
        AsyncMock(return_value=None),
    )

    captured: dict[str, object] = {}

    def _abort_if_unique_id_configured(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return {"type": FlowResultType.ABORT, "reason": "already_configured"}

    monkeypatch.setattr(
        flow, "_abort_if_unique_id_configured", _abort_if_unique_id_configured
    )

    result = await flow._handle_existing_discovery_entry(
        updates={"host": "2.2.2.2"},
        comparison={},
        reload_on_update=True,
    )

    assert result["type"] == FlowResultType.ABORT
    assert captured["updates"] == {"host": "2.2.2.2"}
    assert captured["reload_on_update"] is True


@pytest.mark.asyncio
async def test_handle_existing_discovery_entry_updates_only_when_reload_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discovery updates should persist only when updates are required and reload is on."""
    flow = PawControlConfigFlow()
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"host": "1.1.1.1"})

    monkeypatch.setattr(
        flow,
        "_async_get_entry_for_unique_id",
        AsyncMock(return_value=entry),
    )
    monkeypatch.setattr(
        flow, "_discovery_update_required", lambda *_args, **_kwargs: True
    )

    update_reload = AsyncMock(
        return_value={"type": FlowResultType.ABORT, "reason": "already_configured"}
    )
    monkeypatch.setattr(
        flow,
        "async_update_reload_and_abort",
        update_reload,
        raising=False,
    )

    result = await flow._handle_existing_discovery_entry(
        updates={"host": "2.2.2.2"},
        comparison={},
        reload_on_update=True,
    )
    assert result["type"] == FlowResultType.ABORT
    update_reload.assert_awaited_once()

    result_no_reload = await flow._handle_existing_discovery_entry(
        updates={"host": "2.2.2.2"},
        comparison={},
        reload_on_update=False,
    )
    assert result_no_reload["type"] == FlowResultType.ABORT


def test_validation_signature_and_cache_invalidation() -> None:
    """Validation state signature should include sorted IDs and dog count."""
    flow = PawControlConfigFlow()
    flow._dogs = [{}, {}]
    flow._existing_dog_ids = {"buddy", "alpha"}
    assert flow._get_validation_state_signature() == "2::alpha|buddy"

    flow._profile_estimates_cache = {"cached": 4}
    flow._invalidate_profile_caches()
    assert flow._profile_estimates_cache == {}


@pytest.mark.asyncio
async def test_validate_dog_input_cached_uses_cache_then_revalidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation cache entries should be consumed exactly once before revalidation."""
    flow = PawControlConfigFlow()

    def _fixed_now() -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC)

    monkeypatch.setattr(config_flow_main.dt_util, "utcnow", _fixed_now)

    user_input = {
        "dog_id": "buddy",
        "dog_name": "Buddy",
        "dog_weight": 12,
    }
    cache_key = "buddy_Buddy_12"
    flow._validation_cache[cache_key] = {
        "result": {"dog_id": "cached-buddy"},
        "cached_at": _fixed_now().timestamp(),
        "state_signature": flow._get_validation_state_signature(),
        "clock_token": id(config_flow_main.dt_util.utcnow),
        "consumed": False,
    }

    optimized = AsyncMock(return_value={"dog_id": "fresh-buddy"})
    monkeypatch.setattr(flow, "_validate_dog_input_optimized", optimized)

    cached = await flow._validate_dog_input_cached(user_input)
    assert cached == {"dog_id": "cached-buddy"}
    assert flow._validation_cache[cache_key]["consumed"] is True

    refreshed = await flow._validate_dog_input_cached(user_input)
    assert refreshed == {"dog_id": "fresh-buddy"}
    assert optimized.await_count == 1


@pytest.mark.asyncio
async def test_validate_dog_input_cached_re_raises_flow_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation cache wrapper should preserve original validation exceptions."""
    flow = PawControlConfigFlow()
    monkeypatch.setattr(
        flow,
        "_validate_dog_input_optimized",
        AsyncMock(
            side_effect=FlowValidationError(
                field_errors={"base": "invalid_dog"},
            ),
        ),
    )

    with pytest.raises(FlowValidationError):
        await flow._validate_dog_input_cached(
            {"dog_id": "buddy", "dog_name": "Buddy", "dog_weight": 1},
        )


@pytest.mark.asyncio
async def test_estimate_total_entities_cached_reuses_cached_value() -> None:
    """Entity estimation should cache by profile and dog signature."""
    flow = PawControlConfigFlow()
    flow._dogs = [{DOG_ID_FIELD: "buddy", CONF_MODULES: {MODULE_GPS: True}}]
    estimate = AsyncMock(return_value=5)
    flow._entity_factory.estimate_entity_count_async = estimate

    first = await flow._estimate_total_entities_cached()
    second = await flow._estimate_total_entities_cached()

    assert first == 5
    assert second == 5
    assert estimate.await_count == 1


def test_discovery_hint_performance_and_recommendations() -> None:
    """Hint and recommendation helpers should handle all threshold branches."""
    flow = PawControlConfigFlow()

    assert flow._get_discovery_hint() == ""
    flow._discovery_info = {"hostname": "tracker-a"}
    assert flow._get_discovery_hint() == "Discovered device: tracker-a"

    flow._dogs = [{}, {}, {}, {}, {}]
    assert "basic" in flow._get_performance_note()
    assert "basic" in flow._get_profile_recommendation()

    flow._dogs = [{}, {}, {}]
    assert "standard" in flow._get_performance_note()
    assert "balanced" in flow._get_profile_recommendation()

    flow._dogs = [{CONF_MODULES: {MODULE_GPS: True}}]
    assert "advanced" in flow._get_performance_note()
    assert "full features" in flow._get_profile_recommendation()


@pytest.mark.asyncio
async def test_validate_dog_input_optimized_builds_existing_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optimized validation should forward normalized existing IDs and names."""
    flow = PawControlConfigFlow()
    flow._existing_dog_ids = {"known-id"}
    flow._dogs = [
        {DOG_NAME_FIELD: "  Buddy  "},
        {DOG_NAME_FIELD: ""},
        {DOG_NAME_FIELD: None},
    ]

    observed: dict[str, object] = {}

    def _validate_dog_setup_input(  # type: ignore[no-untyped-def]
        payload,
        *,
        existing_ids,
        existing_names,
        current_dog_count,
        max_dogs,
    ):
        observed["payload"] = payload
        observed["existing_ids"] = set(existing_ids)
        observed["existing_names"] = set(existing_names)
        observed["current_dog_count"] = current_dog_count
        observed["max_dogs"] = max_dogs
        return {"dog_id": "new-id", "dog_name": "New Name", "dog_weight": 1}

    monkeypatch.setattr(
        config_flow_main, "validate_dog_setup_input", _validate_dog_setup_input
    )

    result = await flow._validate_dog_input_optimized(
        {"dog_id": "new-id", "dog_name": "New Name", "dog_weight": 1},
    )

    assert result["dog_id"] == "new-id"
    assert observed["existing_ids"] == {"known-id"}
    assert observed["existing_names"] == {"buddy"}


@pytest.mark.asyncio
async def test_create_dog_config_handles_optional_fields_and_discovery() -> None:
    """Dog config creation should normalize optional fields and discovery payloads."""
    flow = PawControlConfigFlow()
    flow._discovery_info = {"host": "10.0.0.5"}

    without_breed = await flow._create_dog_config(
        {
            "dog_id": "  buddy  ",
            "dog_name": "  Buddy  ",
            "dog_breed": "   ",
            "dog_age": 4,
            "dog_weight": 12.5,
            "dog_size": "large",
        },
    )
    assert without_breed["dog_id"] == "buddy"
    assert without_breed["dog_name"] == "Buddy"
    assert "dog_breed" not in without_breed
    assert without_breed["dog_age"] == 4
    assert without_breed["dog_weight"] == 12.5
    assert without_breed["dog_size"] == "large"
    assert without_breed["discovery_info"]["host"] == "10.0.0.5"

    with_breed = await flow._create_dog_config(
        {"dog_id": "max", "dog_name": "Max", "dog_breed": "Labrador"},
    )
    assert with_breed["dog_breed"] == "Labrador"


@pytest.mark.asyncio
async def test_async_step_dog_modules_covers_no_dog_and_invalid_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dog modules step should delegate when empty and show errors on bad schema."""
    flow = PawControlConfigFlow()

    monkeypatch.setattr(
        flow,
        "async_step_add_dog",
        AsyncMock(return_value={"type": FlowResultType.FORM, "step_id": "add_dog"}),
    )
    no_dog_result = await flow.async_step_dog_modules()
    assert no_dog_result["step_id"] == "add_dog"

    flow._dogs = [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy", CONF_MODULES: {}}]

    def _raise_invalid(_value):  # type: ignore[no-untyped-def]
        raise vol.Invalid("invalid modules")

    monkeypatch.setattr(config_flow_main, "MODULES_SCHEMA", _raise_invalid)
    invalid_result = await flow.async_step_dog_modules({MODULE_GPS: True})
    assert invalid_result["type"] == FlowResultType.FORM
    assert invalid_result["errors"] == {"base": "invalid_modules"}


@pytest.mark.asyncio
async def test_async_step_add_another_and_entity_profile_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Add-another and profile steps should route based on limits and validation."""
    flow = PawControlConfigFlow()
    flow._dogs = [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]

    add_dog = AsyncMock(return_value={"step_id": "add_dog"})
    entity_profile = AsyncMock(return_value={"step_id": "entity_profile"})
    monkeypatch.setattr(flow, "async_step_add_dog", add_dog)
    monkeypatch.setattr(flow, "async_step_entity_profile", entity_profile)

    go_add = await flow.async_step_add_another({"add_another": True})
    assert go_add["step_id"] == "add_dog"

    flow._dogs = [
        {DOG_ID_FIELD: str(index), DOG_NAME_FIELD: f"Dog {index}"}
        for index in range(config_flow_main.MAX_DOGS_PER_INTEGRATION)
    ]
    at_limit = await flow.async_step_add_another({"add_another": True})
    assert at_limit["step_id"] == "entity_profile"

    form_result = await flow.async_step_add_another()
    assert form_result["type"] == FlowResultType.FORM
    assert form_result["step_id"] == "add_another"

    profile_flow = PawControlConfigFlow()
    profile_flow._dogs = [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]
    configure_modules = AsyncMock(return_value={"step_id": "configure_modules"})
    final_setup = AsyncMock(return_value={"step_id": "final_setup"})
    monkeypatch.setattr(profile_flow, "async_step_configure_modules", configure_modules)
    monkeypatch.setattr(profile_flow, "async_step_final_setup", final_setup)
    monkeypatch.setattr(
        config_flow_main,
        "validate_profile_selection",
        lambda _value: "standard",
    )

    monkeypatch.setattr(
        profile_flow,
        "_aggregate_enabled_modules",
        lambda: {MODULE_GPS: True},
    )
    profile_with_gps = await profile_flow.async_step_entity_profile(
        {"entity_profile": "standard"},
    )
    assert profile_with_gps["step_id"] == "configure_modules"

    monkeypatch.setattr(
        profile_flow,
        "_aggregate_enabled_modules",
        lambda: {MODULE_FEEDING: True},
    )
    profile_without_gps = await profile_flow.async_step_entity_profile(
        {"entity_profile": "standard"},
    )
    assert profile_without_gps["step_id"] == "final_setup"

    def _raise_invalid(_value):  # type: ignore[no-untyped-def]
        raise vol.Invalid("bad profile")

    monkeypatch.setattr(config_flow_main, "validate_profile_selection", _raise_invalid)
    invalid_profile = await profile_flow.async_step_entity_profile(
        {"entity_profile": "bad"},
    )
    assert invalid_profile["type"] == FlowResultType.FORM
    assert invalid_profile["errors"] == {"base": "invalid_profile"}

    monkeypatch.setattr(
        profile_flow,
        "_estimate_total_entities",
        AsyncMock(return_value=9),
    )
    initial_profile_form = await profile_flow.async_step_entity_profile()
    assert initial_profile_form["type"] == FlowResultType.FORM
    assert initial_profile_form["step_id"] == "entity_profile"


@pytest.mark.asyncio
async def test_perform_validation_and_reconfigure_entry_missing_path() -> None:
    """Comprehensive validation and missing reconfigure entry should error clearly."""
    flow = PawControlConfigFlow()
    flow._dogs = [{DOG_ID_FIELD: "buddy"}]
    flow._entity_profile = "not-a-profile"
    flow._is_dog_config_valid_for_flow = lambda _dog: False  # type: ignore[method-assign]
    flow._estimate_total_entities_cached = AsyncMock(return_value=250)

    result = await flow._perform_comprehensive_validation()
    assert result["valid"] is False
    assert any("Invalid dog configuration" in err for err in result["errors"])
    assert any("Too many estimated entities" in err for err in result["errors"])
    assert any("Invalid profile" in err for err in result["errors"])

    flow.context["entry_id"] = "missing-entry"
    flow.hass = type(
        "HassStub",
        (),
        {
            "config_entries": type(
                "EntriesStub",
                (),
                {"async_get_entry": staticmethod(lambda _entry_id: None)},
            )()
        },
    )()
    with pytest.raises(ConfigEntryNotReady, match="Config entry not found"):
        await flow.async_step_reconfigure()


def test_build_config_entry_data_and_profile_resolution() -> None:
    """Entry payload builder and profile resolver should honor all fallback paths."""
    flow = PawControlConfigFlow()
    flow._integration_name = "Paw Control"
    flow._dogs = [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]
    flow._entity_profile = "standard"
    flow._external_entities = {"sensor.test": {"enabled": True}}
    flow._global_settings = {
        "performance_mode": "balanced",
        "enable_analytics": 1,
        "enable_cloud_backup": 0,
        "debug_logging": True,
        "data_retention_days": 14,
    }
    flow._discovery_info = {
        "host": "10.0.0.5",
        "port": 8443,
        "properties": {"https": "yes", "api_key": "token-from-properties"},
    }

    config_data, options_data = flow._build_config_entry_data()
    assert "external_entities" in config_data
    assert config_data["discovery_info"]["host"] == "10.0.0.5"
    assert options_data["api_endpoint"] == "https://10.0.0.5:8443"
    assert options_data["api_token"] == "token-from-properties"

    flow._discovery_info = {"ip": "10.0.0.9", "api_key": "token-from-discovery"}
    _, fallback_options = flow._build_config_entry_data()
    assert fallback_options["api_endpoint"] == "http://10.0.0.9"
    assert fallback_options["api_token"] == "token-from-discovery"

    entry_options = MockConfigEntry(
        domain=DOMAIN,
        data={"entity_profile": "basic"},
        options={"entity_profile": "standard"},
    )
    entry_data = MockConfigEntry(
        domain=DOMAIN,
        data={"entity_profile": "advanced"},
        options={"entity_profile": "not-real"},
    )
    entry_default = MockConfigEntry(
        domain=DOMAIN,
        data={"entity_profile": "not-real"},
        options={},
    )
    assert flow._resolve_entry_profile(entry_options) == "standard"
    assert flow._resolve_entry_profile(entry_data) == "advanced"
    assert (
        flow._resolve_entry_profile(entry_default) == config_flow_main.DEFAULT_PROFILE
    )


def test_history_placeholders_merge_helpers_and_extract_entry_dogs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """History and merge helpers should normalize telemetry and legacy dog payloads."""
    flow = PawControlConfigFlow()
    history_without_telemetry = flow._reconfigure_history_placeholders(
        {"last_reconfigure": "2025-01-01T10:00:00Z"},
    )
    assert history_without_telemetry["reconfigure_requested_profile"] == "Not recorded"

    history_with_telemetry = flow._reconfigure_history_placeholders(
        {
            "last_reconfigure": "2025-01-01T10:00:00Z",
            "reconfigure_telemetry": {
                "requested_profile": "",
                "previous_profile": "",
                "dogs_count": 2.0,
                "estimated_entities": 7.0,
                "compatibility_warnings": ["warn-a", 2],
                "merge_notes": [" one ", None],
                "timestamp": "2025-01-02T10:00:00Z",
            },
        },
    )
    assert history_with_telemetry["reconfigure_requested_profile"] == "Unknown"
    assert history_with_telemetry["reconfigure_entities"] == "7"
    assert "warn-a" in history_with_telemetry["reconfigure_warnings"]
    assert "one" in history_with_telemetry["reconfigure_merge_notes"]

    monkeypatch.setattr(config_flow_main.dt_util, "UTC", UTC, raising=False)
    monkeypatch.setattr(config_flow_main.dt_util, "as_local", lambda value: value)
    assert flow._format_local_timestamp("2025-01-05T12:30:00").startswith("2025-01-05")
    assert flow._sequence_requests_removal([{_LIST_REMOVE_DIRECTIVE: True}]) is True
    assert flow._merge_sequence_values("not-a-sequence", []) == []
    assert flow._merge_sequence_values(["a"], []) == ["a"]
    assert flow._merge_nested_mapping(None, {"value": 1}) == {"value": 1}

    merged: dict[str, dict[str, object]] = {}
    notes: list[str] = []
    flow._merge_dog_entry(
        merged,
        {DOG_ID_FIELD: 123},  # type: ignore[dict-item]
        notes,
        source="options_dog_options",
    )
    assert merged == {}

    flow._merge_dog_entry(
        merged,
        {DOG_ID_FIELD: "luna", DOG_NAME_FIELD: "Luna"},
        notes,
        source="options_dog_options",
    )
    assert any("added a dog configuration" in note for note in notes)

    merged["luna"] = {
        DOG_ID_FIELD: "luna",
        DOG_NAME_FIELD: "",
        DOG_MODULES_FIELD: {MODULE_GPS: False},
        "settings": {"a": 1},
        "tags": ["legacy"],
    }
    flow._merge_dog_entry(
        merged,
        {
            DOG_ID_FIELD: "luna",
            DOG_NAME_FIELD: "  ",
            DOG_MODULES_FIELD: ["not-used"],  # type: ignore[dict-item]
            "settings": {"b": 2},
            "tags": ["new"],
            "notes": None,
        },
        notes,
        source="options_dog_options",
    )
    flow._merge_dog_entry(
        merged,
        {
            DOG_ID_FIELD: "luna",
            DOG_NAME_FIELD: "luna",
        },
        notes,
        source="options_dog_options",
    )
    assert merged["luna"]["settings"] == {"a": 1, "b": 2}
    assert merged["luna"]["tags"] == ["new", "legacy"]
    assert any("set the name" in note for note in notes)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DOGS: [
                {
                    DOG_ID_FIELD: "buddy",
                    DOG_NAME_FIELD: "Buddy",
                    DOG_MODULES_FIELD: {MODULE_GPS: False},
                },
            ],
            CONF_DOG_OPTIONS: [
                {
                    DOG_ID_FIELD: "buddy",
                    DOG_MODULES_FIELD: {MODULE_FEEDING: True},
                },
            ],
        },
        options={
            CONF_DOGS: [
                {
                    DOG_ID_FIELD: "buddy",
                    DOG_MODULES_FIELD: {MODULE_GPS: True},
                },
            ],
            CONF_DOG_OPTIONS: [
                {
                    DOG_ID_FIELD: "buddy",
                    DOG_NAME_FIELD: "Buddy Prime",
                },
            ],
        },
    )
    dogs, merge_notes = flow._extract_entry_dogs(entry)
    assert dogs[0][DOG_MODULES_FIELD][MODULE_FEEDING] is True
    assert dogs[0][DOG_NAME_FIELD] == "Buddy Prime"
    assert any("renamed this dog" in note for note in merge_notes)

    monkeypatch.setattr(
        config_flow_main,
        "normalize_dog_id",
        lambda _value: (_ for _ in ()).throw(
            InputCoercionError("dog_id", "bad", "invalid")
        ),
    )
    assert flow._resolve_dog_identifier({DOG_ID_FIELD: "bad"}, "  Raw Id  ") == "Raw Id"


@pytest.mark.asyncio
async def test_candidate_toggle_and_reconfigure_compatibility_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Candidate normalization and compatibility helpers should cover edge paths."""
    flow = PawControlConfigFlow()

    assert flow._build_dog_candidate("invalid") is None
    assert flow._build_dog_candidate({DOG_NAME_FIELD: "No ID"}) is None

    candidate = flow._build_dog_candidate(
        {
            DOG_ID_FIELD: "  Buddy  ",
            DOG_NAME_FIELD: "bad",
            "name": "Legacy Name",
            CONF_MODULES: [
                "unknown",
                MODULE_GPS,
                {"name": MODULE_FEEDING, "value": "off"},
                {"key": "invalid"},
                5,
            ],
        },
    )
    assert candidate is not None
    assert candidate[DOG_ID_FIELD] == "buddy"
    assert candidate[DOG_MODULES_FIELD][MODULE_GPS] is True
    assert candidate[DOG_MODULES_FIELD][MODULE_FEEDING] is False

    no_modules = flow._build_dog_candidate(
        {DOG_ID_FIELD: "alpha", CONF_MODULES: "legacy-string"},
    )
    assert no_modules is not None
    assert DOG_MODULES_FIELD not in no_modules

    assert flow._coerce_legacy_toggle(None) is True
    assert flow._coerce_legacy_toggle(False) is False
    assert flow._coerce_legacy_toggle(0) is False
    assert flow._coerce_legacy_toggle(" ") is True
    assert flow._coerce_legacy_toggle("disabled") is False
    assert flow._coerce_legacy_toggle("enabled") is True
    assert flow._coerce_legacy_toggle("unsupported") is False
    assert flow._coerce_legacy_toggle(object()) is True

    normalized_modules = flow._normalise_dog_modules(
        {CONF_MODULES: {MODULE_GPS: 1, MODULE_FEEDING: 0}},
    )
    assert normalized_modules[MODULE_GPS] is True
    assert normalized_modules[MODULE_FEEDING] is False
    assert flow._normalise_dog_modules({}) == {}

    valid_dog = {
        DOG_ID_FIELD: "buddy",
        DOG_NAME_FIELD: "Buddy",
        CONF_MODULES: {MODULE_GPS: True},
    }
    estimate_mock = AsyncMock(return_value=4)
    flow._entity_factory.estimate_entity_count_async = estimate_mock
    estimated = await flow._estimate_entities_for_reconfigure(
        [valid_dog, {}], "standard"
    )
    assert estimated == 4
    assert estimate_mock.await_count == 1

    flow._entity_factory.validate_profile_for_modules = lambda *_args, **_kwargs: False
    compatibility = flow._check_profile_compatibility("basic", [valid_dog])
    assert compatibility["compatible"] is False
    assert compatibility["warnings"]

    flow._dogs = [
        {CONF_MODULES: {"unknown": True, MODULE_GPS: False}},
        {CONF_MODULES: {MODULE_GPS: True}},
    ]
    aggregated = flow._aggregate_enabled_modules()
    assert MODULE_GPS in aggregated
    assert "unknown" not in aggregated

    assert "No dogs configured yet." not in flow._format_dogs_list_enhanced()
    assert "Estimated entities" in flow._get_profiles_info_enhanced()

    many_dogs = [
        {
            CONF_MODULES: {
                MODULE_GPS: True,
                MODULE_FEEDING: True,
                MODULE_HEALTH: True,
                MODULE_WALK: True,
            }
        }
        for _ in range(5)
    ]
    assert "High dog count" in flow._get_compatibility_info("standard", many_dogs)

    module_heavy = [
        {CONF_MODULES: {key: True for key in config_flow_main.MODULE_TOGGLE_KEYS}}
        for _ in range(4)
    ]
    assert "Many modules enabled" in flow._get_compatibility_info(
        "standard", module_heavy
    )
    assert "supports all profiles" in flow._get_compatibility_info(
        "standard", [valid_dog]
    )

    monkeypatch.setattr(
        flow,
        "_estimate_total_entities_cached",
        AsyncMock(return_value=12),
    )
    assert await flow._estimate_total_entities() == 12


def test_async_get_options_flow_initializes_from_config_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Options flow factory should initialize the returned flow with the entry."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    seen: dict[str, object] = {}

    def _initialize(self, config_entry):  # type: ignore[no-untyped-def]
        seen["entry"] = config_entry

    monkeypatch.setattr(
        config_flow_main.PawControlOptionsFlow,
        "initialize_from_config_entry",
        _initialize,
        raising=False,
    )

    options_flow = PawControlConfigFlow.async_get_options_flow(entry)
    assert seen["entry"] is entry
    assert isinstance(options_flow, config_flow_main.PawControlOptionsFlow)


def test_discovery_helpers_cover_remaining_branch_paths() -> None:
    """Discovery normalization and update checks should cover fallback branches."""
    flow = PawControlConfigFlow()

    normalized = flow._normalise_discovery_metadata(
        {
            "source": "dhcp",
            "hostname": "   ",
            "port": "not-a-port",
            "properties": {"number": 7},
        },
        include_last_seen=False,
    )
    assert "hostname" not in normalized
    assert "port" not in normalized
    assert normalized["properties"]["number"] == 7

    updates, _comparison = flow._prepare_discovery_updates(
        {"source": "dhcp"}, source="dhcp"
    )
    assert "host" not in updates
    assert "device" not in updates
    assert "address" not in updates

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "discovery_info": {"source": "dhcp", "host": "1.1.1.1"},
            "host": "1.1.1.1",
        },
    )
    comparison = flow._strip_dynamic_discovery_fields(
        flow._normalise_discovery_metadata(
            {"source": "dhcp", "host": "1.1.1.1"},
            source="dhcp",
            include_last_seen=False,
        ),
    )
    assert (
        flow._discovery_update_required(
            entry,
            updates={"discovery_info": {"source": "dhcp", "host": "1.1.1.1"}},
            comparison=comparison,
        )
        is False
    )
    assert (
        flow._discovery_update_required(
            entry,
            updates={
                "discovery_info": {"source": "dhcp", "host": "1.1.1.1"},
                "host": "1.1.1.1",
            },
            comparison=comparison,
        )
        is False
    )


@pytest.mark.asyncio
async def test_casefold_lookup_and_abort_when_discovery_updates_are_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Casefold lookup should skip non-string IDs and unchanged updates should abort."""
    flow = PawControlConfigFlow()
    flow._unique_id = "pawcontrol"  # type: ignore[attr-defined]
    wrong_type = MockConfigEntry(domain=DOMAIN, unique_id=None, data={})
    casefold_match = MockConfigEntry(domain=DOMAIN, unique_id="PAWCONTROL", data={})
    flow._async_current_entries = lambda: [wrong_type, casefold_match]  # type: ignore[method-assign]
    assert await flow._async_get_entry_for_unique_id() is casefold_match

    monkeypatch.setattr(
        flow,
        "_async_get_entry_for_unique_id",
        AsyncMock(return_value=casefold_match),
    )
    monkeypatch.setattr(
        flow, "_discovery_update_required", lambda *_args, **_kwargs: False
    )
    result = await flow._handle_existing_discovery_entry(
        updates={"host": "1.1.1.1"},
        comparison={},
        reload_on_update=True,
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_add_dog_and_modules_steps_cover_remaining_edge_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dog setup steps should cover None validation and non-mapping module inputs."""
    flow = PawControlConfigFlow()
    monkeypatch.setattr(
        flow,
        "_validate_dog_input_cached",
        AsyncMock(return_value=None),
    )
    no_result = await flow.async_step_add_dog({"dog_id": "buddy"})
    assert no_result["type"] == FlowResultType.FORM

    monkeypatch.setattr(
        flow,
        "_validate_dog_input_cached",
        AsyncMock(
            return_value={"dog_id": "buddy", "dog_name": "Buddy", "dog_weight": 1}
        ),
    )
    monkeypatch.setattr(
        flow,
        "_create_dog_config",
        AsyncMock(
            return_value={DOG_ID_FIELD: 42, DOG_NAME_FIELD: "Buddy", CONF_MODULES: {}}
        ),
    )
    monkeypatch.setattr(
        flow,
        "async_step_dog_modules",
        AsyncMock(return_value={"step_id": "dog_modules"}),
    )
    with_non_string_id = await flow.async_step_add_dog({"dog_id": "buddy"})
    assert with_non_string_id["step_id"] == "dog_modules"
    assert flow._existing_dog_ids == set()

    modules_flow = PawControlConfigFlow()
    modules_flow._dogs = [
        {DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy", CONF_MODULES: {}}
    ]
    monkeypatch.setattr(
        config_flow_main,
        "coerce_dog_modules_config",
        lambda _value: {MODULE_GPS: True},
    )
    monkeypatch.setattr(config_flow_main, "MODULES_SCHEMA", lambda value: value)
    monkeypatch.setattr(
        modules_flow,
        "async_step_add_another_dog",
        AsyncMock(return_value={"step_id": "add_another"}),
    )
    modules_result = await modules_flow.async_step_dog_modules([])  # non-mapping input
    assert modules_result["step_id"] == "add_another"


@pytest.mark.asyncio
async def test_final_setup_profile_compatibility_warning_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Final setup should continue when profile compatibility warning is emitted."""
    flow = PawControlConfigFlow()
    flow._dogs = [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy", CONF_MODULES: {}}]
    monkeypatch.setattr(
        flow,
        "_perform_comprehensive_validation",
        AsyncMock(return_value={"valid": True, "errors": [], "estimated_entities": 3}),
    )
    monkeypatch.setattr(flow, "_validate_profile_compatibility", lambda: False)
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


def test_profile_compatibility_and_discovery_option_branches() -> None:
    """Compatibility and discovery options should cover fallback endpoint/token branches."""
    flow = PawControlConfigFlow()
    flow._dogs = [
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            CONF_MODULES: {MODULE_GPS: True},
        }
    ]
    flow._entity_factory.validate_profile_for_modules = lambda *_args, **_kwargs: False
    assert flow._validate_profile_compatibility() is False

    flow._integration_name = "Paw Control"
    flow._entity_profile = "standard"
    flow._dogs = [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]
    flow._global_settings = {}
    flow._discovery_info = {"host": "10.0.0.2", "properties": {"https": 1}}
    _, options_data = flow._build_config_entry_data()
    assert options_data["api_endpoint"] == "https://10.0.0.2"
    assert "api_token" not in options_data

    flow._discovery_info = {"host": 123, "properties": "invalid"}  # type: ignore[dict-item]
    _, fallback_options = flow._build_config_entry_data()
    assert "api_endpoint" not in fallback_options
    assert "api_token" not in fallback_options


def test_empty_dogs_list_and_unknown_module_aggregation_path() -> None:
    """Dog list/aggregation helpers should cover empty and unknown-module branches."""
    flow = PawControlConfigFlow()
    assert flow._format_dogs_list_enhanced() == "No dogs configured yet."
    flow._dogs = [
        {CONF_MODULES: {"unknown": True, MODULE_GPS: False}},
        {CONF_MODULES: {MODULE_GPS: True}},
    ]
    aggregated = flow._aggregate_enabled_modules()
    assert "unknown" not in aggregated
    assert aggregated[MODULE_GPS] is True


@pytest.mark.asyncio
async def test_reconfigure_success_telemetry_captures_warning_and_merge_notes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconfigure step should include compatibility and merge-note telemetry."""
    flow = PawControlConfigFlow()
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry-1",
        unique_id="uid-1",
        data={
            CONF_DOGS: [
                {DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy", CONF_MODULES: {}}
            ],
            "entity_profile": "standard",
        },
        options={
            CONF_DOG_OPTIONS: [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy Prime"}],
        },
    )

    flow.context["entry_id"] = "entry-1"
    flow.hass = type(
        "HassStub",
        (),
        {
            "config_entries": type(
                "EntriesStub",
                (),
                {"async_get_entry": staticmethod(lambda _entry_id: entry)},
            )()
        },
    )()
    monkeypatch.setattr(flow, "async_set_unique_id", AsyncMock())
    monkeypatch.setattr(flow, "_abort_if_unique_id_mismatch", lambda **_kwargs: None)
    monkeypatch.setattr(
        flow,
        "_check_profile_compatibility",
        lambda *_args: {"compatible": False, "warnings": ["profile warning"]},
    )
    monkeypatch.setattr(
        flow,
        "_check_config_health_enhanced",
        AsyncMock(return_value={"healthy": False, "issues": ["issue a"]}),
    )
    monkeypatch.setattr(
        flow,
        "_estimate_entities_for_reconfigure",
        AsyncMock(return_value=7),
    )
    update_abort = AsyncMock(
        return_value={"type": FlowResultType.ABORT, "reason": "reconfigure_successful"},
    )
    monkeypatch.setattr(
        flow, "async_update_reload_and_abort", update_abort, raising=False
    )

    result = await flow.async_step_reconfigure({"entity_profile": "advanced"})
    assert result["reason"] == "reconfigure_successful"

    kwargs = update_abort.await_args.kwargs
    telemetry = kwargs["options_updates"]["reconfigure_telemetry"]
    assert telemetry["compatibility_warnings"] == ["profile warning"]
    assert telemetry["merge_notes"]


def test_extract_entry_dogs_handles_non_mapping_options() -> None:
    """Dog extraction should skip options payloads that are not mappings."""
    flow = PawControlConfigFlow()

    class _Entry:
        data = {CONF_DOGS: [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]}
        options = ["not-a-mapping"]

    dogs, notes = flow._extract_entry_dogs(_Entry())  # type: ignore[arg-type]
    assert len(dogs) == 1
    assert notes == []


def test_history_and_merge_sequence_branch_edges() -> None:
    """History and sequence helpers should cover remaining conditional branches."""
    flow = PawControlConfigFlow()
    history = flow._reconfigure_history_placeholders(
        {
            "reconfigure_telemetry": {
                "requested_profile": "standard",
                "previous_profile": "basic",
                "dogs_count": 1,
                "estimated_entities": 3,
                "compatibility_warnings": [],
            },
        },
    )
    assert "reconfigure_merge_notes" in history

    assert flow._merge_sequence_values("not-seq", ["x"]) == ["x"]

    merged = {
        "buddy": {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            CONF_MODULES: {MODULE_GPS: True},
        }
    }
    notes: list[str] = []
    flow._merge_dog_entry(
        merged,
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy Prime",
            "age": 5,
        },
        notes,
        source="config_entry_data",
    )
    assert merged["buddy"]["age"] == 5
    assert notes == []


def test_payload_candidate_identifier_and_compatibility_edge_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Candidate and identifier helpers should cover fallback loops and skips."""
    flow = PawControlConfigFlow()
    dogs = flow._normalise_dogs_payload(["skip-me", {DOG_ID_FIELD: "buddy"}])
    assert len(dogs) == 1

    def _validate_flow_dog_name(value, *, required=False):  # type: ignore[no-untyped-def]
        if value == "bad":
            raise ValidationError("dog_name")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    monkeypatch.setattr(
        config_flow_main, "validate_flow_dog_name", _validate_flow_dog_name
    )
    candidate = flow._build_dog_candidate(
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "bad",
            "name": "Legacy",
            CONF_MODULES: [{"value": True}],
        },
    )
    assert candidate is not None
    assert candidate[DOG_NAME_FIELD] == "Legacy"
    assert CONF_MODULES not in candidate

    def _normalize_dog_id(value):  # type: ignore[no-untyped-def]
        text = str(value).strip()
        return "" if not text else text.lower()

    monkeypatch.setattr(config_flow_main, "normalize_dog_id", _normalize_dog_id)
    resolved = flow._resolve_dog_identifier({DOG_ID_FIELD: "  ", "id": "Dog-2"}, None)
    assert resolved == "dog-2"

    flow._entity_factory.validate_profile_for_modules = lambda *_args, **_kwargs: False
    compatibility = flow._check_profile_compatibility(
        "standard",
        [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}],
    )
    assert compatibility["compatible"] is True


def test_discovery_update_loop_and_unknown_module_continue_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicitly cover discovery loop continue and unknown module aggregation skips."""
    flow = PawControlConfigFlow()
    comparison = {"source": "dhcp", "host": "1.1.1.1"}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"discovery_info": comparison, "host": "1.1.1.1"},
    )
    monkeypatch.setattr(
        flow,
        "_strip_dynamic_discovery_fields",
        lambda _value: comparison,
    )
    assert (
        flow._discovery_update_required(
            entry,
            updates={"discovery_info": {"source": "dhcp", "host": "1.1.1.1"}},
            comparison=comparison,
        )
        is False
    )

    flow._dogs = [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]
    monkeypatch.setattr(
        config_flow_main,
        "ensure_dog_modules_mapping",
        lambda _dog: {"unknown-module": True, MODULE_GPS: False},
    )
    aggregated = flow._aggregate_enabled_modules()
    assert aggregated[MODULE_GPS] is False
    assert "unknown-module" not in aggregated


def test_merge_dog_entry_skips_non_string_name_value() -> None:
    """Merge should ignore non-string ``dog_name`` values without changing existing name."""
    flow = PawControlConfigFlow()
    merged = {
        "buddy": {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: "Buddy",
            CONF_MODULES: {},
        }
    }
    notes: list[str] = []

    flow._merge_dog_entry(
        merged,
        {
            DOG_ID_FIELD: "buddy",
            DOG_NAME_FIELD: 123,  # type: ignore[dict-item]
        },
        notes,
        source="options_dog_options",
    )
    assert merged["buddy"][DOG_NAME_FIELD] == "Buddy"


@pytest.mark.asyncio
async def test_reconfigure_unhealthy_without_issues_skips_issue_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconfigure should continue when health is unhealthy but no issue list is present."""
    flow = PawControlConfigFlow()
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry-2",
        unique_id="uid-2",
        data={CONF_DOGS: [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}]},
        options={},
    )
    flow.context["entry_id"] = "entry-2"
    flow.hass = type(
        "HassStub",
        (),
        {
            "config_entries": type(
                "EntriesStub",
                (),
                {"async_get_entry": staticmethod(lambda _entry_id: entry)},
            )()
        },
    )()
    monkeypatch.setattr(flow, "async_set_unique_id", AsyncMock())
    monkeypatch.setattr(flow, "_abort_if_unique_id_mismatch", lambda **_kwargs: None)
    monkeypatch.setattr(
        flow,
        "_check_profile_compatibility",
        lambda *_args: {"compatible": True, "warnings": []},
    )
    monkeypatch.setattr(
        flow,
        "_check_config_health_enhanced",
        AsyncMock(return_value={"healthy": False, "issues": []}),
    )
    monkeypatch.setattr(
        flow,
        "_estimate_entities_for_reconfigure",
        AsyncMock(return_value=2),
    )
    monkeypatch.setattr(
        flow,
        "async_update_reload_and_abort",
        AsyncMock(
            return_value={
                "type": FlowResultType.ABORT,
                "reason": "reconfigure_successful",
            }
        ),
        raising=False,
    )

    result = await flow.async_step_reconfigure({"entity_profile": "advanced"})
    assert result["reason"] == "reconfigure_successful"
