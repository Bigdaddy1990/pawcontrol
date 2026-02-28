"""Tests for logging and redaction helpers."""

from __future__ import annotations

import logging
from types import ModuleType
from unittest.mock import Mock

import pytest

from custom_components.pawcontrol import logging_utils
from custom_components.pawcontrol.logging_utils import StructuredLogger


def test_redact_sensitive_redacts_nested_and_partial_sensitive_keys() -> None:
    """Sensitive keys should be redacted recursively."""
    payload = {
        "token": "abc",
        "dog_api_token": "nested",
        "profile": {"password": "secret", "name": "Fido"},
        "safe": "value",
    }

    assert logging_utils.redact_sensitive(payload) == {
        "token": "***REDACTED***",
        "dog_api_token": "***REDACTED***",
        "profile": {"password": "***REDACTED***", "name": "Fido"},
        "safe": "value",
    }


def test_redact_value_only_masks_sensitive_key() -> None:
    """redact_value should keep non-sensitive values untouched."""
    assert logging_utils.redact_value("api_token", "x") == "***REDACTED***"
    assert logging_utils.redact_value("name", "fido") == "fido"


def test_structured_logger_emit_formats_context_and_redacts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Structured logging should append context and hide secrets."""
    caplog.set_level(logging.INFO)
    logger = StructuredLogger("pawcontrol.tests.logging")

    logger.info("Hello %s", "world", api_token="abc", dog="Milo")

    assert "Hello world" in caplog.text
    assert "api_token='***REDACTED***'" in caplog.text
    assert "dog='Milo'" in caplog.text


def test_structured_logger_emit_handles_format_errors() -> None:
    """Formatting failures should gracefully fall back to repr args."""
    logger = StructuredLogger("pawcontrol.tests.logging.format")
    logger.logger.isEnabledFor = Mock(return_value=True)  # type: ignore[method-assign]
    logger.logger.log = Mock()  # type: ignore[method-assign]

    logger.info("bad %d", "x")
    logger.info("bad %", "x")

    first = logger.logger.log.call_args_list[0].args[1]
    second = logger.logger.log.call_args_list[1].args[1]
    assert first == "bad %d('x',)"
    assert second == "bad %('x',)"


def test_structured_logger_emit_skips_when_level_disabled() -> None:
    """No log record should be emitted when logger level is disabled."""
    logger = StructuredLogger("pawcontrol.tests.logging.disabled")
    logger.logger.isEnabledFor = Mock(return_value=False)  # type: ignore[method-assign]
    logger.logger.log = Mock()  # type: ignore[method-assign]

    logger.debug("ignored", foo="bar")

    logger.logger.log.assert_not_called()


def test_log_api_client_build_error_strips_credentials() -> None:
    """API endpoint logs must hide URL user credentials."""
    logger = Mock()

    logging_utils.log_api_client_build_error(
        logger,
        "https://user:pass@example.com/path",
        ValueError("bad"),
    )

    message, safe_endpoint, error_obj, error_cls = logger.warning.call_args.args
    assert message.startswith("Invalid PawControl API endpoint")
    assert safe_endpoint == "https://example.com/path"
    assert str(error_obj) == "bad"
    assert error_cls == "ValueError"


def test_strip_url_credentials_returns_original_when_yarl_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credential stripping should be best-effort when yarl import fails."""
    fake_yarl = ModuleType("yarl")
    monkeypatch.setitem(__import__("sys").modules, "yarl", fake_yarl)

    assert (
        logging_utils._strip_url_credentials("https://user:pass@example.com/path")
        == "https://user:pass@example.com/path"
    )


def test_get_logger_returns_stdlib_logger() -> None:
    """get_logger should delegate to logging.getLogger."""
    logger = logging_utils.get_logger("pawcontrol.tests.logger")
    assert isinstance(logger, logging.Logger)
