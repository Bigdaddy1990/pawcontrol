"""Coverage tests for error classification helpers."""

from custom_components.pawcontrol.error_classification import classify_error_reason


def test_classify_error_reason_prefers_explicit_reason_mapping() -> None:
    """Known reason strings map directly to stable classifications."""
    assert classify_error_reason("missing_instance") == "missing_service"
    assert classify_error_reason("service_not_executed") == "guard_skipped"
    assert classify_error_reason("authentication_failed") == "auth_error"


def test_classify_error_reason_detects_auth_from_error_message() -> None:
    """Authentication hints in free-form errors produce auth_error."""
    assert classify_error_reason(None, error="Forbidden by remote API") == "auth_error"


def test_classify_error_reason_detects_unreachable_from_exception() -> None:
    """Network hints found in exception text classify device reachability."""
    error = RuntimeError("Connection refused while contacting endpoint")
    assert classify_error_reason(None, error=error) == "device_unreachable"


def test_classify_error_reason_detects_timeout_and_rate_limit() -> None:
    """Timeout and rate-limit errors classify independently."""
    assert (
        classify_error_reason(None, error="Deadline exceeded waiting for response")
        == "timeout"
    )
    assert classify_error_reason(None, error="429 too many requests") == "rate_limited"


def test_classify_error_reason_classifies_exception_reason_and_unknown() -> None:
    """Fallback reason handling distinguishes exception and unknown buckets."""
    assert classify_error_reason("exception", error=None) == "exception"
    assert classify_error_reason("not_a_known_reason", error=object()) == "unknown"


def test_classify_error_reason_normalises_case_and_whitespace() -> None:
    """Reason lookup should be resilient to casing and surrounding spaces."""
    assert classify_error_reason("  Authentication_Failed  ") == "auth_error"


def test_classify_error_reason_handles_empty_reason_without_error() -> None:
    """Blank inputs should be reduced to the unknown classification."""
    assert classify_error_reason("   ", error=None) == "unknown"
