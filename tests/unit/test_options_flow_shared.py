"""Unit tests for options flow shared helper methods."""

from custom_components.pawcontrol.const import CONF_DOG_ID, CONF_DOG_NAME, CONF_MODULES
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.options_flow_shared import OptionsFlowSharedMixin


class _SharedHost(OptionsFlowSharedMixin):
    """Minimal host exposing pure shared helper methods."""


def test_string_sequence_handles_scalar_sequence_and_none_values() -> None:
    """String sequence helper should normalise all supported payload types."""
    assert _SharedHost._string_sequence(None) == []
    assert _SharedHost._string_sequence("  walk_started  ") == ["walk_started"]
    assert _SharedHost._string_sequence("   ") == []
    assert _SharedHost._string_sequence(["a", "  b  ", 3, ""]) == ["a", "b", "3"]
    assert _SharedHost._string_sequence(("  gps  ", "")) == ["gps"]
    assert _SharedHost._string_sequence(42) == ["42"]


def test_coerce_manual_event_with_default_prefers_trimmed_string() -> None:
    """Manual-event coercion should keep valid strings and fallback otherwise."""
    assert (
        _SharedHost._coerce_manual_event_with_default("  walk  ", "fallback")
        == "walk"
    )
    assert _SharedHost._coerce_manual_event_with_default("   ", "fallback") is None
    assert _SharedHost._coerce_manual_event_with_default(12, "fallback") == "fallback"
    assert _SharedHost._coerce_manual_event_with_default(None, None) is None


def test_map_import_payload_error_covers_all_branches() -> None:
    """Import payload errors should map to deterministic flow error codes."""
    host = _SharedHost()

    assert host._map_import_payload_error(FlowValidationError(base_errors=["invalid"])) == (
        "dog_invalid"
    )
    assert host._map_import_payload_error(
        FlowValidationError(field_errors={CONF_MODULES: "dog_invalid_modules"}),
    ) == "dog_invalid_modules"
    assert host._map_import_payload_error(
        FlowValidationError(field_errors={CONF_DOG_ID: "dog_id_already_exists"}),
    ) == "dog_duplicate"
    assert host._map_import_payload_error(
        FlowValidationError(field_errors={CONF_DOG_ID: "missing"}),
    ) == "dog_missing_id"
    assert host._map_import_payload_error(
        FlowValidationError(field_errors={CONF_DOG_NAME: "invalid"}),
    ) == "dog_invalid"
    assert host._map_import_payload_error(FlowValidationError(field_errors={})) == (
        "dog_invalid"
    )
