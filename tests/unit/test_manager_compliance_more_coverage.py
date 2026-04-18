"""Additional branch coverage for manager_compliance helpers."""

from custom_components.pawcontrol import manager_compliance as mc


class _ProbeLogger:
    """Capture logger calls for compliance report assertions."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def info(self, message: str, *args: object) -> None:
        self.messages.append(("info", message % args if args else message))

    def warning(self, message: str, *args: object) -> None:
        self.messages.append(("warning", message % args if args else message))

    def error(self, message: str, *args: object) -> None:
        self.messages.append(("error", message % args if args else message))


class _BaseLike:
    """A manager stub that satisfies BaseManager inheritance for validation."""

    MANAGER_NAME = "BaseLike"
    MANAGER_VERSION = "1.0"

    async def async_setup(self) -> None:
        """Setup manager."""

    async def async_shutdown(self) -> None:
        """Shutdown manager."""

    def get_diagnostics(self) -> dict[str, object]:
        """Get diagnostics."""
        return {}


class _ManagerWithUnknownSeverity:
    """Manager placeholder for report logging tests."""


def test_print_compliance_report_uses_info_for_unknown_severity() -> None:
    """Unknown severities should fall back to info-level logger output."""
    report = mc.ComplianceReport(manager_name="m")
    report.issues.append(
        mc.ComplianceIssue(
            severity="debug",
            category="interface",
            message="non-standard",
            manager_name="m",
        )
    )

    logger = _ProbeLogger()
    mc.print_compliance_report(report, logger)

    assert ("info", "Found 1 issues:") in logger.messages
    assert (
        "info",
        "  [DEBUG/interface] non-standard",
    ) in logger.messages


def test_validate_all_managers_uses_report_manager_name_keys() -> None:
    """Validation output should key reports by resolved manager name."""

    class ValidManager(_BaseLike):
        """Long enough docstring for documentation checks."""

    reports = mc.validate_all_managers(ValidManager(), ValidManager)

    # Passing both an instance and class should collapse to same MANAGER_NAME key.
    assert list(reports) == ["BaseLike"]
    assert reports["BaseLike"].manager_name == "BaseLike"


def test_get_compliance_summary_counts_issue_severities() -> None:
    """Summary should aggregate compliance and issue counters across reports."""
    first = mc.ComplianceReport(manager_name="first")
    first.add_issue("error", "interface", "missing method")

    second = mc.ComplianceReport(manager_name="second")
    second.add_issue("warning", "docs", "short docstring")
    second.add_issue("info", "docs", "missing method docs")

    summary = mc.get_compliance_summary({"first": first, "second": second})

    assert summary["manager_count"] == 2
    assert summary["compliant_count"] == 1
    assert summary["non_compliant_count"] == 1
    assert summary["total_issues"] == 3
    assert summary["error_count"] == 1
    assert summary["warning_count"] == 1
    assert summary["info_count"] == 1


def test_get_compliance_level_threshold_edges() -> None:
    """Threshold helper should map exact boundaries to expected levels."""
    assert mc.get_compliance_level(mc.PLATINUM_COMPLIANCE_THRESHOLD) == "platinum"
    assert mc.get_compliance_level(mc.GOLD_COMPLIANCE_THRESHOLD) == "gold"
    assert mc.get_compliance_level(mc.SILVER_COMPLIANCE_THRESHOLD) == "silver"
    assert mc.get_compliance_level(mc.BRONZE_COMPLIANCE_THRESHOLD) == "bronze"
    assert (
        mc.get_compliance_level(mc.BRONZE_COMPLIANCE_THRESHOLD - 1)
        == "needs_improvement"
    )


def test_compliance_report_add_issue_unknown_severity_keeps_score() -> None:
    """Unknown severities should not change compliance score."""
    report = mc.ComplianceReport(manager_name="unknown")
    report.add_issue("debug", "misc", "custom severity")
    assert report.score == 100
    assert report.is_compliant is True


def test_check_method_signatures_skips_absent_methods() -> None:
    """Signature checks should no-op when optional methods are absent."""

    class _NoSignatureMethods:
        pass

    report = mc.ComplianceReport(manager_name="nosig")
    mc.check_method_signatures(_NoSignatureMethods, report)
    assert report.issues == []


def test_check_documentation_skips_missing_methods_without_issue() -> None:
    """Documentation checks should skip method-doc checks for absent methods."""

    class _PartialManager:
        """Long enough manager docs to avoid brief-docstring warning."""

        async def async_setup(self) -> None:
            """Setup docs."""

    report = mc.ComplianceReport(manager_name="partial")
    mc.check_documentation(_PartialManager, report)
    assert report.issues == []


def test_print_compliance_report_without_issues_logs_summary_only() -> None:
    """Printing a clean report should not emit per-issue log lines."""
    report = mc.ComplianceReport(manager_name="clean")
    logger = _ProbeLogger()
    mc.print_compliance_report(report, logger)

    assert ("info", "Compliance report for clean: score=100/100, compliant=True") in (
        logger.messages
    )
    assert all("Found" not in message for _level, message in logger.messages)
