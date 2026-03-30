"""Targeted coverage tests for date.py — uncovered paths (49% → 62%+).

Covers: PawControlDateBase.native_value, extra_state_attributes (with/without value,
        birthdate age calc), async_set_value, entity constructors
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pawcontrol.date import (
    PawControlAdoptionDate,
    PawControlBirthdateDate,
    PawControlLastVetVisitDate,
)


def _make_date_entity(cls, coordinator=None, dog_id="rex", dog_name="Rex"):
    coord = coordinator or MagicMock()
    coord.data = {dog_id: {}}
    coord.last_update_success = True
    return cls(coord, dog_id, dog_name)


# ═══════════════════════════════════════════════════════════════════════════════
# Constructors
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_birthdate_date_init() -> None:
    e = _make_date_entity(PawControlBirthdateDate)
    assert e._dog_id == "rex"
    assert e._date_type == "birthdate"


@pytest.mark.unit
def test_adoption_date_init() -> None:
    e = _make_date_entity(PawControlAdoptionDate)
    assert e._date_type == "adoption_date"


@pytest.mark.unit
def test_last_vet_visit_init() -> None:
    e = _make_date_entity(PawControlLastVetVisitDate)
    assert e._date_type == "last_vet_visit"


# ═══════════════════════════════════════════════════════════════════════════════
# native_value
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_native_value_none_initially() -> None:
    e = _make_date_entity(PawControlBirthdateDate)
    assert e.native_value is None


@pytest.mark.unit
def test_native_value_after_set() -> None:
    e = _make_date_entity(PawControlBirthdateDate)
    d = date(2020, 3, 15)
    e._current_value = d
    assert e.native_value == d


# ═══════════════════════════════════════════════════════════════════════════════
# extra_state_attributes
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_extra_state_attributes_no_value() -> None:
    e = _make_date_entity(PawControlBirthdateDate)
    attrs = e.extra_state_attributes
    assert isinstance(attrs, dict)
    assert "date_type" in attrs
    assert "days_from_today" not in attrs


@pytest.mark.unit
def test_extra_state_attributes_future_date(monkeypatch) -> None:
    e = _make_date_entity(PawControlBirthdateDate)
    future = date(2025, 6, 15)
    e._current_value = future

    fixed_now = datetime(2025, 6, 1, tzinfo=UTC)
    import custom_components.pawcontrol.date as date_mod

    monkeypatch.setattr(date_mod.dt_util, "now", lambda: fixed_now)

    attrs = e.extra_state_attributes
    assert attrs["is_future"] is True
    assert attrs["is_past"] is False
    assert attrs["days_from_today"] == 14


@pytest.mark.unit
def test_extra_state_attributes_past_birthdate_has_age(monkeypatch) -> None:
    e = _make_date_entity(PawControlBirthdateDate)
    birth = date(2020, 6, 1)
    e._current_value = birth

    fixed_now = datetime(2025, 6, 1, tzinfo=UTC)
    import custom_components.pawcontrol.date as date_mod

    monkeypatch.setattr(date_mod.dt_util, "now", lambda: fixed_now)

    attrs = e.extra_state_attributes
    assert attrs["is_past"] is True
    assert "age_years" in attrs
    assert attrs["age_years"] == pytest.approx(5.0, abs=0.1)


# ═══════════════════════════════════════════════════════════════════════════════
# async_set_value
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_set_value_updates_current() -> None:
    """async_set_value stores the date (data_manager mocked out)."""
    e = _make_date_entity(PawControlBirthdateDate)
    e.async_write_ha_state = MagicMock()

    # Patch _get_data_manager to return None so no await is attempted
    with patch.object(e, "_get_data_manager", return_value=None):
        d = date(2022, 1, 1)
        await e.async_set_value(d)

    assert e._current_value == d
