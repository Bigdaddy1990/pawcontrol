"""Tests for `custom_components.pawcontrol.utils` package exports."""

import importlib

import pytest

from custom_components.pawcontrol import utils
from custom_components.pawcontrol.utils import serialize


def _reloaded_utils_module() -> object:
    """Reload the utils package so module-level export wiring is exercised."""
    return importlib.reload(utils)


@pytest.mark.parametrize(
    "name",
    [
        "serialize_datetime",
        "serialize_timedelta",
        "serialize_dataclass",
        "serialize_entity_attributes",
    ],
)
def test_serialize_helpers_are_lazily_resolved(name: str) -> None:
    """Serialize helpers should be served by the serialize submodule."""
    module = _reloaded_utils_module()

    assert name not in module.__dict__
    assert getattr(module, name) is getattr(serialize, name)


def test_package_all_contains_legacy_and_serialize_symbols() -> None:
    """`__all__` should expose explicit legacy and serialize helpers."""
    module = _reloaded_utils_module()
    exported = set(module.__all__)

    assert {
        "sanitize_dog_id",
        "deep_merge_dicts",
        "serialize_datetime",
        "serialize_timedelta",
    }.issubset(exported)


def test_utils_getattr_unknown_symbol_raises_attribute_error() -> None:
    """Unknown symbols should raise `AttributeError` via module `__getattr__`."""
    module = _reloaded_utils_module()

    with pytest.raises(AttributeError):
        module.definitely_not_exported
