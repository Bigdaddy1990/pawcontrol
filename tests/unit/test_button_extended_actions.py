"""Extended coverage for walk, GPS, health and garden action buttons."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest

from custom_components.pawcontrol import button


def _coordinator(dog_id: str = "dog-1") -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = {dog_id: {}}
    coordinator.last_update_success = True
    coordinator.available = True
    coordinator.get_dog_data = MagicMock(return_value=coordinator.data[dog_id])
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_request_selective_refresh = AsyncMock()
    coordinator.config_entry = SimpleNamespace(entry_id="entry-1")
    coordinator.hass = SimpleNamespace(config=SimpleNamespace(language="en"))
    return coordinator


@pytest.mark.unit
@pytest.mark.asyncio
async def test_walk_buttons_validate_state_and_availability() -> None:
    """Start/end walk controls should validate state before service calls."""
    coordinator = _coordinator()

    start_btn = button.PawControlStartWalkButton(coordinator, "dog-1", "Buddy")
    start_btn._get_walk_payload = lambda: {  # type: ignore[method-assign]
        button.WALK_IN_PROGRESS_FIELD: True,
        "current_walk_id": 123,
        "current_walk_start": "2026-01-01T08:00:00+00:00",
    }
    with pytest.raises(HomeAssistantError):
        await start_btn.async_press()

    start_btn._get_walk_payload = lambda: {button.WALK_IN_PROGRESS_FIELD: False}  # type: ignore[method-assign]
    start_btn._async_service_call = AsyncMock(side_effect=ServiceValidationError("bad"))  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await start_btn.async_press()

    start_btn._async_service_call = AsyncMock()  # type: ignore[method-assign]
    await start_btn.async_press()

    start_btn._get_dog_data_cached = lambda: None  # type: ignore[method-assign]
    assert start_btn.available is False
    start_btn._get_dog_data_cached = lambda: {"ok": True}  # type: ignore[method-assign]
    start_btn._get_walk_payload = lambda: None  # type: ignore[method-assign]
    assert start_btn.available is True
    start_btn._get_walk_payload = lambda: {button.WALK_IN_PROGRESS_FIELD: True}  # type: ignore[method-assign]
    assert start_btn.available is False

    end_btn = button.PawControlEndWalkButton(coordinator, "dog-1", "Buddy")
    end_btn._get_walk_payload = lambda: None  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await end_btn.async_press()

    end_btn._get_walk_payload = lambda: {button.WALK_IN_PROGRESS_FIELD: True}  # type: ignore[method-assign]
    end_btn._async_service_call = AsyncMock(side_effect=ServiceValidationError("bad"))  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await end_btn.async_press()

    end_btn._async_service_call = AsyncMock()  # type: ignore[method-assign]
    await end_btn.async_press()

    end_btn._get_dog_data_cached = lambda: None  # type: ignore[method-assign]
    assert end_btn.available is False
    end_btn._get_dog_data_cached = lambda: {"ok": True}  # type: ignore[method-assign]
    end_btn._get_walk_payload = lambda: None  # type: ignore[method-assign]
    assert end_btn.available is False
    end_btn._get_walk_payload = lambda: {button.WALK_IN_PROGRESS_FIELD: True}  # type: ignore[method-assign]
    assert end_btn.available is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_walk_utility_buttons_dispatch_expected_services() -> None:
    """Quick and manual walk controls should dispatch start/end service calls."""
    coordinator = _coordinator()

    quick_btn = button.PawControlQuickWalkButton(coordinator, "dog-1", "Buddy")
    quick_btn._async_press_service = AsyncMock()  # type: ignore[method-assign]
    await quick_btn.async_press()
    assert quick_btn._async_press_service.await_count == 2

    manual_btn = button.PawControlLogWalkManuallyButton(coordinator, "dog-1", "Buddy")
    manual_btn._async_press_service = AsyncMock()  # type: ignore[method-assign]
    await manual_btn.async_press()
    assert manual_btn._async_press_service.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_gps_action_buttons_cover_success_and_error_paths() -> None:
    """GPS action buttons should exercise location, map and export paths."""
    coordinator = _coordinator()

    refresh_btn = button.PawControlRefreshLocationButton(coordinator, "dog-1", "Buddy")
    await refresh_btn.async_press()
    coordinator.async_request_selective_refresh.assert_awaited_with(
        ["dog-1"], priority=9
    )

    coordinator.async_request_selective_refresh = AsyncMock(
        side_effect=RuntimeError("gps")
    )
    with pytest.raises(HomeAssistantError):
        await refresh_btn.async_press()

    alias_btn = button.PawControlUpdateLocationButton(coordinator, "dog-1", "Buddy")
    assert alias_btn._button_type == "update_location"
    assert "update_location" in alias_btn._attr_unique_id

    export_btn = button.PawControlExportRouteButton(coordinator, "dog-1", "Buddy")
    export_btn._async_press_service = AsyncMock()  # type: ignore[method-assign]
    await export_btn.async_press()
    export_btn._async_press_service.assert_awaited()

    center_btn = button.PawControlCenterMapButton(coordinator, "dog-1", "Buddy")
    center_btn._get_gps_payload = lambda: None  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await center_btn.async_press()
    center_btn._get_gps_payload = lambda: {"lat": 1.0}  # type: ignore[method-assign]
    await center_btn.async_press()

    call_btn = button.PawControlCallDogButton(coordinator, "dog-1", "Buddy")
    call_btn._get_gps_payload = lambda: {"source": "manual"}  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await call_btn.async_press()
    call_btn._get_gps_payload = lambda: {"source": "gps"}  # type: ignore[method-assign]
    await call_btn.async_press()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_buttons_cover_validation_and_translations(monkeypatch) -> None:
    """Health-related buttons should cover weight, meds, grooming and checks."""
    coordinator = _coordinator()

    weight_btn = button.PawControlLogWeightButton(coordinator, "dog-1", "Buddy")
    weight_btn._get_module_data = lambda module: (
        {"weight": 21} if module == button.MODULE_HEALTH else {}
    )  # type: ignore[method-assign]
    weight_btn._async_press_service = AsyncMock()  # type: ignore[method-assign]
    await weight_btn.async_press()
    payload = weight_btn._async_press_service.await_args.args[2]
    assert payload["weight"] == 21.0

    weight_btn._get_module_data = lambda _module: {}  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await weight_btn.async_press()

    weight_btn._get_module_data = lambda module: (
        {"weight": 21} if module == button.MODULE_HEALTH else {}
    )  # type: ignore[method-assign]
    weight_btn._async_press_service = AsyncMock(side_effect=RuntimeError("io"))  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError, match="Failed to log weight"):
        await weight_btn.async_press()

    med_btn = button.PawControlLogMedicationButton(coordinator, "dog-1", "Buddy")
    med_btn._get_module_data = lambda _module: {  # type: ignore[method-assign]
        "medications": [{"name": "Vitamin", "dosage": "2 ml"}]
    }
    med_btn._async_press_service = AsyncMock()  # type: ignore[method-assign]
    await med_btn.async_press()
    med_payload = med_btn._async_press_service.await_args.args[2]
    assert med_payload["medication_name"] == "Vitamin"
    assert med_payload["dose"] == "2 ml"

    med_btn._get_module_data = lambda _module: {"medications": [{"name": "Vitamin"}]}  # type: ignore[method-assign]
    med_btn._async_press_service = AsyncMock()  # type: ignore[method-assign]
    await med_btn.async_press()
    med_default_payload = med_btn._async_press_service.await_args.args[2]
    assert med_default_payload["dose"] == "1 dose"

    med_btn._get_module_data = lambda _module: {"medications": []}  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await med_btn.async_press()

    monkeypatch.setattr(
        button, "translated_grooming_label", lambda *_args, **_kwargs: "Start Grooming"
    )
    monkeypatch.setattr(
        button,
        "translated_grooming_template",
        lambda *_args, **kwargs: f"Grooming failed: {kwargs.get('error')}",
    )
    grooming_btn = button.PawControlStartGroomingButton(coordinator, "dog-1", "Buddy")
    grooming_btn.hass = SimpleNamespace(config=SimpleNamespace(language="de"))
    grooming_btn._async_service_call = AsyncMock(side_effect=RuntimeError("network"))  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await grooming_btn.async_press()
    grooming_btn._async_service_call = AsyncMock()  # type: ignore[method-assign]
    await grooming_btn.async_press()

    vet_btn = button.PawControlScheduleVetButton(coordinator, "dog-1", "Buddy")
    vet_btn._async_press_service = AsyncMock()  # type: ignore[method-assign]
    await vet_btn.async_press()

    check_btn = button.PawControlHealthCheckButton(coordinator, "dog-1", "Buddy")
    check_btn._get_module_data = lambda _module: {
        "health_status": "ok",
        "health_alerts": ["a"],
    }  # type: ignore[method-assign]
    await check_btn.async_press()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_garden_buttons_cover_press_and_availability_paths() -> None:
    """Garden buttons should validate session state and availability."""
    coordinator = _coordinator()

    start_btn = button.PawControlStartGardenSessionButton(coordinator, "dog-1", "Buddy")
    start_btn._get_garden_payload = lambda: {"status": "active"}  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await start_btn.async_press()
    start_btn._get_garden_payload = lambda: {"status": "idle"}  # type: ignore[method-assign]
    start_btn._async_service_call = AsyncMock(side_effect=ServiceValidationError("bad"))  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await start_btn.async_press()
    start_btn._async_service_call = AsyncMock()  # type: ignore[method-assign]
    await start_btn.async_press()
    start_btn._get_dog_data_cached = lambda: None  # type: ignore[method-assign]
    assert start_btn.available is False
    start_btn._get_dog_data_cached = lambda: {"ok": True}  # type: ignore[method-assign]
    start_btn._get_garden_payload = lambda: {"status": "active"}  # type: ignore[method-assign]
    assert start_btn.available is False

    end_btn = button.PawControlEndGardenSessionButton(coordinator, "dog-1", "Buddy")
    end_btn._get_garden_payload = lambda: {"status": "idle"}  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await end_btn.async_press()
    end_btn._get_garden_payload = lambda: {"status": "active"}  # type: ignore[method-assign]
    end_btn._async_service_call = AsyncMock(side_effect=ServiceValidationError("bad"))  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await end_btn.async_press()
    end_btn._async_service_call = AsyncMock()  # type: ignore[method-assign]
    await end_btn.async_press()
    end_btn._get_dog_data_cached = lambda: None  # type: ignore[method-assign]
    assert end_btn.available is False
    end_btn._get_dog_data_cached = lambda: {"ok": True}  # type: ignore[method-assign]
    end_btn._get_garden_payload = lambda: {"status": "active"}  # type: ignore[method-assign]
    assert end_btn.available is True

    activity_btn = button.PawControlLogGardenActivityButton(
        coordinator, "dog-1", "Buddy"
    )
    activity_btn._get_garden_payload = lambda: {"status": "idle"}  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await activity_btn.async_press()
    activity_btn._get_garden_payload = lambda: {"status": "active"}  # type: ignore[method-assign]
    activity_btn._async_service_call = AsyncMock(
        side_effect=ServiceValidationError("bad")
    )  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await activity_btn.async_press()
    activity_btn._async_service_call = AsyncMock()  # type: ignore[method-assign]
    await activity_btn.async_press()
    activity_btn._get_dog_data_cached = lambda: None  # type: ignore[method-assign]
    assert activity_btn.available is False
    activity_btn._get_dog_data_cached = lambda: {"ok": True}  # type: ignore[method-assign]
    assert activity_btn.available is True

    confirm_btn = button.PawControlConfirmGardenPoopButton(
        coordinator, "dog-1", "Buddy"
    )
    confirm_btn._async_call_hass_service = AsyncMock(return_value=False)  # type: ignore[method-assign]
    await confirm_btn.async_press()
    confirm_btn._async_call_hass_service = AsyncMock(return_value=True)  # type: ignore[method-assign]
    await confirm_btn.async_press()
    confirm_btn._async_call_hass_service = AsyncMock(
        side_effect=ServiceValidationError("bad")
    )  # type: ignore[method-assign]
    with pytest.raises(HomeAssistantError):
        await confirm_btn.async_press()
    confirm_btn._get_dog_data_cached = lambda: None  # type: ignore[method-assign]
    assert confirm_btn.available is False
    confirm_btn._get_dog_data_cached = lambda: {"ok": True}  # type: ignore[method-assign]
    confirm_btn._get_garden_payload = lambda: {"pending_confirmations": ["x"]}  # type: ignore[method-assign]
    assert confirm_btn.available is True
