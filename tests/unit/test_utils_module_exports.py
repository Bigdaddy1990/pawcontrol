"""Coverage-focused tests for the ``custom_components.pawcontrol.utils`` package."""

import importlib


def test_utils_package_reloads_and_exposes_expected_exports() -> None:
    """The package should expose legacy and serialization helpers via ``__all__``."""
    utils = importlib.import_module("custom_components.pawcontrol.utils")
    reloaded = importlib.reload(utils)

    assert "serialize_datetime" in reloaded.__all__
    assert "serialize_entity_attributes" in reloaded.__all__
    assert "normalize_value" in reloaded.__all__
    assert "sanitize_dog_id" in reloaded.__all__
    assert reloaded.serialize_datetime is not None


def test_serialize_module_reloads_and_keeps_public_api() -> None:
    """Reloading ``utils.serialize`` should preserve its canonical exported names."""
    serialize = importlib.import_module("custom_components.pawcontrol.utils.serialize")
    reloaded = importlib.reload(serialize)

    assert reloaded.__all__ == [
        "serialize_datetime",
        "serialize_timedelta",
        "serialize_dataclass",
        "serialize_entity_attributes",
    ]
