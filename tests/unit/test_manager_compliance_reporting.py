"""Additional unit tests for manager compliance reporting helpers."""

from unittest.mock import Mock

from custom_components.pawcontrol.manager_compliance import (
    ComplianceIssue,
    ComplianceReport,
    get_compliance_level,
    get_compliance_summary,
    print_compliance_report,
)


def test_compliance_issue_to_dict_round_trips_fields() -> None:
    """Issue dictionaries should preserve all configured metadata."""
    issue = ComplianceIssue(
        severity="warning",
        category="interface",
        message="Missing required method",
        manager_name="WalkManager",
        details={"method": "async_setup"},
    )

    assert issue.to_dict() == {
        "severity": "warning",
        "category": "interface",
        "message": "Missing required method",
        "manager_name": "WalkManager",
        "details": {"method": "async_setup"},
    }


def test_compliance_report_add_issue_updates_state_and_score() -> None:
    """Severity levels should update compliance flags and score deductions."""
    report = ComplianceReport(manager_name="FeedingManager")

    report.add_issue("warning", "docs", "Doc is short")
    report.add_issue("info", "docs", "Minor wording")

    assert report.is_compliant is True
    assert report.score == 85

    report.add_issue("error", "interface", "Missing async_setup")

    assert report.is_compliant is False
    assert report.score == 60


def test_get_compliance_summary_and_levels_cover_threshold_edges() -> None:
    """Summary counters and level thresholds should match documented behavior."""
    first = ComplianceReport(manager_name="One", is_compliant=True, score=95)
    second = ComplianceReport(manager_name="Two", is_compliant=False, score=48)
    second.add_issue("error", "interface", "broken")
    second.add_issue("warning", "docs", "warn")
    second.add_issue("info", "docs", "note")

    summary = get_compliance_summary({"one": first, "two": second})

    assert summary == {
        "manager_count": 2,
        "compliant_count": 1,
        "non_compliant_count": 1,
        "average_score": 51.5,
        "total_issues": 3,
        "error_count": 1,
        "warning_count": 1,
        "info_count": 1,
    }

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


def test_print_compliance_report_uses_severity_specific_logger_methods() -> None:
    """Issue severity should select matching logger methods with fallback to info."""
    report = ComplianceReport(manager_name="DogManager", score=80)
    report.issues.extend([
        ComplianceIssue("error", "interface", "err", "DogManager"),
        ComplianceIssue("warning", "lifecycle", "warn", "DogManager"),
        ComplianceIssue("info", "documentation", "info", "DogManager"),
        ComplianceIssue("custom", "documentation", "fallback", "DogManager"),
    ])

    logger = Mock()

    print_compliance_report(report, logger)

    assert logger.error.call_count == 1
    assert logger.warning.call_count == 1
    assert logger.info.call_count == 4
