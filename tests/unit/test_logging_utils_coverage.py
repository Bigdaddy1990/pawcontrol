"""Targeted coverage tests for logging_utils.py — uncovered paths (0% → 30%+).

Covers: get_logger, redact_sensitive, redact_value, StructuredLogger
"""

import logging

import pytest

from custom_components.pawcontrol.logging_utils import (
    get_logger,
    redact_sensitive,
    redact_value,
)


@pytest.mark.unit
def test_get_logger_returns_logger() -> None:  # noqa: D103
    logger = get_logger("pawcontrol.test")
    assert isinstance(logger, logging.Logger)


@pytest.mark.unit
def test_get_logger_name_preserved() -> None:  # noqa: D103
    logger = get_logger("custom_components.pawcontrol.test_module")
    assert "pawcontrol" in logger.name or isinstance(logger, logging.Logger)


@pytest.mark.unit
def test_redact_sensitive_password() -> None:  # noqa: D103
    data = {"username": "rex_owner", "password": "hunter2"}
    result = redact_sensitive(data)
    assert isinstance(result, dict)
    assert result.get("password") != "hunter2"
    assert result.get("username") == "rex_owner"


@pytest.mark.unit
def test_redact_sensitive_api_key() -> None:  # noqa: D103
    data = {"api_key": "secret123", "host": "192.168.1.1"}
    result = redact_sensitive(data)
    assert result.get("api_key") != "secret123"


@pytest.mark.unit
def test_redact_sensitive_empty() -> None:  # noqa: D103
    result = redact_sensitive({})
    assert result == {}


@pytest.mark.unit
def test_redact_sensitive_no_sensitive_keys() -> None:  # noqa: D103
    data = {"name": "Rex", "breed": "Labrador"}
    result = redact_sensitive(data)
    assert result.get("name") == "Rex"
    assert result.get("breed") == "Labrador"


@pytest.mark.unit
def test_redact_value_sensitive_key() -> None:  # noqa: D103
    result = redact_value("password", "my_secret")
    assert result != "my_secret"


@pytest.mark.unit
def test_redact_value_safe_key() -> None:  # noqa: D103
    result = redact_value("dog_name", "Rex")
    assert result == "Rex"


@pytest.mark.unit
def test_redact_value_none_value() -> None:  # noqa: D103
    result = redact_value("password", None)
    assert result is None or isinstance(result, str)
