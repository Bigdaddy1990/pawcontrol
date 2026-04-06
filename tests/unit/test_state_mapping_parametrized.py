"""Parametrisierte API→HA Mapping-Tests für Reproduce-State-Preprocessing."""

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import State
import pytest

from custom_components.pawcontrol.number import _preprocess_number_state
from custom_components.pawcontrol.select import _preprocess_select_state
from custom_components.pawcontrol.switch import _preprocess_switch_state
from custom_components.pawcontrol.text import _preprocess_text_state


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("12.5", 12.5, id="number-float-string"),
        pytest.param("7", 7.0, id="number-int-string"),
        pytest.param("invalid", None, id="number-invalid"),
    ],
)
def test_number_state_mapping(raw: str, expected: float | None) -> None:
    assert _preprocess_number_state(State("number.rex", raw)) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(STATE_ON, STATE_ON, id="switch-on"),
        pytest.param(STATE_OFF, STATE_OFF, id="switch-off"),
        pytest.param("unknown", None, id="switch-invalid"),
    ],
)
def test_switch_state_mapping(raw: str, expected: str | None) -> None:
    assert _preprocess_switch_state(State("switch.rex", raw)) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("high", "high", id="select-high"),
        pytest.param("eco", "eco", id="select-eco"),
    ],
)
def test_select_state_mapping(raw: str, expected: str) -> None:
    assert _preprocess_select_state(State("select.rex", raw)) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("Tierarzttermin", "Tierarzttermin", id="text-plain"),
        pytest.param("", "", id="text-empty"),
    ],
)
def test_text_state_mapping(raw: str, expected: str) -> None:
    assert _preprocess_text_state(State("text.rex", raw)) == expected
