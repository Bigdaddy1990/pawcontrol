"""Smart diffing and data change detection for PawControl coordinator.

This module provides utilities for minimizing unnecessary entity updates by
detecting meaningful data changes and notifying only affected entities.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
import logging
from typing import Any, TypeVar

from .types import CoordinatorDataPayload, CoordinatorDogData

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
  """  # noqa: E111

  added_keys: frozenset[str] = field(default_factory=frozenset)  # noqa: E111
  removed_keys: frozenset[str] = field(default_factory=frozenset)  # noqa: E111
  modified_keys: frozenset[str] = field(default_factory=frozenset)  # noqa: E111
  unchanged_keys: frozenset[str] = field(default_factory=frozenset)  # noqa: E111

  @property  # noqa: E111
  def has_changes(self) -> bool:  # noqa: E111
    """Return True if there are any changes."""
    return bool(self.added_keys or self.removed_keys or self.modified_keys)

  @property  # noqa: E111
  def change_count(self) -> int:  # noqa: E111
    """Return total number of changes."""
    return len(self.added_keys) + len(self.removed_keys) + len(self.modified_keys)

  @property  # noqa: E111
  def changed_keys(self) -> frozenset[str]:  # noqa: E111
    """Return all keys that changed (added, removed, or modified)."""
    return self.added_keys | self.removed_keys | self.modified_keys

  def to_dict(self) -> dict[str, Any]:  # noqa: E111
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
  """  # noqa: E111

  dog_id: str  # noqa: E111
  module_diffs: Mapping[str, DataDiff] = field(default_factory=dict)  # noqa: E111
  overall_diff: DataDiff = field(default_factory=DataDiff)  # noqa: E111

  @property  # noqa: E111
  def has_changes(self) -> bool:  # noqa: E111
    """Return True if there are any changes."""
    return any(diff.has_changes for diff in self.module_diffs.values())

  @property  # noqa: E111
  def changed_modules(self) -> frozenset[str]:  # noqa: E111
    """Return modules that have changes."""
    return frozenset(
      module for module, diff in self.module_diffs.items() if diff.has_changes
    )

  def to_dict(self) -> dict[str, Any]:  # noqa: E111
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
  """  # noqa: E111

  dog_diffs: Mapping[str, DogDataDiff] = field(default_factory=dict)  # noqa: E111
  added_dogs: frozenset[str] = field(default_factory=frozenset)  # noqa: E111
  removed_dogs: frozenset[str] = field(default_factory=frozenset)  # noqa: E111

  @property  # noqa: E111
  def has_changes(self) -> bool:  # noqa: E111
    """Return True if there are any changes."""
    return bool(
      self.added_dogs
      or self.removed_dogs
      or any(diff.has_changes for diff in self.dog_diffs.values())
    )

  @property  # noqa: E111
  def changed_dogs(self) -> frozenset[str]:  # noqa: E111
    """Return dog IDs that have changes."""
    changed = frozenset(
      dog_id for dog_id, diff in self.dog_diffs.items() if diff.has_changes
    )
    return changed | self.added_dogs | self.removed_dogs

  @property  # noqa: E111
  def change_count(self) -> int:  # noqa: E111
    """Return the number of changed dogs including adds/removals."""
    return len(self.changed_dogs)

  def to_dict(self) -> dict[str, Any]:  # noqa: E111
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
  """  # noqa: E111
  # Fast path for identical objects  # noqa: E114
  if old_value is new_value:  # noqa: E111
    return True

  # Handle None  # noqa: E114
  if old_value is None or new_value is None:  # noqa: E111
    return old_value == new_value

  # Handle different types  # noqa: E114
  if type(old_value) is not type(new_value):  # noqa: E111
    return False

  # Handle mappings recursively  # noqa: E114
  if isinstance(old_value, Mapping) and isinstance(new_value, Mapping):  # noqa: E111
    if old_value.keys() != new_value.keys():
      return False  # noqa: E111
    return all(_compare_values(old_value[k], new_value[k]) for k in old_value)

  # Handle sequences recursively (but not strings)  # noqa: E114
  if isinstance(old_value, (list, tuple)) and isinstance(new_value, (list, tuple)):  # noqa: E111
    if len(old_value) != len(new_value):
      return False  # noqa: E111
    return all(
      _compare_values(o, n) for o, n in zip(old_value, new_value, strict=False)
    )

  # Default equality  # noqa: E114
  return old_value == new_value  # noqa: E111


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
  """  # noqa: E111
  if old_data is None:  # noqa: E111
    old_data = {}
  if new_data is None:  # noqa: E111
    new_data = {}

  old_keys = set(old_data.keys())  # noqa: E111
  new_keys = set(new_data.keys())  # noqa: E111

  added = frozenset(new_keys - old_keys)  # noqa: E111
  removed = frozenset(old_keys - new_keys)  # noqa: E111

  # Check for modifications in common keys  # noqa: E114
  common_keys = old_keys & new_keys  # noqa: E111
  modified: set[str] = set()  # noqa: E111
  unchanged: set[str] = set()  # noqa: E111

  for key in common_keys:  # noqa: E111
    if not _compare_values(old_data[key], new_data[key]):
      modified.add(key)  # noqa: E111
    else:
      unchanged.add(key)  # noqa: E111

  return DataDiff(  # noqa: E111
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
  """  # noqa: E111
  if old_dog_data is None:  # noqa: E111
    old_dog_data = {}
  if new_dog_data is None:  # noqa: E111
    new_dog_data = {}

  # Compute overall diff at dog level  # noqa: E114
  overall_diff = compute_data_diff(old_dog_data, new_dog_data)  # noqa: E111

  # Compute per-module diffs  # noqa: E114
  all_modules = set(old_dog_data.keys()) | set(new_dog_data.keys())  # noqa: E111
  module_diffs: dict[str, DataDiff] = {}  # noqa: E111

  for module in all_modules:  # noqa: E111
    old_module = old_dog_data.get(module)
    new_module = new_dog_data.get(module)

    if isinstance(old_module, Mapping) and isinstance(new_module, Mapping):
      module_diffs[module] = compute_data_diff(old_module, new_module)  # noqa: E111
    elif old_module is None and new_module is not None:
      # Module added  # noqa: E114
      module_diffs[module] = DataDiff(  # noqa: E111
        added_keys=frozenset(
          new_module.keys() if isinstance(new_module, Mapping) else []
        )
      )
    elif old_module is not None and new_module is None:
      # Module removed  # noqa: E114
      module_diffs[module] = DataDiff(  # noqa: E111
        removed_keys=frozenset(
          old_module.keys() if isinstance(old_module, Mapping) else []
        )
      )
    elif not _compare_values(old_module, new_module):
      # Module changed but not a mapping (e.g., scalar value)  # noqa: E114
      module_diffs[module] = DataDiff(modified_keys=frozenset([module]))  # noqa: E111

  return DogDataDiff(  # noqa: E111
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
  """  # noqa: E111
  if old_data is None:  # noqa: E111
    old_data = {}
  if new_data is None:  # noqa: E111
    new_data = {}

  old_dogs = set(old_data.keys())  # noqa: E111
  new_dogs = set(new_data.keys())  # noqa: E111

  added_dogs = frozenset(new_dogs - old_dogs)  # noqa: E111
  removed_dogs = frozenset(old_dogs - new_dogs)  # noqa: E111

  # Compute per-dog diffs  # noqa: E114
  all_dogs = old_dogs | new_dogs  # noqa: E111
  dog_diffs: dict[str, DogDataDiff] = {}  # noqa: E111

  for dog_id in all_dogs:  # noqa: E111
    old_dog = old_data.get(dog_id)
    new_dog = new_data.get(dog_id)
    dog_diffs[dog_id] = compute_dog_diff(dog_id, old_dog, new_dog)

  return CoordinatorDataDiff(  # noqa: E111
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
  """  # noqa: E111
  if not diff.has_changes:  # noqa: E111
    return False

  # If no filters, notify if any changes exist  # noqa: E114
  if dog_id is None and module is None:  # noqa: E111
    return True

  # If dog_id filter specified  # noqa: E114
  if dog_id is not None:  # noqa: E111
    if dog_id in diff.added_dogs or dog_id in diff.removed_dogs:
      return True  # noqa: E111

    dog_diff = diff.dog_diffs.get(dog_id)
    if dog_diff is None:
      return False  # noqa: E111

    if not dog_diff.has_changes:
      return False  # noqa: E111

    # If module filter also specified
    if module is not None:
      return module in dog_diff.changed_modules  # noqa: E111

    return True

  # If only module filter specified (check all dogs)  # noqa: E114
  if module is not None:  # noqa: E111
    return any(
      module in dog_diff.changed_modules for dog_diff in diff.dog_diffs.values()
    )

  return False  # noqa: E111


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
  """  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    """Initialize the diff tracker."""
    self._previous_data: CoordinatorDataPayload | None = None
    self._last_diff: CoordinatorDataDiff | None = None
    self._update_count = 0

  @property  # noqa: E111
  def last_diff(self) -> CoordinatorDataDiff | None:  # noqa: E111
    """Return the most recent diff."""
    return self._last_diff

  @property  # noqa: E111
  def update_count(self) -> int:  # noqa: E111
    """Return number of updates processed."""
    return self._update_count

  def update(self, new_data: CoordinatorDataPayload) -> CoordinatorDataDiff:  # noqa: E111
    """Update with new data and compute diff.

    Args:
        new_data: New coordinator data

    Returns:
        Diff from previous data to new data
    """
    if self._previous_data is None:
      diff = compute_coordinator_diff({}, new_data)  # noqa: E111
    else:
      diff = compute_coordinator_diff(self._previous_data, new_data)  # noqa: E111
    self._previous_data = dict(new_data)  # Deep copy top level
    self._last_diff = diff
    self._update_count += 1
    if diff.has_changes:
      _LOGGER.debug(  # noqa: E111
        "Data diff computed: %d dogs changed, %d added, %d removed",
        len([d for d in diff.dog_diffs.values() if d.has_changes]),
        len(diff.added_dogs),
        len(diff.removed_dogs),
      )

    return diff

  def reset(self) -> None:  # noqa: E111
    """Reset tracker state."""
    self._previous_data = None
    self._last_diff = None
    self._update_count = 0

  def get_changed_entities(  # noqa: E111
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
      diff = self._last_diff  # noqa: E111

    if diff is None or not diff.has_changes:
      return frozenset()  # noqa: E111

    entity_keys: set[str] = set()

    # Filter by dog_id if specified
    dog_ids_to_check = [dog_id] if dog_id is not None else list(diff.dog_diffs.keys())

    for check_dog_id in dog_ids_to_check:
      if check_dog_id in diff.added_dogs or check_dog_id in diff.removed_dogs:  # noqa: E111
        # All entities for this dog should update
        if module is not None:
          entity_keys.add(f"{check_dog_id}.{module}")  # noqa: E111
        else:
          entity_keys.add(check_dog_id)  # noqa: E111
        continue

      dog_diff = diff.dog_diffs.get(check_dog_id)  # noqa: E111
      if dog_diff is None:  # noqa: E111
        continue

      # Filter by module if specified  # noqa: E114
      modules_to_check = (  # noqa: E111
        [module] if module is not None else list(dog_diff.module_diffs.keys())
      )

      for check_module in modules_to_check:  # noqa: E111
        module_diff = dog_diff.module_diffs.get(check_module)
        if module_diff is not None and module_diff.has_changes:
          entity_keys.add(f"{check_dog_id}.{check_module}")  # noqa: E111

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
  """  # noqa: E111
  fields: set[str] = set()  # noqa: E111

  if include_added:  # noqa: E111
    fields.update(diff.added_keys)

  if include_modified:  # noqa: E111
    fields.update(diff.modified_keys)

  if include_removed:  # noqa: E111
    fields.update(diff.removed_keys)

  return frozenset(fields)  # noqa: E111


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
  """  # noqa: E111
  if logger is None:  # noqa: E111
    logger = _LOGGER

  if not diff.has_changes:  # noqa: E111
    logger.debug("Coordinator diff: No changes detected")
    return

  changed_count = len([d for d in diff.dog_diffs.values() if d.has_changes])  # noqa: E111
  added_count = len(diff.added_dogs)  # noqa: E111
  removed_count = len(diff.removed_dogs)  # noqa: E111

  summary_parts = []  # noqa: E111
  if changed_count > 0:  # noqa: E111
    summary_parts.append(f"{changed_count} dogs changed")
  if added_count > 0:  # noqa: E111
    summary_parts.append(f"{added_count} added")
  if removed_count > 0:  # noqa: E111
    summary_parts.append(f"{removed_count} removed")

  # Collect changed modules across all dogs  # noqa: E114
  all_changed_modules: set[str] = set()  # noqa: E111
  for dog_diff in diff.dog_diffs.values():  # noqa: E111
    all_changed_modules.update(dog_diff.changed_modules)

  module_info = (  # noqa: E111
    f" ({', '.join(sorted(all_changed_modules))} modules)"
    if all_changed_modules
    else ""
  )

  logger.debug(  # noqa: E111
    "Coordinator diff: %s%s",
    ", ".join(summary_parts),
    module_info,
  )
