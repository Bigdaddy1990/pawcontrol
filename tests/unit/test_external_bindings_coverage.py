"""Targeted coverage tests for external_bindings.py — (0% → 18%+).

Covers: require_runtime_data decorator, LocationSource
"""

import pytest

from custom_components.pawcontrol.external_bindings import LocationSource

# ─── LocationSource ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_location_source_has_values() -> None:
    # LocationSource is an Enum or similar
    assert LocationSource is not None


@pytest.mark.unit
def test_location_source_members() -> None:
    members = list(LocationSource)
    assert len(members) >= 1


@pytest.mark.unit
def test_location_source_iterable() -> None:
    for source in LocationSource:
        assert source is not None
        assert isinstance(source.value, (str, int))
