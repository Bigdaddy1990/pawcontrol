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


class _TestDateEntity(PawControlDateBase):
    def __init__(
        self, coordinator: object, dog_id: str = "dog-1", dog_name: str = "Dog"
    ) -> None:
        super().__init__(coordinator, dog_id, dog_name, "test_date")


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
