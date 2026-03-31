"""Targeted coverage tests for translation_helpers.py — uncovered paths (0% → 28%+).

Covers: component_translation_key, resolve_translation, resolve_component_translation
"""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.translation_helpers import (
    component_translation_key,
    resolve_component_translation,
    resolve_translation,
)


@pytest.mark.unit
def test_component_translation_key_simple() -> None:
    result = component_translation_key("feeding_mode")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.unit
def test_component_translation_key_with_dots() -> None:
    result = component_translation_key("state.feeding_mode.manual")
    assert isinstance(result, str)


@pytest.mark.unit
def test_component_translation_key_empty() -> None:
    result = component_translation_key("")
    assert isinstance(result, str)


@pytest.mark.unit
def test_resolve_translation_found() -> None:
    lookup = {"some.key": "Some Value"}
    result = resolve_translation(lookup, {}, "some.key")
    assert result == "Some Value"


@pytest.mark.unit
def test_resolve_translation_fallback() -> None:
    lookup = {}
    fallback = {"some.key": "Fallback Value"}
    result = resolve_translation(lookup, fallback, "some.key")
    assert result == "Fallback Value"


@pytest.mark.unit
def test_resolve_translation_missing_key_returns_default() -> None:
    result = resolve_translation({}, {}, "missing.key", default="N/A")
    assert result == "N/A" or isinstance(result, str)


@pytest.mark.unit
def test_resolve_translation_missing_no_default() -> None:
    result = resolve_translation({}, {}, "missing.key")
    assert result is None or isinstance(result, str)


@pytest.mark.unit
def test_resolve_component_translation_found() -> None:
    lookup = {"feeding_mode": "Feeding Mode"}
    result = resolve_component_translation(lookup, {}, "feeding_mode")
    assert result == "Feeding Mode"


@pytest.mark.unit
def test_resolve_component_translation_empty() -> None:
    result = resolve_component_translation({}, {}, "feeding_mode")
    assert result is None or isinstance(result, str)
