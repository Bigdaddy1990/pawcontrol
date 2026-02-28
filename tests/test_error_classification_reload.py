"""Coverage-focused tests for error classification module loading."""

import importlib


def test_error_classification_module_reload_executes_top_level() -> None:
    """Reloading the module should execute its top-level definitions."""
    module = importlib.import_module(
        "custom_components.pawcontrol.error_classification"
    )
    reloaded = importlib.reload(module)

    assert reloaded.classify_error_reason("missing_instance") == "missing_service"
