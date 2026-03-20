"""Tests for walk flow helper constants."""

from custom_components.pawcontrol.flows.walk_helpers import WALK_SETTINGS_FIELDS


def test_walk_settings_fields_stay_stable_and_unique() -> None:
    """Walk settings fields should expose the expected ordered configuration keys."""
    assert WALK_SETTINGS_FIELDS == (
        "walk_detection_timeout",
        "minimum_walk_duration",
        "maximum_walk_duration",
        "auto_end_walks",
    )
    assert len(WALK_SETTINGS_FIELDS) == len(set(WALK_SETTINGS_FIELDS))
