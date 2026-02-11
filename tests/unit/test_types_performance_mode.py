"""Tests for performance mode normalization helpers."""

from __future__ import annotations

from custom_components.pawcontrol.const import (
    DEFAULT_PERFORMANCE_MODE,
    PERFORMANCE_MODES,
)
from custom_components.pawcontrol.types import normalize_performance_mode


def test_normalize_performance_mode_accepts_alias() -> None:
    """The legacy 'standard' alias normalises to the balanced mode."""

    assert normalize_performance_mode("standard") == "balanced"


def test_normalize_performance_mode_accepts_current_alias() -> None:
    """Existing options using the alias remain stable during normalization."""

    assert normalize_performance_mode(None, current="standard") == "balanced"


def test_performance_modes_match_select_options() -> None:
    """Select options stay aligned with the canonical performance modes."""

    assert PERFORMANCE_MODES == ("minimal", DEFAULT_PERFORMANCE_MODE, "full")
    for mode in PERFORMANCE_MODES:
        assert normalize_performance_mode(mode) == mode


def test_normalize_performance_mode_is_case_insensitive() -> None:
    """Case differences do not affect the selected performance mode."""

    assert normalize_performance_mode("STANDARD") == "balanced"
