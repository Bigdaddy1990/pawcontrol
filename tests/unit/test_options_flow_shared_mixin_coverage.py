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
