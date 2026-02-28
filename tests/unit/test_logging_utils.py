"""Tests for logging utility helpers."""

import logging
import sys
import types

import pytest

from custom_components.pawcontrol import logging_utils


def test_redact_sensitive_handles_nested_and_partial_matches() -> None:
    """Sensitive keys should be redacted recursively and case-insensitively."""
    payload = {
        "API_TOKEN": "abc",
        "normal": "value",
        "nested": {"dog_api_token": "secret", "other": 123},
    }

    redacted = logging_utils.redact_sensitive(payload)

    assert redacted == {
        "API_TOKEN": "***REDACTED***",
        "normal": "value",
        "nested": {"dog_api_token": "***REDACTED***", "other": 123},
    }


def test_redact_value_masks_sensitive_key() -> None:
    """Single value redaction should preserve non-sensitive values."""
    assert logging_utils.redact_value("refresh_token", "abc") == "***REDACTED***"
    assert logging_utils.redact_value("dog_name", "Milo") == "Milo"


def test_structured_logger_emits_formatted_context_and_redacts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Structured context should be appended and sensitive keys masked."""
    logger = logging_utils.StructuredLogger("pawcontrol.test.logging")

    with caplog.at_level(logging.INFO, logger="pawcontrol.test.logging"):
        logger.info("Dog %s updated", "Milo", api_token="123", age=4)

    assert "Dog Milo updated" in caplog.text
    assert "api_token='***REDACTED***'" in caplog.text
    assert "age=4" in caplog.text


def test_structured_logger_fallback_for_type_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Bad %-style formatting should fall back without raising."""
    logger = logging_utils.StructuredLogger("pawcontrol.test.typeerror")

    with caplog.at_level(logging.ERROR, logger="pawcontrol.test.typeerror"):
        logger.error("count=%d", "not-an-int", field="x")

    assert "('not-an-int',)" in caplog.text
    assert "field='x'" in caplog.text


def test_structured_logger_fallback_for_value_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid formatting string should be handled via fallback path."""
    logger = logging_utils.StructuredLogger("pawcontrol.test.valueerror")

    with caplog.at_level(logging.WARNING, logger="pawcontrol.test.valueerror"):
        logger.warning("broken %", 1)

    assert "broken %(1,)" in caplog.text


def test_strip_url_credentials_removes_user_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """URLs with username/password should be sanitized."""
    yarl_stub = types.ModuleType("yarl")

    class _URL:
        def __init__(self, url: str) -> None:
            self._url = url
            self.user = "user"
            self.password = "pass"

        def with_user(self, _value: None) -> str:
            return "https://example.com/api"

    yarl_stub.URL = _URL
    monkeypatch.setitem(sys.modules, "yarl", yarl_stub)

    assert (
        logging_utils._strip_url_credentials("https://user:pass@example.com/api")
        == "https://example.com/api"
    )


def test_strip_url_credentials_fallback_on_parse_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Unexpected parser failures should keep URL and emit debug telemetry."""
    yarl_stub = types.ModuleType("yarl")

    def _boom(_url: str) -> object:
        raise ValueError("bad-url")

    yarl_stub.URL = _boom
    monkeypatch.setitem(sys.modules, "yarl", yarl_stub)

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.pawcontrol.logging_utils"
    ):
        result = logging_utils._strip_url_credentials("https://example.com")

    assert result == "https://example.com"
    assert "Failed to strip credentials from PawControl URL" in caplog.text


def test_log_helpers_emit_expected_records(caplog: pytest.LogCaptureFixture) -> None:
    """Public helper functions should emit stable message shapes."""
    logger = logging.getLogger("pawcontrol.test.helpers")

    with caplog.at_level(logging.INFO, logger="pawcontrol.test.helpers"):
        logging_utils.log_config_entry_setup(logger, "entry", 2, "default", 1.23)

    assert "PawControl entry setup complete" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="pawcontrol.test.helpers"):
        logging_utils.log_api_client_build_error(
            logger,
            "https://user:pass@example.com/path",
            RuntimeError("boom"),
        )

    assert "https://example.com/path" in caplog.text
    assert "RuntimeError" in caplog.text


def test_structured_logger_exception_and_level_delegation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Exception logging and level delegation should mirror stdlib logger."""
    logger = logging_utils.StructuredLogger("pawcontrol.test.exception")

    with caplog.at_level(logging.ERROR, logger="pawcontrol.test.exception"):
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.exception("Failed update", dog_name="Milo", api_token="hidden")

    assert "Failed update" in caplog.text
    assert "dog_name='Milo'" in caplog.text
    assert "api_token='***REDACTED***'" in caplog.text
    assert logger.isEnabledFor(logging.ERROR)


def test_get_logger_returns_stdlib_logger() -> None:
    """Public get_logger helper should proxy to logging.getLogger."""
    logger = logging_utils.get_logger("pawcontrol.test.stdlib")

    assert isinstance(logger, logging.Logger)
    assert logger.name == "pawcontrol.test.stdlib"
