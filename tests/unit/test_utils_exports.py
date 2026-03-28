"""Tests for runtime exports of the ``utils`` package modules."""

import importlib
import sys

from custom_components.pawcontrol.utils import _legacy as legacy_utils


def _reload_utils_modules() -> tuple[object, object]:
    """Reload utils package and serialize module from a clean module cache."""
    sys.modules.pop("custom_components.pawcontrol.utils.serialize", None)
    sys.modules.pop("custom_components.pawcontrol.utils", None)
    utils_module = importlib.import_module("custom_components.pawcontrol.utils")
    serialize_module = importlib.import_module(
        "custom_components.pawcontrol.utils.serialize"
    )
    return utils_module, serialize_module


def test_utils_package_reloads_and_exposes_expected_symbols() -> None:
    """Reloading ``utils`` should preserve legacy and serialize re-exports."""
    utils_module, serialize_module = _reload_utils_modules()
    reloaded_utils = importlib.reload(utils_module)

    expected_symbols = {
        "normalize_value",
        "serialize_datetime",
        "serialize_timedelta",
        "serialize_dataclass",
        "serialize_entity_attributes",
        "async_fire_event",
        "validate_portion_size",
    }

    assert expected_symbols <= set(reloaded_utils.__all__)
    assert reloaded_utils.normalize_value is legacy_utils.normalize_value
    assert reloaded_utils.validate_portion_size is legacy_utils.validate_portion_size
    assert reloaded_utils.serialize_datetime is serialize_module.serialize_datetime


def test_serialize_module_reloads_with_public_all() -> None:
    """Reloading ``serialize`` should keep all documented public helpers."""
    _, serialize_module = _reload_utils_modules()
    reloaded_serialize = importlib.reload(serialize_module)

    assert reloaded_serialize.__all__ == [
        "serialize_datetime",
        "serialize_timedelta",
        "serialize_dataclass",
        "serialize_entity_attributes",
    ]
