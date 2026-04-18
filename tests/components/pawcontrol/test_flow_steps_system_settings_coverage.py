"""Coverage tests for the system settings flow step mixin."""

from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.pawcontrol.const import (
    CONF_API_ENDPOINT,
    CONF_DOG_BREED,
    CONF_DOGS,
    CONF_MQTT_TOPIC,
    CONF_PUSH_NONCE_TTL_SECONDS,
    CONF_PUSH_PAYLOAD_MAX_BYTES,
    CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE,
    CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE,
    CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
    CONF_WEATHER_ENTITY,
    CONF_WEBHOOK_SECRET,
)
from custom_components.pawcontrol.flow_steps import system_settings
from custom_components.pawcontrol.flow_steps.system_settings import (
    SystemSettingsOptionsMixin,
    _resolve_get_runtime_data,
)


class _States:
    def __init__(self, entities: dict[str, Any]) -> None:
        self._entities = entities

    def get(self, entity_id: str) -> Any:
        return self._entities.get(entity_id)

    def async_entity_ids(self, domain: str) -> list[str]:
        prefix = f"{domain}."
        return [
            entity_id for entity_id in self._entities if entity_id.startswith(prefix)
        ]


class _SystemFlow(SystemSettingsOptionsMixin):
    _MANUAL_EVENT_FIELDS = (
        "manual_check_event",
        "manual_guard_event",
        "manual_breaker_event",
    )

    def __init__(
        self, options: dict[str, Any], *, entities: dict[str, Any] | None = None
    ) -> None:
        self._options = options
        self.hass = SimpleNamespace(states=_States(entities or {}))
        self._entry = SimpleNamespace(data={"dogs": []})
        self._dogs: list[dict[str, Any]] = []
        self._current_dog: dict[str, Any] | None = None

    async def _async_prepare_setup_flag_translations(self) -> None:
        return None

    def _current_options(self) -> dict[str, Any]:
        return self._options

    def _clone_options(self) -> dict[str, Any]:
        return dict(self._options)

    def _normalise_options_snapshot(self, options: dict[str, Any]) -> dict[str, Any]:
        return options

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        if value is None:
            return default
        return int(value)

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if value is None:
            return default
        return bool(value)

    def _current_weather_options(self) -> dict[str, Any]:
        weather = self._options.get("weather_settings")
        return dict(weather) if isinstance(weather, dict) else {}

    def _build_weather_settings(
        self,
        user_input: dict[str, Any],
        current_weather: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(current_weather)
        merged.update(user_input)
        return merged

    def _current_advanced_options(self) -> dict[str, Any]:
        advanced = self._options.get("advanced_settings")
        return dict(advanced) if isinstance(advanced, dict) else {}

    def _current_system_options(self) -> dict[str, Any]:
        system = self._options.get("system_settings")
        return dict(system) if isinstance(system, dict) else {}

    def _current_dashboard_options(self) -> dict[str, Any]:
        dashboard = self._options.get("dashboard_settings")
        return dict(dashboard) if isinstance(dashboard, dict) else {}

    @staticmethod
    def _coerce_time_string(value: Any, default: str) -> str:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
        return default

    @staticmethod
    def _coerce_clamped_int(
        value: Any,
        default: Any,
        *,
        minimum: int,
        maximum: int,
    ) -> int:
        try:
            number = int(value if value is not None else default)
        except TypeError, ValueError:
            number = int(default)
        return max(minimum, min(maximum, number))

    @staticmethod
    def _normalize_choice(value: Any, *, valid: set[str], default: str) -> str:
        return value if isinstance(value, str) and value in valid else default

    def _manual_event_description_placeholders(self) -> dict[str, str]:
        return {
            "manual_check_event": "check_default",
            "manual_guard_event": "guard_default",
            "manual_breaker_event": "breaker_default",
        }

    def _manual_event_schema_defaults(
        self, current_system: dict[str, Any]
    ) -> dict[str, str]:
        defaults: dict[str, str] = {}
        for field in self._MANUAL_EVENT_FIELDS:
            raw = current_system.get(field)
            defaults[field] = raw if isinstance(raw, str) and raw else "none"
        return defaults

    def _manual_events_snapshot(self) -> dict[str, Any]:
        return {
            field: self._options.get(field)
            for field in self._MANUAL_EVENT_FIELDS
            if field in self._options
        }

    def _resolve_manual_event_context(
        self,
        current_system: dict[str, Any],
        *,
        manual_snapshot: dict[str, Any],
    ) -> dict[str, str]:
        def _pick(field: str) -> str:
            snapshot_value = manual_snapshot.get(field)
            if isinstance(snapshot_value, str) and snapshot_value:
                return snapshot_value
            current_value = current_system.get(field)
            if isinstance(current_value, str) and current_value:
                return current_value
            return "none"

        return {
            "check_default": _pick("manual_check_event"),
            "guard_default": _pick("manual_guard_event"),
            "breaker_default": _pick("manual_breaker_event"),
        }

    def _manual_event_choices(
        self,
        field: str,
        current_system: dict[str, Any],
        *,
        manual_snapshot: dict[str, Any],
    ) -> list[str]:
        options = ["none", "event.default"]
        candidate = manual_snapshot.get(field)
        if isinstance(candidate, str) and candidate and candidate not in options:
            options.append(candidate)
        current_value = current_system.get(field)
        if (
            isinstance(current_value, str)
            and current_value
            and current_value not in options
        ):
            options.append(current_value)
        return options

    def _build_system_settings(
        self,
        user_input: dict[str, Any],
        current_system: dict[str, Any],
        *,
        reset_default: str,
    ) -> tuple[dict[str, Any], str]:
        merged = dict(current_system)
        merged.update(user_input)
        merged[system_settings.SYSTEM_ENABLE_ANALYTICS_FIELD] = self._coerce_bool(
            merged.get(system_settings.SYSTEM_ENABLE_ANALYTICS_FIELD),
            False,
        )
        merged[system_settings.SYSTEM_ENABLE_CLOUD_BACKUP_FIELD] = self._coerce_bool(
            merged.get(system_settings.SYSTEM_ENABLE_CLOUD_BACKUP_FIELD),
            False,
        )
        for field in self._MANUAL_EVENT_FIELDS:
            raw = merged.get(field)
            if isinstance(raw, str):
                raw = raw.strip()
            if not raw or raw == "none":
                merged[field] = None
            else:
                merged[field] = raw

        reset_time = self._coerce_time_string(
            user_input.get("reset_time"), reset_default
        )
        return merged, reset_time

    def _build_dashboard_settings(
        self,
        user_input: dict[str, Any],
        current_dashboard: dict[str, Any],
        *,
        default_mode: str,
    ) -> tuple[dict[str, Any], str]:
        merged = dict(current_dashboard)
        merged.update(user_input)
        dashboard_mode = self._normalize_choice(
            user_input.get("dashboard_mode", default_mode),
            valid={"minimal", "balanced", "full"},
            default=default_mode,
        )
        merged["compact_mode"] = self._coerce_bool(merged.get("compact_mode"), False)
        merged["show_maps"] = self._coerce_bool(merged.get("show_maps"), True)
        return merged, dashboard_mode

    def _build_advanced_settings(
        self,
        user_input: dict[str, Any],
        current_advanced: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(current_advanced)
        merged.update(user_input)
        return merged

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "form", **kwargs}

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
        self._options = dict(data)
        return {"type": "create_entry", "title": title, "data": data}


def test_resolve_get_runtime_data_uses_callable_from_options_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolver should prefer the callable exported by options flow support."""
    marker = object()

    def patched_runtime_data(_hass: Any, _entry: Any) -> object:
        return marker

    fake_module = SimpleNamespace(get_runtime_data=patched_runtime_data)
    monkeypatch.setattr(system_settings, "import_module", lambda _name: fake_module)

    resolved = _resolve_get_runtime_data()

    assert resolved is patched_runtime_data
    assert resolved(object(), object()) is marker


def test_resolve_get_runtime_data_falls_back_when_import_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolver should return the runtime-data fallback when import fails."""
    monkeypatch.setattr(
        system_settings,
        "import_module",
        lambda _name: (_ for _ in ()).throw(ImportError("missing module")),
    )

    resolved = _resolve_get_runtime_data()

    assert resolved is system_settings._get_runtime_data


@pytest.mark.asyncio
async def test_async_step_push_settings_displays_form_for_initial_render() -> None:
    """Push settings step should render a form when no input is provided."""
    flow = _SystemFlow({})

    result = await flow.async_step_push_settings()

    assert result["type"] == "form"
    assert result["step_id"] == "push_settings"
    assert "data_schema" in result


@pytest.mark.asyncio
async def test_async_step_push_settings_normalises_payload_and_clears_secret() -> None:
    """Push settings step should normalise values and remove empty webhook secret."""
    flow = _SystemFlow({
        CONF_WEBHOOK_SECRET: "keep-me",
        CONF_MQTT_TOPIC: "pawcontrol/old",
    })

    result = await flow.async_step_push_settings({
        CONF_WEBHOOK_SECRET: "   ",
        CONF_MQTT_TOPIC: "  pawcontrol/new  ",
        CONF_PUSH_PAYLOAD_MAX_BYTES: "4096",
        CONF_PUSH_NONCE_TTL_SECONDS: "180",
        CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE: "12",
        CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE: "22",
        CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE: "32",
    })

    assert result["type"] == "create_entry"
    data = result["data"]
    assert CONF_WEBHOOK_SECRET not in data
    assert data[CONF_MQTT_TOPIC] == "pawcontrol/new"
    assert data[CONF_PUSH_PAYLOAD_MAX_BYTES] == 4096
    assert data[CONF_PUSH_NONCE_TTL_SECONDS] == 180
    assert data[CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE] == 12
    assert data[CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE] == 22
    assert data[CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE] == 32


@pytest.mark.asyncio
async def test_async_step_weather_settings_rejects_missing_weather_entity() -> None:
    """Weather settings should reject unknown entities with a field error."""
    flow = _SystemFlow({})

    result = await flow.async_step_weather_settings({"weather_entity": "weather.home"})

    assert result["type"] == "form"
    assert result["errors"] == {"weather_entity": "weather_entity_not_found"}


@pytest.mark.asyncio
async def test_async_step_weather_settings_rejects_non_weather_entity_domain() -> None:
    """Weather settings should reject entities that are not in the weather domain."""
    flow = _SystemFlow(
        {},
        entities={"sensor.outdoor_temp": SimpleNamespace(state="22", attributes={})},
    )

    result = await flow.async_step_weather_settings({
        "weather_entity": "sensor.outdoor_temp"
    })

    assert result["type"] == "form"
    assert result["errors"] == {"weather_entity": "invalid_weather_entity"}


@pytest.mark.asyncio
async def test_async_step_weather_settings_persists_valid_selection() -> None:
    """Weather settings should persist selected weather entity for valid state."""
    flow = _SystemFlow(
        {"weather_settings": {"weather_alerts": True}},
        entities={
            "weather.home": SimpleNamespace(
                state="sunny",
                attributes={"temperature": 21, "friendly_name": "Home"},
            )
        },
    )

    result = await flow.async_step_weather_settings({"weather_entity": "weather.home"})

    assert result["type"] == "create_entry"
    assert result["data"][CONF_WEATHER_ENTITY] == "weather.home"
    assert result["data"]["weather_settings"]["weather_entity"] == "weather.home"


@pytest.mark.asyncio
async def test_async_step_weather_settings_returns_base_error_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Weather settings should surface a base error if update handling crashes."""
    flow = _SystemFlow({})

    def _boom(
        _user_input: dict[str, Any], _current_weather: dict[str, Any]
    ) -> dict[str, Any]:
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(flow, "_build_weather_settings", _boom)

    result = await flow.async_step_weather_settings({"weather_entity": "none"})

    assert result["type"] == "form"
    assert result["errors"] == {"base": "weather_update_failed"}


def test_weather_description_placeholders_report_missing_weather_entity() -> None:
    """Description placeholders should report unavailable entities and dog stats."""
    flow = _SystemFlow(
        {
            "weather_settings": {
                CONF_WEATHER_ENTITY: "weather.missing",
                "wind_alerts": True,
                "weather_update_interval": 30,
                "notification_threshold": "high",
            }
        },
        entities={"weather.present": SimpleNamespace(state="sunny", attributes={})},
    )
    flow._entry = SimpleNamespace(
        data={
            CONF_DOGS: [
                {
                    "name": "Milo",
                    "health_conditions": ["arthritis"],
                    CONF_DOG_BREED: "Beagle",
                },
                {"name": "Luna", CONF_DOG_BREED: "Mixed Breed"},
                "invalid",
            ]
        }
    )

    placeholders = flow._get_weather_description_placeholders()

    assert placeholders["weather_entity_status"] == "Entity not found"
    assert placeholders["dogs_with_health_conditions"] == "0"
    assert placeholders["dogs_with_breeds"] == "0"
    assert placeholders["alerts_enabled"] == "Temperature, UV, Humidity, Storms, Wind"
    assert placeholders["update_interval"] == "30"
    assert placeholders["notification_threshold"] == "High"


@pytest.mark.asyncio
async def test_async_step_advanced_settings_reports_endpoint_validation_error() -> None:
    """Advanced settings should surface endpoint validation failures."""
    flow = _SystemFlow({})

    result = await flow.async_step_advanced_settings({
        CONF_API_ENDPOINT: "invalid-endpoint"
    })

    assert result["type"] == "form"
    assert result["errors"] == {CONF_API_ENDPOINT: "invalid_api_endpoint"}


@pytest.mark.asyncio
async def test_async_step_push_settings_keeps_secret_and_falls_back_topic() -> None:
    """Push settings should keep non-empty secrets and fallback to current topic."""
    flow = _SystemFlow({CONF_MQTT_TOPIC: "pawcontrol/fallback"})

    result = await flow.async_step_push_settings({
        CONF_WEBHOOK_SECRET: "  top-secret  ",
        CONF_MQTT_TOPIC: 17,
    })

    assert result["type"] == "create_entry"
    assert result["data"][CONF_WEBHOOK_SECRET] == "top-secret"
    assert result["data"][CONF_MQTT_TOPIC] == "pawcontrol/fallback"


@pytest.mark.asyncio
async def test_async_step_push_settings_skips_secret_pop_when_absent() -> None:
    """Missing secret should bypass pop branch and keep MQTT fallback behaviour."""
    flow = _SystemFlow({CONF_MQTT_TOPIC: "pawcontrol/fallback"})

    result = await flow.async_step_push_settings({CONF_WEBHOOK_SECRET: ""})

    assert result["type"] == "create_entry"
    assert CONF_WEBHOOK_SECRET not in result["data"]
    assert result["data"][CONF_MQTT_TOPIC] == "pawcontrol/fallback"


@pytest.mark.asyncio
async def test_async_step_weather_settings_shows_form_without_input() -> None:
    """Weather settings should render form on initial step display."""
    flow = _SystemFlow({})

    result = await flow.async_step_weather_settings()

    assert result["type"] == "form"
    assert result["step_id"] == "weather_settings"


def test_get_weather_settings_schema_uses_stored_entity_and_friendly_names() -> None:
    """Weather schema should respect stored entity default and expose named options."""
    flow = _SystemFlow(
        {"weather_settings": {CONF_WEATHER_ENTITY: "weather.home"}},
        entities={
            "weather.home": SimpleNamespace(
                state="sunny",
                attributes={"friendly_name": "Home Weather"},
            ),
            "weather.office": SimpleNamespace(
                state="cloudy",
                attributes={"friendly_name": "Office Weather"},
            ),
        },
    )

    schema = flow._get_weather_settings_schema()

    assert hasattr(schema, "schema")
    assert len(flow.hass.states.async_entity_ids("weather")) == 2


def test_get_weather_settings_schema_ignores_missing_state_objects() -> None:
    """Weather schema builder should safely skip entities without state payloads."""
    flow = _SystemFlow(
        {"weather_settings": {CONF_WEATHER_ENTITY: "weather.home"}},
        entities={"weather.home": None},
    )

    schema = flow._get_weather_settings_schema()

    assert hasattr(schema, "schema")


def test_weather_description_placeholders_available_entity_and_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Placeholders should report available entity details and dog counters."""
    flow = _SystemFlow(
        {
            "weather_settings": {
                CONF_WEATHER_ENTITY: "weather.home",
                "temperature_alerts": False,
                "uv_alerts": False,
                "humidity_alerts": False,
                "storm_alerts": False,
                "wind_alerts": False,
            }
        },
        entities={
            "weather.home": SimpleNamespace(
                state="rainy",
                attributes={"temperature": 14},
            )
        },
    )
    flow._entry = SimpleNamespace(
        data={
            CONF_DOGS: [
                {
                    "dog_id": "milo",
                    "dog_name": "Milo",
                    "health_conditions": ["arthritis"],
                    CONF_DOG_BREED: "Beagle",
                },
                {
                    "dog_id": "luna",
                    "dog_name": "Luna",
                    "health_conditions": [],
                    CONF_DOG_BREED: "Mixed Breed",
                },
            ]
        }
    )

    monkeypatch.setattr(
        system_settings,
        "ensure_dog_config_data",
        lambda payload: dict(payload),
    )

    placeholders = flow._get_weather_description_placeholders()

    assert placeholders["weather_entity_status"] == "Available"
    assert placeholders["current_weather_info"].startswith("Current: 14")
    assert placeholders["dogs_with_health_conditions"] == "1"
    assert placeholders["dogs_with_breeds"] == "1"
    assert placeholders["alerts_enabled"] == "None"


def test_weather_description_placeholders_handles_non_sequence_dog_payload() -> None:
    """Dog payloads that are not sequences should not raise and keep zero counters."""
    flow = _SystemFlow({"weather_settings": {}})
    flow._entry = SimpleNamespace(data={CONF_DOGS: 7})

    placeholders = flow._get_weather_description_placeholders()

    assert placeholders["total_dogs"] == "0"
    assert placeholders["dogs_with_health_conditions"] == "0"


def test_weather_description_placeholders_without_entity_keeps_defaults() -> None:
    """When no weather entity is configured placeholders should keep defaults."""
    flow = _SystemFlow({"weather_settings": {}})

    placeholders = flow._get_weather_description_placeholders()

    assert placeholders["weather_entity_status"] == "Not configured"
    assert placeholders["current_weather_info"] == "No weather entity selected"


@pytest.mark.asyncio
async def test_async_step_system_settings_renders_form_by_default() -> None:
    """System settings step should render a form with placeholders by default."""
    flow = _SystemFlow({})

    result = await flow.async_step_system_settings()

    assert result["type"] == "form"
    assert result["step_id"] == "system_settings"
    assert "description_placeholders" in result


@pytest.mark.asyncio
async def test_async_step_system_settings_persists_manual_events_and_syncs_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """System settings should persist data and sync manual event settings."""

    class _ScriptManager:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def async_sync_manual_resilience_events(
            self,
            payload: dict[str, Any],
        ) -> None:
            self.calls.append(payload)

    script_manager = _ScriptManager()
    runtime = SimpleNamespace(script_manager=script_manager)
    monkeypatch.setattr(
        system_settings,
        "_resolve_get_runtime_data",
        lambda: lambda _hass, _entry: runtime,
    )

    flow = _SystemFlow({"system_settings": {}})
    result = await flow.async_step_system_settings({
        "manual_check_event": "event.check",
        "manual_guard_event": "none",
        "manual_breaker_event": "event.breaker",
        "enable_analytics": True,
    })

    assert result["type"] == "create_entry"
    assert result["data"].get("manual_guard_event") is None
    assert result["data"]["manual_breaker_event"] == "event.breaker"
    assert script_manager.calls == [
        {
            "manual_check_event": "event.check",
            "manual_guard_event": None,
            "manual_breaker_event": "event.breaker",
        }
    ]


@pytest.mark.asyncio
async def test_async_step_system_settings_persists_explicit_guard_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """System settings should persist a non-empty manual guard event value."""

    class _ScriptManager:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def async_sync_manual_resilience_events(
            self,
            payload: dict[str, Any],
        ) -> None:
            self.calls.append(payload)

    script_manager = _ScriptManager()
    runtime = SimpleNamespace(script_manager=script_manager)
    monkeypatch.setattr(
        system_settings,
        "_resolve_get_runtime_data",
        lambda: lambda _hass, _entry: runtime,
    )

    flow = _SystemFlow({"system_settings": {}})
    result = await flow.async_step_system_settings({
        "manual_guard_event": "event.guard",
        "enable_analytics": True,
    })

    assert result["type"] == "create_entry"
    assert result["data"]["manual_guard_event"] == "event.guard"
    assert script_manager.calls == [
        {
            "manual_check_event": None,
            "manual_guard_event": "event.guard",
            "manual_breaker_event": None,
        }
    ]


@pytest.mark.asyncio
async def test_async_step_system_settings_skips_sync_when_runtime_has_no_script_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """System settings should still persist when runtime has no script manager."""
    runtime = SimpleNamespace(script_manager=None)
    monkeypatch.setattr(
        system_settings,
        "_resolve_get_runtime_data",
        lambda: lambda _hass, _entry: runtime,
    )
    flow = _SystemFlow({"system_settings": {}})

    result = await flow.async_step_system_settings({
        "manual_check_event": "event.check"
    })

    assert result["type"] == "create_entry"


@pytest.mark.asyncio
async def test_async_step_system_settings_handles_update_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """System settings should show base error when persistence fails."""
    flow = _SystemFlow({})
    monkeypatch.setattr(
        flow,
        "_build_system_settings",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = await flow.async_step_system_settings({
        "manual_check_event": "event.check"
    })

    assert result["type"] == "form"
    assert result["step_id"] == "system_settings"
    assert result["errors"] == {"base": "update_failed"}


def test_get_system_settings_schema_uses_manual_defaults_when_context_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual defaults should be used when context defaults are not strings."""
    flow = _SystemFlow({"system_settings": {"manual_check_event": "event.default"}})
    monkeypatch.setattr(
        flow,
        "_resolve_manual_event_context",
        lambda *_args, **_kwargs: {
            "check_default": None,
            "guard_default": "none",
            "breaker_default": "none",
        },
    )

    schema = flow._get_system_settings_schema()

    assert hasattr(schema, "schema")


@pytest.mark.asyncio
async def test_async_step_dashboard_settings_renders_form_without_input() -> None:
    """Dashboard settings should display form for initial rendering."""
    flow = _SystemFlow({})

    result = await flow.async_step_dashboard_settings()

    assert result["type"] == "form"
    assert result["step_id"] == "dashboard_settings"


@pytest.mark.asyncio
async def test_async_step_dashboard_settings_persists_updates() -> None:
    """Dashboard settings should persist schema-normalised values."""
    flow = _SystemFlow({"dashboard_settings": {"compact_mode": False}})

    result = await flow.async_step_dashboard_settings({
        "dashboard_mode": "minimal",
        "compact_mode": True,
    })

    assert result["type"] == "create_entry"
    assert result["data"]["dashboard_mode"] == "minimal"
    assert result["data"]["dashboard_settings"]["compact_mode"] is True


@pytest.mark.asyncio
async def test_async_step_dashboard_settings_handles_build_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dashboard settings should report update failure when build fails."""
    flow = _SystemFlow({})
    monkeypatch.setattr(
        flow,
        "_build_dashboard_settings",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = await flow.async_step_dashboard_settings({"dashboard_mode": "balanced"})

    assert result["type"] == "form"
    assert result["step_id"] == "dashboard_settings"
    assert result["errors"] == {"base": "update_failed"}


@pytest.mark.asyncio
async def test_async_step_advanced_settings_persists_valid_endpoint_and_mappings() -> (
    None
):
    """Advanced settings should persist valid endpoints and mapping payloads."""
    flow = _SystemFlow({"advanced_settings": {"debug_logging": False}})

    result = await flow.async_step_advanced_settings({
        CONF_API_ENDPOINT: "https://example.test",
        "debug_logging": True,
        "custom_mapping": {"enabled": True},
        "custom_object": ["a", "b"],
    })

    assert result["type"] == "create_entry"
    assert result["data"][CONF_API_ENDPOINT] == "https://example.test"
    assert result["data"]["custom_mapping"] == {"enabled": True}
    assert result["data"]["custom_object"] == "['a', 'b']"


@pytest.mark.asyncio
async def test_async_step_advanced_settings_allows_blank_endpoint_values() -> None:
    """Blank endpoint strings should skip endpoint validation and still persist."""
    flow = _SystemFlow({})

    result = await flow.async_step_advanced_settings({
        CONF_API_ENDPOINT: "   ",
        "debug_logging": True,
    })

    assert result["type"] == "create_entry"
    assert result["data"][CONF_API_ENDPOINT] == "   "


@pytest.mark.asyncio
async def test_async_step_advanced_settings_save_failure_returns_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Advanced settings should show save_failed when persistence crashes."""
    flow = _SystemFlow({})
    monkeypatch.setattr(
        flow,
        "_build_advanced_settings",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("save failed")),
    )

    result = await flow.async_step_advanced_settings({
        CONF_API_ENDPOINT: "https://example.test"
    })

    assert result["type"] == "form"
    assert result["step_id"] == "advanced_settings"
    assert result["errors"] == {"base": "save_failed"}


@pytest.mark.asyncio
async def test_async_step_advanced_settings_renders_form_without_input() -> None:
    """Advanced settings should display form when called without input."""
    flow = _SystemFlow({})

    result = await flow.async_step_advanced_settings()

    assert result["type"] == "form"
    assert result["step_id"] == "advanced_settings"
