"""Coverage tests for config_flow_placeholders.py + config_flow_monitor.py + config_flow_discovery.py."""

import pytest

import custom_components.pawcontrol.config_flow_discovery as cfd_mod
from custom_components.pawcontrol.config_flow_discovery import ConfigFlowDiscoveryData
import custom_components.pawcontrol.config_flow_monitor as cfm_mod
from custom_components.pawcontrol.config_flow_monitor import ConfigFlowPerformanceStats
import custom_components.pawcontrol.config_flow_placeholders as cfp_mod
from custom_components.pawcontrol.config_flow_placeholders import (
    clone_placeholders,
    freeze_placeholders,
)

# ─── freeze_placeholders ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_freeze_placeholders_empty_dict() -> None:  # noqa: D103
    result = freeze_placeholders({})
    # Returns a mappingproxy, not a dict
    assert hasattr(result, "__getitem__")
    assert len(result) == 0


@pytest.mark.unit
def test_freeze_placeholders_with_values() -> None:  # noqa: D103
    result = freeze_placeholders({"host": "192.168.1.1", "port": 8080})
    assert result["host"] == "192.168.1.1"
    assert result["port"] == 8080


@pytest.mark.unit
def test_freeze_placeholders_returns_mapping() -> None:  # noqa: D103
    data = {"key": "value", "num": 42}
    result = freeze_placeholders(data)
    # Returns a mappingproxy
    assert result["key"] == "value"
    assert result["num"] == 42


# ─── clone_placeholders ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_clone_placeholders_empty() -> None:  # noqa: D103
    frozen = freeze_placeholders({})
    result = clone_placeholders(frozen)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_clone_placeholders_with_values() -> None:  # noqa: D103
    frozen = freeze_placeholders({"host": "10.0.0.1", "port": 443})
    result = clone_placeholders(frozen)
    assert result["host"] == "10.0.0.1"


@pytest.mark.unit
def test_clone_is_mutable() -> None:  # noqa: D103
    frozen = freeze_placeholders({"key": "original"})
    clone = clone_placeholders(frozen)
    clone["key"] = "modified"
    assert clone["key"] == "modified"


# ─── ConfigFlowPerformanceStats (TypedDict) ───────────────────────────────────


@pytest.mark.unit
def test_config_flow_performance_stats_as_dict() -> None:  # noqa: D103
    stats: ConfigFlowPerformanceStats = {"operations": {}, "validations": {}}
    assert isinstance(stats["operations"], dict)


@pytest.mark.unit
def test_config_flow_performance_stats_empty_ops() -> None:  # noqa: D103
    stats: ConfigFlowPerformanceStats = {"operations": {}, "validations": {}}
    assert len(stats["operations"]) == 0


# ─── ConfigFlowDiscoveryData (TypedDict) ─────────────────────────────────────


@pytest.mark.unit
def test_config_flow_discovery_data_as_dict() -> None:  # noqa: D103
    data: ConfigFlowDiscoveryData = {
        "source": "mdns",
        "hostname": "pawcontrol.local",
        "host": "192.168.1.50",
        "port": 8080,
        "ip": "192.168.1.50",
    }
    assert data["source"] == "mdns"
    assert data["host"] == "192.168.1.50"


# ─── module import checks ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_config_flow_discovery_module_importable() -> None:  # noqa: D103
    assert cfd_mod is not None
    assert hasattr(cfd_mod, "DiscoveryFlowMixin")


@pytest.mark.unit
def test_config_flow_monitor_has_timed_operation() -> None:  # noqa: D103
    assert cfm_mod is not None
    assert hasattr(cfm_mod, "timed_operation")
    assert callable(cfm_mod.timed_operation)


@pytest.mark.unit
def test_config_flow_placeholders_has_both_fns() -> None:  # noqa: D103
    assert hasattr(cfp_mod, "freeze_placeholders")
    assert hasattr(cfp_mod, "clone_placeholders")
