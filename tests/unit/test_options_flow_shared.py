"""Unit tests for options flow shared helper methods."""

import pytest

from custom_components.pawcontrol.const import CONF_DOG_ID, CONF_DOG_NAME, CONF_MODULES
from custom_components.pawcontrol.exceptions import FlowValidationError
from custom_components.pawcontrol.options_flow_shared import OptionsFlowSharedMixin


class _SharedHost(OptionsFlowSharedMixin):
    """Minimal host exposing pure shared helper methods."""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, []),
        ("  walk_started  ", ["walk_started"]),
        ("   ", []),
        (["a", "  b  ", 3, ""], ["a", "b", "3"]),
        (("  gps  ", ""), ["gps"]),
        (42, ["42"]),
    ],
)
def test_string_sequence_handles_scalar_sequence_and_none_values(
    value: object,
    expected: list[str],
) -> None:
    """String sequence helper should normalise all supported payload types."""
    assert _SharedHost._string_sequence(value) == expected


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        ("  walk  ", "fallback", "walk"),
        ("   ", "fallback", None),
        (12, "fallback", "fallback"),
        (None, None, None),
    ],
)
def test_coerce_manual_event_with_default_prefers_trimmed_string(
    value: object,
    default: str | None,
    expected: str | None,
) -> None:
    """Manual-event coercion should keep valid strings and fallback otherwise."""
    assert (
        _SharedHost._coerce_manual_event_with_default("  walk  ", "fallback") == "walk"
    )
    assert _SharedHost._coerce_manual_event_with_default("   ", "fallback") is None
    assert _SharedHost._coerce_manual_event_with_default(12, "fallback") == "fallback"
    assert _SharedHost._coerce_manual_event_with_default(None, None) is None


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (FlowValidationError(base_errors=["invalid"]), "dog_invalid"),
        (
            FlowValidationError(field_errors={CONF_MODULES: "dog_invalid_modules"}),
            "dog_invalid_modules",
        ),
        (
            FlowValidationError(field_errors={CONF_DOG_ID: "dog_id_already_exists"}),
            "dog_duplicate",
        ),
        (FlowValidationError(field_errors={CONF_DOG_ID: "missing"}), "dog_missing_id"),
        (FlowValidationError(field_errors={CONF_DOG_NAME: "invalid"}), "dog_invalid"),
        (FlowValidationError(field_errors={}), "dog_invalid"),
        (FlowValidationError(field_errors={"other_field": "any_error"}), "dog_invalid"),
    ],
)
def test_map_import_payload_error_covers_all_branches(
    error: FlowValidationError,
    expected_code: str,
) -> None:
    """Import payload errors should map to deterministic flow error codes."""
    host = _SharedHost()

    assert host._map_import_payload_error(
        FlowValidationError(base_errors=["invalid"])
    ) == ("dog_invalid")
    assert (
        host._map_import_payload_error(
            FlowValidationError(field_errors={CONF_MODULES: "dog_invalid_modules"}),
        )
        == "dog_invalid_modules"
    )
    assert (
        host._map_import_payload_error(
            FlowValidationError(field_errors={CONF_DOG_ID: "dog_id_already_exists"}),
        )
        == "dog_duplicate"
    )
    assert (
        host._map_import_payload_error(
            FlowValidationError(field_errors={CONF_DOG_ID: "missing"}),
        )
        == "dog_missing_id"
    )
    assert (
        host._map_import_payload_error(
            FlowValidationError(field_errors={CONF_DOG_NAME: "invalid"}),
        )
        == "dog_invalid"
    )
    assert host._map_import_payload_error(FlowValidationError(field_errors={})) == (
        "dog_invalid"
    )
