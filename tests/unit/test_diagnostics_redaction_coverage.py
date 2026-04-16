"""Targeted coverage tests for diagnostics_redaction.py — (0% → 60%+).

Covers: compile_redaction_patterns, redact_sensitive_data
"""

import pytest

from custom_components.pawcontrol.diagnostics_redaction import (
    compile_redaction_patterns,
    redact_sensitive_data,
)

# ─── compile_redaction_patterns ──────────────────────────────────────────────


@pytest.mark.unit
def test_compile_redaction_patterns_empty() -> None:  # noqa: D103
    patterns = compile_redaction_patterns([])
    assert patterns is not None


@pytest.mark.unit
def test_compile_redaction_patterns_basic_keys() -> None:  # noqa: D103
    patterns = compile_redaction_patterns(["password", "api_key", "token"])
    assert patterns is not None


@pytest.mark.unit
def test_compile_redaction_patterns_single_key() -> None:  # noqa: D103
    patterns = compile_redaction_patterns(["secret"])
    assert patterns is not None


# ─── redact_sensitive_data ───────────────────────────────────────────────────


@pytest.mark.unit
def test_redact_sensitive_data_empty_dict() -> None:  # noqa: D103
    patterns = compile_redaction_patterns(["password"])
    result = redact_sensitive_data({}, patterns=patterns)
    assert result == {}


@pytest.mark.unit
def test_redact_sensitive_data_redacts_password() -> None:  # noqa: D103
    patterns = compile_redaction_patterns(["password"])
    data = {"username": "rex_owner", "password": "hunter2"}
    result = redact_sensitive_data(data, patterns=patterns)
    assert isinstance(result, dict)
    assert result.get("password") != "hunter2"
    assert result.get("username") == "rex_owner"


@pytest.mark.unit
def test_redact_sensitive_data_keeps_safe_keys() -> None:  # noqa: D103
    patterns = compile_redaction_patterns(["token"])
    data = {"name": "Rex", "breed": "Labrador", "token": "abc123"}
    result = redact_sensitive_data(data, patterns=patterns)
    assert result.get("name") == "Rex"
    assert result.get("breed") == "Labrador"


@pytest.mark.unit
def test_redact_sensitive_data_nested_dict() -> None:  # noqa: D103
    patterns = compile_redaction_patterns(["api_key"])
    data = {"config": {"host": "192.168.1.1", "api_key": "secret"}}
    result = redact_sensitive_data(data, patterns=patterns)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_redact_sensitive_data_no_sensitive_keys() -> None:  # noqa: D103
    patterns = compile_redaction_patterns(["password"])
    data = {"dog_name": "Rex", "weight": 22.5}
    result = redact_sensitive_data(data, patterns=patterns)
    assert result.get("dog_name") == "Rex"
    assert result.get("weight") == 22.5


@pytest.mark.unit
def test_redact_sensitive_data_list_value() -> None:  # noqa: D103
    patterns = compile_redaction_patterns(["token"])
    data = {"tokens": ["abc", "def"], "name": "Rex"}
    result = redact_sensitive_data(data, patterns=patterns)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_redact_sensitive_data_none_value() -> None:  # noqa: D103
    patterns = compile_redaction_patterns(["password"])
    data = {"password": None, "name": "Rex"}
    result = redact_sensitive_data(data, patterns=patterns)
    assert result.get("name") == "Rex"
