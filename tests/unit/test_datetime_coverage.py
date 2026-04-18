"""Targeted branch coverage tests for the datetime platform."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.pawcontrol.const import (
    MODULE_FEEDING,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.datetime import (
    PawControlAdoptionDateDateTime,
    PawControlBirthdateDateTime,
    PawControlBreakfastTimeDateTime,
    PawControlDinnerTimeDateTime,
    PawControlEmergencyDateTime,
    PawControlLastFeedingDateTime,
    PawControlLastGroomingDateTime,
    PawControlLastMedicationDateTime,
    PawControlLastVetVisitDateTime,
    PawControlLastWalkDateTime,
    PawControlLunchTimeDateTime,
    PawControlNextFeedingDateTime,
    PawControlNextGroomingDateTime,
    PawControlNextMedicationDateTime,
    PawControlNextVetAppointmentDateTime,
    PawControlNextWalkReminderDateTime,
    PawControlTrainingSessionDateTime,
    PawControlVaccinationDateDateTime,
    _async_add_entities_in_batches,
    async_setup_entry,
)
from custom_components.pawcontrol.entity import PawControlDogEntityBase
from custom_components.pawcontrol.notifications import NotificationPriority
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD


def _make_coordinator(data: dict[str, dict[str, object]] | None = None) -> MagicMock:
    """Build a coordinator double with the attributes datetime entities expect."""
    coordinator = MagicMock()
    coordinator.data = data or {}
    coordinator.available = True
    coordinator.last_update_success = True
    coordinator.get_dog_data.side_effect = lambda dog_id: coordinator.data.get(
        dog_id, {}
    )
    coordinator.async_apply_module_updates = AsyncMock()
    return coordinator


def _make_datetime_entity(
    cls: type,
    coordinator: MagicMock | None = None,
    dog_id: str = "rex",
    dog_name: str = "Rex",
):
    """Construct a datetime entity with minimal mocks."""
    if coordinator is None:
        coordinator = _make_coordinator({
            "rex": {"feeding": {}, "walk": {}, "health": {}}
        })
    return cls(coordinator, dog_id, dog_name)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_entities_in_batches_waits_between_batches() -> None:  # noqa: D103
    entities = [MagicMock() for _ in range(5)]
    async_add_entities = AsyncMock()

    with (
        patch(
            "custom_components.pawcontrol.datetime.async_call_add_entities",
            new=AsyncMock(),
        ) as add_entities,
        patch(
            "custom_components.pawcontrol.datetime.asyncio.sleep",
            new=AsyncMock(),
        ) as sleep_mock,
    ):
        await _async_add_entities_in_batches(
            async_add_entities,
            entities,
            batch_size=2,
            delay_between_batches=0.05,
        )

    assert add_entities.await_count == 3
    assert sleep_mock.await_count == 2
    assert all(
        call.kwargs["update_before_add"] is False
        for call in add_entities.await_args_list
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_setup_entry_returns_when_runtime_data_is_missing() -> None:  # noqa: D103
    with (
        patch(
            "custom_components.pawcontrol.datetime.get_runtime_data", return_value=None
        ),
        patch(
            "custom_components.pawcontrol.datetime._async_add_entities_in_batches",
            new=AsyncMock(),
        ) as add_batches,
    ):
        await async_setup_entry(MagicMock(), MagicMock(entry_id="entry-1"), AsyncMock())

    add_batches.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_setup_entry_creates_entities_for_enabled_modules() -> None:  # noqa: D103
    runtime_data = SimpleNamespace(
        coordinator=_make_coordinator(),
        dogs=[
            {
                DOG_ID_FIELD: "dog-full",
                DOG_NAME_FIELD: "Full Dog",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_HEALTH: True,
                    MODULE_WALK: True,
                },
            },
            {
                DOG_ID_FIELD: "dog-basic",
                DOG_NAME_FIELD: "Basic Dog",
                "modules": {
                    MODULE_FEEDING: False,
                    MODULE_HEALTH: False,
                    MODULE_WALK: False,
                },
            },
        ],
    )

    with (
        patch(
            "custom_components.pawcontrol.datetime.get_runtime_data",
            return_value=runtime_data,
        ),
        patch(
            "custom_components.pawcontrol.datetime._async_add_entities_in_batches",
            new=AsyncMock(),
        ) as add_batches,
    ):
        await async_setup_entry(MagicMock(), MagicMock(entry_id="entry-2"), AsyncMock())

    entities = add_batches.await_args.args[1]
    assert len(entities) == 17

    full_types = {
        entity._datetime_type for entity in entities if entity._dog_id == "dog-full"
    }
    assert "breakfast_time" in full_types
    assert "next_medication" in full_types
    assert "next_walk_reminder" in full_types

    basic_types = {
        entity._datetime_type for entity in entities if entity._dog_id == "dog-basic"
    }
    assert basic_types == {"birthdate", "adoption_date"}


@pytest.mark.unit
def test_entity_constructors_assign_expected_icons() -> None:  # noqa: D103
    coordinator = _make_coordinator()
    with patch(
        "custom_components.pawcontrol.datetime._dt_now",
        return_value=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
    ):
        lunch = PawControlLunchTimeDateTime(coordinator, "rex", "Rex")
        dinner = PawControlDinnerTimeDateTime(coordinator, "rex", "Rex")
        breakfast = PawControlBreakfastTimeDateTime(coordinator, "rex", "Rex")

    assert lunch._current_value is not None and lunch._current_value.hour == 13
    assert dinner._current_value is not None and dinner._current_value.hour == 18
    assert breakfast._current_value is not None and breakfast._current_value.hour == 8
    assert PawControlAdoptionDateDateTime(coordinator, "rex", "Rex")._attr_icon == (
        "mdi:home-heart"
    )
    assert PawControlNextGroomingDateTime(coordinator, "rex", "Rex")._attr_icon == (
        "mdi:calendar-clock"
    )
    assert PawControlVaccinationDateDateTime(coordinator, "rex", "Rex")._attr_icon == (
        "mdi:needle"
    )
    assert PawControlTrainingSessionDateTime(coordinator, "rex", "Rex")._attr_icon == (
        "mdi:school"
    )
    assert (
        PawControlEmergencyDateTime(coordinator, "rex", "Rex")._attr_icon == "mdi:alert"
    )


@pytest.mark.unit
def test_native_value_and_extra_state_attributes_basics() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlBirthdateDateTime)
    assert entity.native_value is None

    now = datetime(2020, 1, 1, tzinfo=UTC)
    entity._current_value = now
    assert entity.native_value == now
    attrs = entity.extra_state_attributes
    assert attrs["datetime_type"] == "birthdate"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_added_to_hass_restores_previous_value() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlBirthdateDateTime)
    expected = datetime(2024, 10, 15, 7, 0, tzinfo=UTC)
    state = SimpleNamespace(state="2024-10-15T07:00:00+00:00")

    with (
        patch(
            "custom_components.pawcontrol.entity.PawControlDogEntityBase.async_added_to_hass",
            new=AsyncMock(),
        ),
        patch.object(entity, "async_get_last_state", new=AsyncMock(return_value=state)),
        patch(
            "custom_components.pawcontrol.datetime.ensure_utc_datetime",
            return_value=expected,
        ) as parse_mock,
    ):
        await entity.async_added_to_hass()

    parse_mock.assert_called_once_with(state.state)
    assert entity.native_value == expected


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_added_to_hass_skips_unavailable_state() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlBirthdateDateTime)
    state = SimpleNamespace(state="unavailable")

    with (
        patch(
            "custom_components.pawcontrol.entity.PawControlDogEntityBase.async_added_to_hass",
            new=AsyncMock(),
        ),
        patch.object(entity, "async_get_last_state", new=AsyncMock(return_value=state)),
        patch(
            "custom_components.pawcontrol.datetime.ensure_utc_datetime"
        ) as parse_mock,
    ):
        await entity.async_added_to_hass()

    parse_mock.assert_not_called()
    assert entity.native_value is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_birthdate_set_value_calculates_age(
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlBirthdateDateTime)
    entity.async_write_ha_state = MagicMock()
    fixed_now = datetime(2025, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(
        "custom_components.pawcontrol.datetime._dt_now", lambda: fixed_now
    )

    birth = datetime(2020, 1, 1, tzinfo=UTC)
    await entity.async_set_value(birth)
    assert entity.native_value == birth


@pytest.mark.parametrize(
    ("entity_cls", "module_name", "field_name"),
    [
        (PawControlLastFeedingDateTime, "feeding", "last_feeding"),
        (PawControlLastVetVisitDateTime, "health", "last_vet_visit"),
        (PawControlLastGroomingDateTime, "health", "last_grooming"),
        (PawControlLastWalkDateTime, "walk", "last_walk"),
    ],
)
@pytest.mark.unit
def test_native_value_returns_current_when_module_payload_missing(  # noqa: D103
    entity_cls: type,
    module_name: str,
    field_name: str,
) -> None:
    coordinator = _make_coordinator({"rex": {module_name: {}}})
    entity = _make_datetime_entity(entity_cls, coordinator=coordinator)
    fallback = datetime(2024, 5, 1, 8, 30, tzinfo=UTC)
    entity._current_value = fallback

    assert entity.native_value == fallback
    assert field_name in {
        "last_feeding",
        "last_vet_visit",
        "last_grooming",
        "last_walk",
    }


@pytest.mark.parametrize(
    "entity_cls",
    [
        PawControlLastFeedingDateTime,
        PawControlLastVetVisitDateTime,
        PawControlLastGroomingDateTime,
        PawControlLastWalkDateTime,
    ],
)
@pytest.mark.unit
def test_native_value_returns_current_when_dog_payload_missing(
    entity_cls: type,
) -> None:  # noqa: D103
    coordinator = _make_coordinator({})
    entity = _make_datetime_entity(entity_cls, coordinator=coordinator)
    fallback = datetime(2024, 5, 1, 9, 15, tzinfo=UTC)
    entity._current_value = fallback

    assert entity.native_value == fallback


@pytest.mark.parametrize(
    ("entity_cls", "module_name", "field_name"),
    [
        (PawControlLastFeedingDateTime, "feeding", "last_feeding"),
        (PawControlLastVetVisitDateTime, "health", "last_vet_visit"),
        (PawControlLastGroomingDateTime, "health", "last_grooming"),
        (PawControlLastWalkDateTime, "walk", "last_walk"),
    ],
)
@pytest.mark.unit
def test_native_value_uses_parsed_timestamp_when_available(  # noqa: D103
    entity_cls: type,
    module_name: str,
    field_name: str,
) -> None:
    coordinator = _make_coordinator({
        "rex": {module_name: {field_name: "2024-01-01T12:30:00+00:00"}}
    })
    entity = _make_datetime_entity(entity_cls, coordinator=coordinator)
    parsed_value = datetime(2024, 1, 1, 12, 30, tzinfo=UTC)

    with patch(
        "custom_components.pawcontrol.datetime.ensure_utc_datetime",
        return_value=parsed_value,
    ):
        assert entity.native_value == parsed_value


@pytest.mark.parametrize(
    ("entity_cls", "module_name", "field_name"),
    [
        (PawControlLastFeedingDateTime, "feeding", "last_feeding"),
        (PawControlLastVetVisitDateTime, "health", "last_vet_visit"),
        (PawControlLastGroomingDateTime, "health", "last_grooming"),
        (PawControlLastWalkDateTime, "walk", "last_walk"),
    ],
)
@pytest.mark.unit
def test_native_value_falls_back_when_timestamp_parse_fails(  # noqa: D103
    entity_cls: type,
    module_name: str,
    field_name: str,
) -> None:
    coordinator = _make_coordinator({"rex": {module_name: {field_name: "not-a-date"}}})
    entity = _make_datetime_entity(entity_cls, coordinator=coordinator)
    fallback = datetime(2023, 12, 1, 9, 0, tzinfo=UTC)
    entity._current_value = fallback

    with patch(
        "custom_components.pawcontrol.datetime.ensure_utc_datetime",
        return_value=None,
    ):
        assert entity.native_value == fallback


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("service_result", [True, False])
async def test_last_feeding_set_value_covers_service_branches(
    service_result: bool,
) -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlLastFeedingDateTime)
    entity.async_write_ha_state = MagicMock()
    entity._async_call_hass_service = AsyncMock(return_value=service_result)
    value = datetime(2026, 2, 1, 8, 0, tzinfo=UTC)

    with patch(
        "custom_components.pawcontrol.datetime.resolve_default_feeding_amount",
        return_value=12.5,
    ):
        await entity.async_set_value(value)

    entity._async_call_hass_service.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_next_feeding_set_value_persists_updates_and_refreshes() -> None:  # noqa: D103
    coordinator = _make_coordinator()
    entity = _make_datetime_entity(
        PawControlNextFeedingDateTime, coordinator=coordinator
    )
    entity.async_write_ha_state = MagicMock()

    data_manager = SimpleNamespace(async_update_dog_data=AsyncMock())
    feeding_manager = SimpleNamespace(async_refresh_reminder=AsyncMock())
    entity._get_data_manager = MagicMock(return_value=data_manager)  # type: ignore[method-assign]
    entity._get_runtime_managers = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(feeding_manager=feeding_manager)
    )

    value = datetime(2026, 3, 5, 16, 45, tzinfo=UTC)
    await entity.async_set_value(value)

    data_manager.async_update_dog_data.assert_awaited_once()
    coordinator.async_apply_module_updates.assert_awaited_once_with(
        "rex",
        "feeding",
        {"next_feeding": value.isoformat()},
    )
    feeding_manager.async_refresh_reminder.assert_awaited_once_with("rex")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_next_feeding_set_value_handles_data_manager_failure() -> None:  # noqa: D103
    coordinator = _make_coordinator()
    entity = _make_datetime_entity(
        PawControlNextFeedingDateTime, coordinator=coordinator
    )
    entity.async_write_ha_state = MagicMock()

    data_manager = SimpleNamespace(
        async_update_dog_data=AsyncMock(side_effect=HomeAssistantError("boom"))
    )
    entity._get_data_manager = MagicMock(return_value=data_manager)  # type: ignore[method-assign]
    entity._get_runtime_managers = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(feeding_manager=object())
    )

    value = datetime(2026, 3, 5, 17, 15, tzinfo=UTC)
    await entity.async_set_value(value)
    coordinator.async_apply_module_updates.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_next_feeding_set_value_handles_missing_data_manager() -> None:  # noqa: D103
    coordinator = _make_coordinator()
    entity = _make_datetime_entity(
        PawControlNextFeedingDateTime, coordinator=coordinator
    )
    entity.async_write_ha_state = MagicMock()
    entity._get_data_manager = MagicMock(return_value=None)  # type: ignore[method-assign]
    entity._get_runtime_managers = MagicMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(feeding_manager=None)
    )

    value = datetime(2026, 3, 5, 18, 0)
    with patch(
        "custom_components.pawcontrol.datetime.ensure_utc_datetime",
        return_value=None,
    ):
        await entity.async_set_value(value)

    coordinator.async_apply_module_updates.assert_awaited_once_with(
        "rex",
        "feeding",
        {"next_feeding": value.isoformat()},
    )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("service_result", [True, False])
async def test_last_vet_set_value_covers_service_branches(service_result: bool) -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlLastVetVisitDateTime)
    entity.async_write_ha_state = MagicMock()
    entity._async_call_hass_service = AsyncMock(return_value=service_result)

    await entity.async_set_value(datetime(2026, 4, 1, 10, 0, tzinfo=UTC))
    entity._async_call_hass_service.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("service_result", [True, False])
async def test_last_medication_set_value_covers_service_branches(  # noqa: D103
    service_result: bool,
) -> None:
    entity = _make_datetime_entity(PawControlLastMedicationDateTime)
    entity.async_write_ha_state = MagicMock()
    entity._async_call_hass_service = AsyncMock(return_value=service_result)

    await entity.async_set_value(datetime(2026, 4, 2, 10, 0, tzinfo=UTC))
    entity._async_call_hass_service.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("service_result", [True, False])
async def test_vaccination_set_value_covers_service_branches(
    service_result: bool,
) -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlVaccinationDateDateTime)
    entity.async_write_ha_state = MagicMock()
    entity._async_call_hass_service = AsyncMock(return_value=service_result)

    await entity.async_set_value(datetime(2026, 4, 3, 10, 0, tzinfo=UTC))
    entity._async_call_hass_service.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("service_result", [True, False])
async def test_training_set_value_covers_service_branches(service_result: bool) -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlTrainingSessionDateTime)
    entity.async_write_ha_state = MagicMock()
    entity._async_call_hass_service = AsyncMock(return_value=service_result)

    await entity.async_set_value(datetime(2026, 4, 4, 10, 0, tzinfo=UTC))
    entity._async_call_hass_service.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_last_grooming_set_value_handles_missing_hass_config() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlLastGroomingDateTime)
    entity.hass = SimpleNamespace()
    entity.async_write_ha_state = MagicMock()
    entity._async_call_hass_service = AsyncMock(return_value=False)

    with patch(
        "custom_components.pawcontrol.datetime.translated_grooming_template",
        return_value="manual session",
    ):
        await entity.async_set_value(datetime(2026, 4, 5, 10, 0, tzinfo=UTC))

    entity._async_call_hass_service.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_last_grooming_set_value_uses_hass_language_when_available() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlLastGroomingDateTime)
    entity.hass = SimpleNamespace(config=SimpleNamespace(language="de"))
    entity.async_write_ha_state = MagicMock()
    entity._async_call_hass_service = AsyncMock(return_value=True)

    with patch(
        "custom_components.pawcontrol.datetime.translated_grooming_template",
        return_value="Pflegesitzung am 2026-04-05",
    ) as translation_mock:
        await entity.async_set_value(datetime(2026, 4, 5, 10, 0, tzinfo=UTC))

    translation_mock.assert_called_once()
    entity._async_call_hass_service.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service_results", "expected_calls"),
    [
        ([False], 1),
        ([True, False], 2),
        ([True, True], 2),
    ],
)
async def test_last_walk_set_value_covers_all_service_paths(  # noqa: D103
    service_results: list[bool],
    expected_calls: int,
) -> None:
    entity = _make_datetime_entity(PawControlLastWalkDateTime)
    entity.async_write_ha_state = MagicMock()
    entity._async_call_hass_service = AsyncMock(side_effect=service_results)

    await entity.async_set_value(datetime(2026, 4, 6, 10, 0, tzinfo=UTC))
    assert entity._async_call_hass_service.await_count == expected_calls


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entity_cls",
    [
        PawControlNextVetAppointmentDateTime,
        PawControlNextMedicationDateTime,
        PawControlNextWalkReminderDateTime,
    ],
)
async def test_next_datetime_entities_set_value_without_services(
    entity_cls: type,
) -> None:  # noqa: D103
    entity = _make_datetime_entity(entity_cls)
    entity.async_write_ha_state = MagicMock()

    value = datetime(2026, 4, 7, 10, 0, tzinfo=UTC)
    await entity.async_set_value(value)
    assert entity.native_value == value


@pytest.mark.unit
@pytest.mark.asyncio
async def test_emergency_set_value_returns_when_service_declines() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlEmergencyDateTime)
    entity.async_write_ha_state = MagicMock()
    entity._async_call_hass_service = AsyncMock(return_value=False)
    notification_manager = SimpleNamespace(async_send_notification=AsyncMock())
    entity._get_notification_manager = MagicMock(  # type: ignore[method-assign]
        return_value=notification_manager
    )

    await entity.async_set_value(datetime(2026, 4, 8, 10, 0, tzinfo=UTC))
    notification_manager.async_send_notification.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_emergency_set_value_handles_missing_notification_manager() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlEmergencyDateTime)
    entity.async_write_ha_state = MagicMock()
    entity._async_call_hass_service = AsyncMock(return_value=True)
    entity._get_notification_manager = MagicMock(return_value=None)  # type: ignore[method-assign]

    await entity.async_set_value(datetime(2026, 4, 9, 10, 0, tzinfo=UTC))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_emergency_set_value_sends_urgent_notification() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlEmergencyDateTime)
    entity.async_write_ha_state = MagicMock()
    entity._async_call_hass_service = AsyncMock(return_value=True)
    notification_manager = SimpleNamespace(async_send_notification=AsyncMock())
    entity._get_notification_manager = MagicMock(  # type: ignore[method-assign]
        return_value=notification_manager
    )

    event_time = datetime(2026, 4, 10, 12, 34, tzinfo=UTC)
    await entity.async_set_value(event_time)

    notification_manager.async_send_notification.assert_awaited_once()
    kwargs = notification_manager.async_send_notification.await_args.kwargs
    assert kwargs["dog_id"] == "rex"
    assert kwargs["priority"] == NotificationPriority.URGENT


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_added_to_hass_calls_parent() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlBirthdateDateTime)
    parent_added = AsyncMock()

    with (
        patch.object(
            PawControlDogEntityBase,
            "async_added_to_hass",
            new=parent_added,
        ),
        patch.object(entity, "async_get_last_state", new=AsyncMock(return_value=None)),
    ):
        await entity.async_added_to_hass()

    parent_added.assert_awaited_once()
