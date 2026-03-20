"""Tests for the ``custom_components.pawcontrol.flows`` package."""

import custom_components.pawcontrol.flows as flows


def test_flows_package_has_expected_docstring() -> None:
    """The flows package should expose its module-level documentation."""
    assert (
        flows.__doc__
        == "Flow-specific mixins for Paw Control configuration and options."
    )
