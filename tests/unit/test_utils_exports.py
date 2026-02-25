"""Tests for runtime exports of the ``utils`` package modules."""

import importlib

from custom_components.pawcontrol import utils as utils_module
from custom_components.pawcontrol.utils import (
    _legacy as legacy_utils,
    serialize as serialize_module,
)


def test_utils_package_reloads_and_exposes_expected_symbols() -> None:
    """Reloading ``utils`` should preserve legacy and serialize re-exports."""
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
    reloaded_serialize = importlib.reload(serialize_module)

    assert reloaded_serialize.__all__ == [
        "serialize_datetime",
        "serialize_timedelta",
        "serialize_dataclass",
        "serialize_entity_attributes",
    ]
