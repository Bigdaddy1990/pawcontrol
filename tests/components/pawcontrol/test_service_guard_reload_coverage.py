"""Import and branch coverage tests for service_guard."""

from collections.abc import Iterator, MutableMapping
import importlib.util
from pathlib import Path
import sys
from types import ModuleType

from custom_components.pawcontrol.service_guard import (
    ServiceGuardResult,
    ServiceGuardSnapshot,
)


class _FlakyReasonsMetrics(MutableMapping[str, object]):
    """Mutable mapping whose ``reasons`` lookup changes between calls."""

    def __init__(self) -> None:
        self._store: dict[str, object] = {
            "executed": 0,
            "skipped": 0,
            "reasons": {"quiet_hours": 2},
            "last_results": [],
        }
        self._reasons_reads = 0

    def __getitem__(self, key: str) -> object:
        return self._store[key]

    def __setitem__(self, key: str, value: object) -> None:
        self._store[key] = value

    def __delitem__(self, key: str) -> None:
        del self._store[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._store)

    def __len__(self) -> int:
        return len(self._store)

    def get(self, key: str, default: object | None = None) -> object | None:
        if key == "reasons":
            self._reasons_reads += 1
            if self._reasons_reads == 2:
                return "invalid-reasons"
        return self._store.get(key, default)


def _load_service_guard_clone() -> ModuleType:
    """Load service_guard under a temporary module name."""
    module_name = "custom_components.pawcontrol._service_guard_cov_clone"
    module_path = (
        Path(__file__).resolve().parents[3]
        / "custom_components"
        / "pawcontrol"
        / "service_guard.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_service_guard_module_clone_executes_import_time_lines() -> None:
    """Reloading the module should keep relative imports and public API usable."""
    clone = _load_service_guard_clone()

    result = clone.ServiceGuardResult("notify", "mobile_app", False, reason="quiet")
    assert result.to_mapping() == {
        "domain": "notify",
        "service": "mobile_app",
        "executed": False,
        "reason": "quiet",
    }


def test_service_guard_module_clone_can_be_reloaded_after_eviction() -> None:
    """Clone loading should still work after a prior module registration is removed."""
    clone = _load_service_guard_clone()
    module_name = clone.__name__
    del sys.modules[module_name]

    reloaded = _load_service_guard_clone()
    snapshot = reloaded.ServiceGuardSnapshot.from_sequence([
        reloaded.ServiceGuardResult("notify", "mobile_app", True)
    ])

    assert snapshot.to_metrics()["executed"] == 1
    assert module_name in sys.modules


def test_accumulate_handles_non_mapping_snapshot_reasons() -> None:
    """The summary payload should fall back to an empty reason snapshot."""
    snapshot = ServiceGuardSnapshot.from_sequence([
        ServiceGuardResult("notify", "mobile_app", False, reason="quiet_hours")
    ])

    metrics = _FlakyReasonsMetrics()
    payload = snapshot.accumulate(metrics)

    assert payload["executed"] == 0
    assert payload["skipped"] == 1
    assert payload["reasons"] == {}
    assert payload["last_results"] == [
        {
            "domain": "notify",
            "service": "mobile_app",
            "executed": False,
            "reason": "quiet_hours",
        }
    ]
