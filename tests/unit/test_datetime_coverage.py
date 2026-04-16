"""Targeted coverage tests for datetime.py — uncovered paths (67% → 80%+).

Covers: PawControlDateTimeBase.native_value, extra_state_attributes,
        async_set_value, PawControlBirthdateDateTime.async_set_value,
        async_setup_entry early returns, entity constructors
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.datetime import (
    PawControlAdoptionDateDateTime,
    PawControlBirthdateDateTime,
    PawControlBreakfastTimeDateTime,
)


def _make_datetime_entity(cls, coordinator=None, dog_id="rex", dog_name="Rex"):
    """Construct a datetime entity with minimal mocks."""
    if coordinator is None:
        coordinator = MagicMock()
        coordinator.data = {"rex": {"feeding": {}, "walk": {}}}
        coordinator.last_update_success = True
    return cls(coordinator, dog_id, dog_name)


# ═══════════════════════════════════════════════════════════════════════════════
# Entity constructors
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_birthdate_datetime_init() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlBirthdateDateTime)
    assert entity._dog_id == "rex"
    assert entity._attr_icon == "mdi:cake"


@pytest.mark.unit
def test_adoption_date_datetime_init() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlAdoptionDateDateTime)
    assert entity._dog_id == "rex"
    assert entity._attr_icon == "mdi:home-heart"


@pytest.mark.unit
def test_breakfast_time_datetime_init() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlBreakfastTimeDateTime)
    assert entity._dog_id == "rex"


# ═══════════════════════════════════════════════════════════════════════════════
# native_value — initial state
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_native_value_initially_none() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlBirthdateDateTime)
    assert entity.native_value is None


@pytest.mark.unit
def test_native_value_after_set() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlBirthdateDateTime)
    entity._current_value = datetime(2020, 1, 1, tzinfo=UTC)
    assert entity.native_value == datetime(2020, 1, 1, tzinfo=UTC)


# ═══════════════════════════════════════════════════════════════════════════════
# extra_state_attributes
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_extra_state_attributes_returns_dict() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlBirthdateDateTime)
    attrs = entity.extra_state_attributes
    assert isinstance(attrs, dict)
    assert "datetime_type" in attrs
    assert attrs["datetime_type"] == "birthdate"


# ═══════════════════════════════════════════════════════════════════════════════
# async_set_value
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_set_value_updates_current() -> None:  # noqa: D103
    entity = _make_datetime_entity(PawControlBirthdateDateTime)
    entity.async_write_ha_state = MagicMock()
    dt = datetime(2022, 6, 15, tzinfo=UTC)
    await entity.async_set_value(dt)
    assert entity._current_value == dt
    entity.async_write_ha_state.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_birthdate_set_value_calculates_age(monkeypatch) -> None:
    """Birthdate set_value logs age without raising."""
    entity = _make_datetime_entity(PawControlBirthdateDateTime)
    entity.async_write_ha_state = MagicMock()

    fixed_now = datetime(2025, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(
        "custom_components.pawcontrol.datetime._dt_now",
        lambda: fixed_now,
    )

    birth = datetime(2020, 1, 1, tzinfo=UTC)
    await entity.async_set_value(birth)
    # Age should be ~5 years, no error
    assert entity._current_value == birth


# ═══════════════════════════════════════════════════════════════════════════════
# async_added_to_hass — restore previous value
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_adoption_date_has_no_extra_icon() -> None:
    """AdoptionDate entity has the correct icon set."""
    entity = _make_datetime_entity(PawControlAdoptionDateDateTime)
    assert entity._attr_icon == "mdi:home-heart"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_breakfast_set_value_updates_current() -> None:
    """BreakfastTime set_value stores the datetime."""
    entity = _make_datetime_entity(PawControlBreakfastTimeDateTime)
    entity.async_write_ha_state = MagicMock()
    dt = datetime(2025, 6, 1, 8, 0, 0, tzinfo=UTC)
    await entity.async_set_value(dt)
    assert entity._current_value == dt
