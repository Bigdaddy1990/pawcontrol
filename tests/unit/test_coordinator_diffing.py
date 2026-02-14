"""Unit tests for coordinator_diffing module.

Tests smart diffing and data change detection including diff computation,
module-level tracking, and entity update minimization.
"""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.coordinator_diffing import compute_coordinator_diff
from custom_components.pawcontrol.coordinator_diffing import compute_data_diff
from custom_components.pawcontrol.coordinator_diffing import compute_dog_diff
from custom_components.pawcontrol.coordinator_diffing import CoordinatorDataDiff
from custom_components.pawcontrol.coordinator_diffing import DataDiff
from custom_components.pawcontrol.coordinator_diffing import DogDataDiff
from custom_components.pawcontrol.coordinator_diffing import get_changed_fields
from custom_components.pawcontrol.coordinator_diffing import log_diff_summary
from custom_components.pawcontrol.coordinator_diffing import should_notify_entities
from custom_components.pawcontrol.coordinator_diffing import SmartDiffTracker


class TestDataDiff:
  """Test DataDiff dataclass."""

  def test_data_diff_has_changes(self) -> None:
    """Test has_changes property."""
    # No changes
    diff = DataDiff()
    assert diff.has_changes is False

    # Has changes
    diff = DataDiff(added_keys=frozenset({"key1"}))
    assert diff.has_changes is True

  def test_data_diff_change_count(self) -> None:
    """Test change_count property."""
    diff = DataDiff(
      added_keys=frozenset({"a", "b"}),
      removed_keys=frozenset({"c"}),
      modified_keys=frozenset({"d", "e", "f"}),
    )
    assert diff.change_count == 6

  def test_data_diff_changed_keys(self) -> None:
    """Test changed_keys property."""
    diff = DataDiff(
      added_keys=frozenset({"a"}),
      removed_keys=frozenset({"b"}),
      modified_keys=frozenset({"c"}),
    )
    assert diff.changed_keys == frozenset({"a", "b", "c"})

  def test_data_diff_to_dict(self) -> None:
    """Test to_dict serialization."""
    diff = DataDiff(
      added_keys=frozenset({"a"}),
      removed_keys=frozenset({"b"}),
      modified_keys=frozenset({"c"}),
      unchanged_keys=frozenset({"d"}),
    )

    result = diff.to_dict()
    assert result["added"] == ["a"]
    assert result["removed"] == ["b"]
    assert result["modified"] == ["c"]
    assert result["unchanged"] == ["d"]
    assert result["has_changes"] is True
    assert result["change_count"] == 3


class TestDogDataDiff:
  """Test DogDataDiff dataclass."""

  def test_dog_data_diff_has_changes(self) -> None:
    """Test has_changes property."""
    # No changes
    diff = DogDataDiff("buddy")
    assert diff.has_changes is False

    # Has changes in module
    diff = DogDataDiff(
      "buddy",
      module_diffs={"gps": DataDiff(modified_keys=frozenset({"lat"}))},
    )
    assert diff.has_changes is True

  def test_dog_data_diff_changed_modules(self) -> None:
    """Test changed_modules property."""
    diff = DogDataDiff(
      "buddy",
      module_diffs={
        "gps": DataDiff(modified_keys=frozenset({"lat"})),
        "walk": DataDiff(modified_keys=frozenset({"distance"})),
        "feeding": DataDiff(),  # No changes
      },
    )

    assert diff.changed_modules == frozenset({"gps", "walk"})

  def test_dog_data_diff_to_dict(self) -> None:
    """Test to_dict serialization."""
    diff = DogDataDiff(
      "buddy",
      module_diffs={"gps": DataDiff(modified_keys=frozenset({"lat"}))},
    )

    result = diff.to_dict()
    assert result["dog_id"] == "buddy"
    assert result["has_changes"] is True
    assert "changed_modules" in result
    assert "module_diffs" in result


class TestCoordinatorDataDiff:
  """Test CoordinatorDataDiff dataclass."""

  def test_coordinator_data_diff_has_changes(self) -> None:
    """Test has_changes property."""
    # No changes
    diff = CoordinatorDataDiff()
    assert diff.has_changes is False

    # Dogs added
    diff = CoordinatorDataDiff(added_dogs=frozenset({"new_dog"}))
    assert diff.has_changes is True

    # Dog data changed
    diff = CoordinatorDataDiff(
      dog_diffs={
        "buddy": DogDataDiff(
          "buddy",
          module_diffs={"gps": DataDiff(modified_keys=frozenset({"lat"}))},
        )
      }
    )
    assert diff.has_changes is True

  def test_coordinator_data_diff_changed_dogs(self) -> None:
    """Test changed_dogs property."""
    diff = CoordinatorDataDiff(
      dog_diffs={
        "buddy": DogDataDiff(
          "buddy",
          module_diffs={"gps": DataDiff(modified_keys=frozenset({"lat"}))},
        ),
        "max": DogDataDiff("max"),  # No changes
      },
      added_dogs=frozenset({"charlie"}),
      removed_dogs=frozenset({"old_dog"}),
    )

    changed = diff.changed_dogs
    assert "buddy" in changed
    assert "charlie" in changed
    assert "old_dog" in changed
    assert "max" not in changed


class TestComputeDataDiff:
  """Test compute_data_diff function."""

  def test_compute_data_diff_basic(self) -> None:
    """Test basic diff computation."""
    old = {"a": 1, "b": 2}
    new = {"b": 3, "c": 4}

    diff = compute_data_diff(old, new)

    assert diff.added_keys == frozenset({"c"})
    assert diff.removed_keys == frozenset({"a"})
    assert diff.modified_keys == frozenset({"b"})

  def test_compute_data_diff_no_changes(self) -> None:
    """Test diff with no changes."""
    old = {"a": 1, "b": 2}
    new = {"a": 1, "b": 2}

    diff = compute_data_diff(old, new)

    assert not diff.has_changes
    assert diff.unchanged_keys == frozenset({"a", "b"})

  def test_compute_data_diff_nested_structures(self) -> None:
    """Test diff with nested dictionaries."""
    old = {"gps": {"lat": 45.0, "lon": -122.0}}
    new = {"gps": {"lat": 45.1, "lon": -122.0}}

    diff = compute_data_diff(old, new)

    assert diff.modified_keys == frozenset({"gps"})

  def test_compute_data_diff_lists(self) -> None:
    """Test diff with lists."""
    old = {"items": [1, 2, 3]}
    new = {"items": [1, 2, 4]}

    diff = compute_data_diff(old, new)

    assert diff.modified_keys == frozenset({"items"})

  def test_compute_data_diff_none_values(self) -> None:
    """Test diff with None old_data or new_data."""
    new = {"a": 1}

    diff = compute_data_diff(None, new)
    assert diff.added_keys == frozenset({"a"})

    old = {"a": 1}
    diff = compute_data_diff(old, None)
    assert diff.removed_keys == frozenset({"a"})


class TestComputeDogDiff:
  """Test compute_dog_diff function."""

  def test_compute_dog_diff_basic(self) -> None:
    """Test basic dog diff computation."""
    old = {"gps": {"lat": 45.0}, "walk": {"active": False}}
    new = {"gps": {"lat": 45.1}, "walk": {"active": False}}

    diff = compute_dog_diff("buddy", old, new)

    assert diff.dog_id == "buddy"
    assert "gps" in diff.changed_modules
    assert "walk" not in diff.changed_modules

  def test_compute_dog_diff_module_added(self) -> None:
    """Test dog diff with module added."""
    old = {"gps": {"lat": 45.0}}
    new = {"gps": {"lat": 45.0}, "walk": {"active": True}}

    diff = compute_dog_diff("buddy", old, new)

    assert "walk" in diff.changed_modules

  def test_compute_dog_diff_module_removed(self) -> None:
    """Test dog diff with module removed."""
    old = {"gps": {"lat": 45.0}, "walk": {"active": True}}
    new = {"gps": {"lat": 45.0}}

    diff = compute_dog_diff("buddy", old, new)

    assert "walk" in diff.changed_modules


class TestComputeCoordinatorDiff:
  """Test compute_coordinator_diff function."""

  def test_compute_coordinator_diff_basic(self) -> None:
    """Test basic coordinator diff."""
    old = {"buddy": {"gps": {"lat": 45.0}}}
    new = {"buddy": {"gps": {"lat": 45.1}}, "max": {"gps": {"lat": 46.0}}}

    diff = compute_coordinator_diff(old, new)

    assert diff.added_dogs == frozenset({"max"})
    assert "buddy" in diff.changed_dogs
    assert "max" in diff.changed_dogs

  def test_compute_coordinator_diff_dog_removed(self) -> None:
    """Test coordinator diff with dog removed."""
    old = {"buddy": {}, "max": {}}
    new = {"buddy": {}}

    diff = compute_coordinator_diff(old, new)

    assert diff.removed_dogs == frozenset({"max"})

  def test_compute_coordinator_diff_no_changes(self) -> None:
    """Test coordinator diff with no changes."""
    old = {"buddy": {"gps": {"lat": 45.0}}}
    new = {"buddy": {"gps": {"lat": 45.0}}}

    diff = compute_coordinator_diff(old, new)

    assert not diff.has_changes


class TestShouldNotifyEntities:
  """Test should_notify_entities function."""

  def test_should_notify_entities_no_changes(self) -> None:
    """Test notification with no changes."""
    diff = CoordinatorDataDiff()
    assert should_notify_entities(diff) is False

  def test_should_notify_entities_any_changes(self) -> None:
    """Test notification with any changes."""
    diff = CoordinatorDataDiff(added_dogs=frozenset({"new_dog"}))
    assert should_notify_entities(diff) is True

  def test_should_notify_entities_specific_dog(self) -> None:
    """Test notification for specific dog."""
    diff = CoordinatorDataDiff(
      dog_diffs={
        "buddy": DogDataDiff(
          "buddy",
          module_diffs={"gps": DataDiff(modified_keys=frozenset({"lat"}))},
        )
      }
    )

    assert should_notify_entities(diff, dog_id="buddy") is True
    assert should_notify_entities(diff, dog_id="max") is False

  def test_should_notify_entities_specific_module(self) -> None:
    """Test notification for specific module."""
    diff = CoordinatorDataDiff(
      dog_diffs={
        "buddy": DogDataDiff(
          "buddy",
          module_diffs={"gps": DataDiff(modified_keys=frozenset({"lat"}))},
        )
      }
    )

    assert should_notify_entities(diff, dog_id="buddy", module="gps") is True
    assert should_notify_entities(diff, dog_id="buddy", module="walk") is False


class TestSmartDiffTracker:
  """Test SmartDiffTracker class."""

  def test_smart_diff_tracker_initialization(self) -> None:
    """Test tracker initialization."""
    tracker = SmartDiffTracker()
    assert tracker.last_diff is None
    assert tracker.update_count == 0

  def test_smart_diff_tracker_update(self) -> None:
    """Test tracker update."""
    tracker = SmartDiffTracker()

    data1 = {"buddy": {"gps": {"lat": 45.0}}}
    diff1 = tracker.update(data1)

    assert tracker.update_count == 1
    assert tracker.last_diff == diff1

  def test_smart_diff_tracker_incremental(self) -> None:
    """Test tracker with incremental updates."""
    tracker = SmartDiffTracker()

    data1 = {"buddy": {"gps": {"lat": 45.0}}}
    diff1 = tracker.update(data1)
    assert not diff1.has_changes  # First update always has no changes

    data2 = {"buddy": {"gps": {"lat": 45.1}}}
    diff2 = tracker.update(data2)
    assert diff2.has_changes
    assert "buddy" in diff2.changed_dogs

  def test_smart_diff_tracker_reset(self) -> None:
    """Test tracker reset."""
    tracker = SmartDiffTracker()

    tracker.update({"buddy": {"gps": {"lat": 45.0}}})
    tracker.reset()

    assert tracker.last_diff is None
    assert tracker.update_count == 0

  def test_smart_diff_tracker_get_changed_entities(self) -> None:
    """Test get_changed_entities method."""
    tracker = SmartDiffTracker()

    tracker.update({"buddy": {"gps": {"lat": 45.0}}})
    data2 = {"buddy": {"gps": {"lat": 45.1}}}
    tracker.update(data2)

    changed = tracker.get_changed_entities(dog_id="buddy", module="gps")
    assert "buddy.gps" in changed


class TestGetChangedFields:
  """Test get_changed_fields function."""

  def test_get_changed_fields_default(self) -> None:
    """Test getting changed fields with defaults."""
    diff = DataDiff(
      added_keys=frozenset({"x"}),
      modified_keys=frozenset({"y"}),
      removed_keys=frozenset({"z"}),
    )

    fields = get_changed_fields(diff)
    assert fields == frozenset({"x", "y"})

  def test_get_changed_fields_all(self) -> None:
    """Test getting all changed fields."""
    diff = DataDiff(
      added_keys=frozenset({"x"}),
      modified_keys=frozenset({"y"}),
      removed_keys=frozenset({"z"}),
    )

    fields = get_changed_fields(
      diff,
      include_added=True,
      include_modified=True,
      include_removed=True,
    )
    assert fields == frozenset({"x", "y", "z"})

  def test_get_changed_fields_only_added(self) -> None:
    """Test getting only added fields."""
    diff = DataDiff(
      added_keys=frozenset({"x"}),
      modified_keys=frozenset({"y"}),
    )

    fields = get_changed_fields(
      diff,
      include_added=True,
      include_modified=False,
    )
    assert fields == frozenset({"x"})


class TestLogDiffSummary:
  """Test log_diff_summary function."""

  def test_log_diff_summary_no_changes(self, caplog: pytest.LogCaptureFixture) -> None:
    """Test logging with no changes."""
    diff = CoordinatorDataDiff()
    log_diff_summary(diff)

    assert "No changes detected" in caplog.text

  def test_log_diff_summary_with_changes(
    self, caplog: pytest.LogCaptureFixture
  ) -> None:
    """Test logging with changes."""
    diff = CoordinatorDataDiff(
      dog_diffs={
        "buddy": DogDataDiff(
          "buddy",
          module_diffs={"gps": DataDiff(modified_keys=frozenset({"lat"}))},
        )
      }
    )

    log_diff_summary(diff)
    assert "1 dogs changed" in caplog.text


class TestEdgeCases:
  """Test edge cases and error conditions."""

  def test_compute_data_diff_empty_dicts(self) -> None:
    """Test diff with empty dictionaries."""
    diff = compute_data_diff({}, {})
    assert not diff.has_changes

  def test_compute_dog_diff_empty_data(self) -> None:
    """Test dog diff with empty data."""
    diff = compute_dog_diff("buddy", {}, {})
    assert not diff.has_changes

  def test_smart_diff_tracker_multiple_resets(self) -> None:
    """Test tracker with multiple resets."""
    tracker = SmartDiffTracker()

    tracker.update({"buddy": {}})
    tracker.reset()
    tracker.reset()  # Double reset

    assert tracker.update_count == 0

  def test_should_notify_entities_added_dog_with_module_filter(self) -> None:
    """Test notification for added dog with module filter."""
    diff = CoordinatorDataDiff(added_dogs=frozenset({"new_dog"}))

    # Should notify regardless of module filter for added dogs
    assert should_notify_entities(diff, dog_id="new_dog", module="gps") is True

  def test_coordinator_diff_serialization(self) -> None:
    """Test full coordinator diff serialization."""
    diff = CoordinatorDataDiff(
      dog_diffs={
        "buddy": DogDataDiff(
          "buddy",
          module_diffs={"gps": DataDiff(modified_keys=frozenset({"lat"}))},
        )
      },
      added_dogs=frozenset({"new_dog"}),
    )

    serialized = diff.to_dict()
    assert "has_changes" in serialized
    assert "changed_dogs" in serialized
    assert "added_dogs" in serialized
    assert "dog_diffs" in serialized
