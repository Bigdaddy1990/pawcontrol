"""Smart diffing and data change detection for PawControl coordinator.

This module provides utilities for minimizing unnecessary entity updates by
detecting meaningful data changes and notifying only affected entities.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from collections.abc import Set
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import TypeVar

from .types import CoordinatorDataPayload
from .types import CoordinatorDogData

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class DataDiff:
  """Represents changes between two data snapshots.

  Attributes:
      added_keys: Keys present in new data but not old
      removed_keys: Keys present in old data but not new
      modified_keys: Keys present in both with different values
      unchanged_keys: Keys present in both with same values
  """

  added_keys: frozenset[str] = field(default_factory=frozenset)
  removed_keys: frozenset[str] = field(default_factory=frozenset)
  modified_keys: frozenset[str] = field(default_factory=frozenset)
  unchanged_keys: frozenset[str] = field(default_factory=frozenset)

  @property
  def has_changes(self) -> bool:
    """Return True if there are any changes."""
    return bool(self.added_keys or self.removed_keys or self.modified_keys)

  @property
  def change_count(self) -> int:
    """Return total number of changes."""
    return len(self.added_keys) + len(self.removed_keys) + len(self.modified_keys)

  @property
  def changed_keys(self) -> frozenset[str]:
    """Return all keys that changed (added, removed, or modified)."""
    return self.added_keys | self.removed_keys | self.modified_keys

  def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary for serialization."""
    return {
      "added": sorted(self.added_keys),
      "removed": sorted(self.removed_keys),
      "modified": sorted(self.modified_keys),
      "unchanged": sorted(self.unchanged_keys),
      "has_changes": self.has_changes,
      "change_count": self.change_count,
    }


@dataclass(frozen=True)
class DogDataDiff:
  """Represents changes for a specific dog.

  Attributes:
      dog_id: Dog identifier
      module_diffs: Per-module change information
      overall_diff: Summary of top-level changes
  """

  dog_id: str
  module_diffs: Mapping[str, DataDiff] = field(default_factory=dict)
  overall_diff: DataDiff = field(default_factory=DataDiff)

  @property
  def has_changes(self) -> bool:
    """Return True if there are any changes."""
    return any(diff.has_changes for diff in self.module_diffs.values())

  @property
  def changed_modules(self) -> frozenset[str]:
    """Return modules that have changes."""
    return frozenset(
      module for module, diff in self.module_diffs.items() if diff.has_changes
    )

  def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary for serialization."""
    return {
      "dog_id": self.dog_id,
      "has_changes": self.has_changes,
      "changed_modules": sorted(self.changed_modules),
      "module_diffs": {
        module: diff.to_dict() for module, diff in self.module_diffs.items()
      },
      "overall_diff": self.overall_diff.to_dict(),
    }


@dataclass(frozen=True)
class CoordinatorDataDiff:
  """Represents changes across all coordinator data.

  Attributes:
      dog_diffs: Per-dog change information
      added_dogs: Dog IDs added in new data
      removed_dogs: Dog IDs removed from old data
  """

  dog_diffs: Mapping[str, DogDataDiff] = field(default_factory=dict)
  added_dogs: frozenset[str] = field(default_factory=frozenset)
  removed_dogs: frozenset[str] = field(default_factory=frozenset)

  @property
  def has_changes(self) -> bool:
    """Return True if there are any changes."""
    return bool(
      self.added_dogs
      or self.removed_dogs
      or any(diff.has_changes for diff in self.dog_diffs.values())
    )

  @property
  def changed_dogs(self) -> frozenset[str]:
    """Return dog IDs that have changes."""
    changed = frozenset(
      dog_id for dog_id, diff in self.dog_diffs.items() if diff.has_changes
    )
    return changed | self.added_dogs | self.removed_dogs

  def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary for serialization."""
    return {
      "has_changes": self.has_changes,
      "changed_dogs": sorted(self.changed_dogs),
      "added_dogs": sorted(self.added_dogs),
      "removed_dogs": sorted(self.removed_dogs),
      "dog_diffs": {dog_id: diff.to_dict() for dog_id, diff in self.dog_diffs.items()},
    }


def _compare_values(old_value: Any, new_value: Any) -> bool:
  """Compare two values for equality, handling nested structures.

  Args:
      old_value: Old value
      new_value: New value

  Returns:
      True if values are equal, False otherwise
  """
  # Fast path for identical objects
  if old_value is new_value:
    return True

  # Handle None
  if old_value is None or new_value is None:
    return old_value == new_value

  # Handle different types
  if type(old_value) is not type(new_value):
    return False

  # Handle mappings recursively
  if isinstance(old_value, Mapping) and isinstance(new_value, Mapping):
    if old_value.keys() != new_value.keys():
      return False
    return all(_compare_values(old_value[k], new_value[k]) for k in old_value)

  # Handle sequences recursively (but not strings)
  if isinstance(old_value, (list, tuple)) and isinstance(new_value, (list, tuple)):
    if len(old_value) != len(new_value):
      return False
    return all(
      _compare_values(o, n) for o, n in zip(old_value, new_value, strict=False)
    )

  # Default equality
  return old_value == new_value


def compute_data_diff(
  old_data: Mapping[str, Any] | None,
  new_data: Mapping[str, Any] | None,
) -> DataDiff:
  """Compute differences between two data dictionaries.

  Args:
      old_data: Previous data snapshot
      new_data: New data snapshot

  Returns:
      DataDiff describing changes

  Examples:
      >>> old = {"a": 1, "b": 2}
      >>> new = {"b": 3, "c": 4}
      >>> diff = compute_data_diff(old, new)
      >>> diff.added_keys
      frozenset({'c'})
      >>> diff.removed_keys
      frozenset({'a'})
      >>> diff.modified_keys
      frozenset({'b'})
  """
  if old_data is None:
    old_data = {}
  if new_data is None:
    new_data = {}

  old_keys = set(old_data.keys())
  new_keys = set(new_data.keys())

  added = frozenset(new_keys - old_keys)
  removed = frozenset(old_keys - new_keys)

  # Check for modifications in common keys
  common_keys = old_keys & new_keys
  modified: Set[str] = set()
  unchanged: Set[str] = set()

  for key in common_keys:
    if not _compare_values(old_data[key], new_data[key]):
      modified.add(key)
    else:
      unchanged.add(key)

  return DataDiff(
    added_keys=added,
    removed_keys=removed,
    modified_keys=frozenset(modified),
    unchanged_keys=frozenset(unchanged),
  )


def compute_dog_diff(
  dog_id: str,
  old_dog_data: CoordinatorDogData | None,
  new_dog_data: CoordinatorDogData | None,
) -> DogDataDiff:
  """Compute differences for a specific dog.

  Args:
      dog_id: Dog identifier
      old_dog_data: Previous dog data
      new_dog_data: New dog data

  Returns:
      DogDataDiff describing changes

  Examples:
      >>> old = {"gps": {"lat": 45.0}, "walk": {"active": False}}
      >>> new = {"gps": {"lat": 45.1}, "walk": {"active": False}}
      >>> diff = compute_dog_diff("buddy", old, new)
      >>> diff.changed_modules
      frozenset({'gps'})
  """
  if old_dog_data is None:
    old_dog_data = {}
  if new_dog_data is None:
    new_dog_data = {}

  # Compute overall diff at dog level
  overall_diff = compute_data_diff(old_dog_data, new_dog_data)

  # Compute per-module diffs
  all_modules = set(old_dog_data.keys()) | set(new_dog_data.keys())
  module_diffs: dict[str, DataDiff] = {}

  for module in all_modules:
    old_module = old_dog_data.get(module)
    new_module = new_dog_data.get(module)

    if isinstance(old_module, Mapping) and isinstance(new_module, Mapping):
      module_diffs[module] = compute_data_diff(old_module, new_module)
    elif old_module is None and new_module is not None:
      # Module added
      module_diffs[module] = DataDiff(
        added_keys=frozenset(
          new_module.keys() if isinstance(new_module, Mapping) else []
        )
      )
    elif old_module is not None and new_module is None:
      # Module removed
      module_diffs[module] = DataDiff(
        removed_keys=frozenset(
          old_module.keys() if isinstance(old_module, Mapping) else []
        )
      )
    elif not _compare_values(old_module, new_module):
      # Module changed but not a mapping (e.g., scalar value)
      module_diffs[module] = DataDiff(modified_keys=frozenset([module]))

  return DogDataDiff(
    dog_id=dog_id,
    module_diffs=module_diffs,
    overall_diff=overall_diff,
  )


def compute_coordinator_diff(
  old_data: CoordinatorDataPayload | None,
  new_data: CoordinatorDataPayload | None,
) -> CoordinatorDataDiff:
  """Compute differences across all coordinator data.

  Args:
      old_data: Previous coordinator data
      new_data: New coordinator data

  Returns:
      CoordinatorDataDiff describing all changes

  Examples:
      >>> old = {"buddy": {"gps": {"lat": 45.0}}}
      >>> new = {"buddy": {"gps": {"lat": 45.1}}, "max": {"gps": {"lat": 46.0}}}
      >>> diff = compute_coordinator_diff(old, new)
      >>> diff.added_dogs
      frozenset({'max'})
      >>> diff.changed_dogs
      frozenset({'buddy', 'max'})
  """
  if old_data is None:
    old_data = {}
  if new_data is None:
    new_data = {}

  old_dogs = set(old_data.keys())
  new_dogs = set(new_data.keys())

  added_dogs = frozenset(new_dogs - old_dogs)
  removed_dogs = frozenset(old_dogs - new_dogs)

  # Compute per-dog diffs
  all_dogs = old_dogs | new_dogs
  dog_diffs: dict[str, DogDataDiff] = {}

  for dog_id in all_dogs:
    old_dog = old_data.get(dog_id)
    new_dog = new_data.get(dog_id)
    dog_diffs[dog_id] = compute_dog_diff(dog_id, old_dog, new_dog)

  return CoordinatorDataDiff(
    dog_diffs=dog_diffs,
    added_dogs=added_dogs,
    removed_dogs=removed_dogs,
  )


def should_notify_entities(
  diff: CoordinatorDataDiff,
  *,
  dog_id: str | None = None,
  module: str | None = None,
) -> bool:
  """Determine if entities should be notified about changes.

  Args:
      diff: Coordinator data diff
      dog_id: Optional dog ID to check
      module: Optional module to check

  Returns:
      True if entities should be notified

  Examples:
      >>> diff = CoordinatorDataDiff(...)
      >>> should_notify_entities(diff, dog_id="buddy", module="gps")
      True
  """
  if not diff.has_changes:
    return False

  # If no filters, notify if any changes exist
  if dog_id is None and module is None:
    return True

  # If dog_id filter specified
  if dog_id is not None:
    if dog_id in diff.added_dogs or dog_id in diff.removed_dogs:
      return True

    dog_diff = diff.dog_diffs.get(dog_id)
    if dog_diff is None:
      return False

    if not dog_diff.has_changes:
      return False

    # If module filter also specified
    if module is not None:
      return module in dog_diff.changed_modules

    return True

  # If only module filter specified (check all dogs)
  if module is not None:
    return any(
      module in dog_diff.changed_modules for dog_diff in diff.dog_diffs.values()
    )

  return False


class SmartDiffTracker:
  """Tracks data changes and provides smart diffing capabilities.

  This class maintains a snapshot of previous data and computes diffs
  on each update, enabling selective entity notifications.

  Examples:
      >>> tracker = SmartDiffTracker()
      >>> tracker.update(new_data)
      >>> diff = tracker.last_diff
      >>> if should_notify_entities(diff, dog_id="buddy", module="gps"):
      ...     # Notify GPS entities for buddy
  """

  def __init__(self) -> None:
    """Initialize the diff tracker."""
    self._previous_data: CoordinatorDataPayload | None = None
    self._last_diff: CoordinatorDataDiff | None = None
    self._update_count = 0

  @property
  def last_diff(self) -> CoordinatorDataDiff | None:
    """Return the most recent diff."""
    return self._last_diff

  @property
  def update_count(self) -> int:
    """Return number of updates processed."""
    return self._update_count

  def update(self, new_data: CoordinatorDataPayload) -> CoordinatorDataDiff:
    """Update with new data and compute diff.

    Args:
        new_data: New coordinator data

    Returns:
        Diff from previous data to new data
    """
    diff = compute_coordinator_diff(self._previous_data, new_data)
    self._previous_data = dict(new_data)  # Deep copy top level
    self._last_diff = diff
    self._update_count += 1

    if diff.has_changes:
      _LOGGER.debug(
        "Data diff computed: %d dogs changed, %d added, %d removed",
        len([d for d in diff.dog_diffs.values() if d.has_changes]),
        len(diff.added_dogs),
        len(diff.removed_dogs),
      )

    return diff

  def reset(self) -> None:
    """Reset tracker state."""
    self._previous_data = None
    self._last_diff = None
    self._update_count = 0

  def get_changed_entities(
    self,
    diff: CoordinatorDataDiff | None = None,
    *,
    dog_id: str | None = None,
    module: str | None = None,
  ) -> frozenset[str]:
    """Get entity keys that should be updated.

    Args:
        diff: Optional diff to use (defaults to last_diff)
        dog_id: Optional dog ID filter
        module: Optional module filter

    Returns:
        Set of entity keys that changed

    Examples:
        >>> tracker = SmartDiffTracker()
        >>> tracker.update(new_data)
        >>> changed = tracker.get_changed_entities(dog_id="buddy", module="gps")
        >>> # Returns: frozenset({'buddy.gps.latitude', 'buddy.gps.longitude'})
    """
    if diff is None:
      diff = self._last_diff

    if diff is None or not diff.has_changes:
      return frozenset()

    entity_keys: set[str] = set()

    # Filter by dog_id if specified
    dog_ids_to_check = [dog_id] if dog_id is not None else list(diff.dog_diffs.keys())

    for check_dog_id in dog_ids_to_check:
      if check_dog_id in diff.added_dogs or check_dog_id in diff.removed_dogs:
        # All entities for this dog should update
        if module is not None:
          entity_keys.add(f"{check_dog_id}.{module}")
        else:
          entity_keys.add(check_dog_id)
        continue

      dog_diff = diff.dog_diffs.get(check_dog_id)
      if dog_diff is None:
        continue

      # Filter by module if specified
      modules_to_check = (
        [module] if module is not None else list(dog_diff.module_diffs.keys())
      )

      for check_module in modules_to_check:
        module_diff = dog_diff.module_diffs.get(check_module)
        if module_diff is not None and module_diff.has_changes:
          entity_keys.add(f"{check_dog_id}.{check_module}")

    return frozenset(entity_keys)


def get_changed_fields(
  diff: DataDiff,
  *,
  include_added: bool = True,
  include_modified: bool = True,
  include_removed: bool = False,
) -> frozenset[str]:
  """Get field names that changed.

  Args:
      diff: Data diff to analyze
      include_added: Include added fields
      include_modified: Include modified fields
      include_removed: Include removed fields

  Returns:
      Set of changed field names

  Examples:
      >>> diff = DataDiff(added_keys={"x"}, modified_keys={"y"})
      >>> get_changed_fields(diff)
      frozenset({'x', 'y'})
      >>> get_changed_fields(diff, include_modified=False)
      frozenset({'x'})
  """
  fields: set[str] = set()

  if include_added:
    fields.update(diff.added_keys)

  if include_modified:
    fields.update(diff.modified_keys)

  if include_removed:
    fields.update(diff.removed_keys)

  return frozenset(fields)


def log_diff_summary(
  diff: CoordinatorDataDiff,
  logger: logging.Logger | None = None,
) -> None:
  """Log a human-readable summary of coordinator changes.

  Args:
      diff: Coordinator diff to summarize
      logger: Optional logger (defaults to module logger)

  Examples:
      >>> diff = compute_coordinator_diff(old_data, new_data)
      >>> log_diff_summary(diff)
      # Logs: "Coordinator diff: 2 dogs changed (gps, walk modules)"
  """
  if logger is None:
    logger = _LOGGER

  if not diff.has_changes:
    logger.debug("Coordinator diff: No changes detected")
    return

  changed_count = len([d for d in diff.dog_diffs.values() if d.has_changes])
  added_count = len(diff.added_dogs)
  removed_count = len(diff.removed_dogs)

  summary_parts = []
  if changed_count > 0:
    summary_parts.append(f"{changed_count} dogs changed")
  if added_count > 0:
    summary_parts.append(f"{added_count} added")
  if removed_count > 0:
    summary_parts.append(f"{removed_count} removed")

  # Collect changed modules across all dogs
  all_changed_modules: set[str] = set()
  for dog_diff in diff.dog_diffs.values():
    all_changed_modules.update(dog_diff.changed_modules)

  module_info = (
    f" ({', '.join(sorted(all_changed_modules))} modules)"
    if all_changed_modules
    else ""
  )

  logger.debug(
    "Coordinator diff: %s%s",
    ", ".join(summary_parts),
    module_info,
  )
