"""Unit tests for system flow step helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.pawcontrol.const import (
    CONF_MQTT_TOPIC,
    CONF_PUSH_NONCE_TTL_SECONDS,
    CONF_PUSH_PAYLOAD_MAX_BYTES,
    CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE,
    CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE,
    CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
    CONF_WEBHOOK_SECRET,
)
from custom_components.pawcontrol.flow_steps.system_settings import (
    SystemSettingsOptionsMixin,
    _resolve_get_runtime_data,
)


class _SystemSettingsHost(SystemSettingsOptionsMixin):
    """Minimal host implementation for exercising the mixin."""

    def __init__(self, current: dict[str, Any]) -> None:
        self._current = dict(current)
        self._created_data: dict[str, Any] | None = None

    async def _async_prepare_setup_flag_translations(self) -> None:
        return None

    def _current_options(self) -> dict[str, Any]:
        return dict(self._current)

    def _clone_options(self) -> dict[str, Any]:
        return dict(self._current)

    def _coerce_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except TypeError, ValueError:
            return default

    def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
        self._created_data = data
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, *, step_id: str, data_schema: object) -> dict[str, Any]:
        return {"type": "form", "step_id": step_id, "data_schema": data_schema}


@pytest.mark.parametrize(
    ("import_error", "patched", "expect_patched"),
    [
        (False, lambda hass, entry: "patched", True),
        (False, None, False),
        (True, None, False),
    ],
)
def test_resolve_get_runtime_data(
    monkeypatch: pytest.MonkeyPatch,
    import_error: bool,
    patched: Any,
    expect_patched: bool,
) -> None:
    """Return patched runtime getter when available."""

    def _fake_import_module(name: str) -> object:
        if import_error:
            raise RuntimeError("boom")
        return SimpleNamespace(get_runtime_data=patched)

    monkeypatch.setattr(
        "custom_components.pawcontrol.flow_steps.system_settings.import_module",
        _fake_import_module,
    )

    resolved = _resolve_get_runtime_data()
    if expect_patched:
        assert resolved is patched
    else:
        assert resolved is not patched


@pytest.mark.asyncio
async def test_async_step_push_settings_shows_form() -> None:
    """The first push settings step shows the expected form."""
    host = _SystemSettingsHost({})

    result = await host.async_step_push_settings()

    assert result["type"] == "form"
    assert result["step_id"] == "push_settings"


@pytest.mark.asyncio
async def test_async_step_push_settings_normalizes_user_input() -> None:
    """Push settings input is normalized and persisted."""
    host = _SystemSettingsHost({
        CONF_MQTT_TOPIC: "pawcontrol/default",
        CONF_PUSH_PAYLOAD_MAX_BYTES: 2048,
        CONF_PUSH_NONCE_TTL_SECONDS: 120,
        CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE: 10,
        CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE: 20,
        CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE: 30,
        CONF_WEBHOOK_SECRET: "old-secret",
    })

    result = await host.async_step_push_settings({
        CONF_MQTT_TOPIC: " pawcontrol/custom ",
        CONF_PUSH_PAYLOAD_MAX_BYTES: "4096",
        CONF_PUSH_NONCE_TTL_SECONDS: "300",
        CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE: "60",
        CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE: "50",
        CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE: "40",
        CONF_WEBHOOK_SECRET: "",
    })

    assert result["type"] == "create_entry"
    saved = result["data"]
    assert saved[CONF_MQTT_TOPIC] == "pawcontrol/custom"
    assert saved[CONF_PUSH_PAYLOAD_MAX_BYTES] == 4096
    assert saved[CONF_PUSH_NONCE_TTL_SECONDS] == 300
    assert saved[CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE] == 60
    assert saved[CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE] == 50
    assert saved[CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE] == 40
    assert CONF_WEBHOOK_SECRET not in saved
