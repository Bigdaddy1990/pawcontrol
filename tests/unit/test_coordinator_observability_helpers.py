"""Additional coverage tests for coordinator observability helpers."""

from custom_components.pawcontrol import coordinator_observability


def test_coerce_float_falls_back_for_invalid_values() -> None:
    """Non-numeric and non-finite values should return the provided default."""
    assert coordinator_observability._coerce_float("abc", 9.5) == 9.5
    assert coordinator_observability._coerce_float(object(), 4.2) == 4.2
    assert coordinator_observability._coerce_float(float("inf"), 3.3) == 3.3


def test_coerce_string_list_handles_scalar_and_iterables() -> None:
    """Resilience value coercion should normalize all supported input types."""
    assert coordinator_observability._coerce_string_list("breaker-a") == ["breaker-a"]
    assert coordinator_observability._coerce_string_list(42) == ["42"]
    assert coordinator_observability._coerce_string_list(["a", None, 2]) == ["a", "2"]


def test_stringify_resilience_value_handles_binary_decode_failure() -> None:
    """Invalid bytes should be decoded using the defensive fallback path."""
    assert coordinator_observability._stringify_resilience_value(b"plain") == "plain"

    invalid_binary = bytearray(b"\xff\xfe")
    assert (
        coordinator_observability._stringify_resilience_value(invalid_binary) == ""
    )


def test_build_security_scorecard_includes_webhook_error_payload() -> None:
    """Webhook error details should be preserved in the scorecard diagnostics."""
    scorecard = coordinator_observability.build_security_scorecard(
        adaptive={"target_cycle_ms": 100, "current_interval_ms": 90},
        entity_summary={"peak_utilization": 40.0},
        webhook_status={
            "configured": True,
            "secure": False,
            "hmac_ready": False,
            "insecure_configs": ("dog-1",),
            "error": "probe failed",
        },
    )

    webhook_check = scorecard["checks"]["webhooks"]
    assert webhook_check["error"] == "probe failed"
    assert webhook_check["reason"] == "Webhook configurations missing HMAC protection"
