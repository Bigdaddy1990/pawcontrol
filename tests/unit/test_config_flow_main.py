"""Focused regression tests for config_flow_main helper logic."""

from collections.abc import Mapping

from custom_components.pawcontrol.config_flow_main import (
    _LIST_REMOVE_DIRECTIVE,
    PawControlConfigFlow,
)
from custom_components.pawcontrol.const import CONF_MODULES, MODULE_FEEDING, MODULE_GPS
from custom_components.pawcontrol.types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
)


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
