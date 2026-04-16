"""Runtime-heavy coverage tests for ``dashboard_cards.py``."""

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import STATE_UNKNOWN
import pytest

from custom_components.pawcontrol import dashboard_cards as dc
from custom_components.pawcontrol.const import (
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
    MODULE_WALK,
    MODULE_WEATHER,
)
from custom_components.pawcontrol.types import (
    DOG_ID_FIELD,
    DOG_IMAGE_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
)

pytestmark = pytest.mark.unit


def _dog(
    dog_id: str,
    dog_name: str,
    *,
    modules: Mapping[str, bool] | None = None,
    image: str | None = None,
    breed: str | None = None,
) -> dict[str, Any]:
    """Return a valid dog config payload for runtime card tests."""
    payload: dict[str, Any] = {
        DOG_ID_FIELD: dog_id,
        DOG_NAME_FIELD: dog_name,
        DOG_MODULES_FIELD: dict(
            modules
            or {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_HEALTH: True,
                MODULE_GPS: True,
                MODULE_NOTIFICATIONS: True,
                MODULE_VISITOR: True,
                MODULE_WEATHER: True,
            },
        ),
    }
    if image is not None:
        payload[DOG_IMAGE_FIELD] = image
    if breed is not None:
        payload["breed"] = breed
    return payload


def _state(
    state: str = "ok",
    attributes: Mapping[str, object] | None = None,
) -> SimpleNamespace:
    """Return a tiny Home Assistant state double."""
    return SimpleNamespace(state=state, attributes=dict(attributes or {}))


class _StateStore:
    """Simple state registry used by generator test doubles."""

    def __init__(
        self,
        entries: Mapping[str, object] | None = None,
        *,
        failing_ids: set[str] | None = None,
    ) -> None:
        self._entries = dict(entries or {})
        self._failing_ids = set(failing_ids or set())

    def get(self, entity_id: str) -> object | None:
        if entity_id in self._failing_ids:
            raise RuntimeError(f"state lookup failure: {entity_id}")
        return self._entries.get(entity_id)


def _hass(
    entries: Mapping[str, object] | None = None,
    *,
    language: str = "en",
    failing_ids: set[str] | None = None,
) -> Any:
    """Build a lightweight Home Assistant-style object."""
    return SimpleNamespace(
        config=SimpleNamespace(language=language),
        states=_StateStore(entries, failing_ids=failing_ids),
    )


class _TemplatesStub:
    """Template surface used by card generators in runtime tests."""

    def __init__(self) -> None:
        self.get_dog_status_card_template = AsyncMock(
            return_value={"type": "entities", "entities": ["sensor.status"]},
        )
        self.get_action_buttons_template = AsyncMock(
            return_value=[{"type": "button", "name": "Action"}],
        )
        self.get_map_card_template = AsyncMock(
            return_value={"type": "map", "entities": ["device_tracker.alpha_location"]},
        )
        self.get_history_graph_template = AsyncMock(
            return_value={"type": "history-graph", "entities": ["sensor.activity"]},
        )
        self.get_feeding_controls_template = AsyncMock(
            return_value={"type": "horizontal-stack", "cards": []},
        )
        self.get_notification_settings_card_template = AsyncMock(
            return_value={"type": "entities", "entities": []},
        )
        self.get_notifications_overview_card_template = AsyncMock(
            return_value={"type": "markdown", "content": "overview"},
        )
        self.get_notifications_actions_card_template = AsyncMock(
            return_value={"type": "horizontal-stack", "cards": []},
        )
        self.get_weather_recommendations_card_template = AsyncMock(
            return_value={"type": "markdown", "content": "recommendations"},
        )
        self.get_statistics_graph_template = AsyncMock(
            return_value={"type": "statistics-graph", "entities": ["sensor.one"]},
        )
        self.get_statistics_summary_template = MagicMock(
            return_value={"type": "markdown", "content": "summary"},
        )


class _MonotonicLoop:
    """Loop double with deterministic ``time`` progression."""

    def __init__(self, values: list[float]) -> None:
        self._values = values
        self._index = 0

    def time(self) -> float:
        if self._index >= len(self._values):
            return self._values[-1]
        value = self._values[self._index]
        self._index += 1
        return value


@pytest.mark.asyncio
async def test_base_generator_validation_cache_and_error_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover batch validation cache hits, timeouts, failures, and cleanup paths."""
    templates = _TemplatesStub()
    hass = _hass(
        {
            "sensor.valid": _state("on"),
            "sensor.invalid": _state(STATE_UNKNOWN),
            "sensor.cached": _state("on"),
            "sensor.uncached": _state("ready"),
        },
        failing_ids={"sensor.raise"},
    )
    generator = dc.BaseCardGenerator(hass, templates)

    now_loop = _MonotonicLoop([100.0, 100.0, 100.0, 102.5, 103.0, 103.5, 104.0, 104.5])
    monkeypatch.setattr(dc.asyncio, "get_running_loop", lambda: now_loop)
    monkeypatch.setattr(
        dc,
        "_entity_validation_cache",
        {
            "sensor.cached": (99.9, True),
            "sensor.stale": (1.0, True),
        },
    )
    monkeypatch.setattr(dc, "_cache_cleanup_threshold", 50)

    valid = await generator._validate_entities_batch(
        ["sensor.cached", "sensor.stale", "sensor.valid", "sensor.invalid"],
    )
    assert "sensor.cached" in valid
    assert "sensor.valid" in valid
    assert "sensor.invalid" not in valid
    assert generator.performance_stats["cache_hits"] >= 1
    assert generator.performance_stats["cache_misses"] >= 1

    no_cache = await generator._validate_entities_batch(
        ["sensor.valid", "sensor.invalid"],
        use_cache=False,
    )
    assert no_cache == ["sensor.valid"]
    assert await generator._validate_entities_batch([]) == []
    assert await generator._validate_single_entity("sensor.raise") is False
    assert await generator._entity_exists_cached("sensor.uncached") is True

    async def _timeout_wait_for(awaitable: object, timeout: float) -> object:
        _ = timeout
        if hasattr(awaitable, "cancel"):
            awaitable.cancel()  # type: ignore[attr-defined]
        raise TimeoutError

    dc._entity_validation_cache.clear()
    monkeypatch.setattr(dc.asyncio, "wait_for", _timeout_wait_for)
    timed_out = await generator._validate_entities_batch(["sensor.valid"])
    assert timed_out == []

    async def _error_wait_for(awaitable: object, timeout: float) -> object:
        _ = timeout
        if hasattr(awaitable, "cancel"):
            awaitable.cancel()  # type: ignore[attr-defined]
        raise RuntimeError("batch failed")

    monkeypatch.setattr(dc.asyncio, "wait_for", _error_wait_for)
    failed = await generator._validate_entities_batch(["sensor.valid"])
    assert failed == []
    assert generator.performance_stats["errors_handled"] >= 1


@pytest.mark.asyncio
async def test_base_generator_cache_cleanup_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover cache cleanup no-op, expiry removal, and oldest-entry trimming."""
    generator = dc.BaseCardGenerator(_hass(), _TemplatesStub())

    monkeypatch.setattr(
        dc.asyncio, "get_running_loop", lambda: SimpleNamespace(time=lambda: 500.0)
    )
    monkeypatch.setattr(dc, "_cache_cleanup_threshold", 100)

    monkeypatch.setattr(dc, "_entity_validation_cache", {"sensor.keep": (490.0, True)})
    await generator._cleanup_validation_cache()
    assert "sensor.keep" in dc._entity_validation_cache

    large_cache = {f"sensor.{idx}": (float(idx), True) for idx in range(230)}
    large_cache["sensor.expired"] = (1.0, True)
    monkeypatch.setattr(dc, "_entity_validation_cache", large_cache)
    await generator._cleanup_validation_cache()
    assert len(dc._entity_validation_cache) <= dc.VALIDATION_CACHE_SIZE


@pytest.mark.asyncio
async def test_overview_generator_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover welcome, counting, grid rendering, and quick-action branches."""
    templates = _TemplatesStub()
    generator = dc.OverviewCardGenerator(_hass(language="de"), templates)

    dogs = [_dog("alpha", "Alpha"), _dog("beta", "Beta")]
    generator._count_active_dogs = AsyncMock(return_value=1)  # type: ignore[method-assign]
    card = await generator.generate_welcome_card(dogs, {"title": "Pack"})
    assert "Pack" in card["content"]
    assert "currently active" in card["content"]

    async def _timeout_wait_for(awaitable: object, timeout: float) -> object:
        _ = timeout
        if hasattr(awaitable, "cancel"):
            awaitable.cancel()  # type: ignore[attr-defined]
        raise TimeoutError

    monkeypatch.setattr(dc.asyncio, "wait_for", _timeout_wait_for)
    timeout_card = await generator.generate_welcome_card([_dog("solo", "Solo")], {})
    assert "Managing **1** dog" in timeout_card["content"]

    generator = dc.OverviewCardGenerator(_hass(), templates)
    assert await generator._count_active_dogs([]) == 0
    generator._validate_entities_batch = AsyncMock(return_value=["sensor.alpha_status"])  # type: ignore[method-assign]
    assert await generator._count_active_dogs(dogs) == 1

    assert await generator.generate_dogs_grid([{}], "/paw") is None
    assert await generator.generate_dogs_grid([_dog("only-id", "")], "/paw") is None
    generator._validate_entities_batch = AsyncMock(return_value=["sensor.alpha_status"])  # type: ignore[method-assign]
    grid = await generator.generate_dogs_grid(
        [_dog("alpha", "Alpha"), _dog("beta", "Beta")], "/paw"
    )
    assert grid is not None
    assert grid["type"] == "grid"
    generator._validate_entities_batch = AsyncMock(return_value=[])  # type: ignore[method-assign]
    assert await generator.generate_dogs_grid([_dog("alpha", "Alpha")], "/paw") is None

    assert await generator.generate_quick_actions([]) is None
    generator._validate_entities_batch = AsyncMock(
        return_value=[
            f"button.{dc.DOMAIN}_feed_all_dogs",
            f"sensor.{dc.DOMAIN}_dogs_walking",
        ],
    )  # type: ignore[method-assign]
    actions = await generator.generate_quick_actions(dogs)
    assert actions is not None
    assert len(actions["cards"]) == 3

    feeding_only = [
        _dog("feed", "Feed", modules={MODULE_FEEDING: True, MODULE_WALK: False})
    ]
    generator._validate_entities_batch = AsyncMock(
        return_value=[f"button.{dc.DOMAIN}_feed_all_dogs"],
    )  # type: ignore[method-assign]
    feeding_actions = await generator.generate_quick_actions(feeding_only)
    assert feeding_actions is not None
    assert len(feeding_actions["cards"]) == 2


@pytest.mark.asyncio
async def test_dog_generator_core_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover dog overview aggregation, timeout fallback, and helper methods."""
    templates = _TemplatesStub()
    generator = dc.DogCardGenerator(_hass(), templates)

    assert await generator.generate_dog_overview_cards({}, {}, {}) == []

    generator._generate_dog_header_card = AsyncMock(
        return_value={"type": "picture-entity"},
    )  # type: ignore[method-assign]
    generator._generate_gps_map_card = AsyncMock(
        return_value={"type": "map"},
    )  # type: ignore[method-assign]
    generator._generate_activity_graph_card = AsyncMock(
        return_value={"type": "history-graph"},
    )  # type: ignore[method-assign]
    templates.get_action_buttons_template = AsyncMock(
        return_value=[{"type": "button"}, {"type": "conditional"}],
    )

    loop = _MonotonicLoop([1.0, 4.5])
    monkeypatch.setattr(dc.asyncio, "get_running_loop", lambda: loop)

    cards = await generator.generate_dog_overview_cards(
        _dog("alpha", "Alpha", modules={MODULE_GPS: True, MODULE_WALK: True}),
        {},
        {"show_activity_graph": True},
    )
    assert cards
    assert any(card.get("type") == "horizontal-stack" for card in cards)

    async def _timeout_wait_for(awaitable: object, timeout: float) -> object:
        _ = timeout
        if hasattr(awaitable, "cancel"):
            awaitable.cancel()  # type: ignore[attr-defined]
        raise TimeoutError

    monkeypatch.setattr(dc.asyncio, "wait_for", _timeout_wait_for)
    timeout_cards = await generator.generate_dog_overview_cards(
        _dog("beta", "Beta", modules={MODULE_GPS: True, MODULE_WALK: True}),
        {},
        {"show_activity_graph": True},
    )
    assert timeout_cards and timeout_cards[0]["type"] == "markdown"

    assert generator._build_action_button_cards(None) == []
    assert generator._build_action_button_cards([]) == []
    built = generator._build_action_button_cards([
        {"type": "button"},
        {"type": "conditional"},
    ])
    assert built[0]["type"] == "horizontal-stack"

    generator = dc.DogCardGenerator(_hass(), templates)
    generator._entity_exists_cached = AsyncMock(return_value=False)  # type: ignore[method-assign]
    assert await generator._generate_dog_header_card(_dog("gamma", "Gamma"), {}) is None
    generator._entity_exists_cached = AsyncMock(return_value=True)  # type: ignore[method-assign]
    header = await generator._generate_dog_header_card(
        _dog("gamma", "Gamma", image="/local/gamma.png"),
        {},
    )
    assert header is not None
    assert header["image"] == "/local/paw_control/gamma.jpg"

    generator._entity_exists_cached = AsyncMock(return_value=False)  # type: ignore[method-assign]
    assert await generator._generate_gps_map_card("gamma", {}) is None
    generator._entity_exists_cached = AsyncMock(return_value=True)  # type: ignore[method-assign]
    map_card = await generator._generate_gps_map_card("gamma", {"zoom": "8"})
    assert map_card["type"] == "map"

    assert (
        await generator._generate_activity_graph_card(
            _dog("gamma", "Gamma"), {"show_activity_graph": False}
        )
        is None
    )
    assert (
        await generator._generate_activity_graph_card({}, {"show_activity_graph": True})
        is None
    )
    generator._validate_entities_batch = AsyncMock(return_value=[])  # type: ignore[method-assign]
    assert (
        await generator._generate_activity_graph_card(
            _dog("gamma", "Gamma"), {"show_activity_graph": True}
        )
        is None
    )
    generator._validate_entities_batch = AsyncMock(
        return_value=["sensor.gamma_activity_level"]
    )  # type: ignore[method-assign]
    activity = await generator._generate_activity_graph_card(
        _dog("gamma", "Gamma", modules={MODULE_WALK: True}),
        {"show_activity_graph": True},
    )
    assert activity is not None


@pytest.mark.asyncio
async def test_health_aware_feeding_generator_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover health-aware feeding card generation including timeout and fallbacks."""
    templates = _TemplatesStub()
    generator = dc.HealthAwareFeedingCardGenerator(_hass(), templates)
    dog = _dog("healthdog", "Health Dog")

    assert await generator.generate_health_feeding_overview({}, {}) == []

    generator._generate_health_feeding_status_card = AsyncMock(
        return_value={"type": "entities"},
    )  # type: ignore[method-assign]
    generator._generate_calorie_tracking_card = AsyncMock(
        side_effect=RuntimeError("calorie failure"),
    )  # type: ignore[method-assign]
    generator._generate_weight_management_card = AsyncMock(
        return_value={"type": "vertical-stack"},
    )  # type: ignore[method-assign]
    generator._generate_portion_calculator_card = AsyncMock(
        return_value={"type": "vertical-stack"},
    )  # type: ignore[method-assign]
    cards = await generator.generate_health_feeding_overview(dog, {})
    assert cards
    assert generator.performance_stats["errors_handled"] >= 1

    async def _timeout_wait_for(awaitable: object, timeout: float) -> object:
        _ = timeout
        if hasattr(awaitable, "cancel"):
            awaitable.cancel()  # type: ignore[attr-defined]
        raise TimeoutError

    monkeypatch.setattr(dc.asyncio, "wait_for", _timeout_wait_for)
    assert await generator.generate_health_feeding_overview(dog, {}) == []

    generator = dc.HealthAwareFeedingCardGenerator(_hass(), templates)
    generator._entity_exists_cached = AsyncMock(return_value=False)  # type: ignore[method-assign]
    assert (
        await generator._generate_health_feeding_status_card("dog", "Dog", {}, "en")
        is None
    )
    generator._entity_exists_cached = AsyncMock(return_value=True)  # type: ignore[method-assign]
    assert await generator._generate_health_feeding_status_card("dog", "Dog", {}, "en")

    generator._validate_entities_batch = AsyncMock(return_value=[])  # type: ignore[method-assign]
    assert await generator._generate_calorie_tracking_card("dog", {}, "en") is None
    generator._validate_entities_batch = AsyncMock(
        return_value=["sensor.dog_calories_consumed_today"]
    )  # type: ignore[method-assign]
    assert await generator._generate_calorie_tracking_card("dog", {}, "en")

    generator._validate_entities_batch = AsyncMock(return_value=[])  # type: ignore[method-assign]
    assert await generator._generate_weight_management_card("dog", {}, "en") is None
    generator._validate_entities_batch = AsyncMock(
        return_value=["sensor.dog_current_weight"]
    )  # type: ignore[method-assign]
    assert await generator._generate_weight_management_card("dog", {}, "en")

    generator._entity_exists_cached = AsyncMock(return_value=False)  # type: ignore[method-assign]
    assert await generator._generate_portion_calculator_card("dog", {}, "en") is None
    generator._entity_exists_cached = AsyncMock(return_value=True)  # type: ignore[method-assign]
    assert await generator._generate_portion_calculator_card("dog", {}, "en")

    assert await generator.generate_health_feeding_controls({}, {}) == []
    controls = await generator.generate_health_feeding_controls(_dog("dog", "Dog"), {})
    assert controls
    smart = generator._generate_smart_feeding_buttons("dog", {}, "en")
    assert smart["type"] == "grid"


@pytest.mark.asyncio
async def test_module_generator_feeding_walk_health_notification_visitor_and_gps_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover module-specific card generators and their error branches."""
    templates = _TemplatesStub()
    generator = dc.ModuleCardGenerator(_hass(language="de"), templates)

    assert await generator.generate_feeding_cards({}, {}) == []

    async def _health_overview(
        _self: Any,
        _dog_config: Any,
        _options: Any,
    ) -> list[dict[str, Any]]:
        return [{"type": "entities", "title": "health"}]

    async def _health_controls(
        _self: Any,
        _dog_config: Any,
        _options: Any,
    ) -> Any:
        return None

    monkeypatch.setattr(
        dc.HealthAwareFeedingCardGenerator,
        "generate_health_feeding_overview",
        _health_overview,
    )
    monkeypatch.setattr(
        dc.HealthAwareFeedingCardGenerator,
        "generate_health_feeding_controls",
        _health_controls,
    )
    generator._generate_feeding_history_card = AsyncMock(
        return_value={"type": "history-graph", "entities": ["sensor.x"]},
    )  # type: ignore[method-assign]
    feeding_cards = await generator.generate_feeding_cards(
        _dog("feed", "Feed", modules={MODULE_FEEDING: True, MODULE_HEALTH: True}),
        {},
    )
    assert feeding_cards

    async def _raise_gather(*_: object, **__: object) -> object:
        raise RuntimeError("gather failed")

    original_gather = dc.asyncio.gather
    monkeypatch.setattr(dc.asyncio, "gather", _raise_gather)
    generator._generate_standard_feeding_cards = AsyncMock(
        return_value=[{"type": "entities", "title": "fallback"}],
    )  # type: ignore[method-assign]
    generator._generate_feeding_history_card = AsyncMock(
        side_effect=RuntimeError("history failed")
    )  # type: ignore[method-assign]
    fallback_cards = await generator.generate_feeding_cards(
        _dog("feed2", "Feed2", modules={MODULE_FEEDING: True, MODULE_HEALTH: True}),
        {},
    )
    assert fallback_cards
    monkeypatch.setattr(dc.asyncio, "gather", original_gather)

    generator = dc.ModuleCardGenerator(_hass(), templates)
    generator._validate_entities_batch = AsyncMock(
        return_value=["sensor.feed_next_meal_time"]
    )  # type: ignore[method-assign]
    standard_cards = await generator._generate_standard_feeding_cards("feed")
    assert standard_cards
    templates.get_feeding_controls_template = AsyncMock(
        side_effect=RuntimeError("template error")
    )
    generator._validate_entities_batch = AsyncMock(return_value=[])  # type: ignore[method-assign]
    assert await generator._generate_standard_feeding_cards("feed") == []

    templates.get_history_graph_template = AsyncMock(
        return_value={"type": "history-graph", "entities": []},
    )
    assert await generator._generate_feeding_history_card("feed") is None
    templates.get_history_graph_template = AsyncMock(
        return_value={"type": "history-graph", "entities": ["sensor.feed_meals_today"]},
    )
    assert await generator._generate_feeding_history_card("feed")

    assert await generator.generate_walk_cards({}, {}) == []
    generator._validate_entities_batch = AsyncMock(
        return_value=["binary_sensor.walkdog_is_walking", "sensor.walkdog_walks_today"],
    )  # type: ignore[method-assign]
    generator._generate_walk_history_card = AsyncMock(
        return_value={
            "type": "history-graph",
            "entities": ["sensor.walkdog_walks_today"],
        },
    )  # type: ignore[method-assign]
    walk_cards = await generator.generate_walk_cards(
        _dog("walkdog", "Walk Dog", modules={MODULE_WALK: True}),
        {},
    )
    assert walk_cards
    generator._generate_walk_history_card = AsyncMock(
        side_effect=RuntimeError("walk history failed")
    )  # type: ignore[method-assign]
    generator._validate_entities_batch = AsyncMock(return_value=[])  # type: ignore[method-assign]
    assert (
        await generator.generate_walk_cards(
            _dog("walkdog", "Walk Dog", modules={MODULE_WALK: True}),
            {},
        )
        == []
    )

    assert await generator.generate_health_cards({}, {}) == []
    generator._validate_entities_batch = AsyncMock(
        side_effect=[
            ["sensor.hdog_health_status"],
            ["date.hdog_next_vet_visit"],
        ],
    )  # type: ignore[method-assign]
    generator._entity_exists_cached = AsyncMock(return_value=True)  # type: ignore[method-assign]
    templates.get_history_graph_template = AsyncMock(
        return_value={"type": "history-graph", "entities": ["sensor.hdog_weight"]},
    )
    health_cards = await generator.generate_health_cards(
        _dog("hdog", "Health", modules={MODULE_HEALTH: True}),
        {},
    )
    assert health_cards

    generator._validate_entities_batch = AsyncMock(
        side_effect=[RuntimeError("metrics"), RuntimeError("dates")],
    )  # type: ignore[method-assign]
    generator._entity_exists_cached = AsyncMock(return_value=True)  # type: ignore[method-assign]
    templates.get_history_graph_template = AsyncMock(
        side_effect=RuntimeError("weight chart failed")
    )
    health_error_cards = await generator.generate_health_cards(
        _dog("hdog", "Health", modules={MODULE_HEALTH: True}),
        {},
    )
    assert health_error_cards

    assert await generator.generate_notification_cards({}, {}) == []
    assert (
        await generator.generate_notification_cards(
            _dog("n1", "N1", modules={MODULE_NOTIFICATIONS: False}),
            {},
        )
        == []
    )
    generator._validate_entities_batch = AsyncMock(return_value=[])  # type: ignore[method-assign]
    templates.get_notification_settings_card_template = AsyncMock(return_value=None)
    notification_cards = await generator.generate_notification_cards(
        _dog("n1", "N1", modules={MODULE_NOTIFICATIONS: True}),
        {"theme": "minimal"},
    )
    assert len(notification_cards) == 2

    assert await generator.generate_visitor_cards({}, {}) == []
    assert (
        await generator.generate_visitor_cards(
            _dog("v1", "V1", modules={MODULE_VISITOR: False}),
            {},
        )
        == []
    )
    generator._validate_entities_batch = AsyncMock(return_value=[])  # type: ignore[method-assign]
    visitor_cards = await generator.generate_visitor_cards(
        _dog("v1", "V1", modules={MODULE_VISITOR: True}),
        {},
    )
    assert len(visitor_cards) == 1

    generator._validate_entities_batch = AsyncMock(
        return_value=["switch.v1_visitor_mode"],
    )  # type: ignore[method-assign]
    visitor_cards_with_entities = await generator.generate_visitor_cards(
        _dog("v1", "V1", modules={MODULE_VISITOR: True}),
        {},
    )
    assert len(visitor_cards_with_entities) == 2

    assert await generator.generate_gps_cards({}, {}) == []
    generator._entity_exists_cached = AsyncMock(return_value=False)  # type: ignore[method-assign]
    assert (
        await generator.generate_gps_cards(
            _dog("g1", "G1", modules={MODULE_GPS: True}), {}
        )
        == []
    )

    generator._entity_exists_cached = AsyncMock(return_value=True)  # type: ignore[method-assign]
    templates.get_map_card_template = AsyncMock(side_effect=RuntimeError("map failed"))
    generator._validate_entities_batch = AsyncMock(
        side_effect=[
            ["device_tracker.g1_location", "sensor.g1_gps_accuracy"],
            ["binary_sensor.g1_at_home"],
        ],
    )  # type: ignore[method-assign]
    templates.get_history_graph_template = AsyncMock(
        return_value={
            "type": "history-graph",
            "entities": ["sensor.g1_distance_from_home"],
        },
    )
    gps_cards = await generator.generate_gps_cards(
        _dog("g1", "G1", modules={MODULE_GPS: True}),
        {"zoom": "7"},
    )
    assert gps_cards
    templates.get_history_graph_template = AsyncMock(
        side_effect=RuntimeError("history failed")
    )
    await generator.generate_gps_cards(
        _dog("g1", "G1", modules={MODULE_GPS: True}),
        {"zoom": "7"},
    )


@pytest.mark.asyncio
async def test_weather_generator_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover weather card generator helpers, success paths, and timeout handling."""
    state_entries = {
        "sensor.weatherdog_weather_recommendations": _state(
            "Hydrate;Shade",
            {"recommendations": ["Hydrate", "Hydrate", "Shade"]},
        ),
        "sensor.weatherdog_breed_weather_advice": _state("ok"),
    }
    generator = dc.WeatherCardGenerator(_hass(state_entries), _TemplatesStub())

    assert dc.WeatherCardGenerator._normalise_recommendations(None) == []
    assert dc.WeatherCardGenerator._normalise_recommendations("a; b\nc") == [
        "a",
        "b",
        "c",
    ]
    assert dc.WeatherCardGenerator._normalise_recommendations({
        "items": ["x", "y"]
    }) == ["x", "y"]
    assert dc.WeatherCardGenerator._normalise_recommendations(["x", {"text": "y"}]) == [
        "x",
        "y",
    ]
    assert dc.WeatherCardGenerator._normalise_recommendations(42) == ["42"]

    assert generator._collect_weather_recommendations("sensor.missing") == []
    collected = generator._collect_weather_recommendations(
        "sensor.weatherdog_weather_recommendations"
    )
    assert collected == ["Hydrate", "Shade"]

    assert await generator.generate_weather_overview_cards({}, {}) == []

    def _ensure_weather_config(dog_config: Any) -> dict[str, Any] | None:
        if not isinstance(dog_config, Mapping):
            return None
        dog_id = dog_config.get(DOG_ID_FIELD)
        dog_name = dog_config.get(DOG_NAME_FIELD)
        if not isinstance(dog_id, str) or not dog_id:
            return None
        if not isinstance(dog_name, str) or not dog_name:
            return None
        weather_enabled = dog_config.get("weather_enabled", True)
        payload: dict[str, Any] = {
            DOG_ID_FIELD: dog_id,
            DOG_NAME_FIELD: dog_name,
            DOG_MODULES_FIELD: {MODULE_WEATHER: bool(weather_enabled)},
        }
        breed_value = dog_config.get("breed")
        if isinstance(breed_value, str):
            payload["breed"] = breed_value
        return payload

    generator._ensure_dog_config = _ensure_weather_config  # type: ignore[method-assign]
    weather_off = _dog("off", "Off")
    weather_off["weather_enabled"] = False
    assert (
        await generator.generate_weather_overview_cards(
            weather_off,
            {},
        )
        == []
    )

    monkeypatch.setattr(
        dc,
        "coerce_dog_modules_config",
        lambda payload: {MODULE_WEATHER: True},
    )

    generator._generate_weather_health_score_card = AsyncMock(
        return_value={"type": "gauge"}
    )  # type: ignore[method-assign]
    generator._generate_active_weather_alerts_card = AsyncMock(
        side_effect=RuntimeError("alerts")
    )  # type: ignore[method-assign]
    generator._generate_weather_recommendations_card = AsyncMock(
        return_value={"type": "markdown"}
    )  # type: ignore[method-assign]
    generator._generate_current_weather_conditions_card = AsyncMock(
        return_value={"type": "entities"}
    )  # type: ignore[method-assign]
    generator._generate_breed_weather_advice_card = AsyncMock(
        return_value={"type": "markdown"}
    )  # type: ignore[method-assign]
    generator._generate_weather_forecast_card = AsyncMock(
        return_value={"type": "vertical-stack"}
    )  # type: ignore[method-assign]
    overview_cards = await generator.generate_weather_overview_cards(
        _dog("weatherdog", "Weather Dog", modules={MODULE_WEATHER: True}),
        {"show_breed_advice": True, "show_weather_forecast": True},
    )
    assert overview_cards
    assert generator.performance_stats["errors_handled"] >= 1

    async def _timeout_wait_for(awaitable: object, timeout: float) -> object:
        _ = timeout
        if hasattr(awaitable, "cancel"):
            awaitable.cancel()  # type: ignore[attr-defined]
        raise TimeoutError

    monkeypatch.setattr(dc.asyncio, "wait_for", _timeout_wait_for)
    timeout_cards = await generator.generate_weather_overview_cards(
        _dog("weatherdog", "Weather Dog"),
        {},
    )
    assert timeout_cards[0]["type"] == "markdown"

    generator = dc.WeatherCardGenerator(_hass(state_entries), _TemplatesStub())
    generator._ensure_dog_config = _ensure_weather_config  # type: ignore[method-assign]
    generator._entity_exists_cached = AsyncMock(return_value=False)  # type: ignore[method-assign]
    assert (
        await generator._generate_weather_health_score_card(
            "weatherdog", "Weather Dog", {}
        )
        is None
    )
    generator._entity_exists_cached = AsyncMock(return_value=True)  # type: ignore[method-assign]
    assert await generator._generate_weather_health_score_card(
        "weatherdog", "Weather Dog", {}
    )

    generator._validate_entities_batch = AsyncMock(return_value=[])  # type: ignore[method-assign]
    assert (
        await generator._generate_active_weather_alerts_card(
            "weatherdog", "Weather Dog", {}
        )
        is None
    )
    generator._validate_entities_batch = AsyncMock(
        return_value=[
            "binary_sensor.weatherdog_heat_stress_alert",
            "binary_sensor.weatherdog_uv_exposure_alert",
        ],
    )  # type: ignore[method-assign]
    assert await generator._generate_active_weather_alerts_card(
        "weatherdog", "Weather Dog", {}
    )

    generator._entity_exists_cached = AsyncMock(return_value=False)  # type: ignore[method-assign]
    assert (
        await generator._generate_weather_recommendations_card(
            "weatherdog", "Weather Dog", {}
        )
        is None
    )
    generator._entity_exists_cached = AsyncMock(return_value=True)  # type: ignore[method-assign]
    recommendation_card = await generator._generate_weather_recommendations_card(
        "weatherdog",
        "Weather Dog",
        {"theme": "modern"},
    )
    assert recommendation_card is not None

    generator._validate_entities_batch = AsyncMock(return_value=[])  # type: ignore[method-assign]
    assert (
        await generator._generate_current_weather_conditions_card(
            "weatherdog", "Weather Dog", {}
        )
        is None
    )
    generator._validate_entities_batch = AsyncMock(
        return_value=[
            "sensor.weatherdog_temperature_impact",
            "sensor.weatherdog_uv_exposure_level",
        ],
    )  # type: ignore[method-assign]
    assert await generator._generate_current_weather_conditions_card(
        "weatherdog", "Weather Dog", {}
    )

    assert await generator._generate_breed_weather_advice_card({}, {}) is None
    generator._entity_exists_cached = AsyncMock(return_value=False)  # type: ignore[method-assign]
    assert (
        await generator._generate_breed_weather_advice_card(
            _dog("weatherdog", "Weather Dog"),
            {},
        )
        is None
    )
    generator._entity_exists_cached = AsyncMock(return_value=True)  # type: ignore[method-assign]
    assert await generator._generate_breed_weather_advice_card(
        _dog(
            "weatherdog",
            "Weather Dog",
            breed="Husky",
            modules={MODULE_WEATHER: True},
        ),
        {},
    )

    generator._entity_exists_cached = AsyncMock(return_value=False)  # type: ignore[method-assign]
    assert (
        await generator._generate_weather_forecast_card("weatherdog", "Weather Dog", {})
        is None
    )
    generator._entity_exists_cached = AsyncMock(return_value=True)  # type: ignore[method-assign]
    assert await generator._generate_weather_forecast_card(
        "weatherdog", "Weather Dog", {}
    )

    assert await generator.generate_weather_controls_card({}, {}) is None
    generator._entity_exists_cached = AsyncMock(return_value=False)  # type: ignore[method-assign]
    assert (
        await generator.generate_weather_controls_card(
            _dog("weatherdog", "Weather Dog"),
            {},
        )
        is None
    )
    generator._entity_exists_cached = AsyncMock(return_value=True)  # type: ignore[method-assign]
    assert await generator.generate_weather_controls_card(
        _dog("weatherdog", "Weather Dog"),
        {},
    )

    assert await generator.generate_weather_history_card({}, {}) is None
    generator._validate_entities_batch = AsyncMock(return_value=[])  # type: ignore[method-assign]
    assert (
        await generator.generate_weather_history_card(
            _dog("weatherdog", "Weather Dog"),
            {},
        )
        is None
    )
    generator._validate_entities_batch = AsyncMock(
        return_value=["sensor.weatherdog_weather_health_score"],
    )  # type: ignore[method-assign]
    assert await generator.generate_weather_history_card(
        _dog("weatherdog", "Weather Dog"),
        {},
    )


@pytest.mark.asyncio
async def test_statistics_generator_and_global_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover statistics generator branches and module-level helper functions."""
    templates = _TemplatesStub()
    generator = dc.StatisticsCardGenerator(_hass(language="de"), templates)
    dogs = [
        _dog(
            "s1",
            "S1",
            modules={
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_HEALTH: True,
            },
        ),
    ]

    assert await generator.generate_statistics_cards([], {}) == []

    generator._generate_activity_statistics = AsyncMock(
        return_value={"type": "statistics-graph"}
    )  # type: ignore[method-assign]
    generator._generate_feeding_statistics = AsyncMock(
        side_effect=RuntimeError("feeding stats failed")
    )  # type: ignore[method-assign]
    generator._generate_walk_statistics = AsyncMock(
        return_value={"type": "statistics-graph"}
    )  # type: ignore[method-assign]
    generator._generate_health_statistics = AsyncMock(
        return_value={"type": "statistics-graph"}
    )  # type: ignore[method-assign]
    cards = await generator.generate_statistics_cards(
        dogs,
        {"theme": "modern"},
        coordinator_statistics={"rejection_metrics": {"rejected_call_count": 1}},
        service_execution_metrics={"rejected_call_count": 2},
        service_guard_metrics={
            "executed": 1,
            "skipped": 0,
            "reasons": {},
            "last_results": [],
        },
    )
    assert cards
    assert generator.performance_stats["errors_handled"] >= 1

    async def _timeout_wait_for(awaitable: object, timeout: float) -> object:
        _ = timeout
        if hasattr(awaitable, "cancel"):
            awaitable.cancel()  # type: ignore[attr-defined]
        raise TimeoutError

    monkeypatch.setattr(dc.asyncio, "wait_for", _timeout_wait_for)
    timeout_cards = await generator.generate_statistics_cards(dogs, {})
    assert timeout_cards

    generator = dc.StatisticsCardGenerator(_hass(), templates)
    generator._validate_entities_batch = AsyncMock(
        return_value=["sensor.s1_activity_level"]
    )  # type: ignore[method-assign]
    assert await generator._generate_activity_statistics([_dog("s1", "S1")], "modern")
    assert (
        await generator._generate_activity_statistics(
            [{DOG_ID_FIELD: "", DOG_NAME_FIELD: "NoId", DOG_MODULES_FIELD: {}}],
            "modern",
        )
        is None
    )

    generator._validate_entities_batch = AsyncMock(
        return_value=["sensor.s1_meals_today"]
    )  # type: ignore[method-assign]
    assert await generator._generate_feeding_statistics([_dog("s1", "S1")], "modern")
    assert (
        await generator._generate_feeding_statistics(
            [_dog("s2", "S2", modules={MODULE_FEEDING: False})],
            "modern",
        )
        is None
    )

    generator._validate_entities_batch = AsyncMock(
        return_value=["sensor.s1_walk_distance_today"]
    )  # type: ignore[method-assign]
    assert await generator._generate_walk_statistics([_dog("s1", "S1")], "modern")
    assert (
        await generator._generate_walk_statistics(
            [_dog("s2", "S2", modules={MODULE_WALK: False})],
            "modern",
        )
        is None
    )

    generator._validate_entities_batch = AsyncMock(return_value=["sensor.s1_weight"])  # type: ignore[method-assign]
    assert await generator._generate_health_statistics([_dog("s1", "S1")], "modern")
    assert (
        await generator._generate_health_statistics(
            [_dog("s2", "S2", modules={MODULE_HEALTH: False})],
            "modern",
        )
        is None
    )

    summary = generator._generate_summary_card([_dog("s1", "S1")], "modern")
    assert summary["type"] == "markdown"

    class _CleanupLoop:
        def time(self) -> float:
            return 500.0

    monkeypatch.setattr(dc.asyncio, "get_running_loop", lambda: _CleanupLoop())
    monkeypatch.setattr(
        dc,
        "_entity_validation_cache",
        {"sensor.old": (1.0, True), "sensor.new": (490.0, True)},
    )
    monkeypatch.setattr(dc, "_cache_cleanup_threshold", 100)
    await dc.cleanup_validation_cache()
    assert "sensor.old" not in dc._entity_validation_cache

    stats = dc.get_global_performance_stats()
    assert "validation_cache_size" in stats
    assert dc._unwrap_async_result("ok", context="value") == "ok"
    assert dc._unwrap_async_result(RuntimeError("boom"), context="error") is None


@pytest.mark.asyncio
async def test_dashboard_cards_branch_fillers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fill remaining rare branches in dashboard card generators."""
    templates = _TemplatesStub()

    # Cover nested map-option iterable handling and unsupported alias logging path.
    normalised_map = dc._coerce_map_options(
        {
            "map_options": [("zoom", "6"), ("hours_to_show", "4")],
            "map_card": object(),
        },
    )
    assert normalised_map["zoom"] == 6
    assert normalised_map["hours_to_show"] == 4

    # Cover cache cleanup branch that trims oldest entries after expiry pruning.
    base_generator = dc.BaseCardGenerator(_hass(), templates)
    monkeypatch.setattr(
        dc.asyncio, "get_running_loop", lambda: SimpleNamespace(time=lambda: 1000.0)
    )
    recent_overflow = {
        f"sensor.cache_{idx}": (999.0 + idx * 0.001, True)
        for idx in range(dc.VALIDATION_CACHE_SIZE + 5)
    }
    monkeypatch.setattr(dc, "_entity_validation_cache", recent_overflow)
    await base_generator._cleanup_validation_cache()
    assert len(dc._entity_validation_cache) == dc.VALIDATION_CACHE_SIZE

    # Overview branches with invalid pre-coerced payloads.
    overview_generator = dc.OverviewCardGenerator(_hass(), templates)
    overview_generator._ensure_dog_configs = lambda _: [  # type: ignore[method-assign]
        {
            DOG_ID_FIELD: "",
            DOG_NAME_FIELD: "",
            DOG_MODULES_FIELD: {},
        }
    ]
    assert (
        await overview_generator._count_active_dogs(
            overview_generator._ensure_dog_configs([])
        )
        == 0
    )
    assert (
        await overview_generator.generate_dogs_grid(
            [_dog("ignored", "Ignored")], "/paw"
        )
        is None
    )

    # Dog overview branches for skipped optional cards and per-task failures.
    dog_generator = dc.DogCardGenerator(_hass(), templates)
    assert await dog_generator._generate_dog_header_card({}, {}) is None
    templates.get_action_buttons_template = AsyncMock(
        return_value=[{"type": "conditional"}]
    )
    cards_without_optional = await dog_generator.generate_dog_overview_cards(
        _dog("minimal", "Minimal", modules={MODULE_GPS: False, MODULE_WALK: False}),
        {},
        {"show_activity_graph": False},
    )
    assert cards_without_optional
    assert dog_generator._build_action_button_cards([{"type": "conditional"}]) == [
        {"type": "conditional"},
    ]

    erroring_dog_generator = dc.DogCardGenerator(_hass(), templates)
    erroring_dog_generator._generate_dog_header_card = AsyncMock(
        side_effect=RuntimeError("header failed")
    )  # type: ignore[method-assign]
    erroring_dog_generator._generate_gps_map_card = AsyncMock(
        return_value={"type": "map"}
    )  # type: ignore[method-assign]
    erroring_dog_generator._generate_activity_graph_card = AsyncMock(
        return_value={"type": "history-graph"}
    )  # type: ignore[method-assign]
    templates.get_action_buttons_template = AsyncMock(return_value=[{"type": "button"}])
    errored_cards = await erroring_dog_generator.generate_dog_overview_cards(
        _dog("errdog", "Err Dog", modules={MODULE_GPS: True, MODULE_WALK: True}),
        {},
        {"show_activity_graph": True},
    )
    assert errored_cards

    activity_generator = dc.DogCardGenerator(_hass(), templates)
    activity_generator._validate_entities_batch = AsyncMock(
        return_value=["sensor.nowalk_activity_level"]
    )  # type: ignore[method-assign]
    activity_card = await activity_generator._generate_activity_graph_card(
        _dog("nowalk", "No Walk", modules={MODULE_WALK: False}),
        {"show_activity_graph": True},
    )
    assert activity_card is not None

    # Feeding branches for None overview, present controls, and standard fallback path.
    module_generator = dc.ModuleCardGenerator(_hass(), templates)

    async def _health_overview_none(
        _self: Any,
        _dog_config: Any,
        _options: Any,
    ) -> Any:
        return None

    async def _health_controls_list(
        _self: Any,
        _dog_config: Any,
        _options: Any,
    ) -> list[dict[str, Any]]:
        return [{"type": "button"}]

    monkeypatch.setattr(
        dc.HealthAwareFeedingCardGenerator,
        "generate_health_feeding_overview",
        _health_overview_none,
    )
    monkeypatch.setattr(
        dc.HealthAwareFeedingCardGenerator,
        "generate_health_feeding_controls",
        _health_controls_list,
    )
    module_generator._generate_feeding_history_card = AsyncMock(return_value=None)  # type: ignore[method-assign]
    health_path_cards = await module_generator.generate_feeding_cards(
        _dog(
            "modulehealth",
            "Module Health",
            modules={MODULE_FEEDING: True, MODULE_HEALTH: True},
        ),
        {},
    )
    assert health_path_cards

    module_generator._generate_standard_feeding_cards = AsyncMock(return_value=[])  # type: ignore[method-assign]
    module_generator._generate_feeding_history_card = AsyncMock(return_value=None)  # type: ignore[method-assign]
    standard_only_cards = await module_generator.generate_feeding_cards(
        _dog(
            "standard", "Standard", modules={MODULE_FEEDING: True, MODULE_HEALTH: False}
        ),
        {},
    )
    assert standard_only_cards == []

    module_generator._validate_entities_batch = AsyncMock(
        return_value=["binary_sensor.walkfill_is_walking"],
    )  # type: ignore[method-assign]
    module_generator._generate_walk_history_card = AsyncMock(return_value=None)  # type: ignore[method-assign]
    walk_cards = await module_generator.generate_walk_cards(
        _dog("walkfill", "Walk Fill", modules={MODULE_WALK: True}),
        {},
    )
    assert walk_cards

    module_generator._validate_entities_batch = AsyncMock(
        side_effect=[
            ["sensor.healthfill_health_status"],
            ["date.healthfill_next_vet_visit"],
        ],
    )  # type: ignore[method-assign]
    module_generator._entity_exists_cached = AsyncMock(return_value=False)  # type: ignore[method-assign]
    health_cards = await module_generator.generate_health_cards(
        _dog("healthfill", "Health Fill", modules={MODULE_HEALTH: True}),
        {},
    )
    assert health_cards

    # GPS map append path and history-card false branch.
    templates.get_map_card_template = AsyncMock(
        return_value={"type": "map", "entities": ["device_tracker.gpsfill_location"]},
    )
    templates.get_history_graph_template = AsyncMock(
        return_value={"type": "history-graph", "entities": []},
    )
    module_generator._entity_exists_cached = AsyncMock(return_value=True)  # type: ignore[method-assign]
    module_generator._validate_entities_batch = AsyncMock(side_effect=[[], []])  # type: ignore[method-assign]
    gps_cards = await module_generator.generate_gps_cards(
        _dog("gpsfill", "GPS Fill", modules={MODULE_GPS: True}),
        {"zoom": "8"},
    )
    assert gps_cards and gps_cards[0]["type"] == "map"

    # Weather helper edge branches and overview task-selection branches.
    weather_states = _hass(
        {
            "sensor.fill_weather_recommendations": SimpleNamespace(
                state="Hydrate;; ",
                attributes="not-a-mapping",
            ),
        },
    )
    weather_generator = dc.WeatherCardGenerator(weather_states, templates)
    assert dc.WeatherCardGenerator._normalise_recommendations("keep;; ;next") == [
        "keep",
        "next",
    ]
    collected_fill = weather_generator._collect_weather_recommendations(
        "sensor.fill_weather_recommendations",
    )
    assert collected_fill == ["Hydrate"]

    blank_weather_generator = dc.WeatherCardGenerator(
        _hass(
            {
                "sensor.blank_weather_recommendations": SimpleNamespace(
                    state="raw",
                    attributes={"recommendations": "raw"},
                ),
            },
        ),
        templates,
    )
    blank_weather_generator._normalise_recommendations = (  # type: ignore[method-assign]
        lambda source: ["", "Keep"]
    )
    assert blank_weather_generator._collect_weather_recommendations(
        "sensor.blank_weather_recommendations",
    ) == ["Keep"]

    weather_generator._ensure_dog_config = lambda dog: {  # type: ignore[method-assign]
        DOG_ID_FIELD: "branchdog",
        DOG_NAME_FIELD: "Branch Dog",
        DOG_MODULES_FIELD: {MODULE_WEATHER: True},
    }
    weather_generator._generate_weather_health_score_card = AsyncMock(
        return_value={"type": "gauge"}
    )  # type: ignore[method-assign]
    weather_generator._generate_active_weather_alerts_card = AsyncMock(
        return_value={"type": "entities"}
    )  # type: ignore[method-assign]
    weather_generator._generate_weather_recommendations_card = AsyncMock(
        return_value={"type": "markdown"}
    )  # type: ignore[method-assign]
    weather_generator._generate_current_weather_conditions_card = AsyncMock(
        return_value={"type": "entities"}
    )  # type: ignore[method-assign]
    weather_generator._generate_breed_weather_advice_card = AsyncMock(
        return_value={"type": "markdown"}
    )  # type: ignore[method-assign]
    weather_generator._generate_weather_forecast_card = AsyncMock(
        return_value={"type": "vertical-stack"}
    )  # type: ignore[method-assign]
    monkeypatch.setattr(
        dc,
        "coerce_dog_modules_config",
        lambda payload: {MODULE_WEATHER: True},
    )

    fast_loop = _MonotonicLoop([1.0, 1.2])
    monkeypatch.setattr(dc.asyncio, "get_running_loop", lambda: fast_loop)
    compact_weather_cards = await weather_generator.generate_weather_overview_cards(
        _dog("branchdog", "Branch Dog"),
        {"show_breed_advice": False, "show_weather_forecast": False},
    )
    assert compact_weather_cards

    slow_loop = _MonotonicLoop([1.0, 3.0])
    monkeypatch.setattr(dc.asyncio, "get_running_loop", lambda: slow_loop)
    full_weather_cards = await weather_generator.generate_weather_overview_cards(
        _dog("branchdog", "Branch Dog"),
        {"show_breed_advice": True, "show_weather_forecast": True},
    )
    assert full_weather_cards
