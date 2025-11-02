from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import cast

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.date import (
    PawControlBirthdateDate,
    PawControlLastVetVisitDate,
)
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

    async def async_request_refresh(self) -> None:  # pragma: no cover - protocol stub
        return None

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        return self.data.get(dog_id)

    def get_enabled_modules(self, dog_id: str) -> frozenset[str]:  # pragma: no cover - unused
        return frozenset()

    @property
    def available(self) -> bool:  # pragma: no cover - compatibility helper
        return True


@pytest.mark.asyncio
async def test_birthdate_extra_attributes_typed(hass, monkeypatch: pytest.MonkeyPatch) -> None:
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

    entity = PawControlBirthdateDate(cast(PawControlCoordinator, coordinator), "dog-1", "Buddy")
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
async def test_last_vet_visit_extracts_datetime(hass, monkeypatch: pytest.MonkeyPatch) -> None:
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
                cast(HealthModulePayload, {"last_vet_visit": "2024-04-30T12:30:00+00:00"}),
            ),
        },
    )

    entity = PawControlLastVetVisitDate(cast(PawControlCoordinator, coordinator), "dog-1", "Buddy")
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
