"""Coverage tests for options_flow_shared.py + options_flow_import_export.py."""
from __future__ import annotations

import pytest

import custom_components.pawcontrol.options_flow_shared as ofs_mod
import custom_components.pawcontrol.options_flow_import_export as ofie_mod
from custom_components.pawcontrol.options_flow_shared import (
    clamp_float_range,
    clamp_int_range,
    coerce_float,
    coerce_int,
)


# ─── clamp_float_range (options_flow_shared) ──────────────────────────────────

@pytest.mark.unit
def test_ofs_clamp_float_range_within() -> None:
    result = clamp_float_range(5.0, field="w", minimum=0.0, maximum=100.0, default=50.0)
    assert result == pytest.approx(5.0)


@pytest.mark.unit
def test_ofs_clamp_float_range_below() -> None:
    result = clamp_float_range(-1.0, field="w", minimum=0.0, maximum=100.0, default=50.0)
    assert result == pytest.approx(0.0)


@pytest.mark.unit
def test_ofs_clamp_float_range_above() -> None:
    result = clamp_float_range(999.0, field="w", minimum=0.0, maximum=100.0, default=50.0)
    assert result == pytest.approx(100.0)


@pytest.mark.unit
def test_ofs_clamp_float_range_none_default() -> None:
    result = clamp_float_range(None, field="w", minimum=0.0, maximum=100.0, default=42.0)
    assert result == pytest.approx(42.0)


# ─── clamp_int_range (options_flow_shared) ────────────────────────────────────

@pytest.mark.unit
def test_ofs_clamp_int_range_valid() -> None:
    result = clamp_int_range(3, field="meals", minimum=1, maximum=6, default=2)
    assert result == 3


@pytest.mark.unit
def test_ofs_clamp_int_range_below() -> None:
    result = clamp_int_range(0, field="meals", minimum=1, maximum=6, default=2)
    assert result == 1


@pytest.mark.unit
def test_ofs_clamp_int_range_above() -> None:
    result = clamp_int_range(99, field="meals", minimum=1, maximum=6, default=2)
    assert result == 6


# ─── coerce_float / coerce_int (options_flow_shared) ─────────────────────────

@pytest.mark.unit
def test_ofs_coerce_float_string() -> None:
    result = coerce_float("weight", "22.5")
    assert result == pytest.approx(22.5)


@pytest.mark.unit
def test_ofs_coerce_int_string() -> None:
    result = coerce_int("meals", "2")
    assert result == 2


# ─── module import checks ────────────────────────────────────────────────────

@pytest.mark.unit
def test_options_flow_shared_has_clone_placeholders() -> None:
    assert hasattr(ofs_mod, "clone_placeholders")
    assert callable(ofs_mod.clone_placeholders)


@pytest.mark.unit
def test_options_flow_import_export_importable() -> None:
    assert ofie_mod is not None
    assert hasattr(ofie_mod, "ImportExportOptionsMixin")


@pytest.mark.unit
def test_options_flow_import_export_has_freeze_placeholders() -> None:
    assert hasattr(ofie_mod, "freeze_placeholders")
    assert callable(ofie_mod.freeze_placeholders)
