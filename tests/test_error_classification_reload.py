"""Tests for verifying error classification module reload behavior.

This test ensures top-level constants and helper definitions are re-executed
when the module is reloaded.
"""

import importlib

from custom_components.pawcontrol import error_classification


def test_error_classification_module_reload_executes_top_level() -> None:
    """Reloading the module should preserve expected classifications."""
    importlib.reload(error_classification)

    assert (
        error_classification.classify_error_reason("missing_instance")
        == "missing_service"
    )
    assert error_classification.classify_error_reason("service_not_executed") == (
        "guard_skipped"
    )
    assert error_classification.classify_error_reason(None, error="Timed out") == (
        "timeout"
    )
