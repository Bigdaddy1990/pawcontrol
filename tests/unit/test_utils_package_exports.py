"""Tests for package-level exports in ``custom_components.pawcontrol.utils``."""

import custom_components.pawcontrol.utils as utils
from custom_components.pawcontrol.utils import _legacy, serialize as serialize_module


def test_utils_all_is_sorted_and_has_no_private_names() -> None:
    """``__all__`` should be deterministic and public-only."""
    assert utils.__all__ == sorted(utils.__all__)
    assert "_coerce_json_mutable" in utils.__all__


def test_utils_re_exports_serialize_helpers() -> None:
    """Serialize helpers should be re-exported from the package root."""
    assert (
        utils.serialize_datetime.__name__
        == serialize_module.serialize_datetime.__name__
    )
    assert (
        utils.serialize_timedelta.__name__
        == serialize_module.serialize_timedelta.__name__
    )
    assert (
        utils.serialize_dataclass.__name__
        == serialize_module.serialize_dataclass.__name__
    )
    assert (
        utils.serialize_entity_attributes.__name__
        == serialize_module.serialize_entity_attributes.__name__
    )


def test_utils_re_exports_known_legacy_helpers() -> None:
    """Selected legacy helpers should be available via package import."""
    assert utils.normalize_value is _legacy.normalize_value
    assert utils.ensure_utc_datetime is _legacy.ensure_utc_datetime
    assert utils.ensure_local_datetime is _legacy.ensure_local_datetime
    assert utils.async_fire_event is _legacy.async_fire_event


def test_utils_exports_include_legacy_public_members() -> None:
    """All non-private names from ``_legacy`` should be present in ``__all__``."""
    legacy_public_names = {name for name in vars(_legacy) if not name.startswith("_")}

    assert legacy_public_names <= set(utils.__all__)
