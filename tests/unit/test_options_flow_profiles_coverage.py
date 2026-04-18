"""Additional coverage tests for ``options_flow_profiles``."""

from types import SimpleNamespace
from typing import Any

import pytest
import voluptuous as vol

import custom_components.pawcontrol.options_flow_profiles as options_flow_profiles
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
async def test_async_step_entity_profiles_handles_vol_invalid(  # noqa: D103
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
async def test_async_step_entity_profiles_handles_generic_error(  # noqa: D103
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
async def test_async_step_entity_profiles_preview_and_save_paths(  # noqa: D103
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
async def test_async_step_profile_preview_apply_or_return() -> None:  # noqa: D103
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
async def test_async_step_performance_settings_success_and_error(  # noqa: D103
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


class _EntityFactoryCoverageStub:
    async def estimate_entity_count_async(
        self,
        profile: str,
        modules: dict[str, Any],
    ) -> int:
        if profile == "advanced":
            return int(modules.get("advanced_estimate", 0))
        if profile == "basic":
            return int(modules.get("basic_estimate", 0))
        return int(modules.get("standard_estimate", 0))

    def validate_profile_for_modules(
        self,
        profile: str,
        modules: dict[str, Any],
    ) -> bool:
        return not (profile == "basic" and bool(modules.get("gps")))


class _ProfileFlowHostDeep(ProfileOptionsMixin):
    """Host exposing non-overridden profile placeholder/preview paths."""

    def __init__(
        self,
        *,
        dogs: Any | None = None,
        options: dict[str, Any] | None = None,
        telemetry: dict[str, Any] | None = None,
        normalise_exception: Exception | None = None,
    ) -> None:
        self._entry = SimpleNamespace(
            data={"dogs": [] if dogs is None else dogs},
            options={"entity_profile": "standard"} if options is None else options,
        )
        self._profile_cache: dict[str, dict[str, str]] = {}
        self._entity_estimates_cache: dict[str, dict[str, Any]] = {}
        self._entity_factory = _EntityFactoryCoverageStub()
        self._telemetry = {"events": 1} if telemetry is None else telemetry
        self._normalise_exception = normalise_exception
        self.invalidated = False

    def _normalise_options_snapshot(self, options: dict[str, Any]) -> dict[str, Any]:
        return dict(options)

    def _invalidate_profile_caches(self) -> None:
        self.invalidated = True
        self._profile_cache.clear()
        self._entity_estimates_cache.clear()

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
        return dict(self._telemetry)

    def _last_reconfigure_timestamp(self) -> str:
        return "2026-04-05T00:00:00+00:00"

    def _normalise_export_value(self, value: dict[str, Any]) -> dict[str, Any]:
        if self._normalise_exception is not None:
            raise self._normalise_exception
        return value

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "form", **kwargs}

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": "create_entry", "title": title, "data": data}


def _install_profile_module_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        options_flow_profiles,
        "ensure_dog_config_data",
        lambda dog: None if dog.get("drop") else dog,
    )
    monkeypatch.setattr(
        options_flow_profiles,
        "ensure_dog_modules_mapping",
        lambda dog: dict(dog.get("modules", {})),
    )
    monkeypatch.setattr(
        options_flow_profiles,
        "ENTITY_PROFILES",
        {
            "standard": {
                "max_entities": 10,
                "description": "Standard profile",
                "performance_impact": "balanced",
            },
            "advanced": {
                "max_entities": 10,
                "description": "Advanced profile",
                "performance_impact": "high",
            },
            "basic": {
                "max_entities": 6,
                "description": "Basic profile",
                "performance_impact": "low",
            },
        },
    )


@pytest.mark.asyncio
async def test_profile_description_placeholders_cached_handles_invalid_dogs_and_cache(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_profile_module_stubs(monkeypatch)
    host = _ProfileFlowHostDeep(
        dogs=[
            1,
            {"dog_name": "Skip", "dog_id": "skip", "drop": True, "modules": {}},
            {
                "dog_name": "Milo",
                "dog_id": "dog-1",
                "modules": {
                    "gps": True,
                    "advanced_estimate": 9,
                    "standard_estimate": 4,
                    "basic_estimate": 3,
                },
            },
        ],
        options={"entity_profile": "basic"},
    )

    first = await host._get_profile_description_placeholders_cached()
    second = await host._get_profile_description_placeholders_cached()

    assert second is first
    assert (
        "Milo modules may not be optimal for basic" in first["compatibility_warnings"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ValueError("bad"),
        TypeError("bad"),
    ],
)
async def test_profile_description_placeholders_cached_handles_telemetry_normalise_errors(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    _install_profile_module_stubs(monkeypatch)
    host = _ProfileFlowHostDeep(
        dogs=123,
        options={"entity_profile": "standard"},
        normalise_exception=error,
    )

    placeholders = await host._get_profile_description_placeholders_cached()
    assert placeholders["current_profile"] == "standard"


@pytest.mark.asyncio
async def test_profile_description_placeholders_cached_skips_telemetry_digest_when_empty(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_profile_module_stubs(monkeypatch)
    host = _ProfileFlowHostDeep(
        dogs=[
            {
                "dog_name": "Milo",
                "dog_id": "dog-1",
                "modules": {"standard_estimate": 2},
            },
        ],
        options={"entity_profile": "standard"},
        telemetry={},
    )

    placeholders = await host._get_profile_description_placeholders_cached()
    assert placeholders["current_profile"] == "standard"


@pytest.mark.asyncio
async def test_calculate_profile_preview_optimized_builds_and_caches_preview(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_profile_module_stubs(monkeypatch)
    host = _ProfileFlowHostDeep(
        dogs=[
            {
                "dog_name": "Milo",
                "dog_id": "dog-1",
                "modules": {
                    "advanced_estimate": 9,
                    "standard_estimate": 4,
                    "basic_estimate": 3,
                    "gps": True,
                },
            },
            {
                "dog_name": "Luna",
                "dog_id": "dog-2",
                "modules": {
                    "advanced_estimate": 7,
                    "standard_estimate": 3,
                    "basic_estimate": 2,
                    "health": False,
                },
            },
        ],
        options={"entity_profile": "standard"},
    )

    preview_advanced = await host._calculate_profile_preview_optimized("advanced")
    cached_advanced = await host._calculate_profile_preview_optimized("advanced")
    preview_standard = await host._calculate_profile_preview_optimized("standard")

    assert preview_advanced["total_entities"] == 16
    assert preview_advanced["current_total"] == 7
    assert preview_advanced["entity_difference"] == 9
    assert cached_advanced is preview_advanced
    assert preview_standard["total_entities"] == preview_standard["current_total"]
    assert preview_standard["entity_difference"] == 0


@pytest.mark.asyncio
async def test_calculate_profile_preview_optimized_skips_invalid_dog_entries(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_profile_module_stubs(monkeypatch)
    host = _ProfileFlowHostDeep(
        dogs=[
            1,
            {"dog_name": "Skip", "dog_id": "skip", "drop": True, "modules": {}},
            {
                "dog_name": "Milo",
                "dog_id": "dog-1",
                "modules": {"standard_estimate": 2},
            },
        ],
        options={"entity_profile": "standard"},
    )

    preview = await host._calculate_profile_preview_optimized("standard")
    assert preview["total_entities"] == 2
    assert preview["entity_difference"] == 0


@pytest.mark.asyncio
async def test_calculate_profile_preview_optimized_handles_non_sequence_dogs_input(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_profile_module_stubs(monkeypatch)
    host = _ProfileFlowHostDeep(
        dogs=123,
        options={"entity_profile": "standard"},
    )

    preview = await host._calculate_profile_preview_optimized("standard")
    assert preview["total_entities"] == 0
    assert preview["entity_difference"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entity_difference", "warnings", "expected_change", "expected_warnings"),
    [
        (2, ["warn-a"], "higher resource usage", "warn-a"),
        (-1, ["warn-b"], "better", "warn-b"),
        (0, "ignored-string", "same", "No warnings"),
    ],
)
async def test_async_step_profile_preview_formats_performance_change_and_warnings(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
    entity_difference: int,
    warnings: Any,
    expected_change: str,
    expected_warnings: str,
) -> None:
    _install_profile_module_stubs(monkeypatch)
    host = _ProfileFlowHostDeep(options={"entity_profile": "standard"})

    async def _preview(_: str) -> dict[str, Any]:
        return {
            "profile": "standard",
            "total_entities": 5,
            "entity_breakdown": [
                {
                    "dog_name": "Milo",
                    "entities": 4,
                    "modules": ["gps", "feeding"],
                    "utilization": 50.0,
                },
                {
                    "dog_name": "Luna",
                    "entities": 1,
                    "modules": "invalid",
                    "utilization": 10.0,
                },
            ],
            "current_total": 5 - entity_difference,
            "entity_difference": entity_difference,
            "performance_score": 90.0,
            "recommendation": "good",
            "warnings": warnings,
        }

    monkeypatch.setattr(host, "_calculate_profile_preview_optimized", _preview)
    result = await host.async_step_profile_preview()

    placeholders = result["description_placeholders"]
    assert placeholders["performance_change"] == expected_change
    assert placeholders["warnings"] == expected_warnings
    assert "modules: none" in placeholders["entity_breakdown"]


@pytest.mark.asyncio
async def test_async_step_performance_settings_uses_stored_int_defaults_and_no_input_form(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_profile_module_stubs(monkeypatch)
    host = _ProfileFlowHostDeep(
        options={
            "entity_profile": "standard",
            "batch_size": 25,
            "cache_ttl": 420,
            "selective_refresh": True,
            "performance_mode": "balanced",
        },
    )

    monkeypatch.setattr(
        options_flow_profiles,
        "validate_profile_selection",
        lambda data: str(data["entity_profile"]),
    )

    saved = await host.async_step_performance_settings(
        {
            "entity_profile": "advanced",
            "performance_mode": "minimal",
            "selective_refresh": False,
        },
    )
    form = await host.async_step_performance_settings()

    assert saved["type"] == "create_entry"
    assert saved["data"]["batch_size"] == 25
    assert saved["data"]["cache_ttl"] == 420
    assert saved["data"]["performance_mode"] == "minimal"
    assert form["type"] == "form"
    assert form["step_id"] == "performance_settings"
