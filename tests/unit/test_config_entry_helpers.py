from types import SimpleNamespace  # noqa: D100
from typing import Any

from custom_components.pawcontrol.config_entry_helpers import get_entry_dogs
from custom_components.pawcontrol.const import CONF_DOGS


def _entry(*, options: dict[str, Any], data: dict[str, Any]) -> Any:
    return SimpleNamespace(options=options, data=data)


def test_get_entry_dogs_prefers_options_list() -> None:  # noqa: D103
    dogs = [{"id": "alpha"}]
    entry = _entry(options={CONF_DOGS: dogs}, data={CONF_DOGS: [{"id": "beta"}]})

    assert get_entry_dogs(entry) == dogs


def test_get_entry_dogs_falls_back_to_data_list() -> None:  # noqa: D103
    data_dogs = [{"id": "beta"}]
    entry = _entry(options={}, data={CONF_DOGS: data_dogs})

    assert get_entry_dogs(entry) == data_dogs


def test_get_entry_dogs_returns_empty_for_invalid_payloads() -> None:  # noqa: D103
    entry = _entry(
        options={CONF_DOGS: "not-a-list"}, data={CONF_DOGS: "also-not-a-list"}
    )

    assert get_entry_dogs(entry) == []


def test_get_entry_dogs_returns_empty_when_payload_is_missing() -> None:  # noqa: D103
    entry = _entry(options={}, data={})

    assert get_entry_dogs(entry) == []
