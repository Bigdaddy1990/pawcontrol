"""Comprehensive branch coverage tests for manager_compliance helpers."""

import logging
from unittest.mock import Mock

from custom_components.pawcontrol.base_manager import BaseManager
from custom_components.pawcontrol.manager_compliance import (
    ComplianceIssue,
    ComplianceReport,
    check_documentation,
    check_inheritance,
    check_lifecycle_properties,
    check_manager_constants,
    check_method_signatures,
    check_required_methods,
    get_compliance_level,
    get_compliance_summary,
    print_compliance_report,
    validate_all_managers,
    validate_manager_compliance,
)


class _ValidManager(BaseManager):
    """A fully documented manager used for green-path checks."""

    MANAGER_NAME = "valid"
    MANAGER_VERSION = "1.0"
    is_setup = False
    is_shutdown = False
    is_ready = True

    async def async_setup(self) -> None:
        """Set up resources for the manager lifecycle."""

    async def async_shutdown(self) -> None:
        """Shut down resources for the manager lifecycle."""

    def get_diagnostics(self) -> dict[str, str]:
        """Return diagnostics payload for introspection."""
        return {"status": "ok"}


class _BrokenInterface:
    """short."""

    MANAGER_NAME = 42

    async def async_setup(self, payload: str) -> None:
        """Set up with payload."""

    async def async_shutdown(self, reason: str) -> None:
        """Shut down with reason."""

    def get_diagnostics(self, verbose: bool = False) -> dict[str, bool]:
        return {"verbose": verbose}


class _NonCallableMethod:
    async_setup = "oops"


class _NoDocManager(BaseManager):
    MANAGER_NAME = "nodoc"
    MANAGER_VERSION = "1.0"

    async def async_setup(self) -> None:
        pass

    async def async_shutdown(self) -> None:
        pass

    def get_diagnostics(self) -> dict[str, str]:
        return {}


def test_check_required_methods_reports_missing_and_non_callable() -> None:
    """Required method checker should report both missing and wrong callables."""
    report = ComplianceReport(manager_name="broken")
    check_required_methods(_NonCallableMethod, report)

    messages = {issue.message for issue in report.issues}
    assert "async_setup is not callable" in messages
    assert "Missing required method: async_shutdown" in messages
    assert "Missing required method: get_diagnostics" in messages


def test_check_lifecycle_properties_and_constants() -> None:
    """Lifecycle and constants checks should emit warnings/errors as expected."""

    class _LifecycleMissing:
        MANAGER_NAME = 123

    report = ComplianceReport(manager_name="life")
    check_lifecycle_properties(_LifecycleMissing, report)
    check_manager_constants(_LifecycleMissing, report)

    messages = {issue.message for issue in report.issues}
    assert "Missing lifecycle property: is_setup" in messages
    assert "Missing lifecycle property: is_shutdown" in messages
    assert "Missing lifecycle property: is_ready" in messages
    assert "MANAGER_NAME must be a string" in messages
    assert "Missing MANAGER_VERSION class constant" in messages


def test_check_method_signatures_warns_for_extra_parameters() -> None:
    """Signature checker should warn when required methods take extra args."""
    report = ComplianceReport(manager_name="sig")
    check_method_signatures(_BrokenInterface, report)

    messages = {issue.message for issue in report.issues}
    assert "async_shutdown should have only 'self' parameter" in messages
    assert "get_diagnostics should have only 'self' parameter" in messages


def test_check_documentation_paths() -> None:
    """Documentation checker should flag short and missing docstrings."""
    report = ComplianceReport(manager_name="docs")
    check_documentation(_BrokenInterface, report)

    messages = {issue.message for issue in report.issues}
    assert "Class docstring is too brief" in messages
    assert "Missing docstring for get_diagnostics" in messages

    report_no_doc = ComplianceReport(manager_name="nodoc")
    check_documentation(_NoDocManager, report_no_doc)
    messages_no_doc = {issue.message for issue in report_no_doc.issues}
    assert "Missing class docstring" in messages_no_doc
    assert "Missing docstring for async_setup" in messages_no_doc
    assert "Missing docstring for async_shutdown" in messages_no_doc
    assert "Missing docstring for get_diagnostics" in messages_no_doc


def test_validate_manager_compliance_class_and_instance_paths() -> None:
    """Validator should support classes and instances and resolve manager names."""
    class_report = validate_manager_compliance(_ValidManager)
    instance_report = validate_manager_compliance(object.__new__(_ValidManager))

    assert class_report.manager_name == "valid"
    assert class_report.issues == []
    assert class_report.is_compliant is True
    assert instance_report.manager_name == "valid"
    assert instance_report.is_compliant is True


def test_check_inheritance_and_validate_all_managers() -> None:
    """Inheritance checker should error for non-BaseManager classes."""
    broken_report = ComplianceReport(manager_name="broken")
    check_inheritance(_BrokenInterface, broken_report)
    assert any(
        issue.message == "Manager does not inherit from BaseManager"
        for issue in broken_report.issues
    )

    reports = validate_all_managers(_ValidManager, _BrokenInterface)
    assert set(reports) == {"valid", 42}
    assert reports["valid"].is_compliant is True
    assert reports[42].is_compliant is False


def test_report_to_dict_and_summary_and_levels() -> None:
    """Report/summary serializers and level helper should cover all branches."""
    report = ComplianceReport(manager_name="demo")
    report.add_issue("error", "interface", "fatal", method="async_setup")
    report.add_issue("warning", "lifecycle", "warn")
    report.add_issue("info", "documentation", "note")

    payload = report.to_dict()
    assert payload["error_count"] == 1
    assert payload["warning_count"] == 1
    assert payload["info_count"] == 1
    assert payload["issues"][0]["details"] == {"method": "async_setup"}

    summary = get_compliance_summary({"demo": report})
    assert summary["manager_count"] == 1
    assert summary["average_score"] == 60.0
    assert summary["non_compliant_count"] == 1

    assert get_compliance_summary({}) == {
        "manager_count": 0,
        "compliant_count": 0,
        "average_score": 0,
        "total_issues": 0,
    }

    assert get_compliance_level(100) == "platinum"
    assert get_compliance_level(90) == "gold"
    assert get_compliance_level(75) == "silver"
    assert get_compliance_level(55) == "bronze"
    assert get_compliance_level(0) == "needs_improvement"


def test_check_manager_constants_missing_name() -> None:
    """Manager constants checker should error when MANAGER_NAME is absent."""

    class _NoManagerName:
        MANAGER_VERSION = "1.0"

    report = ComplianceReport(manager_name="noname")
    check_manager_constants(_NoManagerName, report)

    assert any(
        issue.message == "Missing MANAGER_NAME class constant"
        for issue in report.issues
    )


def test_print_compliance_report_default_and_custom_logger() -> None:
    """Report logging should route severities and default logger fallback."""
    report = ComplianceReport(manager_name="log")
    report.issues.extend([
        ComplianceIssue("error", "interface", "err", "log"),
        ComplianceIssue("warning", "lifecycle", "warn", "log"),
        ComplianceIssue("info", "documentation", "info", "log"),
        ComplianceIssue("custom", "misc", "fallback", "log"),
    ])

    logger = Mock(spec=logging.Logger)
    print_compliance_report(report, logger=logger)
    assert logger.error.call_count == 1
    assert logger.warning.call_count == 1
    assert logger.info.call_count >= 3

    module_logger = Mock(spec=logging.Logger)
    import custom_components.pawcontrol.manager_compliance as mc

    previous = mc._LOGGER
    mc._LOGGER = module_logger
    try:
        print_compliance_report(report)
    finally:
        mc._LOGGER = previous

    assert module_logger.info.called
