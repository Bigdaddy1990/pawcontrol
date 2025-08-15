from datetime import datetime, timedelta
import logging
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.helpers.gps_logic import GPSLogic
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


def test_confirm_walk_start_clears_stale_keys(hass: HomeAssistant, mocker) -> None:
    """Walk start should initialize session state without stale keys."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    gps = GPSLogic(hass, entry)

    gps._walk_sessions["dog1"] = {"foo": "bar"}

    mocker.patch.object(hass, "async_create_task")
    mocker.patch.object(hass.services, "async_call", AsyncMock())

    gps._confirm_walk_start("dog1", "door")

    session = gps._walk_sessions["dog1"]
    assert set(session) == {
        "confirmed",
        "start_time",
        "source",
        "total_distance",
        "last_movement",
    }


def test_confirm_walk_end_logs_duration(hass: HomeAssistant, mocker, caplog) -> None:
    """Walk end should log duration when start_time is present."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    gps = GPSLogic(hass, entry)

    start = datetime(2024, 1, 1, tzinfo=dt_util.UTC)
    gps._walk_sessions["dog1"] = {"confirmed": True, "start_time": start}

    mocker.patch.object(hass, "async_create_task")
    mocker.patch.object(hass.services, "async_call", AsyncMock())

    end = start + timedelta(minutes=5)
    mocker.patch("homeassistant.util.dt.now", return_value=end)

    with caplog.at_level(logging.INFO):
        gps._confirm_walk_end("dog1", "done")

    assert "after 5.0 minutes" in caplog.text
