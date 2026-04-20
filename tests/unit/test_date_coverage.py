"""Additional coverage tests for the date platform."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import custom_components.pawcontrol.date as date_mod
from custom_components.pawcontrol.date import (
    PawControlAdoptionDate,
    PawControlBirthdateDate,
    PawControlDateBase,
    PawControlDewormingDate,
    PawControlDietStartDate,
    PawControlLastGroomingDate,
    PawControlLastVetVisitDate,
    PawControlNextTrainingDate,
    PawControlVaccinationDate,
    _async_add_entities_in_batches,
    async_setup_entry,
)
from custom_components.pawcontrol.entity import PawControlDogEntityBase
from custom_components.pawcontrol.exceptions import PawControlError, ValidationError
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD


class _TestDateEntity(PawControlDateBase):
    def __init__(
        self, coordinator: object, dog_id: str = "dog-1", dog_name: str = "Dog"
    ) -> None:
        super().__init__(coordinator, dog_id, dog_name, "test_date")


class _TokenChangingDateEntity(_TestDateEntity):
    async def _async_handle_date_set(self, value: date) -> None:
        self._active_update_token = object()
        raise RuntimeError(f"token switched for {value.isoformat()}")


class _TokenChangingSuccessDateEntity(_TestDateEntity):
    async def _async_handle_date_set(self, _value: date) -> None:
        self._active_update_token = object()


@pytest.mark.asyncio
async def test_add_entities_in_batches_waits_between_batches() -> None:  # noqa: D103
    add_entities = AsyncMock()
    entities = [MagicMock() for _ in range(5)]

    with patch(
        "custom_components.pawcontrol.date.asyncio.sleep", new=AsyncMock()
    ) as sleep_mock:
        await _async_add_entities_in_batches(
            add_entities,
            entities,
            batch_size=2,
            delay_between_batches=0.2,
        )

    assert add_entities.await_count == 3
    assert sleep_mock.await_count == 2


@pytest.mark.asyncio
async def test_async_setup_entry_adds_expected_entities() -> None:  # noqa: D103
    coordinator = MagicMock()
    runtime_data = SimpleNamespace(
        coordinator=coordinator,
        dogs=[
            {
                "dog_id": "dog-1",
                "dog_name": "Rex",
                "modules": {"health": True, "feeding": True, "walk": True},
            },
        ],
    )
    add_entities = AsyncMock()

    with (
        patch(
            "custom_components.pawcontrol.date.get_runtime_data",
            return_value=runtime_data,
        ),
        patch(
            "custom_components.pawcontrol.date._async_add_entities_in_batches",
            new=AsyncMock(),
        ) as add_batches,
    ):
        await async_setup_entry(
            MagicMock(), MagicMock(entry_id="entry-1"), add_entities
        )

    entities_arg = add_batches.await_args.args[1]
    assert len(entities_arg) == 14
    assert any(entity._date_type == "birthdate" for entity in entities_arg)
    assert any(entity._date_type == "next_training_date" for entity in entities_arg)


@pytest.mark.asyncio
async def test_async_setup_entry_raises_pawcontrol_error_on_failure() -> None:  # noqa: D103
    with (
        patch(
            "custom_components.pawcontrol.date.get_runtime_data",
            side_effect=RuntimeError("boom"),
        ),
        pytest.raises(PawControlError),
    ):
        await async_setup_entry(MagicMock(), MagicMock(entry_id="entry-1"), AsyncMock())


@pytest.mark.asyncio
async def test_async_added_to_hass_restores_valid_date() -> None:  # noqa: D103
    entity = _TestDateEntity(MagicMock())
    state = SimpleNamespace(state="2024-10-15")

    with (
        patch(
            "custom_components.pawcontrol.entity.PawControlDogEntityBase.async_added_to_hass",
            new=AsyncMock(),
        ),
        patch.object(
            date_mod.dt_util, "parse_date", return_value=date(2024, 10, 15), create=True
        ),
        patch.object(entity, "async_get_last_state", new=AsyncMock(return_value=state)),
    ):
        await entity.async_added_to_hass()

    assert entity.native_value == date(2024, 10, 15)


@pytest.mark.asyncio
async def test_async_added_to_hass_handles_invalid_date() -> None:  # noqa: D103
    entity = _TestDateEntity(MagicMock())
    entity.entity_id = "date.dog_1_test_date"
    state = SimpleNamespace(state="not-a-date")

    with (
        patch(
            "custom_components.pawcontrol.entity.PawControlDogEntityBase.async_added_to_hass",
            new=AsyncMock(),
        ),
        patch.object(
            date_mod.dt_util,
            "parse_date",
            side_effect=ValueError("invalid"),
            create=True,
        ),
        patch.object(entity, "async_get_last_state", new=AsyncMock(return_value=state)),
    ):
        await entity.async_added_to_hass()

    assert entity.native_value is None


@pytest.mark.asyncio
async def test_async_set_value_rejects_non_date() -> None:  # noqa: D103
    entity = _TestDateEntity(MagicMock())

    with pytest.raises(ValidationError):
        await entity.async_set_value("2024-01-01")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_async_set_value_wraps_subclass_error() -> None:  # noqa: D103
    entity = _TestDateEntity(MagicMock())
    entity.async_write_ha_state = MagicMock()

    with (
        patch.object(
            entity,
            "_async_handle_date_set",
            new=AsyncMock(side_effect=RuntimeError("broken")),
        ),
        pytest.raises(ValidationError),
    ):
        await entity.async_set_value(date(2024, 1, 1))


@pytest.mark.asyncio
async def test_handle_coordinator_update_extracts_data() -> None:  # noqa: D103
    coordinator = MagicMock()
    coordinator.get_dog_data.return_value = {"profile": {"birthdate": "2020-01-01"}}
    entity = PawControlBirthdateDate(coordinator, "dog-1", "Rex")

    with (
        patch.object(
            date_mod.dt_util, "parse_date", return_value=date(2020, 1, 1), create=True
        ),
        patch.object(
            PawControlDogEntityBase, "_handle_coordinator_update", create=True
        ),
    ):
        entity._handle_coordinator_update()

    assert entity.native_value == date(2020, 1, 1)


@pytest.mark.parametrize(
    ("entity_cls", "payload", "expected"),
    [
        (
            PawControlBirthdateDate,
            {"profile": {"birthdate": "2021-02-03"}},
            date(2021, 2, 3),
        ),
        (
            PawControlAdoptionDate,
            {"profile": {"adoption_date": "2021-02-03"}},
            date(2021, 2, 3),
        ),
        (
            PawControlLastVetVisitDate,
            {"health": {"last_vet_visit": "2021-02-03T10:00:00+00:00"}},
            date(2021, 2, 3),
        ),
        (
            PawControlLastGroomingDate,
            {"health": {"last_grooming": "2021-02-03"}},
            date(2021, 2, 3),
        ),
    ],
)
@pytest.mark.unit
def test_extract_date_from_payload_variants(  # noqa: D103
    entity_cls: type[PawControlDateBase], payload: dict[str, object], expected: date
) -> None:
    entity = entity_cls(MagicMock(), "dog-1", "Rex")
    with patch.object(
        date_mod.dt_util, "parse_date", return_value=expected, create=True
    ):
        assert entity._extract_date_from_dog_data(payload) == expected


@pytest.mark.asyncio
async def test_health_service_date_entities_call_hass_service() -> None:  # noqa: D103
    for entity in (
        PawControlLastVetVisitDate(MagicMock(), "dog-1", "Rex"),
        PawControlVaccinationDate(MagicMock(), "dog-1", "Rex"),
        PawControlDewormingDate(MagicMock(), "dog-1", "Rex"),
    ):
        entity._async_call_hass_service = AsyncMock(return_value=True)  # type: ignore[attr-defined]
        await entity._async_handle_date_set(date(2024, 4, 1))
        entity._async_call_hass_service.assert_awaited()  # type: ignore[attr-defined]


@pytest.mark.unit
def test_extra_state_attributes_today_date_flags(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity = PawControlBirthdateDate(MagicMock(), "dog-1", "Rex")
    today = date(2025, 6, 1)
    entity._current_value = today

    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.now",
        lambda: datetime(2025, 6, 1, tzinfo=UTC),
    )

    attrs = entity.extra_state_attributes
    assert attrs["is_today"] is True
    assert attrs["days_from_today"] == 0


@pytest.mark.asyncio
async def test_next_training_and_diet_handlers_do_not_raise() -> None:  # noqa: D103
    next_training = PawControlNextTrainingDate(MagicMock(), "dog-1", "Rex")
    diet_start = PawControlDietStartDate(MagicMock(), "dog-1", "Rex")

    await next_training._async_handle_date_set(date(2025, 7, 1))
    await diet_start._async_handle_date_set(date(2025, 6, 1))


@pytest.mark.asyncio
async def test_async_setup_entry_returns_early_when_runtime_data_missing() -> None:
    """Setup should return without registering entities when runtime data is unavailable."""
    add_entities = AsyncMock()
    entry = MagicMock(entry_id="entry-missing")

    with (
        patch("custom_components.pawcontrol.date.get_runtime_data", return_value=None),
        patch(
            "custom_components.pawcontrol.date._async_add_entities_in_batches",
            new=AsyncMock(),
        ) as add_batches,
    ):
        await async_setup_entry(MagicMock(), entry, add_entities)

    add_batches.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_setup_entry_handles_key_and_runtime_errors_per_dog() -> None:
    """Setup should skip malformed dog rows and continue after per-dog failures."""
    coordinator = MagicMock()
    runtime_data = SimpleNamespace(
        coordinator=coordinator,
        dogs=[
            {DOG_NAME_FIELD: "Missing ID"},
            {DOG_ID_FIELD: "boom", DOG_NAME_FIELD: "Boom Dog", "modules": {}},
            {DOG_ID_FIELD: "ok", DOG_NAME_FIELD: "Okay Dog", "modules": {}},
        ],
    )

    def _modules_for_dog(dog: dict[str, object]) -> dict[str, bool]:
        if dog.get(DOG_ID_FIELD) == "boom":
            raise RuntimeError("bad modules")
        return {}

    with (
        patch(
            "custom_components.pawcontrol.date.get_runtime_data",
            return_value=runtime_data,
        ),
        patch(
            "custom_components.pawcontrol.date.ensure_dog_modules_mapping",
            side_effect=_modules_for_dog,
        ),
        patch(
            "custom_components.pawcontrol.date._async_add_entities_in_batches",
            new=AsyncMock(),
        ) as add_batches,
    ):
        await async_setup_entry(MagicMock(), MagicMock(entry_id="entry-errors"), AsyncMock())

    entities = add_batches.await_args.args[1]
    assert len(entities) == 2
    assert all(entity._dog_id == "ok" for entity in entities)


def test_extra_state_attributes_without_current_value() -> None:
    """State attributes should still be returned when no date value is set."""
    entity = _TestDateEntity(MagicMock())

    attrs = entity.extra_state_attributes

    assert attrs["date_type"] == "test_date"
    assert "days_from_today" not in attrs


@pytest.mark.asyncio
async def test_async_added_to_hass_skips_unavailable_state() -> None:
    """Unavailable restored states should be ignored."""
    entity = _TestDateEntity(MagicMock())
    state = SimpleNamespace(state="unavailable")

    with (
        patch(
            "custom_components.pawcontrol.entity.PawControlDogEntityBase.async_added_to_hass",
            new=AsyncMock(),
        ),
        patch.object(entity, "async_get_last_state", new=AsyncMock(return_value=state)),
        patch.object(date_mod.dt_util, "parse_date", create=True) as parse_date,
    ):
        await entity.async_added_to_hass()

    parse_date.assert_not_called()
    assert entity.native_value is None


@pytest.mark.asyncio
async def test_async_set_value_handles_token_switch_without_state_rollback() -> None:
    """If update token changes during failure, rollback write-back should be skipped."""
    entity = _TokenChangingDateEntity(MagicMock())
    entity._current_value = date(2020, 1, 1)
    entity.async_write_ha_state = MagicMock()

    with pytest.raises(ValidationError, match="Failed to set date: token switched"):
        await entity.async_set_value(date(2024, 1, 1))

    entity.async_write_ha_state.assert_not_called()
    assert entity._active_update_token is not None


@pytest.mark.asyncio
async def test_async_set_value_keeps_switched_token_on_success() -> None:
    """When token changes during a successful update, finally should skip token reset."""
    entity = _TokenChangingSuccessDateEntity(MagicMock())
    entity.async_write_ha_state = MagicMock()

    await entity.async_set_value(date(2024, 1, 2))

    assert entity.native_value == date(2024, 1, 2)
    assert entity._active_update_token is not None
    entity.async_write_ha_state.assert_called_once_with()


@pytest.mark.asyncio
async def test_default_date_set_handler_is_noop() -> None:
    """Base date handler should be callable without side effects."""
    entity = _TestDateEntity(MagicMock())
    await entity._async_handle_date_set(date(2025, 1, 1))


def test_base_extract_date_from_dog_data_returns_none() -> None:
    """Base extractor should default to None."""
    entity = _TestDateEntity(MagicMock())
    assert entity._extract_date_from_dog_data({}) is None


@pytest.mark.asyncio
async def test_birthdate_handler_skips_profile_update_without_data_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Birthdate handler should not fail when data manager is unavailable."""
    entity = PawControlBirthdateDate(MagicMock(), "dog-1", "Rex")
    monkeypatch.setattr(entity, "_get_data_manager", lambda: None)
    await entity._async_handle_date_set(date(2024, 1, 1))


@pytest.mark.asyncio
async def test_birthdate_handler_propagates_profile_update_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Birthdate handler should bubble up profile update errors."""
    entity = PawControlBirthdateDate(MagicMock(), "dog-1", "Rex")
    manager = SimpleNamespace(
        async_update_dog_profile=AsyncMock(side_effect=RuntimeError("profile update failed"))
    )
    monkeypatch.setattr(entity, "_get_data_manager", lambda: manager)

    with pytest.raises(RuntimeError, match="profile update failed"):
        await entity._async_handle_date_set(date(2024, 1, 1))


def test_adoption_extractor_returns_none_for_missing_profile_values() -> None:
    """Adoption extractor should return None when no parsable date exists."""
    entity = PawControlAdoptionDate(MagicMock(), "dog-1", "Rex")
    assert entity._extract_date_from_dog_data({"profile": {}}) is None


def test_birthdate_extractor_returns_none_for_missing_profile_values() -> None:
    """Birthdate extractor should return None when no parsable birthdate is available."""
    entity = PawControlBirthdateDate(MagicMock(), "dog-1", "Rex")
    assert entity._extract_date_from_dog_data({"profile": {}}) is None


def test_birthdate_extractor_returns_none_for_non_mapping_profile() -> None:
    """Birthdate extractor should return None when profile payload is not a mapping."""
    entity = PawControlBirthdateDate(MagicMock(), "dog-1", "Rex")
    assert entity._extract_date_from_dog_data({"profile": "invalid"}) is None


def test_adoption_extractor_returns_none_for_non_mapping_profile() -> None:
    """Adoption extractor should return None when profile payload is not a mapping."""
    entity = PawControlAdoptionDate(MagicMock(), "dog-1", "Rex")
    assert entity._extract_date_from_dog_data({"profile": "invalid"}) is None


def test_last_vet_extractor_handles_non_mapping_and_missing_value() -> None:
    """Vet extractor should return None for unsupported health payloads."""
    entity = PawControlLastVetVisitDate(MagicMock(), "dog-1", "Rex")
    assert entity._extract_date_from_dog_data({"health": "invalid"}) is None
    assert entity._extract_date_from_dog_data({"health": {}}) is None


@pytest.mark.asyncio
async def test_last_vet_handler_returns_when_service_declines() -> None:
    """Vet handler should return cleanly when service call reports no-op."""
    entity = PawControlLastVetVisitDate(MagicMock(), "dog-1", "Rex")
    entity._async_call_hass_service = AsyncMock(return_value=False)  # type: ignore[attr-defined]

    await entity._async_handle_date_set(date(2024, 2, 2))

    entity._async_call_hass_service.assert_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_last_vet_handler_propagates_service_exceptions() -> None:
    """Vet handler should re-raise service call failures."""
    entity = PawControlLastVetVisitDate(MagicMock(), "dog-1", "Rex")
    entity._async_call_hass_service = AsyncMock(  # type: ignore[attr-defined]
        side_effect=RuntimeError("vet service failed")
    )

    with pytest.raises(RuntimeError, match="vet service failed"):
        await entity._async_handle_date_set(date(2024, 2, 2))


@pytest.mark.asyncio
async def test_next_vet_handler_skips_reminder_logging_when_far_future(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reminder log branch should be skipped when appointment is not within 7 days."""
    entity = date_mod.PawControlNextVetAppointmentDate(MagicMock(), "dog-1", "Rex")
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.now",
        lambda: datetime(2024, 5, 1, tzinfo=UTC),
    )
    await entity._async_handle_date_set(date(2024, 6, 1))


def test_last_grooming_extractor_falls_back_to_parse_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Grooming extractor should use date parsing fallback when datetime parsing fails."""
    entity = PawControlLastGroomingDate(MagicMock(), "dog-1", "Rex")
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.parse_datetime",
        lambda _value: None,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.parse_date",
        lambda _value: date(2024, 1, 15),
        raising=False,
    )

    extracted = entity._extract_date_from_dog_data({
        "health": {"last_grooming": "2024-01-15"}
    })

    assert extracted == date(2024, 1, 15)


def test_last_grooming_extractor_returns_none_for_missing_value() -> None:
    """Grooming extractor should return None when no grooming date is present."""
    entity = PawControlLastGroomingDate(MagicMock(), "dog-1", "Rex")
    assert entity._extract_date_from_dog_data({"health": {}}) is None


def test_last_grooming_extractor_returns_none_for_non_mapping_health_payload() -> None:
    """Grooming extractor should return None when health payload is not a mapping."""
    entity = PawControlLastGroomingDate(MagicMock(), "dog-1", "Rex")
    assert entity._extract_date_from_dog_data({"health": "invalid"}) is None


@pytest.mark.asyncio
async def test_vaccination_handler_returns_when_service_declines() -> None:
    """Vaccination handler should return when service indicates no action was taken."""
    entity = PawControlVaccinationDate(MagicMock(), "dog-1", "Rex")
    entity._async_call_hass_service = AsyncMock(return_value=False)  # type: ignore[attr-defined]

    await entity._async_handle_date_set(date(2024, 2, 2))

    entity._async_call_hass_service.assert_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_deworming_handler_propagates_service_exceptions() -> None:
    """Deworming handler should re-raise service call failures."""
    entity = PawControlDewormingDate(MagicMock(), "dog-1", "Rex")
    entity._async_call_hass_service = AsyncMock(  # type: ignore[attr-defined]
        side_effect=RuntimeError("deworming service failed")
    )

    with pytest.raises(RuntimeError, match="deworming service failed"):
        await entity._async_handle_date_set(date(2024, 2, 2))


@pytest.mark.asyncio
async def test_deworming_handler_returns_when_service_declines() -> None:
    """Deworming handler should return when service indicates no action was taken."""
    entity = PawControlDewormingDate(MagicMock(), "dog-1", "Rex")
    entity._async_call_hass_service = AsyncMock(return_value=False)  # type: ignore[attr-defined]

    await entity._async_handle_date_set(date(2024, 2, 2))

    entity._async_call_hass_service.assert_awaited()  # type: ignore[attr-defined]


def test_handle_coordinator_update_covers_empty_and_unchanged_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coordinator update should handle missing payloads and unchanged extracted values."""
    coordinator = MagicMock()
    entity = PawControlBirthdateDate(coordinator, "dog-1", "Rex")
    handled_updates: list[str] = []

    def _super_update(_self: object) -> None:
        handled_updates.append("super")

    monkeypatch.setattr(
        PawControlDogEntityBase,
        "_handle_coordinator_update",
        _super_update,
        raising=False,
    )

    coordinator.get_dog_data.return_value = None
    entity._handle_coordinator_update()

    coordinator.get_dog_data.return_value = {"profile": {"birthdate": "2022-01-01"}}
    entity._current_value = date(2022, 1, 1)
    monkeypatch.setattr(
        date_mod.dt_util,
        "parse_date",
        lambda _value: date(2022, 1, 1),
        raising=False,
    )
    entity._handle_coordinator_update()

    assert handled_updates == ["super", "super"]


def test_extra_state_attributes_birthdate_past_includes_age(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Birthdate attributes should expose age details for dates in the past."""
    entity = PawControlBirthdateDate(MagicMock(), "dog-1", "Rex")
    entity._current_value = date(2020, 6, 1)
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.now",
        lambda: datetime(2025, 6, 1, tzinfo=UTC),
    )

    attrs = entity.extra_state_attributes

    assert attrs["is_past"] is True
    assert attrs["age_days"] == (date(2025, 6, 1) - date(2020, 6, 1)).days
    assert attrs["age_years"] > 0
    assert "age_months" in attrs


def test_handle_coordinator_update_logs_extract_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coordinator update should swallow extractor errors and still call super."""
    coordinator = MagicMock()
    coordinator.get_dog_data.return_value = {"profile": {"birthdate": "invalid"}}
    entity = PawControlBirthdateDate(coordinator, "dog-1", "Rex")
    handled_updates: list[str] = []

    def _super_update(_self: object) -> None:
        handled_updates.append("super")

    def _raise(_dog_data: object) -> date | None:
        raise RuntimeError("broken extractor")

    monkeypatch.setattr(
        PawControlDogEntityBase,
        "_handle_coordinator_update",
        _super_update,
        raising=False,
    )
    monkeypatch.setattr(entity, "_extract_date_from_dog_data", _raise)

    entity._handle_coordinator_update()

    assert handled_updates == ["super"]
    assert entity.native_value is None


@pytest.mark.asyncio
async def test_adoption_handler_reports_days_since(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adoption handler should compute and log elapsed days."""
    entity = PawControlAdoptionDate(MagicMock(), "dog-1", "Rex")
    info_mock = MagicMock()
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.now",
        lambda: datetime(2024, 2, 10, tzinfo=UTC),
    )
    monkeypatch.setattr(date_mod._LOGGER, "info", info_mock)

    await entity._async_handle_date_set(date(2024, 2, 1))

    assert info_mock.call_args.args[3] == 9


def test_last_vet_extractor_falls_back_to_parse_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vet extractor should use parse_date when parse_datetime yields no result."""
    entity = PawControlLastVetVisitDate(MagicMock(), "dog-1", "Rex")
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.parse_datetime",
        lambda _value: None,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.parse_date",
        lambda _value: date(2024, 3, 4),
        raising=False,
    )

    extracted = entity._extract_date_from_dog_data({
        "health": {"last_vet_visit": "2024-03-04"}
    })

    assert extracted == date(2024, 3, 4)


@pytest.mark.asyncio
async def test_next_vet_handler_logs_reminder_when_within_week(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Next vet handler should log reminder details when appointment is soon."""
    entity = date_mod.PawControlNextVetAppointmentDate(MagicMock(), "dog-1", "Rex")
    info_mock = MagicMock()
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.now",
        lambda: datetime(2024, 5, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(date_mod._LOGGER, "info", info_mock)

    await entity._async_handle_date_set(date(2024, 5, 4))

    assert any(
        "consider setting up reminders" in call.args[0]
        for call in info_mock.call_args_list
    )


@pytest.mark.asyncio
async def test_vaccination_handler_logs_and_reraises_service_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vaccination handler should debug-log and re-raise service failures."""
    entity = PawControlVaccinationDate(MagicMock(), "dog-1", "Rex")
    entity._async_call_hass_service = AsyncMock(  # type: ignore[attr-defined]
        side_effect=RuntimeError("vaccination failed")
    )
    debug_mock = MagicMock()
    monkeypatch.setattr(date_mod._LOGGER, "debug", debug_mock)

    with pytest.raises(RuntimeError, match="vaccination failed"):
        await entity._async_handle_date_set(date(2024, 2, 2))

    debug_mock.assert_called_once()
