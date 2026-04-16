"""Targeted coverage tests for manager_compliance.py and schemas.py."""

import logging

import pytest

from custom_components.pawcontrol.base_manager import BaseManager
from custom_components.pawcontrol.manager_compliance import (
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
from custom_components.pawcontrol.schemas import (
    SchemaViolation,
    validate_json_schema_payload,
)


@pytest.mark.unit
def test_compliance_report_defaults_and_custom_values() -> None:
    """ComplianceReport should expose expected defaults and accept overrides."""
    report = ComplianceReport(manager_name="TestManager")
    assert report.is_compliant is True
    assert report.manager_name == "TestManager"
    assert report.score == 100
    assert report.issues == []

    custom = ComplianceReport(manager_name="BadManager", is_compliant=False, score=50)
    assert custom.is_compliant is False
    assert custom.score == 50


@pytest.mark.unit
def test_check_required_methods_records_missing_and_non_callable() -> None:
    """Required-method validation should detect missing and non-callable methods."""

    class BrokenManager:
        async_setup = "not callable"

        async def async_shutdown(self) -> None:
            """Shutdown."""

    report = ComplianceReport(manager_name="BrokenManager")

    check_required_methods(BrokenManager, report)

    messages = {issue.message for issue in report.issues}
    assert "async_setup is not callable" in messages
    assert "Missing required method: get_diagnostics" in messages


@pytest.mark.unit
def test_check_required_methods_accepts_valid_methods() -> None:
    """Required-method validation should not add issues for valid managers."""

    class GoodManager:
        async def async_setup(self) -> None:
            """Setup."""

        async def async_shutdown(self) -> None:
            """Shutdown."""

        def get_diagnostics(self) -> dict[str, bool]:
            """Diagnostics."""
            return {"ok": True}

    report = ComplianceReport(manager_name="GoodManager")

    check_required_methods(GoodManager, report)

    assert report.issues == []


@pytest.mark.unit
def test_validate_json_schema_payload_valid() -> None:  # noqa: D103
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    violations = validate_json_schema_payload({"name": "Rex"}, schema)
    assert isinstance(violations, list)
    assert len(violations) == 0


@pytest.mark.unit
def test_validate_json_schema_payload_missing_required() -> None:  # noqa: D103
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    violations = validate_json_schema_payload({}, schema)
    assert isinstance(violations, list)
    assert len(violations) >= 1


@pytest.mark.unit
def test_validate_json_schema_payload_wrong_type() -> None:  # noqa: D103
    schema = {"type": "object", "properties": {"age": {"type": "integer"}}}
    violations = validate_json_schema_payload({"age": "not_a_number"}, schema)
    assert isinstance(violations, list)


@pytest.mark.unit
def test_validate_json_schema_payload_empty_payload() -> None:  # noqa: D103
    schema = {"type": "object"}
    violations = validate_json_schema_payload({}, schema)
    assert isinstance(violations, list)


@pytest.mark.unit
def test_validate_json_schema_payload_rejects_non_dict_payload() -> None:  # noqa: D103
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}

    violations = validate_json_schema_payload(["not", "a", "dict"], schema)

    assert len(violations) == 1
    assert violations[0].field == "payload"
    assert violations[0].constraint == "type"


@pytest.mark.unit
def test_validate_json_schema_payload_flags_additional_properties() -> None:  # noqa: D103
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "additionalProperties": False,
    }

    violations = validate_json_schema_payload(
        {"name": "Rex", "unknown": "value"},
        schema,
    )

    assert len(violations) == 1
    assert violations[0].field == "unknown"
    assert violations[0].constraint == "additional"


@pytest.mark.unit
def test_validate_json_schema_payload_applies_enum_length_and_numeric_constraints() -> (  # noqa: D103
    None
):
    schema = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["auto", "manual"]},
            "alias": {"type": "string", "minLength": 3, "maxLength": 4},
            "radius": {"type": "integer", "minimum": 10, "maximum": 20},
            "stride": {"type": "integer", "multipleOf": 3},
            "optional": {"type": ["number", "null"]},
            "armed": {"type": "boolean"},
        },
    }

    violations = validate_json_schema_payload(
        {
            "mode": "invalid",
            "alias": "ab",
            "radius": 25,
            "stride": 4,
            "optional": None,
            "armed": True,
        },
        schema,
    )

    by_field = {(item.field, item.constraint) for item in violations}
    assert ("mode", "enum") in by_field
    assert ("alias", "minLength") in by_field
    assert ("radius", "maximum") in by_field
    assert ("stride", "multipleOf") in by_field


@pytest.mark.unit
def test_validate_json_schema_payload_accepts_union_numeric_types() -> None:  # noqa: D103
    schema = {
        "type": "object",
        "properties": {
            "threshold": {"type": ["number", "null"], "minimum": 1, "maximum": 3},
            "count": {"type": "integer", "minimum": 1, "maximum": 3},
        },
    }

    violations = validate_json_schema_payload(
        {"threshold": 0.5, "count": 0},
        schema,
    )

    by_field = {(item.field, item.constraint) for item in violations}
    assert ("threshold", "minimum") in by_field
    assert ("count", "minimum") in by_field


@pytest.mark.unit
def test_schema_violation_init() -> None:  # noqa: D103
    v = SchemaViolation(field="name", value=None, constraint="required")
    assert v.field == "name"
    assert v.constraint == "required"


class _CompliantManager(BaseManager):
    """A fully compliant manager implementation for tests."""

    MANAGER_NAME = "Compliant"
    MANAGER_VERSION = "1.0.0"
    is_setup = True
    is_shutdown = False
    is_ready = True

    async def async_setup(self) -> None:
        """Set up resources."""

    async def async_shutdown(self) -> None:
        """Shut down resources."""

    def get_diagnostics(self) -> dict[str, bool]:
        """Return diagnostics."""
        return {"ok": True}


@pytest.mark.unit
def test_compliance_report_add_issue_updates_score_and_counts() -> None:  # noqa: D103
    report = ComplianceReport(manager_name="ScoredManager")

    report.add_issue("warning", "lifecycle", "warn")
    report.add_issue("info", "documentation", "info")
    report.add_issue("error", "interface", "error")

    data = report.to_dict()
    assert report.is_compliant is False
    assert report.score == 60
    assert data["error_count"] == 1
    assert data["warning_count"] == 1
    assert data["info_count"] == 1


@pytest.mark.unit
def test_lifecycle_constants_and_signature_checks_emit_expected_issues() -> None:  # noqa: D103
    class SignatureManager:
        MANAGER_NAME = 123

        def async_setup(self, extra: str) -> None:
            """Bad signature."""

        def async_shutdown(self, reason: str) -> None:
            """Bad signature."""

        def get_diagnostics(self, include_all: bool) -> dict[str, bool]:
            """Bad signature."""
            return {"ok": include_all}

    report = ComplianceReport(manager_name="SignatureManager")

    check_lifecycle_properties(SignatureManager, report)
    check_manager_constants(SignatureManager, report)
    check_method_signatures(SignatureManager, report)

    messages = {issue.message for issue in report.issues}
    assert "Missing lifecycle property: is_setup" in messages
    assert "MANAGER_NAME must be a string" in messages
    assert "Missing MANAGER_VERSION class constant" in messages
    assert "async_setup should have only 'self' parameter" in messages
    assert "async_shutdown should have only 'self' parameter" in messages
    assert "get_diagnostics should have only 'self' parameter" in messages


@pytest.mark.unit
def test_documentation_and_inheritance_checks_emit_expected_issues() -> None:  # noqa: D103
    class NoDocsManager:
        MANAGER_NAME = "NoDocs"
        MANAGER_VERSION = "1.0.0"
        is_setup = True
        is_shutdown = False
        is_ready = True

        async def async_setup(self) -> None:
            pass

        async def async_shutdown(self) -> None:
            pass

        def get_diagnostics(self) -> dict[str, bool]:
            return {"ok": True}

    report = ComplianceReport(manager_name="NoDocs")
    check_documentation(NoDocsManager, report)
    check_inheritance(NoDocsManager, report)

    messages = {issue.message for issue in report.issues}
    assert "Missing class docstring" in messages
    assert "Missing docstring for async_setup" in messages
    assert "Missing docstring for async_shutdown" in messages
    assert "Missing docstring for get_diagnostics" in messages
    assert "Manager does not inherit from BaseManager" in messages


@pytest.mark.unit
def test_validate_manager_and_summary_helpers() -> None:  # noqa: D103
    report_class = validate_manager_compliance(_CompliantManager)
    report_instance = validate_manager_compliance(_CompliantManager(hass=object()))

    assert report_class.manager_name == "Compliant"
    assert report_class.is_compliant is True
    assert report_class.score == 100
    assert report_instance.is_compliant is True

    reports = validate_all_managers(_CompliantManager)
    summary = get_compliance_summary(reports)
    assert summary["manager_count"] == 1
    assert summary["compliant_count"] == 1
    assert summary["average_score"] == 100.0
    assert get_compliance_summary({}) == {
        "manager_count": 0,
        "compliant_count": 0,
        "average_score": 0,
        "total_issues": 0,
    }


@pytest.mark.unit
def test_print_report_and_compliance_levels(caplog: pytest.LogCaptureFixture) -> None:  # noqa: D103
    report = ComplianceReport(manager_name="LoggerManager")
    report.add_issue("warning", "interface", "warning-message")
    report.add_issue("error", "interface", "error-message")
    report.add_issue("info", "documentation", "info-message")

    logger = logging.getLogger("tests.manager_compliance")
    with caplog.at_level(logging.INFO, logger=logger.name):
        print_compliance_report(report, logger=logger)

    messages = {record.getMessage() for record in caplog.records}
    assert any("Compliance report for LoggerManager" in msg for msg in messages)
    assert any("warning-message" in msg for msg in messages)
    assert any("error-message" in msg for msg in messages)
    assert any("info-message" in msg for msg in messages)

    assert get_compliance_level(95) == "platinum"
    assert get_compliance_level(85) == "gold"
    assert get_compliance_level(70) == "silver"
    assert get_compliance_level(50) == "bronze"
    assert get_compliance_level(49) == "needs_improvement"
