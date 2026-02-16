"""Error recovery coordinator for PawControl integration.

This module coordinates error handling, recovery attempts, and repair issue
creation to provide a seamless user experience during failures.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .exceptions import (
  AuthenticationError,
  ConfigurationError,
  GPSUnavailableError,
  NetworkError,
  RateLimitError,
  ServiceUnavailableError,
  StorageError,
  ValidationError,
)
from .logging_utils import StructuredLogger
from .resilience import FallbackStrategy, RetryStrategy

if TYPE_CHECKING:
  pass  # noqa: E111

_LOGGER = logging.getLogger(__name__)


@dataclass
class ErrorPattern:
  """Error pattern for recovery.

  Attributes:
      exception_type: Type of exception
      retry_strategy: Whether to retry
      circuit_breaker: Whether to use circuit breaker
      create_repair_issue: Whether to create repair issue
      recovery_action: Optional recovery action
      severity: Error severity (low, medium, high, critical)
  """  # noqa: E111

  exception_type: type[Exception]  # noqa: E111
  retry_strategy: bool = True  # noqa: E111
  circuit_breaker: bool = False  # noqa: E111
  create_repair_issue: bool = False  # noqa: E111
  recovery_action: Callable[..., Any] | None = None  # noqa: E111
  severity: str = "medium"  # noqa: E111


@dataclass
class ErrorStats:
  """Error statistics.

  Attributes:
      exception_type: Exception type
      total_count: Total occurrences
      recovery_count: Successful recoveries
      unrecovered_count: Failed recoveries
      last_occurrence: Last occurrence time
      repair_issues_created: Number of repair issues created
  """  # noqa: E111

  exception_type: str  # noqa: E111
  total_count: int = 0  # noqa: E111
  recovery_count: int = 0  # noqa: E111
  unrecovered_count: int = 0  # noqa: E111
  last_occurrence: datetime | None = None  # noqa: E111
  repair_issues_created: int = 0  # noqa: E111

  @property  # noqa: E111
  def recovery_rate(self) -> float:  # noqa: E111
    """Return recovery rate (0.0-1.0)."""
    total = self.recovery_count + self.unrecovered_count
    return self.recovery_count / total if total > 0 else 0.0

  def to_dict(self) -> dict[str, Any]:  # noqa: E111
    """Convert to dictionary."""
    return {
      "exception_type": self.exception_type,
      "total_count": self.total_count,
      "recovery_count": self.recovery_count,
      "unrecovered_count": self.unrecovered_count,
      "recovery_rate": round(self.recovery_rate, 3),
      "last_occurrence": (
        self.last_occurrence.isoformat() if self.last_occurrence else None
      ),
      "repair_issues_created": self.repair_issues_created,
    }


class ErrorRecoveryCoordinator:
  """Coordinates error handling and recovery.

  Manages error patterns, recovery strategies, and repair issue creation
  to provide intelligent error handling throughout the integration.

  Examples:
      >>> coordinator = ErrorRecoveryCoordinator(hass)
      >>> await coordinator.async_setup()
      >>> result = await coordinator.handle_error(error, context)
  """  # noqa: E111

  def __init__(self, hass: HomeAssistant, domain: str = "pawcontrol") -> None:  # noqa: E111
    """Initialize error recovery coordinator.

    Args:
        hass: Home Assistant instance
        domain: Integration domain
    """
    self._hass = hass
    self._domain = domain
    self._logger = StructuredLogger(__name__)
    self._patterns: dict[type[Exception], ErrorPattern] = {}
    self._stats: dict[str, ErrorStats] = defaultdict(
      lambda: ErrorStats(exception_type="unknown")
    )
    self._retry_strategy = RetryStrategy()
    self._fallback_strategy = FallbackStrategy(default_value=None)

  async def async_setup(self) -> None:  # noqa: E111
    """Set up error recovery coordinator."""
    self._register_default_patterns()
    self._logger.info("Error recovery coordinator initialized")

  def _register_default_patterns(self) -> None:  # noqa: E111
    """Register default error patterns."""
    # Network errors: retry with circuit breaker
    self._patterns[NetworkError] = ErrorPattern(
      exception_type=NetworkError,
      retry_strategy=True,
      circuit_breaker=True,
      create_repair_issue=True,
      severity="high",
    )

    # Authentication errors: create repair issue immediately
    self._patterns[AuthenticationError] = ErrorPattern(
      exception_type=AuthenticationError,
      retry_strategy=False,
      circuit_breaker=False,
      create_repair_issue=True,
      severity="critical",
    )

    # Rate limit: wait and retry, no repair issue
    self._patterns[RateLimitError] = ErrorPattern(
      exception_type=RateLimitError,
      retry_strategy=True,
      circuit_breaker=False,
      create_repair_issue=False,
      severity="medium",
    )

    # Service unavailable: retry with circuit breaker
    self._patterns[ServiceUnavailableError] = ErrorPattern(
      exception_type=ServiceUnavailableError,
      retry_strategy=True,
      circuit_breaker=True,
      create_repair_issue=True,
      severity="high",
    )

    # Configuration errors: create repair issue
    self._patterns[ConfigurationError] = ErrorPattern(
      exception_type=ConfigurationError,
      retry_strategy=False,
      circuit_breaker=False,
      create_repair_issue=True,
      severity="critical",
    )

    # Validation errors: create repair issue
    self._patterns[ValidationError] = ErrorPattern(
      exception_type=ValidationError,
      retry_strategy=False,
      circuit_breaker=False,
      create_repair_issue=True,
      severity="medium",
    )

    # GPS errors: retry, no repair issue
    self._patterns[GPSUnavailableError] = ErrorPattern(
      exception_type=GPSUnavailableError,
      retry_strategy=True,
      circuit_breaker=False,
      create_repair_issue=False,
      severity="low",
    )

    # Storage errors: retry
    self._patterns[StorageError] = ErrorPattern(
      exception_type=StorageError,
      retry_strategy=True,
      circuit_breaker=False,
      create_repair_issue=True,
      severity="high",
    )

  def register_pattern(self, pattern: ErrorPattern) -> None:  # noqa: E111
    """Register error pattern.

    Args:
        pattern: Error pattern to register
    """
    self._patterns[pattern.exception_type] = pattern
    self._logger.debug(
      f"Registered error pattern for {pattern.exception_type.__name__}"
    )

  async def handle_error(  # noqa: E111
    self,
    error: Exception,
    *,
    context: dict[str, Any] | None = None,
    fallback_value: Any = None,
  ) -> dict[str, Any]:
    """Handle error with recovery attempts.

    Args:
        error: Exception to handle
        context: Optional context data
        fallback_value: Optional fallback value

    Returns:
        Recovery result dictionary
    """
    error_type = error.__class__.__name__
    pattern = self._patterns.get(type(error))

    # Update stats
    stats = self._stats[error_type]
    stats.exception_type = error_type
    stats.total_count += 1
    stats.last_occurrence = datetime.now()

    # Log error
    self._logger.error(
      f"Handling error: {error_type}",
      error=str(error),
      pattern_found=pattern is not None,
      **(context or {}),
    )

    # Build recovery result
    result: dict[str, Any] = {
      "error_type": error_type,
      "error_message": str(error),
      "recovered": False,
      "recovery_method": None,
      "fallback_used": False,
      "repair_issue_created": False,
    }

    # Attempt recovery if pattern exists
    if pattern:
      # Create repair issue if needed  # noqa: E114
      if pattern.create_repair_issue:  # noqa: E111
        await self._create_repair_issue(error, pattern, context)
        result["repair_issue_created"] = True
        stats.repair_issues_created += 1

      # Attempt recovery action  # noqa: E114
      if pattern.recovery_action:  # noqa: E111
        try:
          recovery_result = await pattern.recovery_action(error, context)  # noqa: E111
          result["recovered"] = True  # noqa: E111
          result["recovery_method"] = "recovery_action"  # noqa: E111
          result["recovery_result"] = recovery_result  # noqa: E111
          stats.recovery_count += 1  # noqa: E111
          self._logger.info(f"Error recovered via recovery action: {error_type}")  # noqa: E111
        except Exception as recovery_error:
          self._logger.error(  # noqa: E111
            f"Recovery action failed: {recovery_error}",
            exc_info=True,
          )
          stats.unrecovered_count += 1  # noqa: E111

    # Use fallback if provided and not recovered
    if not result["recovered"] and fallback_value is not None:
      result["fallback_used"] = True  # noqa: E111
      result["fallback_value"] = fallback_value  # noqa: E111
      self._logger.info(f"Using fallback value for {error_type}")  # noqa: E111

    # Log recovery result
    if result["recovered"]:
      self._logger.info("Error recovery successful", **result)  # noqa: E111
    else:
      self._logger.warning("Error recovery failed", **result)  # noqa: E111
      stats.unrecovered_count += 1  # noqa: E111

    return result

  async def _create_repair_issue(  # noqa: E111
    self,
    error: Exception,
    pattern: ErrorPattern,
    context: dict[str, Any] | None,
  ) -> None:
    """Create repair issue for error.

    Args:
        error: Exception that occurred
        pattern: Error pattern
        context: Optional context
    """
    try:
      # Generate issue ID  # noqa: E114
      issue_id = f"{self._domain}_{error.__class__.__name__.lower()}"  # noqa: E111

      # Determine severity  # noqa: E114
      severity_map = {  # noqa: E111
        "low": ir.IssueSeverity.WARNING,
        "medium": ir.IssueSeverity.WARNING,
        "high": ir.IssueSeverity.ERROR,
        "critical": ir.IssueSeverity.CRITICAL,
      }
      severity = severity_map.get(pattern.severity, ir.IssueSeverity.ERROR)  # noqa: E111

      # Build description  # noqa: E114
      description = f"{error.__class__.__name__}: {error}"  # noqa: E111
      if context:  # noqa: E111
        description += f"\n\nContext: {context}"

      # Create issue  # noqa: E114
      ir.async_create_issue(  # noqa: E111
        self._hass,
        self._domain,
        issue_id,
        is_fixable=True,
        severity=severity,
        translation_key=error.__class__.__name__.lower(),
        translation_placeholders={
          "error": str(error),
          "error_type": error.__class__.__name__,
        },
      )

      self._logger.info(  # noqa: E111
        f"Created repair issue: {issue_id}",
        severity=pattern.severity,
      )

    except Exception as e:
      self._logger.error(  # noqa: E111
        f"Failed to create repair issue: {e}",
        exc_info=True,
      )

  def get_stats(self) -> dict[str, ErrorStats]:  # noqa: E111
    """Get error statistics.

    Returns:
        Dictionary of error statistics
    """
    return dict(self._stats)

  def get_recovery_summary(self) -> dict[str, Any]:  # noqa: E111
    """Get recovery summary.

    Returns:
        Summary dictionary
    """
    total_errors = sum(stats.total_count for stats in self._stats.values())
    total_recovered = sum(stats.recovery_count for stats in self._stats.values())
    total_unrecovered = sum(stats.unrecovered_count for stats in self._stats.values())

    return {
      "total_errors": total_errors,
      "total_recovered": total_recovered,
      "total_unrecovered": total_unrecovered,
      "recovery_rate": (
        total_recovered / (total_recovered + total_unrecovered)
        if (total_recovered + total_unrecovered) > 0
        else 0.0
      ),
      "error_types": len(self._stats),
      "most_common": (
        sorted(
          self._stats.values(),
          key=lambda s: s.total_count,
          reverse=True,
        )[:5]
      ),
    }

  def reset_stats(self) -> None:  # noqa: E111
    """Reset error statistics."""
    self._stats.clear()
    self._logger.info("Error statistics reset")


# Global error recovery coordinator instance
_error_recovery_coordinator: ErrorRecoveryCoordinator | None = None


def get_error_recovery_coordinator(
  hass: HomeAssistant,
  domain: str = "pawcontrol",
) -> ErrorRecoveryCoordinator:
  """Get or create error recovery coordinator.

  Args:
      hass: Home Assistant instance
      domain: Integration domain

  Returns:
      ErrorRecoveryCoordinator instance
  """  # noqa: E111
  global _error_recovery_coordinator  # noqa: E111
  if _error_recovery_coordinator is None:  # noqa: E111
    _error_recovery_coordinator = ErrorRecoveryCoordinator(hass, domain)
  return _error_recovery_coordinator  # noqa: E111


# Helper functions


async def handle_error_with_recovery(
  hass: HomeAssistant,
  error: Exception,
  *,
  context: dict[str, Any] | None = None,
  fallback_value: Any = None,
) -> dict[str, Any]:
  """Handle error with automatic recovery.

  Args:
      hass: Home Assistant instance
      error: Exception to handle
      context: Optional context
      fallback_value: Optional fallback value

  Returns:
      Recovery result

  Examples:
      >>> try:
      ...   result = await api.fetch()
      ... except NetworkError as e:
      ...   recovery = await handle_error_with_recovery(hass, e)
      ...   if recovery["recovered"]:
      ...     result = recovery["recovery_result"]
  """  # noqa: E111
  coordinator = get_error_recovery_coordinator(hass)  # noqa: E111
  return await coordinator.handle_error(  # noqa: E111
    error,
    context=context,
    fallback_value=fallback_value,
  )
