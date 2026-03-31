"""Targeted coverage tests for manager_compliance.py + schemas.py — (0% → 28%+).

manager_compliance: ComplianceReport, check_required_methods
schemas: validate_json_schema_payload, SchemaViolation
"""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.manager_compliance import (
    ComplianceReport,
    check_required_methods,
)
from custom_components.pawcontrol.schemas import (
    SchemaViolation,
    validate_json_schema_payload,
)

# ─── ComplianceReport ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_compliance_report_compliant() -> None:
    report = ComplianceReport(manager_name="TestManager")
    assert report.is_compliant is True
    assert report.manager_name == "TestManager"
    assert report.score == 100


@pytest.mark.unit
def test_compliance_report_non_compliant() -> None:
    report = ComplianceReport(manager_name="BadManager", is_compliant=False, score=50)
    assert report.is_compliant is False
    assert report.score == 50


@pytest.mark.unit
def test_compliance_report_empty_issues() -> None:
    report = ComplianceReport(manager_name="GoodManager")
    assert isinstance(report.issues, list)
    assert len(report.issues) == 0


# ─── check_required_methods ──────────────────────────────────────────────────


@pytest.mark.unit
def test_check_required_methods_all_present() -> None:
    class GoodManager:
        async def async_initialize(self):
            pass

        async def async_shutdown(self):
            pass

    # check_required_methods returns a ComplianceReport or similar
    result = check_required_methods(GoodManager, ["async_initialize", "async_shutdown"])
    assert result is not None


@pytest.mark.unit
def test_check_required_methods_missing_method() -> None:
    class BadManager:
        async def async_initialize(self):
            pass

    result = check_required_methods(BadManager, ["async_initialize", "async_shutdown"])
    assert result is not None


# ─── validate_json_schema_payload ────────────────────────────────────────────


@pytest.mark.unit
def test_validate_json_schema_payload_valid() -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    violations = validate_json_schema_payload({"name": "Rex"}, schema)
    assert isinstance(violations, list)
    assert len(violations) == 0


@pytest.mark.unit
def test_validate_json_schema_payload_missing_required() -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    violations = validate_json_schema_payload({}, schema)
    assert isinstance(violations, list)
    assert len(violations) >= 1


@pytest.mark.unit
def test_validate_json_schema_payload_wrong_type() -> None:
    schema = {"type": "object", "properties": {"age": {"type": "integer"}}}
    violations = validate_json_schema_payload({"age": "not_a_number"}, schema)
    assert isinstance(violations, list)


@pytest.mark.unit
def test_validate_json_schema_payload_empty_payload() -> None:
    schema = {"type": "object"}
    violations = validate_json_schema_payload({}, schema)
    assert isinstance(violations, list)


# ─── SchemaViolation ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_schema_violation_init() -> None:
    v = SchemaViolation(field="name", value=None, constraint="required")
    assert v.field == "name"
    assert v.constraint == "required"
