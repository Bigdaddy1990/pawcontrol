"""Direct execution tests for ``custom_components.pawcontrol.utils.__init__``."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType

import pytest


@pytest.fixture
def loaded_utils_module(monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, ModuleType]:
    """Load the real ``utils/__init__.py`` with controlled sibling modules."""

    package_name = "_coverage_utils_pkg"

    legacy_module = ModuleType(f"{package_name}._legacy")

    def _legacy_normalize_value(value: object) -> object:
        return value

    def _legacy_ensure_utc_datetime(value: object) -> object:
        return value

    def _legacy_ensure_local_datetime(value: object) -> object:
        return value

    def _legacy_async_fire_event(*_: object, **__: object) -> None:
        return None

    legacy_module.normalize_value = _legacy_normalize_value
    legacy_module.ensure_utc_datetime = _legacy_ensure_utc_datetime
    legacy_module.ensure_local_datetime = _legacy_ensure_local_datetime
    legacy_module.async_fire_event = _legacy_async_fire_event
    legacy_module.serialize_datetime = object()

    for explicit_name in (
        "ErrorContext",
        "DateTimeConvertible",
        "JSONMutableMapping",
        "JSONMappingLike",
        "Number",
        "PawControlDeviceLinkMixin",
        "_coerce_json_mutable",
        "async_call_add_entities",
        "async_call_hass_service_if_available",
        "async_capture_service_guard_results",
        "build_error_context",
        "deep_merge_dicts",
        "is_number",
        "normalise_entity_attributes",
        "resolve_default_feeding_amount",
        "sanitize_dog_id",
    ):
        setattr(legacy_module, explicit_name, object())

    serialize_module = ModuleType(f"{package_name}.serialize")

    def serialize_datetime(value: object) -> object:
        return value

    def serialize_timedelta(value: object) -> object:
        return value

    def serialize_dataclass(value: object) -> object:
        return value

    def serialize_entity_attributes(value: object) -> object:
        return value

    serialize_module.serialize_datetime = serialize_datetime
    serialize_module.serialize_timedelta = serialize_timedelta
    serialize_module.serialize_dataclass = serialize_dataclass
    serialize_module.serialize_entity_attributes = serialize_entity_attributes

    monkeypatch.setitem(sys.modules, f"{package_name}._legacy", legacy_module)
    monkeypatch.setitem(sys.modules, f"{package_name}.serialize", serialize_module)

    module_path = (
        Path(__file__).resolve().parents[2]
        / "custom_components"
        / "pawcontrol"
        / "utils"
        / "__init__.py"
    )
    spec = importlib.util.spec_from_file_location(
        package_name,
        module_path,
        submodule_search_locations=[str(module_path.parent)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to create module spec for utils package")

    loaded_module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, package_name, loaded_module)
    spec.loader.exec_module(loaded_module)

    return loaded_module, serialize_module


def test_utils_init_re_exports_and_lazy_serialize_helpers(
    loaded_utils_module: tuple[ModuleType, ModuleType],
) -> None:
    """The package init should preserve exports while deferring serialize lookups."""

    module, serialize_module = loaded_utils_module

    assert module.normalize_value("value") == "value"

    assert "serialize_datetime" in module.__all__
    assert "normalize_value" in module.__all__
    assert module.__all__ == sorted(module.__all__)

    assert module.__getattr__("serialize_datetime") is serialize_module.serialize_datetime
    assert module.__getattr__("serialize_timedelta") is serialize_module.serialize_timedelta
    with pytest.raises(AttributeError):
        module.__getattr__("not_exported")
