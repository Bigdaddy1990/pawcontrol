"""Coverage tests for lazy serialize helper resolution in ``utils``."""

from __future__ import annotations

from datetime import datetime
import importlib

from custom_components.pawcontrol import utils
from custom_components.pawcontrol.utils import serialize as serialize_module


def test_utils_serialize_helpers_resolve_latest_module_bindings(
    monkeypatch,
) -> None:
    """Package-level serialize helpers should resolve from ``utils.serialize`` lazily."""
    importlib.reload(utils)

    def replacement(value: datetime) -> str:
        return "updated-binding"

    monkeypatch.setattr(serialize_module, "serialize_datetime", replacement)

    assert utils.serialize_datetime is replacement
    assert utils.serialize_datetime(datetime(2026, 1, 1, 12, 0, 0)) == "updated-binding"


def test_utils_getattr_unknown_helper_raises_attribute_error() -> None:
    """Unknown package helper names should raise ``AttributeError`` via ``__getattr__``."""
    importlib.reload(utils)

    try:
        _ = utils.this_helper_does_not_exist
    except AttributeError as err:
        assert str(err) == "this_helper_does_not_exist"
    else:  # pragma: no cover - defensive branch
        raise AssertionError("Expected AttributeError for unknown helper")
