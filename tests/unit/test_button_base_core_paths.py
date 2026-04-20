"""Additional coverage tests for button base helpers and core actions."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.pawcontrol import button


def _coordinator(dog_id: str = "dog-1") -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = {dog_id: {"visitor_mode_active": True}}
    coordinator.last_update_success = True
    coordinator.available = True
    coordinator.get_dog_data = MagicMock(return_value=coordinator.data[dog_id])
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_request_selective_refresh = AsyncMock()
    coordinator.config_entry = SimpleNamespace(entry_id="entry-1")
    return coordinator


def _registry() -> SimpleNamespace:
    return SimpleNamespace(async_call=AsyncMock())


@pytest.mark.unit
def test_button_base_helpers_cover_normalization_and_payload_access(
    monkeypatch,
) -> None:
    """Base helper methods should normalize flags, parse datetimes and payloads."""
    entity = button.PawControlTestNotificationButton(_coordinator(), "dog-1", "Buddy")

    payloads = {
        button.MODULE_GPS: {"lat": 1.0},
        button.MODULE_GARDEN: {"status": "active"},
    }
    entity._get_module_data = lambda module: payloads.get(module)  # type: ignore[method-assign]

    attrs = entity.extra_state_attributes
    assert attrs["button_type"] == "test_notification"
    assert attrs["action_description"] == "Send a test notification"
    assert entity._get_gps_payload() == {"lat": 1.0}
    assert entity._get_garden_payload() == {"status": "active"}

    assert entity._normalize_module_flag(True, "x") is True
    assert entity._normalize_module_flag(1, "x") is True
    assert entity._normalize_module_flag("yes", "x") is True
    assert entity._normalize_module_flag("off", "x") is False
    assert entity._normalize_module_flag("unexpected", "x") is False

    parsed = entity._parse_datetime("2026-01-02T03:04:05+00:00")
    assert isinstance(parsed, datetime)
    assert entity._parse_datetime(datetime(2026, 1, 1, tzinfo=UTC)) is not None
    assert entity._parse_datetime("invalid") is None

    entity._get_dog_data_cached = lambda: {"ok": True}  # type: ignore[method-assign]
    assert entity.available is True
    entity._get_dog_data_cached = lambda: None  # type: ignore[method-assign]
    assert entity.available is False

    fake_registry = _registry()
    monkeypatch.setattr(button.HomeAssistant, "services", fake_registry, raising=False)
    entity.hass = None
    assert entity._ensure_patchable_services() is fake_registry

    monkeypatch.setattr(button.HomeAssistant, "services", object(), raising=False)
    assert entity._ensure_patchable_services() is None


@pytest.mark.unit
def test_ensure_patchable_services_prefers_proxy_then_hass_service_like(
    monkeypatch,
) -> None:
    """When hass exists, use proxy first and fallback to service-like objects."""
    entity = button.PawControlTestNotificationButton(_coordinator(), "dog-1", "Buddy")

    proxy_registry = _registry()
    entity.hass = SimpleNamespace(services=object())
    monkeypatch.setattr(button, "_prepare_service_proxy", lambda _hass: proxy_registry)
    assert entity._ensure_patchable_services() is proxy_registry

    service_like = _registry()
    entity.hass = SimpleNamespace(services=service_like)
    monkeypatch.setattr(button, "_prepare_service_proxy", lambda _hass: None)
    assert entity._ensure_patchable_services() is service_like


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_service_call_handles_missing_registry_and_payload_changes(
    monkeypatch,
) -> None:
    """Service calls should no-op without a registry and call through otherwise."""
    entity = button.PawControlTestNotificationButton(_coordinator(), "dog-1", "Buddy")

    entity._ensure_patchable_services = lambda: None  # type: ignore[method-assign]
    await entity._async_service_call("pawcontrol", "noop", {"value": 1})

    registry = _registry()
    entity._ensure_patchable_services = lambda: registry  # type: ignore[method-assign]

    monkeypatch.setattr(
        button, "normalize_value", lambda payload: {"x": payload["x"] + 1}
    )
    await entity._async_service_call("pawcontrol", "value_change", {"x": 1})
    registry.async_call.assert_awaited_with("pawcontrol", "value_change", {"x": 2})

    monkeypatch.setattr(
        button, "normalize_value", lambda _payload: {"x": 1, "extra": 2}
    )
    await entity._async_service_call("pawcontrol", "key_change", {"x": 1})
    registry.async_call.assert_awaited_with(
        "pawcontrol", "key_change", {"x": 1, "extra": 2}
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_press_service_wraps_errors() -> None:
    """_async_press_service should convert runtime failures to HomeAssistantError."""
    entity = button.PawControlTestNotificationButton(_coordinator(), "dog-1", "Buddy")
    entity._async_service_call = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

    with pytest.raises(HomeAssistantError):
        await entity._async_press_service(
            "pawcontrol",
            "failing",
            {"a": 1},
            error_message="call failed",
            blocking=False,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_button_actions_cover_press_paths(monkeypatch) -> None:
    """Core button implementations should call expected service/refresh helpers."""
    coordinator = _coordinator()

    test_btn = button.PawControlTestNotificationButton(coordinator, "dog-1", "Buddy")
    test_btn._async_press_service = AsyncMock()  # type: ignore[method-assign]
    await test_btn.async_press()
    assert test_btn._last_pressed is not None
    test_btn._async_press_service.assert_awaited()

    refresh_btn = button.PawControlRefreshDataButton(coordinator, "dog-1", "Buddy")
    await refresh_btn.async_press()
    coordinator.async_request_refresh.assert_awaited()

    sync_btn = button.PawControlSyncDataButton(coordinator, "dog-1", "Buddy")
    await sync_btn.async_press()
    coordinator.async_request_selective_refresh.assert_awaited_with(
        ["dog-1"], priority=10
    )

    visitor_btn = button.PawControlToggleVisitorModeButton(
        coordinator, "dog-1", "Buddy"
    )
    visitor_btn._async_service_call = AsyncMock()  # type: ignore[method-assign]
    await visitor_btn.async_press()
    visitor_btn._async_service_call.assert_awaited()
    payload = visitor_btn._async_service_call.await_args.args[2]
    assert payload["enabled"] is False

    runtime = SimpleNamespace(
        runtime_managers=SimpleNamespace(
            data_manager=SimpleNamespace(async_reset_dog_daily_stats=AsyncMock())
        ),
        data_manager=None,
    )
    monkeypatch.setattr(button, "get_runtime_data", lambda _hass, _entry: runtime)
    reset_btn = button.PawControlResetDailyStatsButton(coordinator, "dog-1", "Buddy")
    reset_btn.hass = SimpleNamespace()
    await reset_btn.async_press()
    runtime.runtime_managers.data_manager.async_reset_dog_daily_stats.assert_awaited_with(
        "dog-1"
    )
    coordinator.async_request_selective_refresh.assert_awaited_with(
        ["dog-1"], priority=8
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_button_actions_raise_expected_errors(monkeypatch) -> None:
    """Error paths should raise HomeAssistantError for core action buttons."""
    coordinator = _coordinator()

    monkeypatch.setattr(button, "get_runtime_data", lambda _hass, _entry: None)
    reset_btn = button.PawControlResetDailyStatsButton(coordinator, "dog-1", "Buddy")
    reset_btn.hass = SimpleNamespace()
    with pytest.raises(HomeAssistantError):
        await reset_btn.async_press()

    runtime_without_data_manager = SimpleNamespace(
        runtime_managers=SimpleNamespace(data_manager=None),
        data_manager=None,
    )
    monkeypatch.setattr(
        button,
        "get_runtime_data",
        lambda _hass, _entry: runtime_without_data_manager,
    )
    with pytest.raises(HomeAssistantError, match="Data manager not available"):
        await reset_btn.async_press()

    coordinator.async_request_refresh = AsyncMock(side_effect=RuntimeError("refresh"))
    refresh_btn = button.PawControlRefreshDataButton(coordinator, "dog-1", "Buddy")
    with pytest.raises(HomeAssistantError):
        await refresh_btn.async_press()

    coordinator.async_request_selective_refresh = AsyncMock(
        side_effect=RuntimeError("sync")
    )
    sync_btn = button.PawControlSyncDataButton(coordinator, "dog-1", "Buddy")
    with pytest.raises(HomeAssistantError):
        await sync_btn.async_press()

    visitor_btn = button.PawControlToggleVisitorModeButton(
        coordinator, "dog-1", "Buddy"
    )
    visitor_btn._async_service_call = AsyncMock(side_effect=RuntimeError("visitor"))  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await visitor_btn.async_press()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_feeding_buttons_cover_meal_selection_and_payloads(monkeypatch) -> None:
    """Feeding buttons should resolve meal type/amount and dispatch service payloads."""
    coordinator = _coordinator()
    monkeypatch.setattr(button, "resolve_default_feeding_amount", lambda *_args: 42)

    mark_fed_btn = button.PawControlMarkFedButton(coordinator, "dog-1", "Buddy")
    mark_fed_btn._async_press_service = AsyncMock()  # type: ignore[method-assign]
    monkeypatch.setattr(
        button.dt_util, "now", lambda: datetime(2026, 1, 1, 9, tzinfo=UTC)
    )
    await mark_fed_btn.async_press()
    assert (
        mark_fed_btn._async_press_service.await_args.args[2]["meal_type"] == "breakfast"
    )

    monkeypatch.setattr(
        button.dt_util, "now", lambda: datetime(2026, 1, 1, 23, tzinfo=UTC)
    )
    await mark_fed_btn.async_press()
    assert mark_fed_btn._async_press_service.await_args.args[2]["meal_type"] == "snack"

    feed_now_btn = button.PawControlFeedNowButton(coordinator, "dog-1", "Buddy")
    feed_now_btn._async_press_service = AsyncMock()  # type: ignore[method-assign]
    await feed_now_btn.async_press()
    assert (
        feed_now_btn._async_press_service.await_args.args[2]["meal_type"] == "immediate"
    )

    feed_meal_btn = button.PawControlFeedMealButton(
        coordinator, "dog-1", "Buddy", "dinner"
    )
    feed_meal_btn._async_press_service = AsyncMock()  # type: ignore[method-assign]
    await feed_meal_btn.async_press()
    assert (
        feed_meal_btn._async_press_service.await_args.args[2]["meal_type"] == "dinner"
    )

    custom_btn = button.PawControlLogCustomFeedingButton(coordinator, "dog-1", "Buddy")
    custom_btn._async_press_service = AsyncMock()  # type: ignore[method-assign]
    await custom_btn.async_press()
    assert (
        custom_btn._async_press_service.await_args.args[2]["notes"]
        == "Custom feeding via button"
    )
