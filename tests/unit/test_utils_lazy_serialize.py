"""Coverage tests for lazy serialize helper resolution in ``utils``."""

from datetime import datetime
import importlib
import sys


def _reload_utils_modules() -> tuple[object, object]:
    """Reload utils package and serialize module from a clean module cache."""
    sys.modules.pop("custom_components.pawcontrol.utils.serialize", None)
    sys.modules.pop("custom_components.pawcontrol.utils", None)
    utils = importlib.import_module("custom_components.pawcontrol.utils")
    serialize_module = importlib.import_module(
        "custom_components.pawcontrol.utils.serialize"
    )
    importlib.reload(utils)
    return utils, serialize_module


def test_utils_serialize_helpers_resolve_latest_module_bindings(
    monkeypatch,
) -> None:
    """Package-level serialize helpers should resolve from ``utils.serialize`` lazily."""  # noqa: E501
    utils, serialize_module = _reload_utils_modules()

    def replacement(value: datetime) -> str:
        return "updated-binding"

    monkeypatch.setattr(serialize_module, "serialize_datetime", replacement)

    assert utils.serialize_datetime is replacement
    assert utils.serialize_datetime(datetime(2026, 1, 1, 12, 0, 0)) == "updated-binding"


def test_utils_getattr_unknown_helper_raises_attribute_error() -> None:
    """Unknown package helper names should raise ``AttributeError`` via ``__getattr__``."""  # noqa: E501
    utils, _ = _reload_utils_modules()

    try:
        _ = utils.this_helper_does_not_exist
    except AttributeError as err:
        assert str(err) == "this_helper_does_not_exist"
    else:  # pragma: no cover - defensive branch
        raise AssertionError("Expected AttributeError for unknown helper")
