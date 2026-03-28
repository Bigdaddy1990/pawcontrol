"""Direct runtime coverage for ``utils.serialize`` module import paths."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
import sys
from types import ModuleType


def _load_serialize_module(module_name: str) -> ModuleType:
    """Load the serialize module directly from disk under ``module_name``."""
    module_path = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "pawcontrol"
        / "utils"
        / "serialize.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load serialize module spec")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_module_import_updates_parent_re_exports(monkeypatch) -> None:
    """Import-time re-export wiring should attach helper functions to parent module."""
    parent_name = "custom_components.pawcontrol.utils"
    serialize_name = "custom_components.pawcontrol.utils.serialize"
    original_parent = sys.modules.get(parent_name)
    original_serialize = sys.modules.get(serialize_name)
    parent_module = ModuleType(parent_name)
    sys.modules[parent_name] = parent_module
    try:
        module = _load_serialize_module(serialize_name)

        assert parent_module.serialize_datetime is module.serialize_datetime
        assert parent_module.serialize_timedelta is module.serialize_timedelta
        assert parent_module.serialize_dataclass is module.serialize_dataclass
        assert (
            parent_module.serialize_entity_attributes
            is module.serialize_entity_attributes
        )
    finally:
        if original_serialize is None:
            sys.modules.pop(serialize_name, None)
        else:
            sys.modules[serialize_name] = original_serialize
        if original_parent is None:
            sys.modules.pop(parent_name, None)
        else:
            sys.modules[parent_name] = original_parent


@dataclass(slots=True)
class _Payload:
    when: datetime
    duration: timedelta


class _Stringy:
    def __str__(self) -> str:
        return "stringy"


def test_private_serializer_covers_all_supported_types() -> None:
    """The private recursive serializer should handle every conversion branch."""
    module = _load_serialize_module("tests.runtime.serialize_for_branches")
    serializer = module._serialize_value

    payload = _Payload(
        when=datetime(2026, 3, 1, 8, 45, tzinfo=UTC),
        duration=timedelta(seconds=90),
    )

    assert serializer(None) is None
    assert (
        serializer(datetime(2026, 3, 1, 8, 45, tzinfo=UTC))
        == "2026-03-01T08:45:00+00:00"
    )
    assert serializer(timedelta(seconds=5)) == 5
    assert serializer(payload) == {
        "when": "2026-03-01T08:45:00+00:00",
        "duration": 90,
    }
    assert serializer({"nested": (1, 2, payload)}) == {
        "nested": [1, 2, {"when": "2026-03-01T08:45:00+00:00", "duration": 90}]
    }
    assert serializer("ok") == "ok"
    assert serializer(5) == 5
    assert serializer(3.5) == 3.5
    assert serializer(True) is True
    assert serializer(_Stringy()) == "stringy"


def test_public_helpers_from_runtime_module() -> None:
    """Public helpers should preserve expected runtime behavior."""
    module = _load_serialize_module("tests.runtime.serialize_public")

    assert module.serialize_datetime(datetime(2026, 1, 2, 3, 4, tzinfo=UTC)) == (
        "2026-01-02T03:04:00+00:00"
    )
    assert module.serialize_timedelta(timedelta(minutes=2, seconds=4)) == 124

    assert module.serialize_dataclass(
        _Payload(
            when=datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
            duration=timedelta(seconds=1),
        )
    ) == {
        "when": datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        "duration": timedelta(seconds=1),
    }

    attributes = module.serialize_entity_attributes({
        "time": datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        "delta": timedelta(seconds=11),
        "nested": [timedelta(seconds=3)],
    })
    assert attributes == {
        "time": "2026-01-02T03:04:00+00:00",
        "delta": 11,
        "nested": [3],
    }
