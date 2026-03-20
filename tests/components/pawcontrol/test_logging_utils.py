"""Tests for logging and redaction helpers."""

import logging
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


def test_structured_logger_exception_critical_and_is_enabled_for() -> None:
    """StructuredLogger should proxy exception/critical/isEnabledFor helpers."""
    logger = StructuredLogger("pawcontrol.tests.logging.proxy")
    logger.logger.log = Mock()  # type: ignore[method-assign]
    logger.logger.isEnabledFor = Mock(return_value=True)  # type: ignore[method-assign]

    logger.exception("boom", context="test")
    logger.critical("critical", mode="emergency")

    assert logger.isEnabledFor(logging.ERROR) is True
    assert logger.logger.isEnabledFor.call_args_list[-1].args == (logging.ERROR,)

    exception_call = logger.logger.log.call_args_list[0]
    critical_call = logger.logger.log.call_args_list[1]

    assert exception_call.kwargs["exc_info"] is True
    assert "context='test'" in exception_call.args[1]
    assert critical_call.args[0] == logging.CRITICAL
    assert "mode='emergency'" in critical_call.args[1]


def test_log_config_entry_setup_emits_structured_message() -> None:
    """Setup logging helper should include all key setup fields."""
    logger = Mock()

    logging_utils.log_config_entry_setup(
        logger,
        entry_id="entry-123",
        dogs_count=2,
        profile="default",
        duration_s=1.23,
    )

    message, entry_id, dogs_count, profile, duration_s = logger.info.call_args.args
    assert message.startswith("PawControl entry setup complete")
    assert entry_id == "entry-123"
    assert dogs_count == 2
    assert profile == "default"
    assert duration_s == 1.23


def test_structured_logger_warning_and_error_proxy_methods() -> None:
    """warning/error helpers should route through the shared emit path."""
    logger = StructuredLogger("pawcontrol.tests.logging.warning_error")
    logger.logger.log = Mock()  # type: ignore[method-assign]

    logger.warning("warn", dog="Milo")
    logger.error("err", exc_info=True, source="api")

    warning_call = logger.logger.log.call_args_list[0]
    error_call = logger.logger.log.call_args_list[1]

    assert warning_call.args[0] == logging.WARNING
    assert "dog='Milo'" in warning_call.args[1]
    assert error_call.args[0] == logging.ERROR
    assert error_call.kwargs["exc_info"] is True
    assert "source='api'" in error_call.args[1]


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


def test_strip_url_credentials_uses_stdlib_parsing_without_extra_dependencies() -> None:
    """Credential stripping should not depend on optional URL helper packages."""
    assert (
        logging_utils._strip_url_credentials("https://user:pass@example.com/path")
        == "https://example.com/path"
    )


def test_get_logger_returns_stdlib_logger() -> None:
    """get_logger should delegate to logging.getLogger."""
    logger = logging_utils.get_logger("pawcontrol.tests.logger")
    assert isinstance(logger, logging.Logger)


def test_strip_url_credentials_returns_clean_url_when_no_credentials() -> None:
    """URLs without embedded credentials should be returned unchanged."""
    clean_url = "https://example.com/path"

    assert logging_utils._strip_url_credentials(clean_url) == clean_url


def test_strip_url_credentials_logs_debug_when_url_parsing_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credential stripping should log a debug message on parser failures."""
    debug_logger = Mock()
    get_logger = Mock(return_value=debug_logger)
    monkeypatch.setattr(logging_utils.logging, "getLogger", get_logger)

    original_url = "https://user:pass@example.com:bad/path"
    assert logging_utils._strip_url_credentials(original_url) == original_url

    get_logger.assert_called_once_with(logging_utils.__name__)
    debug_logger.debug.assert_called_once_with(
        "Failed to strip credentials from PawControl URL: %s",
        "ValueError",
    )
