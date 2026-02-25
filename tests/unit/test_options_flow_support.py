"""Tests for options flow support re-export helpers."""

from custom_components.pawcontrol import options_flow_support
from custom_components.pawcontrol.repairs import async_create_issue
from custom_components.pawcontrol.runtime_data import (
    get_runtime_data,
    require_runtime_data,
)


def test_options_flow_support_re_exports_runtime_helpers() -> None:
    """The support module should expose runtime helpers for compatibility."""
    assert options_flow_support.get_runtime_data is get_runtime_data
    assert options_flow_support.require_runtime_data is require_runtime_data


def test_options_flow_support_re_exports_issue_helper() -> None:
    """The support module should re-export issue creation helper."""
    assert options_flow_support.async_create_issue is async_create_issue


def test_options_flow_support_all_exports() -> None:
    """The exported symbol list should stay stable for importers."""
    assert options_flow_support.__all__ == [
        "async_create_issue",
        "get_runtime_data",
        "require_runtime_data",
    ]
