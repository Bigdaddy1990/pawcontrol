"""Tests for `custom_components.pawcontrol.utils` package exports."""

import importlib
import sys

import pytest


def _reloaded_utils_module() -> object:
    """Reload the utils package so module-level export wiring is exercised."""
    module_name = "custom_components.pawcontrol.utils"
    importlib.import_module(module_name)

    # `tests/unit/test_utils_package_exports.py` intentionally removes and
    # reinstalls the package module while exercising import wiring. Importing
    # through `sys.modules` keeps reload bound to the currently-registered
    # module object instead of a stale module reference captured at import time.
    current = sys.modules[module_name]
    return importlib.reload(current)


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
    resolved = getattr(module, name)
    assert resolved is getattr(module.serialize, name)
    assert resolved.__module__ == "custom_components.pawcontrol.utils.serialize"


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
        _ = module.definitely_not_exported


def test_reload_skips_legacy_serialize_name_collisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy symbols that collide with serialize exports stay lazily resolved."""
    module = _reloaded_utils_module()

    monkeypatch.setattr(
        module._legacy_utils,
        "serialize_datetime",
        object(),
        raising=False,
    )

    reloaded = _reloaded_utils_module()

    assert "serialize_datetime" not in reloaded.__dict__
    assert reloaded.serialize_datetime is reloaded.serialize.serialize_datetime
    assert (
        reloaded.serialize_datetime.__module__
        == "custom_components.pawcontrol.utils.serialize"
    )
