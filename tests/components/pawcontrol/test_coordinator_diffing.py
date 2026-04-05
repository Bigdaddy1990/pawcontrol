"""Tests for coordinator diffing helpers."""

from __future__ import annotations

import logging

from custom_components.pawcontrol.coordinator_diffing import (
    CoordinatorDataDiff,
    DataDiff,
    SmartDiffTracker,
    compute_coordinator_diff,
    compute_data_diff,
    compute_dog_diff,
    get_changed_fields,
    log_diff_summary,
    should_notify_entities,
)


def test_compute_data_diff_handles_none_and_type_changes() -> None:
    """Diffing should normalize None and detect modified keys by type/value."""
    diff = compute_data_diff(
        {"same": 1, "typed": "5", "gone": {"a": 1}},
        {"same": 1, "typed": 5, "new": {"b": 2}},
    )

    assert diff.added_keys == frozenset({"new"})
    assert diff.removed_keys == frozenset({"gone"})
    assert diff.modified_keys == frozenset({"typed"})
    assert diff.unchanged_keys == frozenset({"same"})
    assert diff.has_changes is True
    assert diff.change_count == 3
    assert diff.changed_keys == frozenset({"new", "gone", "typed"})

    empty_diff = compute_data_diff(None, None)
    assert empty_diff.has_changes is False
    assert empty_diff.to_dict()["change_count"] == 0


def test_compute_dog_diff_covers_module_added_removed_mapping_and_scalar() -> None:
    """Dog diff should classify mapping/scalar additions, removals, and updates."""
    old_dog = {
        "gps": {"lat": 50.0, "lon": 8.0},
        "status": "idle",
        "legacy": {"flag": True},
        "score": 4,
    }
    new_dog = {
        "gps": {"lat": 50.1, "lon": 8.0},
        "status": "running",
        "battery": {"level": 80},
        "score": 4,
    }

    diff = compute_dog_diff("buddy", old_dog, new_dog)

    assert diff.has_changes is True
    assert diff.changed_modules == frozenset({"gps", "status", "legacy", "battery"})
    assert diff.module_diffs["gps"].modified_keys == frozenset({"lat"})
    assert diff.module_diffs["battery"].added_keys == frozenset({"level"})
    assert diff.module_diffs["legacy"].removed_keys == frozenset({"flag"})
    assert diff.module_diffs["status"].modified_keys == frozenset({"status"})
    assert diff.overall_diff.modified_keys == frozenset({"gps", "status"})


def test_compute_coordinator_diff_and_notifications() -> None:
    """Coordinator diff should expose change metadata and notification filters."""
    old_data = {
        "buddy": {"gps": {"lat": 1.0}, "walk": {"active": False}},
        "max": {"gps": {"lat": 2.0}},
    }
    new_data = {
        "buddy": {"gps": {"lat": 1.1}, "walk": {"active": False}},
        "newdog": {"gps": {"lat": 5.0}},
    }

    diff = compute_coordinator_diff(old_data, new_data)

    assert diff.has_changes is True
    assert diff.added_dogs == frozenset({"newdog"})
    assert diff.removed_dogs == frozenset({"max"})
    assert diff.changed_dogs == frozenset({"buddy", "newdog", "max"})
    assert diff.change_count == 3

    assert should_notify_entities(diff) is True
    assert should_notify_entities(diff, dog_id="newdog") is True
    assert should_notify_entities(diff, dog_id="max") is True
    assert should_notify_entities(diff, dog_id="buddy", module="gps") is True
    assert should_notify_entities(diff, dog_id="buddy", module="walk") is False
    assert should_notify_entities(diff, dog_id="unknown") is False
    assert should_notify_entities(diff, module="gps") is True
    assert should_notify_entities(diff, module="feeding") is False

    no_change = CoordinatorDataDiff()
    assert should_notify_entities(no_change) is False


def test_smart_diff_tracker_update_reset_and_changed_entities() -> None:
    """SmartDiffTracker should keep last diff and expose filtered entity keys."""
    tracker = SmartDiffTracker()

    first = tracker.update({"buddy": {"gps": {"lat": 1.0}}})
    assert tracker.update_count == 1
    assert tracker.last_diff == first
    assert tracker.get_changed_entities(first) == frozenset({"buddy"})
    assert tracker.get_changed_entities(
        first, dog_id="buddy", module="gps"
    ) == frozenset({"buddy.gps"})

    second = tracker.update({
        "buddy": {"gps": {"lat": 1.2}, "walk": {"active": True}},
        "newdog": {"gps": {"lat": 2.0}},
    })
    assert tracker.update_count == 2
    assert tracker.get_changed_entities(second) == frozenset({
        "buddy.gps",
        "buddy.walk",
        "newdog",
    })
    assert tracker.get_changed_entities(second, dog_id="buddy") == frozenset({
        "buddy.gps",
        "buddy.walk",
    })
    assert tracker.get_changed_entities(second, module="gps") == frozenset({
        "buddy.gps",
        "newdog.gps",
    })
    assert tracker.get_changed_entities(
        second, dog_id="newdog", module="gps"
    ) == frozenset({"newdog.gps"})

    tracker.reset()
    assert tracker.last_diff is None
    assert tracker.update_count == 0
    assert tracker.get_changed_entities() == frozenset()


def test_get_changed_fields_and_log_diff_summary(caplog) -> None:
    """Changed fields helper and logging summary should honor filters and messages."""
    data_diff = DataDiff(
        added_keys=frozenset({"added"}),
        modified_keys=frozenset({"mod"}),
        removed_keys=frozenset({"gone"}),
    )
    assert get_changed_fields(data_diff) == frozenset({"added", "mod"})
    assert get_changed_fields(
        data_diff,
        include_added=False,
        include_modified=True,
        include_removed=True,
    ) == frozenset({"mod", "gone"})

    with caplog.at_level(logging.DEBUG):
        log_diff_summary(CoordinatorDataDiff())
    assert "No changes detected" in caplog.text

    diff = compute_coordinator_diff(
        {"buddy": {"gps": {"lat": 1.0}}, "max": {"walk": {"active": True}}},
        {"buddy": {"gps": {"lat": 1.1}}, "newdog": {"walk": {"active": True}}},
    )
    logger = logging.getLogger("tests.coordinator_diffing")
    with caplog.at_level(logging.DEBUG, logger=logger.name):
        log_diff_summary(diff, logger)
    assert "dogs changed" in caplog.text
    assert "added" in caplog.text
    assert "removed" in caplog.text
    assert "gps" in caplog.text
