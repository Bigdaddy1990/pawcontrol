"""Coverage tests for script manager helpers and option migration paths."""

from dataclasses import dataclass
from types import SimpleNamespace

from custom_components.pawcontrol import script_manager
from custom_components.pawcontrol.const import (
    DEFAULT_RESILIENCE_BREAKER_THRESHOLD,
    DEFAULT_RESILIENCE_SKIP_THRESHOLD,
    DOMAIN,
    RESILIENCE_BREAKER_THRESHOLD_MAX,
)


@dataclass(slots=True)
class _FieldDefault:
    """Minimal script field object exposing ``default`` for extraction."""

    default: object


def _build_entry(**overrides: object) -> SimpleNamespace:
    """Return a light-weight config-entry stub for helper tests."""
    entry = {
        "title": "My Fancy Entry",
        "entry_id": "entry-123",
        "options": {},
        "data": {},
        "runtime_data": {},
    }
    entry.update(overrides)
    return SimpleNamespace(**entry)


def _build_hass(state: object | None = None) -> SimpleNamespace:
    """Return a light-weight Home Assistant stub."""
    states = SimpleNamespace(get=lambda entity_id: state)
    return SimpleNamespace(states=states, data={DOMAIN: {}})


def test_helper_slug_and_event_normalisation_paths() -> None:
    """Helpers should normalise slugs and strip event values predictably."""
    titled = _build_entry(title="Front Door Dog", entry_id="entry-1")
    blank_title = _build_entry(title="   ", entry_id="entry-2")
    no_identity = _build_entry(title="", entry_id="")

    assert script_manager._normalise_entry_slug(titled) == "front-door-dog"
    assert script_manager._normalise_entry_slug(blank_title) == DOMAIN
    assert script_manager._normalise_entry_slug(no_identity) == DOMAIN

    assert script_manager._normalise_manual_event("  paw_event  ") == "paw_event"
    assert script_manager._normalise_manual_event("   ") is None
    assert script_manager._normalise_manual_event(42) is None


def test_parse_manual_resilience_options_and_selection() -> None:
    """Parser helpers should keep valid values and drop invalid payloads."""
    payload = {
        "manual_guard_event": " guard_event ",
        "manual_breaker_event": "breaker_event",
        "resilience_skip_threshold": "6",
        "resilience_breaker_threshold": 9.0,
        "manual_event_history_size": "4",
        "system_settings": {
            "manual_check_event": " check_event ",
            "resilience_skip_threshold": "8",
            "resilience_breaker_threshold": 12,
        },
    }

    options = script_manager._parse_manual_resilience_options(payload)
    assert options == {
        "manual_guard_event": "guard_event",
        "manual_breaker_event": "breaker_event",
        "resilience_skip_threshold": 6,
        "resilience_breaker_threshold": 9,
        "manual_event_history_size": 4,
        "system_settings": {
            "manual_check_event": "check_event",
            "resilience_skip_threshold": 8,
            "resilience_breaker_threshold": 12,
        },
    }

    selection = script_manager._parse_event_selection(
        {
            "manual_guard_event": "",
            "manual_breaker_event": " breaker ",
        }
    )
    assert selection == {
        "manual_guard_event": None,
        "manual_breaker_event": "breaker",
    }


def test_resolve_resilience_script_thresholds_reads_field_defaults() -> None:
    """Script threshold resolution should support mapping and object field types."""
    state = SimpleNamespace(
        attributes={
            "fields": {
                "skip_threshold": {"default": "7"},
                "breaker_threshold": _FieldDefault("11"),
            }
        }
    )
    hass = _build_hass(state)
    entry = _build_entry(title="My Entry", entry_id="entry-script")

    skip, breaker = script_manager.resolve_resilience_script_thresholds(hass, entry)

    assert skip == 7
    assert breaker == 11


def test_ensure_resilience_threshold_options_migrates_legacy_script_defaults() -> None:
    """Migration helper should inject script defaults into system settings."""
    hass = _build_hass(
        SimpleNamespace(
            attributes={
                "fields": {
                    "skip_threshold": {"default": "8"},
                    "breaker_threshold": {"default": "16"},
                }
            }
        )
    )
    entry = _build_entry(
        options={"system_settings": {"manual_guard_event": "guard.custom"}},
    )

    manager = script_manager.PawControlScriptManager(hass, entry)
    migrated = manager.ensure_resilience_threshold_options()

    assert migrated is not None
    assert migrated["system_settings"] == {
        "manual_guard_event": "guard.custom",
        "resilience_skip_threshold": 8,
        "resilience_breaker_threshold": RESILIENCE_BREAKER_THRESHOLD_MAX,
    }
    assert migrated["resilience_skip_threshold"] == 8
    assert migrated["resilience_breaker_threshold"] == RESILIENCE_BREAKER_THRESHOLD_MAX


def test_ensure_resilience_threshold_options_skips_when_already_configured() -> None:
    """Migration should no-op when options already include both thresholds."""
    hass = _build_hass(
        SimpleNamespace(
            attributes={
                "fields": {
                    "skip_threshold": {"default": "99"},
                    "breaker_threshold": {"default": "99"},
                }
            }
        )
    )
    entry = _build_entry(
        options={
            "system_settings": {
                "resilience_skip_threshold": DEFAULT_RESILIENCE_SKIP_THRESHOLD,
                "resilience_breaker_threshold": DEFAULT_RESILIENCE_BREAKER_THRESHOLD,
            }
        }
    )

    manager = script_manager.PawControlScriptManager(hass, entry)

    assert manager.ensure_resilience_threshold_options() is None
