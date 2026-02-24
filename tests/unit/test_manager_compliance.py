"""Tests for manager compliance helpers."""

from __future__ import annotations

import logging
from unittest.mock import Mock

from custom_components.pawcontrol.base_manager import BaseManager
from custom_components.pawcontrol.manager_compliance import (
    ComplianceIssue,
    ComplianceReport,
    get_compliance_level,
    get_compliance_summary,
    print_compliance_report,
    validate_all_managers,
    validate_manager_compliance,
)


class GoodManager(BaseManager):
    """Manager with the expected compliance interface and docs."""

    MANAGER_NAME = "good"
    MANAGER_VERSION = "2.0"

    async def async_setup(self) -> None:
        """Set up."""

    async def async_shutdown(self) -> None:
        """Shut down."""

    def get_diagnostics(self) -> dict[str, str]:
        """Return diagnostics."""
        return {"ok": "yes"}


class MissingManagerBits:
    pass


class WrongSignatureManager(BaseManager):
    """Short doc."""

    MANAGER_NAME = 123

    async def async_setup(self, extra: str) -> None:  # type: ignore[override]
        """Set up manager."""

    async def async_shutdown(self, extra: str) -> None:  # type: ignore[override]
        """Shut down manager."""

    def get_diagnostics(self, full: bool = False) -> dict[str, bool]:  # type: ignore[override]
        return {"full": full}


def test_compliance_issue_and_report_serialization() -> None:
    """Issue/report dataclasses should serialize consistently."""
    issue = ComplianceIssue(
        severity="warning",
        category="interface",
        message="Needs MANAGER_VERSION",
        manager_name="test",
    )
    assert issue.to_dict() == {
        "severity": "warning",
        "category": "interface",
        "message": "Needs MANAGER_VERSION",
        "manager_name": "test",
        "details": {},
    }

    report = ComplianceReport("demo")
    report.add_issue("error", "interface", "fatal")
    report.add_issue("warning", "lifecycle", "warn")
    report.add_issue("info", "documentation", "info")

    data = report.to_dict()
    assert data["is_compliant"] is False
    assert data["score"] == 60
    assert data["error_count"] == 1
    assert data["warning_count"] == 1
    assert data["info_count"] == 1


def test_validate_manager_compliance_detects_common_problems() -> None:
    """Validation should report inheritance, interface and docs issues."""
    report = validate_manager_compliance(MissingManagerBits)

    assert report.manager_name == "MissingManagerBits"
    assert report.is_compliant is False
    assert report.score < 100
    messages = {issue.message for issue in report.issues}
    assert "Manager does not inherit from BaseManager" in messages
    assert "Missing required method: async_setup" in messages
    assert "Missing lifecycle property: is_setup" in messages
    assert "Missing MANAGER_NAME class constant" in messages
    assert "Missing class docstring" in messages


def test_validate_manager_compliance_checks_signatures_and_doc_lengths() -> None:
    """Signature mismatch and short docs should downgrade with warnings/info."""
    report = validate_manager_compliance(WrongSignatureManager)
    messages = {issue.message for issue in report.issues}

    assert "MANAGER_NAME must be a string" in messages
    assert "async_setup should have only 'self' parameter" in messages
    assert "async_shutdown should have only 'self' parameter" in messages
    assert "get_diagnostics should have only 'self' parameter" in messages
    assert "Class docstring is too brief" in messages
    assert "Missing docstring for get_diagnostics" in messages


def test_validate_all_managers_and_summary_support_instances() -> None:
    """Aggregate validation and summary stats should include compliant managers."""
    good_instance = object.__new__(GoodManager)
    reports = validate_all_managers(good_instance, MissingManagerBits)

    assert set(reports) == {"good", "MissingManagerBits"}
    summary = get_compliance_summary(reports)
    assert summary["manager_count"] == 2
    assert summary["compliant_count"] == 1
    assert summary["non_compliant_count"] == 1
    assert summary["total_issues"] >= 1
    assert summary["error_count"] >= 1


def test_compliance_summary_handles_empty_input() -> None:
    """Summary should return zero stats for empty reports."""
    assert get_compliance_summary({}) == {
        "manager_count": 0,
        "compliant_count": 0,
        "average_score": 0,
        "total_issues": 0,
    }


def test_print_compliance_report_logs_expected_levels() -> None:
    """Printing reports should dispatch to severity-specific logger methods."""
    report = ComplianceReport("demo")
    report.add_issue("error", "interface", "fatal")
    report.add_issue("warning", "interface", "careful")
    report.add_issue("info", "documentation", "heads-up")
    report.add_issue("custom", "interface", "fallback to info")

    logger = Mock(spec=logging.Logger)
    print_compliance_report(report, logger=logger)

    assert logger.info.call_count >= 3
    logger.error.assert_called_once()
    logger.warning.assert_called_once()


def test_get_compliance_level_thresholds() -> None:
    """All compliance bands should resolve to the right labels."""
    assert get_compliance_level(95) == "platinum"
    assert get_compliance_level(85) == "gold"
    assert get_compliance_level(70) == "silver"
    assert get_compliance_level(50) == "bronze"
    assert get_compliance_level(49) == "needs_improvement"
