"""Coverage tests for flow_steps modules — system_settings, health, notifications, __init__."""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.flow_steps.system_settings import normalize_performance_mode
from custom_components.pawcontrol.flow_steps.notifications import (
    NotificationOptions,
    ensure_notification_options,
)
import custom_components.pawcontrol.flow_steps as fs_init
import custom_components.pawcontrol.flow_steps.system_settings as ss_mod
import custom_components.pawcontrol.flow_steps.health as health_mod
import custom_components.pawcontrol.flow_steps.notifications as notif_mod


# ─── normalize_performance_mode ──────────────────────────────────────────────

@pytest.mark.unit
def test_normalize_performance_mode_balanced() -> None:
    result = normalize_performance_mode("balanced")
    assert result == "balanced"


@pytest.mark.unit
def test_normalize_performance_mode_minimal() -> None:
    result = normalize_performance_mode("minimal")
    assert result == "minimal"


@pytest.mark.unit
def test_normalize_performance_mode_full() -> None:
    result = normalize_performance_mode("full")
    assert result == "full"


@pytest.mark.unit
def test_normalize_performance_mode_invalid_uses_fallback() -> None:
    result = normalize_performance_mode("turbo", fallback="balanced")
    assert result == "balanced"


@pytest.mark.unit
def test_normalize_performance_mode_none_uses_fallback() -> None:
    result = normalize_performance_mode(None, fallback="minimal")
    assert result == "minimal"


@pytest.mark.unit
def test_normalize_performance_mode_with_current() -> None:
    result = normalize_performance_mode(None, current="full", fallback="balanced")
    assert result in ("full", "balanced", "minimal")


# ─── ensure_notification_options ─────────────────────────────────────────────

@pytest.mark.unit
def test_ensure_notification_options_empty() -> None:
    result = ensure_notification_options({})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_ensure_notification_options_with_values() -> None:
    result = ensure_notification_options({
        "mobile_notifications": True,
        "priority_notifications": False,
    })
    assert isinstance(result, dict)


@pytest.mark.unit
def test_ensure_notification_options_with_defaults() -> None:
    defaults = {"mobile_notifications": True, "quiet_hours": False}
    result = ensure_notification_options({}, defaults=defaults)
    assert isinstance(result, dict)


# ─── NotificationOptions (TypedDict) ─────────────────────────────────────────

@pytest.mark.unit
def test_notification_options_as_dict() -> None:
    opts: NotificationOptions = {
        "quiet_hours": False,
        "quiet_start": "22:00",
        "quiet_end": "07:00",
        "mobile_notifications": True,
    }
    assert opts["mobile_notifications"] is True
    assert opts["quiet_hours"] is False


# ─── module import checks ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_flow_steps_init_importable() -> None:
    assert fs_init is not None
    assert hasattr(fs_init, "DogGPSFlowMixin") or hasattr(fs_init, "DogHealthFlowMixin")


@pytest.mark.unit
def test_system_settings_has_normalize_performance_mode() -> None:
    assert hasattr(ss_mod, "normalize_performance_mode")
    assert callable(ss_mod.normalize_performance_mode)


@pytest.mark.unit
def test_health_module_has_build_health_settings_schema() -> None:
    assert hasattr(health_mod, "build_health_settings_schema")
    assert callable(health_mod.build_health_settings_schema)


@pytest.mark.unit
def test_notifications_module_has_build_notifications_schema() -> None:
    assert hasattr(notif_mod, "build_notifications_schema")
    assert callable(notif_mod.build_notifications_schema)
