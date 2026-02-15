"""Manager pattern compliance validation for PawControl.

This module validates that managers follow the standardized BaseManager pattern
and provides automated checks for interface consistency.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  pass

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComplianceIssue:
  """Represents a manager compliance issue.

  Attributes:
      severity: Issue severity (error, warning, info)
      category: Issue category (interface, lifecycle, documentation)
      message: Human-readable message
      manager_name: Name of the manager
      details: Additional details
  """

  severity: str
  category: str
  message: str
  manager_name: str
  details: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary."""
    return {
      "severity": self.severity,
      "category": self.category,
      "message": self.message,
      "manager_name": self.manager_name,
      "details": self.details,
    }


@dataclass
class ComplianceReport:
  """Manager compliance validation report.

  Attributes:
      manager_name: Name of the manager
      is_compliant: Whether manager is fully compliant
      issues: List of compliance issues
      score: Compliance score (0-100)
  """

  manager_name: str
  is_compliant: bool = True
  issues: list[ComplianceIssue] = field(default_factory=list)
  score: int = 100

  def add_issue(
    self,
    severity: str,
    category: str,
    message: str,
    **details: Any,
  ) -> None:
    """Add a compliance issue.

    Args:
        severity: Issue severity
        category: Issue category
        message: Issue message
        **details: Additional details
    """
    issue = ComplianceIssue(
      severity=severity,
      category=category,
      message=message,
      manager_name=self.manager_name,
      details=details,
    )
    self.issues.append(issue)

    # Update compliance status
    if severity == "error":
      self.is_compliant = False
      self.score = max(0, self.score - 25)
    elif severity == "warning":
      self.score = max(0, self.score - 10)
    elif severity == "info":
      self.score = max(0, self.score - 5)

  def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary."""
    return {
      "manager_name": self.manager_name,
      "is_compliant": self.is_compliant,
      "score": self.score,
      "issues": [issue.to_dict() for issue in self.issues],
      "error_count": sum(1 for i in self.issues if i.severity == "error"),
      "warning_count": sum(1 for i in self.issues if i.severity == "warning"),
      "info_count": sum(1 for i in self.issues if i.severity == "info"),
    }


def check_required_methods(
  manager: type[Any],
  report: ComplianceReport,
) -> None:
  """Check for required method implementations.

  Args:
      manager: Manager class to check
      report: Compliance report to update
  """
  required_methods = {
    "async_setup": "Setup lifecycle method",
    "async_shutdown": "Shutdown lifecycle method",
    "get_diagnostics": "Diagnostics reporting method",
  }

  for method_name, description in required_methods.items():
    if not hasattr(manager, method_name):
      report.add_issue(
        "error",
        "interface",
        f"Missing required method: {method_name}",
        method=method_name,
        description=description,
      )
      continue

    method = getattr(manager, method_name)
    if not callable(method):
      report.add_issue(
        "error",
        "interface",
        f"{method_name} is not callable",
        method=method_name,
      )


def check_lifecycle_properties(
  manager: type[Any],
  report: ComplianceReport,
) -> None:
  """Check for required lifecycle properties.

  Args:
      manager: Manager class to check
      report: Compliance report to update
  """
  required_properties = {
    "is_setup": "Setup state tracking",
    "is_shutdown": "Shutdown state tracking",
    "is_ready": "Ready state checking",
  }

  for prop_name, description in required_properties.items():
    if not hasattr(manager, prop_name):
      report.add_issue(
        "warning",
        "lifecycle",
        f"Missing lifecycle property: {prop_name}",
        property=prop_name,
        description=description,
      )


def check_manager_constants(
  manager: type[Any],
  report: ComplianceReport,
) -> None:
  """Check for required manager constants.

  Args:
      manager: Manager class to check
      report: Compliance report to update
  """
  if not hasattr(manager, "MANAGER_NAME"):
    report.add_issue(
      "error",
      "interface",
      "Missing MANAGER_NAME class constant",
    )
  elif not isinstance(manager.MANAGER_NAME, str):
    report.add_issue(
      "error",
      "interface",
      "MANAGER_NAME must be a string",
      actual_type=type(manager.MANAGER_NAME).__name__,
    )

  if not hasattr(manager, "MANAGER_VERSION"):
    report.add_issue(
      "warning",
      "interface",
      "Missing MANAGER_VERSION class constant",
    )


def check_method_signatures(
  manager: type[Any],
  report: ComplianceReport,
) -> None:
  """Check method signatures for compliance.

  Args:
      manager: Manager class to check
      report: Compliance report to update
  """
  # Check async_setup signature
  if hasattr(manager, "async_setup"):
    sig = inspect.signature(manager.async_setup)
    params = list(sig.parameters.keys())

    # Should have only self parameter
    if len(params) != 1 or params[0] != "self":
      report.add_issue(
        "warning",
        "interface",
        "async_setup should have only 'self' parameter",
        actual_params=params,
      )

  # Check async_shutdown signature
  if hasattr(manager, "async_shutdown"):
    sig = inspect.signature(manager.async_shutdown)
    params = list(sig.parameters.keys())

    # Should have only self parameter
    if len(params) != 1 or params[0] != "self":
      report.add_issue(
        "warning",
        "interface",
        "async_shutdown should have only 'self' parameter",
        actual_params=params,
      )

  # Check get_diagnostics signature
  if hasattr(manager, "get_diagnostics"):
    sig = inspect.signature(manager.get_diagnostics)
    params = list(sig.parameters.keys())

    # Should have only self parameter
    if len(params) != 1 or params[0] != "self":
      report.add_issue(
        "warning",
        "interface",
        "get_diagnostics should have only 'self' parameter",
        actual_params=params,
      )


def check_documentation(
  manager: type[Any],
  report: ComplianceReport,
) -> None:
  """Check for proper documentation.

  Args:
      manager: Manager class to check
      report: Compliance report to update
  """
  # Check class docstring
  if not manager.__doc__:
    report.add_issue(
      "warning",
      "documentation",
      "Missing class docstring",
    )
  elif len(manager.__doc__.strip()) < 20:
    report.add_issue(
      "info",
      "documentation",
      "Class docstring is too brief",
      length=len(manager.__doc__.strip()),
    )

  # Check method docstrings
  methods_to_check = ["async_setup", "async_shutdown", "get_diagnostics"]
  for method_name in methods_to_check:
    if hasattr(manager, method_name):
      method = getattr(manager, method_name)
      if not method.__doc__:
        report.add_issue(
          "info",
          "documentation",
          f"Missing docstring for {method_name}",
          method=method_name,
        )


def check_inheritance(
  manager: type[Any],
  report: ComplianceReport,
) -> None:
  """Check inheritance from BaseManager.

  Args:
      manager: Manager class to check
      report: Compliance report to update
  """
  # Check if inherits from BaseManager
  from .base_manager import BaseManager

  if not issubclass(manager, BaseManager):
    report.add_issue(
      "error",
      "interface",
      "Manager does not inherit from BaseManager",
      mro=[c.__name__ for c in manager.__mro__],
    )


def validate_manager_compliance(
  manager: type[Any] | Any,
) -> ComplianceReport:
  """Validate manager compliance with BaseManager pattern.

  Args:
      manager: Manager class or instance to validate

  Returns:
      Compliance report with issues and score

  Examples:
      >>> report = validate_manager_compliance(MyManager)
      >>> if report.is_compliant:
      ...   print(f"Manager is compliant (score: {report.score})")
      >>> else:
      ...     print(f"Found {len(report.issues)} issues")
  """
  # Get class if instance was passed
  if not inspect.isclass(manager):
    manager = manager.__class__

  manager_name = getattr(manager, "MANAGER_NAME", manager.__name__)
  report = ComplianceReport(manager_name=manager_name)

  # Run all checks
  check_inheritance(manager, report)
  check_required_methods(manager, report)
  check_lifecycle_properties(manager, report)
  check_manager_constants(manager, report)
  check_method_signatures(manager, report)
  check_documentation(manager, report)

  return report


def validate_all_managers(
  *managers: type[Any] | Any,
) -> dict[str, ComplianceReport]:
  """Validate multiple managers.

  Args:
      *managers: Manager classes or instances to validate

  Returns:
      Dictionary mapping manager names to compliance reports

  Examples:
      >>> reports = validate_all_managers(DataManager, EventManager)
      >>> for name, report in reports.items():
      ...   print(f"{name}: {report.score}/100")
  """
  reports: dict[str, ComplianceReport] = {}

  for manager in managers:
    report = validate_manager_compliance(manager)
    reports[report.manager_name] = report

  return reports


def print_compliance_report(
  report: ComplianceReport,
  logger: logging.Logger | None = None,
) -> None:
  """Print compliance report to logger.

  Args:
      report: Compliance report to print
      logger: Optional logger (defaults to module logger)

  Examples:
      >>> report = validate_manager_compliance(MyManager)
      >>> print_compliance_report(report)
  """
  if logger is None:
    logger = _LOGGER

  logger.info(
    "Compliance report for %s: score=%d/100, compliant=%s",
    report.manager_name,
    report.score,
    report.is_compliant,
  )

  if report.issues:
    logger.info("Found %d issues:", len(report.issues))
    for issue in report.issues:
      level_map = {
        "error": logger.error,
        "warning": logger.warning,
        "info": logger.info,
      }
      log_func = level_map.get(issue.severity, logger.info)
      log_func(
        "  [%s/%s] %s",
        issue.severity.upper(),
        issue.category,
        issue.message,
      )


def get_compliance_summary(
  reports: dict[str, ComplianceReport],
) -> dict[str, Any]:
  """Get summary of multiple compliance reports.

  Args:
      reports: Dictionary of compliance reports

  Returns:
      Summary dictionary

  Examples:
      >>> reports = validate_all_managers(manager1, manager2)
      >>> summary = get_compliance_summary(reports)
      >>> print(f"Average score: {summary['average_score']}")
  """
  if not reports:
    return {
      "manager_count": 0,
      "compliant_count": 0,
      "average_score": 0,
      "total_issues": 0,
    }

  compliant_count = sum(1 for r in reports.values() if r.is_compliant)
  total_issues = sum(len(r.issues) for r in reports.values())
  average_score = sum(r.score for r in reports.values()) / len(reports)

  return {
    "manager_count": len(reports),
    "compliant_count": compliant_count,
    "non_compliant_count": len(reports) - compliant_count,
    "average_score": round(average_score, 1),
    "total_issues": total_issues,
    "error_count": sum(
      sum(1 for i in r.issues if i.severity == "error") for r in reports.values()
    ),
    "warning_count": sum(
      sum(1 for i in r.issues if i.severity == "warning") for r in reports.values()
    ),
    "info_count": sum(
      sum(1 for i in r.issues if i.severity == "info") for r in reports.values()
    ),
  }


# Compliance levels

PLATINUM_COMPLIANCE_THRESHOLD = 95
GOLD_COMPLIANCE_THRESHOLD = 85
SILVER_COMPLIANCE_THRESHOLD = 70
BRONZE_COMPLIANCE_THRESHOLD = 50


def get_compliance_level(score: int) -> str:
  """Get compliance level from score.

  Args:
      score: Compliance score (0-100)

  Returns:
      Compliance level name

  Examples:
      >>> get_compliance_level(98)
      'platinum'
      >>> get_compliance_level(72)
      'silver'
  """
  if score >= PLATINUM_COMPLIANCE_THRESHOLD:
    return "platinum"
  if score >= GOLD_COMPLIANCE_THRESHOLD:
    return "gold"
  if score >= SILVER_COMPLIANCE_THRESHOLD:
    return "silver"
  if score >= BRONZE_COMPLIANCE_THRESHOLD:
    return "bronze"
  return "needs_improvement"
