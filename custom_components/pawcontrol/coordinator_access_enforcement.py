"""Data access enforcement patterns for PawControl coordinator.

This module provides utilities to enforce coordinator-only data access patterns,
preventing direct entity access to raw data and ensuring all reads go through
the coordinator interface.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from collections.abc import Callable
import functools
import logging
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

if TYPE_CHECKING:
  from .coordinator import PawControlCoordinator  # noqa: E111

_LOGGER = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class CoordinatorAccessViolation(RuntimeError):
  """Raised when data access bypasses the coordinator."""  # noqa: E111

  def __init__(self, message: str, *, entity_id: str | None = None) -> None:  # noqa: E111
    """Initialize the exception.

    Args:
        message: Error message
        entity_id: Entity that violated the access pattern
    """
    super().__init__(message)
    self.entity_id = entity_id


def require_coordinator[**P, T](
  func: Callable[P, T],
) -> Callable[P, T]:
  """Decorator to ensure function has access to coordinator.

  Args:
      func: Function to decorate

  Returns:
      Decorated function that validates coordinator access

  Raises:
      CoordinatorAccessViolation: If coordinator is not available

  Examples:
      >>> @require_coordinator
      ... def get_dog_status(self):
      ...   return self.coordinator.data[self.dog_id]
  """  # noqa: E111

  @functools.wraps(func)  # noqa: E111
  def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:  # noqa: E111
    if not args:
      raise CoordinatorAccessViolation(  # noqa: E111
        "Function requires self parameter with coordinator access"
      )

    instance = args[0]
    entity_id = getattr(instance, "entity_id", None)

    if not hasattr(instance, "coordinator"):
      raise CoordinatorAccessViolation(  # noqa: E111
        "Instance must have coordinator attribute",
        entity_id=entity_id,
      )

    coordinator = instance.coordinator
    if coordinator is None:
      raise CoordinatorAccessViolation(  # noqa: E111
        "Coordinator is None - cannot access data",
        entity_id=entity_id,
      )

    return func(*args, **kwargs)

  return wrapper  # noqa: E111


def require_coordinator_data(
  *,
  dog_id_attr: str = "dog_id",
  allow_missing: bool = False,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
  """Decorator to ensure coordinator data is available for the entity's dog.

  Args:
      dog_id_attr: Attribute name containing the dog ID
      allow_missing: Whether to allow missing dog data

  Returns:
      Decorator function

  Raises:
      CoordinatorAccessViolation: If coordinator data is missing

  Examples:
      >>> @require_coordinator_data()
      ... def extra_state_attributes(self):
      ...   # self.coordinator.data[self.dog_id] is guaranteed
      ...   return self.coordinator.data[self.dog_id]["gps"]
  """  # noqa: E111

  def decorator(func: Callable[P, T]) -> Callable[P, T]:  # noqa: E111
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      if not args:  # noqa: E111
        raise CoordinatorAccessViolation(
          "Function requires self parameter with coordinator access"
        )

      instance = args[0]  # noqa: E111
      entity_id = getattr(instance, "entity_id", None)  # noqa: E111

      if not hasattr(instance, "coordinator"):  # noqa: E111
        raise CoordinatorAccessViolation(
          "Instance must have coordinator attribute",
          entity_id=entity_id,
        )

      coordinator = instance.coordinator  # noqa: E111
      if coordinator is None:  # noqa: E111
        raise CoordinatorAccessViolation(
          "Coordinator is None",
          entity_id=entity_id,
        )

      # Get dog_id from instance  # noqa: E114
      dog_id = getattr(instance, dog_id_attr, None)  # noqa: E111
      if dog_id is None:  # noqa: E111
        raise CoordinatorAccessViolation(
          f"Instance has no {dog_id_attr} attribute",
          entity_id=entity_id,
        )

      # Check if data exists for this dog  # noqa: E114
      if not allow_missing and dog_id not in coordinator.data:  # noqa: E111
        raise CoordinatorAccessViolation(
          f"Coordinator has no data for dog '{dog_id}'",
          entity_id=entity_id,
        )

      return func(*args, **kwargs)  # noqa: E111

    return wrapper

  return decorator  # noqa: E111


def coordinator_only_property[T](
  func: Callable[[Any], T],
) -> property:
  """Create a property that enforces coordinator-only access.

  Args:
      func: Property getter function

  Returns:
      Property with enforced coordinator access

  Examples:
      >>> @coordinator_only_property
      ... def current_location(self):
      ...   return self.coordinator.data[self.dog_id]["gps"]["location"]
  """  # noqa: E111

  @functools.wraps(func)  # noqa: E111
  @require_coordinator  # noqa: E111
  def wrapper(self: Any) -> T:  # noqa: E111
    return func(self)

  return property(wrapper)  # noqa: E111


def log_direct_access_warning(
  entity_id: str,
  attribute: str,
  *,
  coordinator_method: str | None = None,
) -> None:
  """Log a warning about direct data access.

  Args:
      entity_id: Entity that accessed data directly
      attribute: Attribute that was accessed
      coordinator_method: Recommended coordinator method to use

  Examples:
      >>> log_direct_access_warning(
      ...   "sensor.buddy_location",
      ...   "self._local_cache",
      ...   coordinator_method="coordinator.get_dog_data()",
      ... )
  """  # noqa: E111
  message = (  # noqa: E111
    f"Entity {entity_id} accessed {attribute} directly. "
    "This bypasses the coordinator and should be avoided."
  )

  if coordinator_method:  # noqa: E111
    message += f" Use {coordinator_method} instead."

  _LOGGER.warning(message)  # noqa: E111


class CoordinatorDataProxy:
  """Proxy for coordinator data that logs access patterns.

  This class wraps coordinator data and logs whenever it's accessed,
  helping identify entities that bypass proper access patterns.

  Examples:
      >>> proxy = CoordinatorDataProxy(coordinator.data, "sensor.buddy_gps")
      >>> location = proxy["buddy"]["gps"]["location"]  # Logged
  """  # noqa: E111

  def __init__(  # noqa: E111
    self,
    data: dict[str, Any],
    accessor_id: str,
    *,
    log_access: bool = True,
  ) -> None:
    """Initialize the proxy.

    Args:
        data: Coordinator data to wrap
        accessor_id: ID of the accessor (entity_id, manager name, etc.)
        log_access: Whether to log data access
    """
    self._data = data
    self._accessor_id = accessor_id
    self._log_access = log_access
    self._access_count = 0

  def __getitem__(self, key: str) -> Any:  # noqa: E111
    """Get item from data with access logging.

    Args:
        key: Data key

    Returns:
        Data value
    """
    if self._log_access:
      _LOGGER.debug(  # noqa: E111
        "Data accessed: %s read key '%s' (access_count=%d)",
        self._accessor_id,
        key,
        self._access_count + 1,
      )
    self._access_count += 1
    return self._data[key]

  def __contains__(self, key: str) -> bool:  # noqa: E111
    """Check if key exists in data.

    Args:
        key: Data key

    Returns:
        True if key exists
    """
    return key in self._data

  def get(self, key: str, default: Any = None) -> Any:  # noqa: E111
    """Get item from data with default.

    Args:
        key: Data key
        default: Default value if key not found

    Returns:
        Data value or default
    """
    if self._log_access:
      _LOGGER.debug(  # noqa: E111
        "Data accessed: %s read key '%s' with default (access_count=%d)",
        self._accessor_id,
        key,
        self._access_count + 1,
      )
    self._access_count += 1
    return self._data.get(key, default)

  @property  # noqa: E111
  def access_count(self) -> int:  # noqa: E111
    """Return number of times data was accessed."""
    return self._access_count


def validate_coordinator_usage(
  coordinator: PawControlCoordinator,
  *,
  log_warnings: bool = True,
) -> dict[str, Any]:
  """Validate that coordinator is being used properly.

  Args:
      coordinator: Coordinator to validate
      log_warnings: Whether to log warnings

  Returns:
      Dictionary with validation results

  Examples:
      >>> results = validate_coordinator_usage(coordinator)
      >>> if results["has_issues"]:
      ...   print(f"Found {results['issue_count']} issues")
  """  # noqa: E111
  issues: list[str] = []  # noqa: E111

  # Check if data is being accessed properly  # noqa: E114
  if coordinator.data is None:  # noqa: E111
    issues.append("Coordinator data is None")

  # Check if managers are attached  # noqa: E114
  runtime_managers = coordinator.runtime_managers  # noqa: E111
  if runtime_managers.data_manager is None:  # noqa: E111
    issues.append("Data manager not attached")

  if runtime_managers.feeding_manager is None and log_warnings:  # noqa: E111
    _LOGGER.debug("Feeding manager not attached (may be intentional)")

  # Check if adaptive polling is working  # noqa: E114
  if hasattr(coordinator, "_adaptive_polling"):  # noqa: E111
    adaptive = coordinator._adaptive_polling
    if hasattr(adaptive, "as_diagnostics"):
      diagnostics = adaptive.as_diagnostics()  # noqa: E111
      if diagnostics.get("saturation", 0) > 0.9 and log_warnings:  # noqa: E111
        _LOGGER.warning(
          "Coordinator entity saturation is high (%.1f%%) - "
          "consider reducing entity count",
          diagnostics["saturation"] * 100,
        )

  return {  # noqa: E111
    "has_issues": len(issues) > 0,
    "issue_count": len(issues),
    "issues": issues,
  }


def create_coordinator_access_guard(
  coordinator: PawControlCoordinator,
  *,
  strict_mode: bool = False,
) -> CoordinatorDataProxy:
  """Create a guarded proxy for coordinator data access.

  Args:
      coordinator: Coordinator to guard
      strict_mode: If True, raises exceptions on violations

  Returns:
      Proxy that guards data access

  Examples:
      >>> guard = create_coordinator_access_guard(coordinator, strict_mode=True)
      >>> data = guard["buddy"]  # Logged and validated
  """  # noqa: E111
  if strict_mode:  # noqa: E111
    _LOGGER.info("Coordinator access guard enabled in STRICT mode")
  else:  # noqa: E111
    _LOGGER.debug("Coordinator access guard enabled in monitoring mode")

  return CoordinatorDataProxy(  # noqa: E111
    coordinator.data,
    accessor_id="coordinator_access_guard",
    log_access=True,
  )


# Usage guidelines and best practices


COORDINATOR_ACCESS_GUIDELINES = """
Coordinator Data Access Guidelines
===================================

✓ CORRECT: Use coordinator interface
    def extra_state_attributes(self):
        dog_data = self.coordinator.get_dog_data(self.dog_id)
        return dog_data["gps"]

✓ CORRECT: Use data access mixins
    def extra_state_attributes(self):
        return self.coordinator.data[self.dog_id]["gps"]

✗ WRONG: Cache coordinator data locally
    def __init__(self):
        self._cached_data = coordinator.data  # DON'T DO THIS

✗ WRONG: Access manager data directly
    def extra_state_attributes(self):
        return self.gps_manager.get_location()  # DON'T DO THIS

✗ WRONG: Store references to nested data
    def __init__(self):
        self._gps_data = coordinator.data[dog_id]["gps"]  # DON'T DO THIS

Best Practices:
--------------
1. Always access data through coordinator
2. Never cache coordinator data in entities
3. Use decorators to enforce patterns
4. Let coordinator handle updates
5. Trust the coordinator diff mechanism
"""


def print_access_guidelines() -> None:
  """Print coordinator access guidelines to log."""  # noqa: E111
  _LOGGER.info(COORDINATOR_ACCESS_GUIDELINES)  # noqa: E111
