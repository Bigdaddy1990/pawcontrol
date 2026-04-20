"""Coverage tests for ProfileAwareButtonFactory and button async setup paths."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol import button


def _dog(dog_id: str = "dog-1", dog_name: str = "Buddy") -> dict[str, object]:
    return {
        button.DOG_ID_FIELD: dog_id,
        button.DOG_NAME_FIELD: dog_name,
    }


def _core_button_class(label: str):
    class _CoreButton:
        def __init__(self, *_args, **_kwargs) -> None:
            self.label = label

    return _CoreButton


@pytest.mark.unit
def test_create_buttons_for_dog_handles_rule_errors_and_limits(monkeypatch) -> None:
    """Factory should continue after rule errors and enforce max profile buttons."""

    class _RuleButton:
        created: list[tuple[str, str, tuple[object, ...]]] = []

        def __init__(
            self,
            _coordinator: object,
            dog_id: str,
            dog_name: str,
            *args: object,
        ) -> None:
            self.created.append((dog_id, dog_name, args))

    class _FailingRuleButton:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(
        button,
        "ensure_dog_modules_projection",
        lambda _dog: SimpleNamespace(
            mapping={"feeding": True, "walk": False, "unknown": True},
            config={"feeding": True},
        ),
    )
    monkeypatch.setattr(
        button,
        "PawControlTestNotificationButton",
        _core_button_class("test_notification"),
    )
    monkeypatch.setattr(
        button,
        "PawControlResetDailyStatsButton",
        _core_button_class("reset_daily_stats"),
    )
    monkeypatch.setattr(
        button,
        "PawControlRefreshDataButton",
        _core_button_class("refresh_data"),
    )
    monkeypatch.setattr(
        button,
        "PawControlSyncDataButton",
        _core_button_class("sync_data"),
    )
    monkeypatch.setattr(
        button,
        "PawControlToggleVisitorModeButton",
        _core_button_class("toggle_visitor_mode"),
    )

    factory = button.ProfileAwareButtonFactory(SimpleNamespace(), profile="advanced")
    factory._button_rules_cache = {
        "feeding": [
            {
                "factory": _RuleButton,
                "type": "rule_ok",
                "priority": 99,
                "args": ("lunch",),
            },
            {
                "factory": _FailingRuleButton,
                "type": "rule_fail",
                "priority": 99,
            },
        ]
    }
    factory.max_buttons = 2

    entities = factory.create_buttons_for_dog(_dog())

    assert len(entities) == 2
    assert _RuleButton.created == [("dog-1", "Buddy", ("lunch",))]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_button_async_setup_entry_returns_when_runtime_missing(
    monkeypatch,
) -> None:
    """Setup should short-circuit when runtime data is unavailable."""
    monkeypatch.setattr(button, "get_runtime_data", lambda _hass, _entry: None)

    add_entities = AsyncMock()
    await button.async_setup_entry(
        SimpleNamespace(),
        SimpleNamespace(entry_id="entry-1"),
        add_entities,
    )

    add_entities.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_button_async_setup_entry_returns_when_no_valid_dogs(monkeypatch) -> None:
    """Setup should stop early when no dog configs survive normalization."""
    runtime = SimpleNamespace(
        coordinator=SimpleNamespace(),
        dogs=["not-a-mapping", _dog()],
        entity_profile="standard",
    )
    add_entities = AsyncMock()
    add_entities_helper = AsyncMock()

    monkeypatch.setattr(button, "get_runtime_data", lambda _hass, _entry: runtime)
    monkeypatch.setattr(button, "ensure_dog_config_data", lambda _raw: None)
    monkeypatch.setattr(button, "async_call_add_entities", add_entities_helper)

    await button.async_setup_entry(
        SimpleNamespace(),
        SimpleNamespace(entry_id="entry-2"),
        add_entities,
    )

    add_entities_helper.assert_not_awaited()


class _SingleBatchFactory:
    def __init__(self, _coordinator: object, _profile: str) -> None:
        return None

    def create_buttons_for_dog(self, dog: dict[str, object]) -> list[object]:
        dog_id = str(dog[button.DOG_ID_FIELD])
        return [f"{dog_id}-a", f"{dog_id}-b"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_button_async_setup_entry_single_batch(monkeypatch) -> None:
    """Setup should add all buttons in a single helper call when count <= batch."""
    runtime = SimpleNamespace(
        coordinator=SimpleNamespace(),
        dogs=[_dog("dog-1", "Buddy"), _dog("dog-2", "Luna")],
        entity_profile="standard",
    )
    add_entities = AsyncMock()
    add_entities_helper = AsyncMock()

    monkeypatch.setattr(button, "get_runtime_data", lambda _hass, _entry: runtime)
    monkeypatch.setattr(button, "ensure_dog_config_data", lambda raw: dict(raw))
    monkeypatch.setattr(
        button,
        "ensure_dog_modules_projection",
        lambda _dog: SimpleNamespace(
            config={"feeding": True}, mapping={"feeding": True}
        ),
    )
    monkeypatch.setattr(button, "ProfileAwareButtonFactory", _SingleBatchFactory)
    monkeypatch.setattr(button, "async_call_add_entities", add_entities_helper)

    await button.async_setup_entry(
        SimpleNamespace(),
        SimpleNamespace(entry_id="entry-3"),
        add_entities,
    )

    assert add_entities_helper.await_count == 1
    args = add_entities_helper.await_args
    entities = args.args[1]
    assert len(entities) == 4
    assert args.kwargs["update_before_add"] is False


class _MultiBatchFactory:
    def __init__(self, _coordinator: object, _profile: str) -> None:
        return None

    def create_buttons_for_dog(self, _dog: dict[str, object]) -> list[object]:
        return [object() for _ in range(10)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_button_async_setup_entry_batches_large_entity_sets(monkeypatch) -> None:
    """Setup should split button entities into multiple batches when count > 15."""
    runtime = SimpleNamespace(
        coordinator=SimpleNamespace(),
        dogs=[_dog("dog-1", "Buddy"), _dog("dog-2", "Luna")],
        entity_profile="advanced",
    )
    add_entities = AsyncMock()
    add_entities_helper = AsyncMock()

    monkeypatch.setattr(button, "get_runtime_data", lambda _hass, _entry: runtime)
    monkeypatch.setattr(button, "ensure_dog_config_data", lambda raw: dict(raw))
    monkeypatch.setattr(
        button,
        "ensure_dog_modules_projection",
        lambda _dog: SimpleNamespace(
            config={"feeding": True}, mapping={"feeding": True}
        ),
    )
    monkeypatch.setattr(button, "ProfileAwareButtonFactory", _MultiBatchFactory)
    monkeypatch.setattr(button, "async_call_add_entities", add_entities_helper)

    await button.async_setup_entry(
        SimpleNamespace(),
        SimpleNamespace(entry_id="entry-4"),
        add_entities,
    )

    assert add_entities_helper.await_count == 2
    batch_sizes = [len(call.args[1]) for call in add_entities_helper.await_args_list]
    assert batch_sizes == [15, 5]
    assert all(
        call.kwargs["update_before_add"] is False
        for call in add_entities_helper.await_args_list
    )
