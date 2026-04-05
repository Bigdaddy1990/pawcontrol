"""Coverage tests for the system settings flow step mixin."""

from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.pawcontrol.const import (
    CONF_API_ENDPOINT,
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
        return [entity_id for entity_id in self._entities if entity_id.startswith(prefix)]


class _SystemFlow(SystemSettingsOptionsMixin):
    def __init__(self, options: dict[str, Any], *, entities: dict[str, Any] | None = None) -> None:
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
    """Resolver should prefer callable get_runtime_data exported by options flow support."""
    marker = object()

    def patched_runtime_data(_hass: Any, _entry: Any) -> object:
        return marker

    fake_module = SimpleNamespace(get_runtime_data=patched_runtime_data)
    monkeypatch.setattr(system_settings, "import_module", lambda _name: fake_module)

    resolved = _resolve_get_runtime_data()

    assert resolved is patched_runtime_data
    assert resolved(object(), object()) is marker


@pytest.mark.asyncio
async def test_async_step_push_settings_normalises_payload_and_clears_secret() -> None:
    """Push settings step should normalise values and remove empty webhook secret."""
    flow = _SystemFlow(
        {
            CONF_WEBHOOK_SECRET: "keep-me",
            CONF_MQTT_TOPIC: "pawcontrol/old",
        }
    )

    result = await flow.async_step_push_settings(
        {
            CONF_WEBHOOK_SECRET: "   ",
            CONF_MQTT_TOPIC: "  pawcontrol/new  ",
            CONF_PUSH_PAYLOAD_MAX_BYTES: "4096",
            CONF_PUSH_NONCE_TTL_SECONDS: "180",
            CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE: "12",
            CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE: "22",
            CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE: "32",
        }
    )

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
async def test_async_step_advanced_settings_reports_endpoint_validation_error() -> None:
    """Advanced settings should surface endpoint validation failures."""
    flow = _SystemFlow({})

    result = await flow.async_step_advanced_settings({CONF_API_ENDPOINT: "invalid-endpoint"})

    assert result["type"] == "form"
    assert result["errors"] == {CONF_API_ENDPOINT: "invalid_api_endpoint"}
