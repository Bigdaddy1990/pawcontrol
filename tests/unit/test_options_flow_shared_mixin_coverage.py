"""Focused branch coverage tests for ``OptionsFlowSharedMixin``."""

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.pawcontrol.const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_DOGS,
    CONF_MODULES,
    CONF_WEATHER_ENTITY,
    DEFAULT_MANUAL_CHECK_EVENT,
)
from custom_components.pawcontrol.exceptions import FlowValidationError
import custom_components.pawcontrol.options_flow_shared as shared_module
from custom_components.pawcontrol.options_flow_shared import (
    ADVANCED_SETTINGS_FIELD,
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    DOG_OPTIONS_FIELD,
    OptionsFlowSharedMixin,
)
from custom_components.pawcontrol.validation import InputCoercionError


class _SharedCoverageHost(OptionsFlowSharedMixin):
    _EXPORT_VERSION = 1

    def __init__(self) -> None:
        self._entry = SimpleNamespace(data={CONF_DOGS: []}, options={})
        self._dogs: list[dict[str, Any]] = []
        self._current_dog: dict[str, Any] | None = None
        self.hass: Any = None
        self._manual_snapshot: Mapping[str, Any] | None = None

    def _clone_options(self) -> dict[str, Any]:
        return dict(self._entry.options)

    def _normalise_options_snapshot(self, options: Mapping[str, Any]) -> dict[str, Any]:
        return dict(options)

    def _current_options(self) -> dict[str, Any]:
        return dict(self._entry.options)

    def _manual_events_snapshot(self) -> Mapping[str, Any] | None:
        return self._manual_snapshot

    def _manual_event_defaults(
        self, current: Mapping[str, Any]
    ) -> dict[str, str | None]:
        return {
            "manual_check_event": current.get(
                "manual_check_event", DEFAULT_MANUAL_CHECK_EVENT
            ),  # type: ignore[dict-item]
            "manual_guard_event": current.get(
                "manual_guard_event", "pawcontrol_manual_guard"
            ),  # type: ignore[dict-item]
            "manual_breaker_event": current.get(
                "manual_breaker_event",
                "pawcontrol_manual_breaker",
            ),  # type: ignore[dict-item]
        }

    def _reconfigure_telemetry(self) -> Mapping[str, Any] | None:
        return None

    def _format_local_timestamp(self, timestamp: str | None) -> str:
        return timestamp or "Never"

    def _summarise_health_summary(self, health: Any) -> str:
        return str(health)

    def _last_reconfigure_timestamp(self) -> str | None:
        return None

    def _resolve_manual_event_choices(self) -> dict[str, list[str]]:
        return {}


def test_build_export_payload_removes_empty_modules_field(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _SharedCoverageHost()
    host._entry.data = {
        CONF_DOGS: [
            {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna", DOG_MODULES_FIELD: {}}
        ]
    }
    monkeypatch.setattr(shared_module, "ensure_dog_modules_mapping", lambda _dog: {})

    payload = host._build_export_payload()

    dog = payload["dogs"][0]
    assert DOG_MODULES_FIELD not in dog


def test_build_export_payload_skips_module_cleanup_when_field_missing(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _SharedCoverageHost()
    host._entry.data = {CONF_DOGS: [{DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"}]}
    monkeypatch.setattr(shared_module, "ensure_dog_modules_mapping", lambda _dog: {})

    payload = host._build_export_payload()
    assert DOG_MODULES_FIELD not in payload["dogs"][0]


def test_weather_dog_options_and_selection_helpers_cover_fallback_branches(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _SharedCoverageHost()
    host._entry.options = {
        "weather_settings": "bad",
        CONF_WEATHER_ENTITY: "  weather.home  ",
    }
    weather = host._current_weather_options()
    assert weather[CONF_WEATHER_ENTITY] == "weather.home"

    host._entry.options = {DOG_OPTIONS_FIELD: "bad"}
    assert host._current_dog_options() == {}

    monkeypatch.setattr(shared_module, "ensure_dog_options_entry", lambda *_a, **_k: {})
    host._entry.options = {DOG_OPTIONS_FIELD: {"dog-1": "bad", "dog-2": {"x": 1}}}
    assert host._current_dog_options() == {}

    host._dogs = [{DOG_ID_FIELD: "dog-1"}, {DOG_ID_FIELD: "dog-2"}]
    host._current_dog = None
    assert host._require_current_dog() is None
    assert host._select_dog_by_id(None) is None


def test_current_weather_options_ignores_blank_root_weather_entity() -> None:  # noqa: D103
    host = _SharedCoverageHost()
    host._entry.options = {"weather_settings": {}, CONF_WEATHER_ENTITY: "   "}

    weather = host._current_weather_options()
    assert CONF_WEATHER_ENTITY not in weather


def test_current_system_and_dashboard_options_support_non_mapping_storage() -> None:  # noqa: D103
    host = _SharedCoverageHost()
    host._entry.options = {
        "system_settings": "bad",
        "dashboard_settings": "bad",
        "enable_analytics": True,
        "enable_cloud_backup": False,
    }

    system = host._current_system_options()
    dashboard = host._current_dashboard_options()

    assert system["enable_analytics"] is True
    assert dashboard == {}


def test_manual_event_context_collects_runtime_suggestions_and_defaults() -> None:  # noqa: D103
    host = _SharedCoverageHost()

    with_events = host._resolve_manual_event_context(
        {},
        manual_snapshot={
            "system_guard_event": "guard_system",
            "system_breaker_event": "breaker_system",
            "configured_check_events": ["check_one"],
            "configured_guard_events": ["guard_one"],
            "configured_breaker_events": ["breaker_one"],
        },
    )
    assert "check_one" in with_events["check_suggestions"]
    assert "guard_system" in with_events["guard_suggestions"]

    with_preferred = host._resolve_manual_event_context(
        {},
        manual_snapshot={
            "configured_check_events": [],
            "preferred_events": {"manual_check_event": "check_preferred"},
            "preferred_check_event": "check_fallback",
        },
    )
    assert with_preferred["check_default"] == "check_preferred"


def test_manual_event_context_without_snapshot_uses_current_defaults_only() -> None:  # noqa: D103
    host = _SharedCoverageHost()
    host._manual_snapshot = None

    context = host._resolve_manual_event_context(
        {
            "manual_guard_event": "guard_current",
            "manual_breaker_event": "breaker_current",
        },
    )
    assert context["guard_default"] == "guard_current"
    assert context["breaker_default"] == "breaker_current"


def test_manual_event_context_prefers_specific_check_event_when_preferred_not_mapping() -> (  # noqa: D103
    None
):
    host = _SharedCoverageHost()

    context = host._resolve_manual_event_context(
        {},
        manual_snapshot={
            "configured_check_events": [],
            "preferred_events": "not-mapping",
            "preferred_check_event": "check_specific",
        },
    )
    assert context["check_default"] == "check_specific"


def test_manual_event_context_skips_normalised_none_entries_in_sequences(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _SharedCoverageHost()
    current = {
        "manual_check_event": "check_current",
        "manual_guard_event": "guard_current",
        "manual_breaker_event": "breaker_current",
    }

    original = host._coerce_manual_event

    def _coerce(value: Any) -> str | None:
        if value == "bad":
            return None
        return original(value)

    monkeypatch.setattr(host, "_coerce_manual_event", _coerce)

    context = host._resolve_manual_event_context(
        current,
        manual_snapshot={
            "configured_check_events": ["bad", "check_valid"],
            "configured_guard_events": ["bad", "guard_valid"],
            "configured_breaker_events": ["bad", "breaker_valid"],
        },
    )
    assert "guard_valid" in context["guard_suggestions"]
    assert "breaker_valid" in context["breaker_suggestions"]


def test_resilience_threshold_helpers_cover_all_fallback_paths() -> None:  # noqa: D103
    host = _SharedCoverageHost()

    assert (
        host._resolve_resilience_threshold_default(
            {"field": 3},
            {},
            field="field",
            fallback=1,
        )
        == 3
    )
    assert (
        host._resolve_resilience_threshold_default(
            {},
            {"field": 4},
            field="field",
            fallback=1,
        )
        == 4
    )
    assert host._resolve_script_threshold_fallbacks(
        has_skip=True, has_breaker=True
    ) == (
        None,
        None,
    )
    assert host._resolve_script_threshold_fallbacks(
        has_skip=False, has_breaker=False
    ) == (
        None,
        None,
    )
    assert (
        host._finalise_resilience_threshold(
            candidate=5,
            default=4,
            script_value=9,
            include_script=True,
            minimum=1,
            maximum=10,
            fallback=2,
        )
        == 9
    )


def test_coercion_helpers_cover_bool_int_time_float_and_choice_fallbacks(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _SharedCoverageHost()

    assert host._coerce_bool(None, True) is True
    assert host._coerce_bool(False, True) is False
    assert host._coerce_bool(" yes ", False) is True
    assert host._coerce_bool(0, True) is False

    assert host._coerce_manual_event("   ") is None
    assert host._coerce_int(None, 7) == 7
    monkeypatch.setattr(
        shared_module,
        "coerce_int",
        lambda *_a, **_k: (_ for _ in ()).throw(InputCoercionError("x", "y", "bad")),
    )
    assert host._coerce_int("bad", 7) == 7

    assert host._coerce_time_string(object(), "08:00:00") == "08:00:00"
    assert host._coerce_optional_float(None, 1.5) == 1.5
    monkeypatch.setattr(
        shared_module,
        "coerce_float",
        lambda *_a, **_k: (_ for _ in ()).throw(InputCoercionError("x", "y", "bad")),
    )
    assert host._coerce_optional_float("bad", 1.5) == 1.5

    assert host._coerce_clamped_float(
        "2.5", 1.0, minimum=0.0, maximum=5.0
    ) == pytest.approx(2.5)
    assert host._normalize_choice("invalid", valid={"a", "b"}, default="invalid") == "a"
    assert host._normalize_choice(5, valid={"a", "b"}, default=1) == "a"


def test_build_weather_settings_uses_current_entity_for_non_string_input() -> None:  # noqa: D103
    host = _SharedCoverageHost()

    weather = host._build_weather_settings(
        {
            "weather_update_interval": 90,
            "notification_threshold": "high",
            "weather_health_monitoring": True,
            "weather_alerts": True,
        },
        {
            CONF_WEATHER_ENTITY: "weather.home",
            "notification_threshold": "moderate",
        },
    )

    assert weather[CONF_WEATHER_ENTITY] == "weather.home"


def test_build_system_settings_manual_event_merge_paths() -> None:  # noqa: D103
    host = _SharedCoverageHost()

    system_with_user_guard_none, _ = host._build_system_settings(
        {
            "manual_guard_event": "   ",
            "manual_breaker_event": "breaker_new",
        },
        {
            "manual_guard_event": "guard_old",
            "manual_breaker_event": "breaker_old",
        },
        reset_default="00:00:00",
    )
    assert system_with_user_guard_none["manual_guard_event"] is None
    assert system_with_user_guard_none["manual_breaker_event"] == "breaker_new"

    system_with_current_defaults, _ = host._build_system_settings(
        {},
        {
            "manual_guard_event": "guard_existing",
            "manual_breaker_event": "breaker_existing",
        },
        reset_default="00:00:00",
    )
    assert system_with_current_defaults["manual_guard_event"] == "guard_existing"
    assert system_with_current_defaults["manual_breaker_event"] == "breaker_existing"

    system_with_blank_current, _ = host._build_system_settings(
        {},
        {
            "manual_guard_event": "   ",
            "manual_breaker_event": "   ",
        },
        reset_default="00:00:00",
    )
    assert system_with_blank_current["manual_guard_event"] == "   "
    assert system_with_blank_current["manual_breaker_event"] == "   "

    system_without_current_keys, _ = host._build_system_settings(
        {},
        {},
        reset_default="00:00:00",
    )
    assert "manual_guard_event" in system_without_current_keys
    assert "manual_breaker_event" in system_without_current_keys


def test_build_advanced_settings_sanitizes_mapping_sequence_and_repr(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    host = _SharedCoverageHost()
    host._entry.options = {ADVANCED_SETTINGS_FIELD: {"persisted": True}}

    monkeypatch.setattr(
        shared_module,
        "ensure_advanced_options",
        lambda source, defaults: dict(source),
    )

    class _Opaque:
        pass

    opaque = _Opaque()
    result = host._build_advanced_settings(
        {
            "map_value": {"a": 1},
            "seq_value": [1, "two"],
            "opaque_value": opaque,
            CONF_MODULES: {"walk": True},
        },
        {CONF_API_ENDPOINT: "https://old", CONF_API_TOKEN: "token-old"},
    )

    assert result["map_value"] == {"a": 1}
    assert result["seq_value"] == [1, "two"]
    assert "opaque_value" in result
    assert CONF_API_ENDPOINT not in result
    assert CONF_API_TOKEN not in result
    assert "non-JSON-serializable value" in caplog.text


def test_manual_and_reconfigure_placeholder_builders_cover_branches(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _SharedCoverageHost()

    monkeypatch.setattr(
        host,
        "_resolve_manual_event_choices",
        lambda: {"check": ["event_a", "event_b"], "guard": []},
    )
    manual = host._manual_event_description_placeholders()
    assert manual["check_options"] == "event_a, event_b"
    assert manual["guard_options"] == "—"

    no_telemetry = host._get_reconfigure_description_placeholders()
    assert no_telemetry["reconfigure_requested_profile"] == "Not recorded"
    assert no_telemetry["reconfigure_merge_notes"] == "No merge adjustments recorded"

    monkeypatch.setattr(
        host,
        "_reconfigure_telemetry",
        lambda: {
            "requested_profile": "advanced",
            "previous_profile": "standard",
            "dogs_count": 2,
            "estimated_entities": 18,
            "compatibility_warnings": ["warn_a", "warn_b"],
            "merge_notes": ["merged one", "merged two"],
            "health_summary": {"healthy": 2},
            "timestamp": "",
        },
    )
    monkeypatch.setattr(
        host,
        "_last_reconfigure_timestamp",
        lambda: "2026-04-18T00:00:00+00:00",
    )
    monkeypatch.setattr(
        host,
        "_format_local_timestamp",
        lambda value: f"TS:{value}" if value else "Never",
    )

    with_telemetry = host._get_reconfigure_description_placeholders()
    assert with_telemetry["last_reconfigure"].startswith("TS:2026-04-18")
    assert with_telemetry["reconfigure_requested_profile"] == "advanced"
    assert with_telemetry["reconfigure_previous_profile"] == "standard"
    assert with_telemetry["reconfigure_entities"] == "18"
    assert with_telemetry["reconfigure_dogs"] == "2"
    assert with_telemetry["reconfigure_warnings"] == "warn_a, warn_b"
    assert with_telemetry["reconfigure_merge_notes"] == "merged one\nmerged two"


def test_build_export_payload_filters_invalid_entries_and_keeps_modules(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _SharedCoverageHost()
    host._entry.options = {"existing": True}
    host._entry.data = {
        CONF_DOGS: [
            123,
            {DOG_ID_FIELD: "", DOG_NAME_FIELD: "Skip"},
            {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna", DOG_MODULES_FIELD: {}},
            {DOG_ID_FIELD: "dog-2", DOG_NAME_FIELD: "Milo", DOG_MODULES_FIELD: {}},
        ],
    }

    def _modules(dog: Mapping[str, Any]) -> dict[str, bool]:
        if dog.get(DOG_ID_FIELD) == "dog-1":
            return {"walk": True}
        return {}

    monkeypatch.setattr(shared_module, "ensure_dog_modules_mapping", _modules)

    payload = host._build_export_payload()

    assert payload["options"]["existing"] is True
    assert [dog[DOG_ID_FIELD] for dog in payload["dogs"]] == ["dog-1", "dog-2"]
    assert payload["dogs"][0][DOG_MODULES_FIELD] == {"walk": True}
    assert DOG_MODULES_FIELD not in payload["dogs"][1]


def test_validate_import_payload_success_and_error_paths(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _SharedCoverageHost()
    host._entry.options = {"existing": "yes"}

    monkeypatch.setattr(
        shared_module,
        "validate_dog_config_payload",
        lambda payload, **_kwargs: {
            DOG_ID_FIELD: str(payload[DOG_ID_FIELD]),
            DOG_NAME_FIELD: str(payload.get(DOG_NAME_FIELD, payload[DOG_ID_FIELD])),
        },
    )

    validated = host._validate_import_payload(
        {
            "version": 1,
            "options": {"new": 1},
            "dogs": [{DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"}],
            "created_at": "",
        },
    )
    assert validated["version"] == 1
    assert validated["options"]["existing"] == "yes"
    assert validated["options"]["new"] == 1
    assert validated["dogs"][0][DOG_ID_FIELD] == "dog-1"
    assert isinstance(validated["created_at"], str)
    assert validated["created_at"]

    with pytest.raises(FlowValidationError) as not_mapping:
        host._validate_import_payload("invalid")
    assert not_mapping.value.field_errors["payload"] == "payload_not_mapping"

    with pytest.raises(FlowValidationError) as bad_version:
        host._validate_import_payload({"version": 2, "options": {}, "dogs": []})
    assert bad_version.value.field_errors["payload"] == "unsupported_version"

    with pytest.raises(FlowValidationError) as missing_options:
        host._validate_import_payload({"version": 1, "options": [], "dogs": []})
    assert missing_options.value.field_errors["payload"] == "options_missing"

    with pytest.raises(FlowValidationError) as dogs_not_list:
        host._validate_import_payload({"version": 1, "options": {}, "dogs": {}})
    assert dogs_not_list.value.field_errors["payload"] == "dogs_invalid"

    with pytest.raises(FlowValidationError) as invalid_dog_payload:
        host._validate_import_payload({"version": 1, "options": {}, "dogs": [1]})
    assert invalid_dog_payload.value.field_errors["payload"] == "dog_invalid"

    monkeypatch.setattr(
        shared_module,
        "validate_dog_config_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FlowValidationError(field_errors={DOG_ID_FIELD: "dog_id_already_exists"})
        ),
    )
    with pytest.raises(FlowValidationError) as mapped_payload_error:
        host._validate_import_payload(
            {
                "version": 1,
                "options": {},
                "dogs": [{DOG_ID_FIELD: "dog-1"}],
            },
        )
    assert mapped_payload_error.value.field_errors["payload"] == "dog_duplicate"


def test_validate_import_payload_preserves_non_empty_created_at(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _SharedCoverageHost()
    monkeypatch.setattr(
        shared_module,
        "validate_dog_config_payload",
        lambda payload, **_kwargs: {
            DOG_ID_FIELD: str(payload[DOG_ID_FIELD]),
            DOG_NAME_FIELD: str(payload.get(DOG_NAME_FIELD, payload[DOG_ID_FIELD])),
        },
    )

    payload = host._validate_import_payload(
        {
            "version": 1,
            "options": {},
            "dogs": [{DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"}],
            "created_at": "2026-04-18T01:02:03+00:00",
        },
    )
    assert payload["created_at"] == "2026-04-18T01:02:03+00:00"


def test_selection_and_system_option_helpers_cover_remaining_branches(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _SharedCoverageHost()
    host._dogs = [{DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"}]
    host._current_dog = None

    required = host._require_current_dog()
    assert required is not None
    assert required[DOG_ID_FIELD] == "dog-1"

    assert host._select_dog_by_id("dog-1") is not None
    assert host._select_dog_by_id("missing") is None

    selector_schema = host._build_dog_selector_schema()
    assert isinstance(selector_schema, shared_module.vol.Schema)

    host._entry.options = {
        "system_settings": {},
        "enable_analytics": True,
        "enable_cloud_backup": False,
    }
    system = host._current_system_options()
    assert system["enable_analytics"] is True
    assert system["enable_cloud_backup"] is False

    host.hass = object()
    monkeypatch.setattr(
        shared_module,
        "resolve_resilience_script_thresholds",
        lambda _hass, _entry: (11, 22),
    )
    assert host._resolve_script_threshold_fallbacks(has_skip=False, has_breaker=True) == (
        11,
        22,
    )

    host._entry.options = {"dashboard_settings": {"show_alerts": False}}
    assert host._current_dashboard_options()["show_alerts"] is False

    monkeypatch.setattr(
        shared_module,
        "ensure_advanced_options",
        lambda source, defaults: {"source": dict(source), "defaults": dict(defaults)},
    )
    host._entry.options = {ADVANCED_SETTINGS_FIELD: {"api": "x"}, "root_flag": True}
    advanced = host._current_advanced_options()
    assert advanced["source"] == {"api": "x"}
    assert advanced["defaults"]["root_flag"] is True

    class _IsoValue:
        def isoformat(self) -> str:
            return "09:15:00"

    assert host._coerce_time_string(_IsoValue(), "00:00:00") == "09:15:00"
    assert host._normalize_choice("ignored", valid={"a", "b"}, default="b") == "b"


def test_current_option_helpers_cover_remaining_fast_paths(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _SharedCoverageHost()

    host._entry.options = {
        "weather_settings": {CONF_WEATHER_ENTITY: "weather.preserved"},
        CONF_WEATHER_ENTITY: "weather.root",
    }
    weather = host._current_weather_options()
    assert weather[CONF_WEATHER_ENTITY] == "weather.preserved"

    monkeypatch.setattr(
        shared_module,
        "ensure_dog_options_entry",
        lambda value, dog_id: {DOG_ID_FIELD: dog_id, **dict(value)},
    )
    host._entry.options = {DOG_OPTIONS_FIELD: {"dog-1": {"sample": 1}}}
    dog_options = host._current_dog_options()
    assert dog_options["dog-1"][DOG_ID_FIELD] == "dog-1"

    host._current_dog = {DOG_ID_FIELD: "dog-1", DOG_NAME_FIELD: "Luna"}
    assert host._require_current_dog()[DOG_ID_FIELD] == "dog-1"  # type: ignore[index]

    host._entry.options = {
        "system_settings": {
            "enable_analytics": False,
            "enable_cloud_backup": True,
        },
        "enable_analytics": True,
        "enable_cloud_backup": False,
    }
    system = host._current_system_options()
    assert system["enable_analytics"] is False
    assert system["enable_cloud_backup"] is True

    assert host._coerce_time_string("08:00:00", "00:00:00") == "08:00:00"


def test_build_weather_system_dashboard_and_advanced_cover_extra_paths(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _SharedCoverageHost()

    weather = host._build_weather_settings(
        {
            "weather_entity": " none ",
            "weather_update_interval": 45,
            "notification_threshold": "invalid",
        },
        {
            "notification_threshold": "moderate",
            "weather_health_monitoring": True,
            "weather_alerts": True,
        },
    )
    assert weather[CONF_WEATHER_ENTITY] is None

    system, _reset_time = host._build_system_settings(
        {
            "manual_guard_event": "guard_now",
            "manual_breaker_event": "   ",
        },
        {
            "manual_guard_event": "guard_old",
            "manual_breaker_event": "breaker_old",
        },
        reset_default="00:00:00",
    )
    assert system["manual_guard_event"] == "guard_now"
    assert system["manual_breaker_event"] is None

    dashboard, mode = host._build_dashboard_settings(
        {
            "dashboard_mode": "compact",
            "show_statistics": False,
            "show_alerts": True,
            "compact_mode": True,
            "show_maps": False,
        },
        {
            "show_statistics": True,
            "show_alerts": False,
            "compact_mode": False,
            "show_maps": True,
        },
        default_mode="full",
    )
    assert mode in {"full", "compact", "minimal"}
    assert dashboard["compact_mode"] is True

    monkeypatch.setattr(
        shared_module,
        "ensure_advanced_options",
        lambda source, defaults: dict(source) | {"_defaults": dict(defaults)},
    )
    host._entry.options = {ADVANCED_SETTINGS_FIELD: {"persisted": "yes"}}
    advanced = host._build_advanced_settings(
        {
            CONF_API_ENDPOINT: " https://api.example.test ",
            CONF_API_TOKEN: " token-value ",
            "simple": 1,
        },
        {CONF_API_ENDPOINT: "old", CONF_API_TOKEN: "old"},
    )
    assert advanced[CONF_API_ENDPOINT] == "https://api.example.test"
    assert advanced[CONF_API_TOKEN] == "token-value"
    assert advanced["simple"] == 1
