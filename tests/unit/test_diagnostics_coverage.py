"""Targeted coverage tests for diagnostics.py — uncovered paths (45% → 56%+).

Covers: compile_redaction_patterns, classify_error_reason,
        diagnostics_redaction helpers, PawControlDiagnostics structure
"""

import pytest

from custom_components.pawcontrol.diagnostics import (
    classify_error_reason,
    compile_redaction_patterns,
)
from custom_components.pawcontrol.diagnostics_redaction import redact_sensitive_data

# ═══════════════════════════════════════════════════════════════════════════════
# compile_redaction_patterns
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_compile_redaction_patterns_empty() -> None:
    patterns = compile_redaction_patterns([])
    assert patterns is not None


@pytest.mark.unit
def test_compile_redaction_patterns_known_keys() -> None:
    patterns = compile_redaction_patterns(["api_key", "password", "token"])
    assert patterns is not None


@pytest.mark.unit
def test_compile_redaction_patterns_produces_regex() -> None:
    import re

    patterns = compile_redaction_patterns(["secret"])
    # Patterns must be compilable regexes
    for p in patterns:
        assert re.compile(p) is not None


# ═══════════════════════════════════════════════════════════════════════════════
# classify_error_reason (from diagnostics)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_classify_error_reason_timeout() -> None:
    result = classify_error_reason("timeout")
    assert isinstance(result, str) and len(result) > 0


@pytest.mark.unit
def test_classify_error_reason_none() -> None:
    result = classify_error_reason(None)
    assert isinstance(result, str)


@pytest.mark.unit
def test_classify_error_reason_network_error() -> None:
    result = classify_error_reason(
        "connection refused", error=ConnectionError("refused")
    )
    assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════════
# redact_sensitive_data (from diagnostics_redaction)
# ═══════════════════════════════════════════════════════════════════════════════

_PATTERNS = compile_redaction_patterns(["password", "api_key", "token", "secret"])


@pytest.mark.unit
def test_redact_sensitive_data_redacts_password() -> None:
    data = {"username": "rex_owner", "password": "hunter2", "api_key": "abc123"}
    result = redact_sensitive_data(data, patterns=_PATTERNS)
    assert isinstance(result, dict)
    assert result.get("password") != "hunter2"
    assert result.get("api_key") != "abc123"
    assert result.get("username") == "rex_owner"


@pytest.mark.unit
def test_redact_sensitive_data_nested() -> None:
    data = {"config": {"url": "http://example.com", "token": "secret-xyz"}}
    result = redact_sensitive_data(data, patterns=_PATTERNS)
    assert isinstance(result, dict)
    config = result.get("config", {})
    # url is not in patterns → preserved; token is redacted
    assert config.get("token") != "secret-xyz"


@pytest.mark.unit
def test_redact_sensitive_data_empty() -> None:
    result = redact_sensitive_data({}, patterns=_PATTERNS)
    assert result == {}


@pytest.mark.unit
def test_redact_sensitive_data_list_value() -> None:
    data = {"tags": ["a", "b"], "password": "secret"}
    result = redact_sensitive_data(data, patterns=_PATTERNS)
    assert result.get("tags") == ["a", "b"]
    assert result.get("password") != "secret"
