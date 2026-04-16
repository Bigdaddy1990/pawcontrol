from collections.abc import Mapping  # noqa: D100
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant")

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.date import (
    PawControlAdoptionDate,
    PawControlBirthdateDate,
    PawControlDateBase,
    PawControlDewormingDate,
    PawControlDietStartDate,
    PawControlLastVetVisitDate,
    PawControlNextTrainingDate,
    PawControlNextVetAppointmentDate,
    PawControlVaccinationDate,
)
from custom_components.pawcontrol.entity import PawControlDogEntityBase
from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.types import (
    CoordinatorDogData,
    DogProfileSnapshot,
    HealthModulePayload,
    PawControlConfigEntry,
)


@dataclass
class _DummyEntry:
    entry_id: str


class _DummyCoordinator:
    """Minimal coordinator double tailored for date entity tests."""

    def __init__(self) -> None:
        self.data: dict[str, CoordinatorDogData] = {}
        self.config_entry = cast(PawControlConfigEntry, _DummyEntry("entry"))
        self.last_update_success = True
        self.runtime_managers = None

    def async_add_listener(self, _callback):  # pragma: no cover - coordinator protocol
        return lambda: None

    async def async_request_refresh(
        self,
    ) -> None:  # pragma: no cover - protocol stub
        return None

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        return self.data.get(dog_id)

    def get_enabled_modules(
        self, dog_id: str
    ) -> frozenset[str]:  # pragma: no cover - unused
        return frozenset()

    @property
    def available(
        self,
    ) -> bool:  # pragma: no cover - compatibility helper
        return True


class _BrokenDateEntity(PawControlDateBase):
    """Minimal test double that raises while applying values."""

    def __init__(self, coordinator: PawControlCoordinator) -> None:
        super().__init__(coordinator, "dog-1", "Buddy", "broken_date")

    async def _async_handle_date_set(self, value: date) -> None:
        raise RuntimeError(f"cannot store {value.isoformat()}")

    def _extract_date_from_dog_data(self, dog_data: CoordinatorDogData) -> date | None:
        raise RuntimeError("bad snapshot")


@pytest.mark.asyncio
async def test_birthdate_extra_attributes_typed(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure birthdate entities expose structured, typed attributes."""
    coordinator = _DummyCoordinator()
    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
            "status": "online",
            "last_update": datetime.now(tz=UTC).isoformat(),
            "profile": cast(DogProfileSnapshot, {"birthdate": "2020-05-01"}),
        },
    )

    entity = PawControlBirthdateDate(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    entity.hass = hass

    # Freeze time so the derived counters remain deterministic.
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.now",
        lambda: datetime(2024, 5, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.parse_date",
        lambda value: datetime.fromisoformat(str(value)).date(),
        raising=False,
    )

    snapshot = cast(CoordinatorDogData, coordinator.data["dog-1"])
    entity._current_value = entity._extract_date_from_dog_data(snapshot)

    attrs = entity.extra_state_attributes
    assert attrs["dog_id"] == "dog-1"
    assert attrs["date_type"] == "birthdate"
    assert attrs["iso_string"] == "2020-05-01"

    today = date(2024, 5, 1)
    expected_days = (date(2020, 5, 1) - today).days
    assert attrs["days_from_today"] == expected_days
    assert attrs["is_past"] is True
    assert attrs["is_future"] is False
    assert attrs["age_days"] == abs(expected_days)
    assert attrs["age_years"] == round(abs(expected_days) / 365.25, 2)
    assert attrs["age_months"] == round((abs(expected_days) % 365.25) / 30.44, 1)


@pytest.mark.asyncio
async def test_last_vet_visit_extracts_datetime(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure health snapshots provide typed dates for vet visits."""
    coordinator = _DummyCoordinator()
    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
            "status": "online",
            "last_update": datetime.now(tz=UTC).isoformat(),
            "health": cast(
                Mapping[str, object],
                cast(
                    HealthModulePayload, {"last_vet_visit": "2024-04-30T12:30:00+00:00"}
                ),
            ),
        },
    )

    entity = PawControlLastVetVisitDate(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    entity.hass = hass

    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.now",
        lambda: datetime(2024, 5, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.parse_date",
        lambda value: datetime.fromisoformat(str(value)).date(),
        raising=False,
    )

    snapshot = cast(CoordinatorDogData, coordinator.data["dog-1"])
    entity._current_value = entity._extract_date_from_dog_data(snapshot)
    assert entity.native_value == date(2024, 4, 30)

    attrs = entity.extra_state_attributes
    assert attrs["date_type"] == "last_vet_visit"
    assert attrs["is_past"] is True
    assert attrs["days_from_today"] == -1


@pytest.mark.asyncio
async def test_async_added_to_hass_restores_valid_dates(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Date entities should restore valid persisted state."""
    coordinator = _DummyCoordinator()
    entity = PawControlBirthdateDate(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    entity.hass = hass

    async def _super_added(self) -> None:
        return None

    async def _valid_last_state() -> SimpleNamespace:
        return SimpleNamespace(state="2020-06-15")

    monkeypatch.setattr(PawControlDogEntityBase, "async_added_to_hass", _super_added)
    monkeypatch.setattr(entity, "async_get_last_state", _valid_last_state)
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.parse_date",
        lambda value: datetime.fromisoformat(str(value)).date(),
        raising=False,
    )

    await entity.async_added_to_hass()

    assert entity.native_value == date(2020, 6, 15)


@pytest.mark.asyncio
async def test_async_set_value_updates_profile_and_writes_state(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Birthdate updates should persist through the data manager and update state."""
    coordinator = _DummyCoordinator()
    entity = PawControlBirthdateDate(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    entity.hass = hass

    manager = SimpleNamespace(async_update_dog_profile=AsyncMock())
    write_state = Mock()
    monkeypatch.setattr(entity, "_get_data_manager", lambda: manager)
    monkeypatch.setattr(entity, "async_write_ha_state", write_state)
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.now",
        lambda: datetime(2024, 5, 1, tzinfo=UTC),
    )

    new_value = date(2020, 5, 2)
    await entity.async_set_value(new_value)

    assert entity.native_value == new_value
    assert entity._active_update_token is None
    manager.async_update_dog_profile.assert_awaited_once_with(
        "dog-1",
        {"birthdate": "2020-05-02"},
    )
    write_state.assert_called_once_with()


@pytest.mark.asyncio
async def test_async_set_value_rejects_non_date_values(
    hass,
) -> None:
    """Date entities should reject values that are not date objects."""
    coordinator = _DummyCoordinator()
    entity = PawControlBirthdateDate(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    entity.hass = hass

    with pytest.raises(ValidationError, match="Value must be a date object"):
        await entity.async_set_value(cast(date, "2020-05-01"))


@pytest.mark.asyncio
async def test_async_set_value_wraps_handler_errors_and_restores_previous_state(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Handler failures should preserve the previous value and raise ValidationError."""
    coordinator = _DummyCoordinator()
    entity = _BrokenDateEntity(cast(PawControlCoordinator, coordinator))
    entity.hass = hass
    entity._current_value = date(2020, 1, 1)

    write_state = Mock()
    monkeypatch.setattr(entity, "async_write_ha_state", write_state)

    with pytest.raises(ValidationError, match="Failed to set date: cannot store"):
        await entity.async_set_value(date(2024, 5, 3))

    assert entity.native_value == date(2020, 1, 1)
    assert entity._active_update_token is None
    write_state.assert_called_once_with()


def test_handle_coordinator_update_refreshes_values_and_swallow_errors(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coordinator updates should refresh entity values and tolerate bad payloads."""
    coordinator = _DummyCoordinator()
    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
            "status": "online",
            "last_update": datetime.now(tz=UTC).isoformat(),
            "profile": cast(DogProfileSnapshot, {"birthdate": "2021-02-03"}),
        },
    )

    entity = PawControlBirthdateDate(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    entity.hass = hass

    handled_updates: list[str] = []

    def _super_update(self) -> None:
        handled_updates.append("super")

    monkeypatch.setattr(
        CoordinatorEntity,
        "_handle_coordinator_update",
        _super_update,
        raising=False,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.parse_date",
        lambda value: datetime.fromisoformat(str(value)).date(),
        raising=False,
    )

    entity._handle_coordinator_update()

    assert entity.native_value == date(2021, 2, 3)
    assert handled_updates == ["super"]

    broken = _BrokenDateEntity(cast(PawControlCoordinator, coordinator))
    broken.hass = hass
    handled_updates.clear()

    broken._handle_coordinator_update()

    assert handled_updates == ["super"]
    assert broken.native_value is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entity_factory", "service_payload"),
    [
        (
            lambda coordinator: PawControlLastVetVisitDate(
                coordinator, "dog-1", "Buddy"
            ),
            {
                "dog_id": "dog-1",
                "note": "Vet visit recorded for 2024-05-04",
                "health_status": "checked",
            },
        ),
        (
            lambda coordinator: PawControlVaccinationDate(
                coordinator, "dog-1", "Buddy"
            ),
            {
                "dog_id": "dog-1",
                "note": "Vaccination recorded for 2024-05-04",
                "health_status": "vaccinated",
            },
        ),
        (
            lambda coordinator: PawControlDewormingDate(coordinator, "dog-1", "Buddy"),
            {
                "dog_id": "dog-1",
                "note": "Deworming treatment recorded for 2024-05-04",
                "health_status": "treated",
            },
        ),
    ],
)
async def test_health_date_entities_forward_expected_service_payloads(
    hass,
    monkeypatch: pytest.MonkeyPatch,
    entity_factory,
    service_payload: dict[str, str],
) -> None:
    """Health date entities should forward the correct Home Assistant payloads."""
    coordinator = _DummyCoordinator()
    entity = entity_factory(cast(PawControlCoordinator, coordinator))
    entity.hass = hass

    call_service = AsyncMock(return_value=True)
    monkeypatch.setattr(entity, "_async_call_hass_service", call_service)

    await entity._async_handle_date_set(date(2024, 5, 4))

    call_service.assert_awaited_once_with(
        "pawcontrol",
        "log_health_data",
        service_payload,
    )


@pytest.mark.asyncio
async def test_health_date_entities_propagate_service_errors(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Health service logging errors should surface to the caller."""
    coordinator = _DummyCoordinator()
    entity = PawControlVaccinationDate(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    entity.hass = hass

    monkeypatch.setattr(
        entity,
        "_async_call_hass_service",
        AsyncMock(side_effect=RuntimeError("service offline")),
    )

    with pytest.raises(RuntimeError, match="service offline"):
        await entity._async_handle_date_set(date(2024, 5, 4))


@pytest.mark.asyncio
async def test_misc_date_entities_log_without_side_effects(
    hass, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Other date entity handlers should execute their lightweight bookkeeping."""
    coordinator = _DummyCoordinator()
    adoption = PawControlAdoptionDate(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    next_vet = PawControlNextVetAppointmentDate(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    diet = PawControlDietStartDate(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    training = PawControlNextTrainingDate(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    for entity in (adoption, next_vet, diet, training):
        entity.hass = hass

    monkeypatch.setattr(
        "custom_components.pawcontrol.date.dt_util.now",
        lambda: datetime(2024, 5, 1, tzinfo=UTC),
    )

    await adoption._async_handle_date_set(date(2024, 4, 20))
    await next_vet._async_handle_date_set(date(2024, 5, 5))
    await diet._async_handle_date_set(date(2024, 5, 6))
    await training._async_handle_date_set(date(2024, 5, 8))


def test_extractors_fall_back_to_date_strings() -> None:
    """Date extractors should support both date-only and malformed payloads."""
    coordinator = _DummyCoordinator()

    adoption = PawControlAdoptionDate(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    last_vet = PawControlLastVetVisitDate(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )

    adoption_payload = cast(
        CoordinatorDogData,
        {"profile": cast(DogProfileSnapshot, {"adoption_date": "2024-01-02"})},
    )
    vet_payload = cast(
        CoordinatorDogData,
        {"health": cast(HealthModulePayload, {"last_vet_visit": "2024-01-03"})},
    )
    bad_payload = cast(
        CoordinatorDogData,
        {"health": cast(HealthModulePayload, {"last_vet_visit": "bad-date"})},
    )

    from custom_components.pawcontrol import date as date_module

    date_module.dt_util.parse_date = lambda value: datetime.fromisoformat(
        str(value)
    ).date()

    assert adoption._extract_date_from_dog_data(adoption_payload) == date(2024, 1, 2)
    assert last_vet._extract_date_from_dog_data(vet_payload) == date(2024, 1, 3)
    assert last_vet._extract_date_from_dog_data(bad_payload) is None
