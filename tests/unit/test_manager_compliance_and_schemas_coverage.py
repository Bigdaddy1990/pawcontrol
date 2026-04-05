"""Targeted coverage tests for manager_compliance.py and schemas.py."""

import pytest

from custom_components.pawcontrol.manager_compliance import (
    ComplianceReport,
    check_required_methods,
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


@pytest.mark.unit
def test_validate_json_schema_payload_rejects_non_dict_payload() -> None:
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}

    violations = validate_json_schema_payload(["not", "a", "dict"], schema)

    assert len(violations) == 1
    assert violations[0].field == "payload"
    assert violations[0].constraint == "type"


@pytest.mark.unit
def test_validate_json_schema_payload_flags_additional_properties() -> None:
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
def test_validate_json_schema_payload_applies_enum_length_and_numeric_constraints() -> (
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
def test_validate_json_schema_payload_accepts_union_numeric_types() -> None:
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
def test_schema_violation_init() -> None:
    v = SchemaViolation(field="name", value=None, constraint="required")
    assert v.field == "name"
    assert v.constraint == "required"
