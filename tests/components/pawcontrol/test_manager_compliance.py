"""Coverage tests for manager_compliance helpers."""

import logging

from custom_components.pawcontrol.base_manager import BaseManager
from custom_components.pawcontrol.manager_compliance import (
    ComplianceReport,
    check_required_methods,
    get_compliance_level,
    get_compliance_summary,
    print_compliance_report,
    validate_all_managers,
    validate_manager_compliance,
)


class MinimalCompliantManager(BaseManager):
    """Manager implementation used for compliance tests."""

    MANAGER_NAME = "MinimalCompliantManager"
    MANAGER_VERSION = "1.2.3"

    async def async_setup(self) -> None:
        """Set up manager resources."""

    async def async_shutdown(self) -> None:
        """Shut down manager resources."""

    def get_diagnostics(self) -> dict[str, str]:
        """Return diagnostics for tests."""
        return {"status": "ok"}


class MissingMethodsManager:
    """Tiny."""

    MANAGER_NAME = 5


class NonCallableMethodsManager(BaseManager):
    """Manager with malformed method attributes."""

    MANAGER_NAME = "NonCallableMethodsManager"
    MANAGER_VERSION = "0.0.1"

    async_setup = "not-callable"
    async_shutdown = "not-callable"
    get_diagnostics = "not-callable"


def test_compliance_report_add_issue_updates_score_and_counts() -> None:
    """Each severity should affect score and counters predictably."""
    report = ComplianceReport(manager_name="TestManager")

    report.add_issue("error", "interface", "missing method")
    report.add_issue("warning", "lifecycle", "missing property")
    report.add_issue("info", "documentation", "brief docstring")

    serialized = report.to_dict()

    assert report.is_compliant is False
    assert report.score == 60
    assert serialized["error_count"] == 1
    assert serialized["warning_count"] == 1
    assert serialized["info_count"] == 1


def test_check_required_methods_detects_non_callables() -> None:
    """Non-callable required method attributes should be flagged as errors."""
    report = ComplianceReport(manager_name="NonCallableMethodsManager")

    check_required_methods(NonCallableMethodsManager, report)

    assert report.is_compliant is False
    assert {issue.message for issue in report.issues} == {
        "async_setup is not callable",
        "async_shutdown is not callable",
        "get_diagnostics is not callable",
    }


def test_validate_manager_compliance_accepts_instance_and_reports_issues() -> None:
    """Validator should normalize instances and capture class-level violations."""
    report = validate_manager_compliance(MissingMethodsManager())

    assert report.manager_name == 5
    assert report.is_compliant is False
    assert any("Missing required method" in issue.message for issue in report.issues)
    assert any(
        issue.message == "MANAGER_NAME must be a string" for issue in report.issues
    )


def test_validate_all_managers_and_summary_for_mixed_reports() -> None:
    """Summary should aggregate compliant and non-compliant manager reports."""
    reports = validate_all_managers(MinimalCompliantManager, MissingMethodsManager)
    summary = get_compliance_summary(reports)

    assert summary["manager_count"] == 2
    assert summary["compliant_count"] == 1
    assert summary["non_compliant_count"] == 1
    assert summary["total_issues"] > 0
    assert summary["error_count"] >= 1


def test_get_compliance_summary_empty_and_threshold_levels() -> None:
    """Empty summary and level thresholds should return canonical values."""
    assert get_compliance_summary({}) == {
        "manager_count": 0,
        "compliant_count": 0,
        "average_score": 0,
        "total_issues": 0,
    }
    assert get_compliance_level(95) == "platinum"
    assert get_compliance_level(85) == "gold"
    assert get_compliance_level(70) == "silver"
    assert get_compliance_level(50) == "bronze"
    assert get_compliance_level(49) == "needs_improvement"


def test_print_compliance_report_logs_with_default_and_custom_severity(
    caplog,
) -> None:
    """Logger routing should handle known and unknown severity entries."""
    report = ComplianceReport(manager_name="LoggerManager")
    report.add_issue("warning", "interface", "warning issue")
    report.issues.append(
        report.issues[0].__class__(
            severity="custom",
            category="misc",
            message="custom severity issue",
            manager_name=report.manager_name,
            details={},
        )
    )

    logger = logging.getLogger("tests.manager_compliance")
    with caplog.at_level(logging.INFO, logger=logger.name):
        print_compliance_report(report, logger=logger)

    assert "Compliance report for LoggerManager" in caplog.text
    assert "[WARNING/interface] warning issue" in caplog.text
    assert "[CUSTOM/misc] custom severity issue" in caplog.text
