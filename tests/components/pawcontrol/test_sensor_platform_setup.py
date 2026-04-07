"""Coverage tests for sensor platform setup orchestration."""

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("aiohttp")

from custom_components.pawcontrol import sensor
from custom_components.pawcontrol.const import MODULE_FEEDING, MODULE_GPS, MODULE_WALK


class _FakeFactory:
    """Entity factory double with deterministic budget behavior."""

    def __init__(self, budget_remaining: int | str | None = None) -> None:
        self._budget = SimpleNamespace(remaining=budget_remaining)
        self.begin_calls: list[tuple[str, str, int]] = []
        self.finalize_calls: list[tuple[str, str]] = []
        self.config_calls: list[dict[str, object]] = []

    def begin_budget(self, dog_id: str, profile: str, base_allocation: int) -> None:
        self.begin_calls.append((dog_id, profile, base_allocation))

    def finalize_budget(self, dog_id: str, profile: str) -> None:
        self.finalize_calls.append((dog_id, profile))

    def get_budget(self, dog_id: str, profile: str) -> SimpleNamespace:
        return self._budget

    def create_entity_config(self, **kwargs: object) -> dict[str, object] | None:
        self.config_calls.append(dict(kwargs))
        return {"enabled": True}


@pytest.mark.asyncio
async def test_async_setup_entry_skips_when_runtime_data_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    add_entities = AsyncMock()
    monkeypatch.setattr(sensor, "get_runtime_data", lambda _hass, _entry: None)

    await sensor.async_setup_entry(
        SimpleNamespace(),
        SimpleNamespace(entry_id="abc"),
        add_entities,
    )

    add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_builds_entities_and_awaits_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _FakeFactory(budget_remaining=3)
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(),
        dogs=[{"dog_id": "dog-1", "dog_name": "Buddy"}],
        entity_factory=factory,
        entity_profile="standard",
    )

    monkeypatch.setattr(sensor, "get_runtime_data", lambda _hass, _entry: runtime_data)
    monkeypatch.setattr(
        sensor,
        "_create_core_entities",
        lambda *_args: ["core-1", "core-2"],
    )
    monkeypatch.setattr(sensor, "_create_module_entities", lambda *_args: ["module-1"])

    add_entities = AsyncMock(return_value=None)

    await sensor.async_setup_entry(
        SimpleNamespace(),
        SimpleNamespace(entry_id="entry"),
        add_entities,
    )

    add_entities.assert_awaited_once_with(["core-1", "core-2", "module-1"])
    assert factory.begin_calls == [("dog-1", "standard", 2)]
    assert factory.finalize_calls == [("dog-1", "standard")]


@pytest.mark.asyncio
async def test_async_setup_entry_finalizes_budget_when_module_creation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Budget finalization should run even when module entity creation raises."""
    factory = _FakeFactory(budget_remaining=5)
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(),
        dogs=[{"dog_id": "dog-1", "dog_name": "Buddy"}],
        entity_factory=factory,
        entity_profile="standard",
    )
    monkeypatch.setattr(sensor, "get_runtime_data", lambda _hass, _entry: runtime_data)
    monkeypatch.setattr(sensor, "_create_core_entities", lambda *_args: ["core-1"])
    monkeypatch.setattr(
        sensor,
        "_create_module_entities",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("module-failure")),
    )

    with pytest.raises(RuntimeError, match="module-failure"):
        await sensor.async_setup_entry(
            SimpleNamespace(),
            SimpleNamespace(entry_id="entry"),
            AsyncMock(),
        )

    assert factory.begin_calls == [("dog-1", "standard", 1)]
    assert factory.finalize_calls == [("dog-1", "standard")]


def test_create_module_entities_uses_profile_fallback_and_budget_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Entity:
        def __init__(self, _coordinator: object, _dog_id: str, _dog_name: str) -> None:
            self.marker = "ok"

    rules = {
        MODULE_GPS: {
            "standard": [("gps_standard", _Entity, 1)],
        },
        MODULE_FEEDING: {
            "standard": [("feeding_standard", _Entity, 1)],
        },
    }
    monkeypatch.setattr(sensor, "_MODULE_ENTITY_RULES", rules)

    factory = _FakeFactory(budget_remaining=1)

    def _create_config(**kwargs: object) -> dict[str, object] | None:
        # Exhaust budget after the first entity has been approved.
        if kwargs["entity_key"] == "gps_standard":
            factory._budget.remaining = 0
            return {"enabled": True}
        return {"enabled": True}

    factory.create_entity_config = _create_config

    entities = sensor._create_module_entities(
        coordinator=SimpleNamespace(),
        entity_factory=factory,
        dog_id="dog-1",
        dog_name="Buddy",
        modules={MODULE_GPS: True, MODULE_FEEDING: True, MODULE_WALK: False},
        profile="advanced",
    )

    assert len(entities) == 1


def test_coerce_budget_remaining_handles_invalid_values() -> None:
    @dataclass
    class _Budget:
        remaining: object

    assert sensor._coerce_budget_remaining(_Budget("7")) == 7
    assert sensor._coerce_budget_remaining(_Budget(object())) is None
    assert sensor._is_budget_exhausted(_Budget("0")) is True


@pytest.mark.asyncio
async def test_async_setup_entry_skips_registration_when_no_dogs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should skip registration when runtime has no configured dogs."""
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(),
        dogs=[],
        entity_factory=_FakeFactory(),
        entity_profile="standard",
    )
    add_entities = AsyncMock()
    monkeypatch.setattr(sensor, "get_runtime_data", lambda _hass, _entry: runtime_data)

    await sensor.async_setup_entry(
        SimpleNamespace(),
        SimpleNamespace(entry_id="entry"),
        add_entities,
    )

    add_entities.assert_not_called()
