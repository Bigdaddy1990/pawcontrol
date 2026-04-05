"""Additional coverage tests for ``options_flow_profiles``."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
import voluptuous as vol

from custom_components.pawcontrol.options_flow_profiles import ProfileOptionsMixin


class _EntityFactoryStub:
    async def estimate_entity_count_async(
        self,
        profile: str,
        modules: dict[str, bool],
    ) -> int:
        base = sum(1 for enabled in modules.values() if enabled)
        return base + (1 if profile == "advanced" else 0)

    def validate_profile_for_modules(
        self, profile: str, modules: dict[str, bool]
    ) -> bool:
        return not (profile == "basic" and modules.get("gps"))


class _ProfileFlowHost(ProfileOptionsMixin):
    """Minimal host for exercising profile option step branches."""

    def __init__(self) -> None:
        self._entry = SimpleNamespace(
            data={"dogs": [{"dog_name": "Milo", "dog_id": "dog-1", "gps": True}]},
            options={"entity_profile": "standard"},
        )
        self._profile_cache: dict[str, dict[str, str]] = {}
        self._entity_estimates_cache: dict[str, dict[str, Any]] = {}
        self._entity_factory = _EntityFactoryStub()
        self.invalidated = False

    def _normalise_options_snapshot(self, options: dict[str, Any]) -> dict[str, Any]:
        return dict(options)

    def _invalidate_profile_caches(self) -> None:
        self.invalidated = True

    def _current_options(self) -> dict[str, Any]:
        return dict(self._entry.options)

    def _clone_options(self) -> dict[str, Any]:
        return dict(self._entry.options)

    def _coerce_int(self, value: object, default: int) -> int:
        return value if isinstance(value, int) else default

    def _coerce_bool(self, value: object, default: bool) -> bool:
        return value if isinstance(value, bool) else default

    def _get_reconfigure_description_placeholders(self) -> dict[str, str]:
        return {"status": "ok"}

    def _reconfigure_telemetry(self) -> dict[str, Any]:
        return {"events": 1}

    def _last_reconfigure_timestamp(self) -> str:
        return "2026-04-05T00:00:00+00:00"

    def _normalise_export_value(self, value: dict[str, Any]) -> dict[str, Any]:
        return value

    async def _calculate_profile_preview_optimized(
        self, profile: str
    ) -> dict[str, Any]:
        return {
            "profile": profile,
            "total_entities": 4,
            "entity_breakdown": [
                {
                    "dog_name": "Milo",
                    "entities": 4,
                    "modules": ["gps", "feeding"],
                    "utilization": 50.0,
                }
            ],
            "current_total": 3,
            "entity_difference": 1,
            "performance_score": 92.5,
            "recommendation": "good",
            "warnings": ["warn"],
        }

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "form", **kwargs}

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": "create_entry", "title": title, "data": data}


@pytest.mark.asyncio
async def test_async_step_entity_profiles_handles_vol_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _ProfileFlowHost()

    def _raise_invalid(_: dict[str, Any]) -> str:
        raise vol.Invalid("bad profile")

    monkeypatch.setattr(
        "custom_components.pawcontrol.options_flow_profiles.validate_profile_selection",
        _raise_invalid,
    )

    result = await host.async_step_entity_profiles({"entity_profile": "broken"})

    assert result["type"] == "form"
    assert result["step_id"] == "entity_profiles"
    assert result["errors"] == {"base": "invalid_profile"}


@pytest.mark.asyncio
async def test_async_step_entity_profiles_handles_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _ProfileFlowHost()

    def _raise_error(_: dict[str, Any]) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "custom_components.pawcontrol.options_flow_profiles.validate_profile_selection",
        _raise_error,
    )

    result = await host.async_step_entity_profiles({"entity_profile": "advanced"})

    assert result["type"] == "form"
    assert result["errors"] == {"base": "profile_update_failed"}


@pytest.mark.asyncio
async def test_async_step_entity_profiles_preview_and_save_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _ProfileFlowHost()

    monkeypatch.setattr(
        "custom_components.pawcontrol.options_flow_profiles.validate_profile_selection",
        lambda data: str(data["entity_profile"]),
    )

    preview_result = await host.async_step_entity_profiles({
        "entity_profile": "advanced",
        "preview_estimate": True,
    })
    assert preview_result["step_id"] == "entity_profiles"

    save_result = await host.async_step_entity_profiles({"entity_profile": "advanced"})
    assert save_result == {
        "type": "create_entry",
        "title": "",
        "data": {"entity_profile": "advanced"},
    }
    assert host.invalidated is True


@pytest.mark.asyncio
async def test_async_step_profile_preview_apply_or_return() -> None:
    host = _ProfileFlowHost()

    apply_result = await host.async_step_profile_preview({
        "profile": "advanced",
        "apply_profile": True,
    })
    assert apply_result["type"] == "create_entry"
    assert apply_result["data"]["entity_profile"] == "advanced"

    form_result = await host.async_step_profile_preview({"profile": "advanced"})
    assert form_result["type"] == "form"
    assert form_result["step_id"] == "entity_profiles"


@pytest.mark.asyncio
async def test_async_step_performance_settings_success_and_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _ProfileFlowHost()

    success = await host.async_step_performance_settings({
        "entity_profile": "advanced",
        "performance_mode": "full",
        "batch_size": 20,
        "cache_ttl": 600,
        "selective_refresh": False,
    })
    assert success["type"] == "create_entry"
    assert success["data"]["performance_mode"] == "full"

    def _raise_profile(_: dict[str, str]) -> str:
        raise RuntimeError("invalid")

    monkeypatch.setattr(
        "custom_components.pawcontrol.options_flow_profiles.validate_profile_selection",
        _raise_profile,
    )
    failed = await host.async_step_performance_settings({"entity_profile": "oops"})
    assert failed["type"] == "form"
    assert failed["errors"] == {"base": "performance_update_failed"}
