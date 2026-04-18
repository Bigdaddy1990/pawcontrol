"""Runtime coverage tests for person_entity_manager branches."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.const import STATE_HOME
from homeassistant.util import dt as dt_util
import pytest

from custom_components.pawcontrol import person_entity_manager as pem
from custom_components.pawcontrol.person_entity_manager import (
    PersonEntityInfo,
    PersonEntityManager,
)


def _state(
    *,
    state: str,
    friendly_name: str | None = None,
    source: object | None = None,
    user_id: str | None = None,
) -> SimpleNamespace:
    """Build a lightweight Home Assistant state double."""
    attrs: dict[str, object] = {}
    if friendly_name is not None:
        attrs["friendly_name"] = friendly_name
    if source is not None:
        attrs["source"] = source
    if user_id is not None:
        attrs["user_id"] = user_id
    return SimpleNamespace(
        state=state,
        attributes=attrs,
        last_updated=dt_util.utcnow(),
    )


def _person(
    entity_id: str,
    *,
    state: str = STATE_HOME,
    name: str = "person",
    friendly_name: str = "Person",
    notification_service: str | None = None,
    mobile_device_id: str | None = None,
) -> PersonEntityInfo:
    """Build a person info record for manager tests."""
    return PersonEntityInfo(
        entity_id=entity_id,
        name=name,
        friendly_name=friendly_name,
        state=state,
        is_home=(state == STATE_HOME),
        last_updated=dt_util.utcnow(),
        notification_service=notification_service,
        mobile_device_id=mobile_device_id,
    )


def _registry_entry(
    entity_id: str,
    *,
    domain: str = "person",
    disabled_by: str | None = None,
    name: str | None = None,
) -> SimpleNamespace:
    """Build a lightweight entity registry entry."""
    return SimpleNamespace(
        entity_id=entity_id,
        domain=domain,
        disabled_by=disabled_by,
        name=name,
    )


@pytest.mark.unit
def test_coerce_helpers_cover_default_and_clamped_paths() -> None:
    """Static coercion helpers should cover invalid, empty, and valid inputs."""
    assert PersonEntityManager._coerce_discovery_interval("bad") == (
        pem.DEFAULT_DISCOVERY_INTERVAL
    )
    assert PersonEntityManager._coerce_discovery_interval(10) == pem.MIN_DISCOVERY_INTERVAL
    assert PersonEntityManager._coerce_discovery_interval(9999) == pem.MAX_DISCOVERY_INTERVAL

    assert PersonEntityManager._coerce_positive_int(None, default=7) == 7
    assert PersonEntityManager._coerce_positive_int(0, default=7) == 7
    assert PersonEntityManager._coerce_positive_int(3, default=7) == 3

    assert PersonEntityManager._coerce_string_list(None) == []
    assert PersonEntityManager._coerce_string_list(["a", 1, "b"]) == ["a", "b"]

    assert PersonEntityManager._coerce_string_mapping(None) == {}
    assert PersonEntityManager._coerce_string_mapping({"a": "x", 1: "y", "b": 2}) == {
        "a": "x"
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_initialize_registers_cache_monitors_when_registrar_present(
    mock_hass,
) -> None:
    """Initialize should register cache monitors after locked setup."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    registrar = Mock()
    manager._cache_registrar = registrar
    manager._async_initialize_locked = AsyncMock()  # type: ignore[method-assign]
    manager.register_cache_monitors = Mock()  # type: ignore[method-assign]

    await manager.async_initialize({"enabled": True})

    manager._async_initialize_locked.assert_awaited_once()
    manager.register_cache_monitors.assert_called_once_with(registrar)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_initialize_without_registrar_skips_monitor_registration(
    mock_hass,
) -> None:
    """Initialize should skip registration when no cache registrar is configured."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._cache_registrar = None
    manager._async_initialize_locked = AsyncMock()  # type: ignore[method-assign]
    manager.register_cache_monitors = Mock()  # type: ignore[method-assign]

    await manager.async_initialize({"enabled": True})

    manager.register_cache_monitors.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_initialize_locked_disables_and_clears_state(mock_hass) -> None:
    """Disabled config should stop discovery setup and clear discovered persons."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._persons["person.old"] = _person("person.old")
    manager._cancel_discovery_task_locked = AsyncMock()  # type: ignore[method-assign]
    manager._clear_state_listeners_locked = Mock()  # type: ignore[method-assign]
    manager._discover_person_entities = AsyncMock()  # type: ignore[method-assign]
    manager._setup_state_tracking = AsyncMock()  # type: ignore[method-assign]
    manager._start_discovery_task = AsyncMock()  # type: ignore[method-assign]

    await manager._async_initialize_locked({"enabled": False})

    assert manager._persons == {}
    manager._discover_person_entities.assert_not_awaited()
    manager._setup_state_tracking.assert_not_awaited()
    manager._start_discovery_task.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_initialize_locked_uses_existing_config_when_none_passed(
    mock_hass,
) -> None:
    """Locked initializer should support ``config=None`` and respect auto-discovery off."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._config.auto_discovery = False
    manager._cancel_discovery_task_locked = AsyncMock()  # type: ignore[method-assign]
    manager._clear_state_listeners_locked = Mock()  # type: ignore[method-assign]
    manager._discover_person_entities = AsyncMock()  # type: ignore[method-assign]
    manager._setup_state_tracking = AsyncMock()  # type: ignore[method-assign]
    manager._start_discovery_task = AsyncMock()  # type: ignore[method-assign]

    await manager._async_initialize_locked(None)

    manager._discover_person_entities.assert_awaited_once()
    manager._setup_state_tracking.assert_awaited_once()
    manager._start_discovery_task.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_initialize_locked_runs_discovery_tracking_and_task(mock_hass) -> None:
    """Enabled config with auto discovery should execute all startup steps."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._cancel_discovery_task_locked = AsyncMock()  # type: ignore[method-assign]
    manager._clear_state_listeners_locked = Mock()  # type: ignore[method-assign]
    manager._discover_person_entities = AsyncMock()  # type: ignore[method-assign]
    manager._setup_state_tracking = AsyncMock()  # type: ignore[method-assign]
    manager._start_discovery_task = AsyncMock()  # type: ignore[method-assign]

    await manager._async_initialize_locked(
        {
            "enabled": True,
            "auto_discovery": True,
            "discovery_interval": 120,
            "cache_ttl": 60,
        }
    )

    manager._discover_person_entities.assert_awaited_once()
    manager._setup_state_tracking.assert_awaited_once()
    manager._start_discovery_task.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discover_person_entities_populates_persons_and_stats(mock_hass) -> None:
    """Discovery should process valid person entities and refresh state/cache stats."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._config.excluded_entities = ["person.excluded"]
    manager._config.notification_mapping = {"person.mapped": "notify.mapped"}
    manager._targets_cache.store("old", ["notify.old"], dt_util.now())

    registry = SimpleNamespace(
        entities={
            "person.mapped": _registry_entry("person.mapped", name="Mapped"),
            "person.generated": _registry_entry("person.generated", name=None),
            "person.excluded": _registry_entry("person.excluded", name="Excluded"),
            "person.disabled": _registry_entry(
                "person.disabled",
                name="Disabled",
                disabled_by="user",
            ),
            "sensor.ignore": _registry_entry("sensor.ignore", domain="sensor"),
        }
    )
    states = {
        "person.mapped": _state(state=STATE_HOME, friendly_name="Mapped Name"),
        "person.generated": _state(state="not_home", friendly_name="Generated Person"),
        "person.excluded": _state(state=STATE_HOME, friendly_name="Excluded"),
        "person.disabled": _state(state=STATE_HOME, friendly_name="Disabled"),
    }
    mock_hass.states.get = lambda entity_id: states.get(entity_id)
    manager._find_mobile_device_for_person = AsyncMock(  # type: ignore[method-assign]
        side_effect=["mobile_app_tracker", None]
    )

    with patch.object(pem.er, "async_get", return_value=registry):
        await manager._discover_person_entities()

    assert set(manager._persons) == {"person.mapped", "person.generated"}
    assert manager._persons["person.mapped"].notification_service == "notify.mapped"
    assert manager._persons["person.mapped"].mobile_device_id == "mobile_app_tracker"
    assert manager._persons["person.generated"].name == "generated_person"
    assert len(manager._targets_cache) == 0
    assert manager._stats["persons_discovered"] == 2
    assert manager._stats["discovery_runs"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discover_person_entities_skips_registry_entries_without_state(mock_hass) -> None:
    """Discovery should ignore person entries when no current state exists."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    registry = SimpleNamespace(
        entities={"person.ghost": _registry_entry("person.ghost", name="Ghost")}
    )
    mock_hass.states.get = lambda _entity_id: None
    manager._find_mobile_device_for_person = AsyncMock(return_value=None)  # type: ignore[method-assign]

    with patch.object(pem.er, "async_get", return_value=registry):
        await manager._discover_person_entities()

    assert manager._persons == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discover_person_entities_swallows_registry_errors(mock_hass) -> None:
    """Unexpected discovery failures should be logged without bubbling up."""
    manager = PersonEntityManager(mock_hass, "entry-id")

    with patch.object(pem.er, "async_get", side_effect=RuntimeError("registry-fail")):
        await manager._discover_person_entities()

    assert manager._persons == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_mobile_device_for_person_source_patterns_and_user_id(mock_hass) -> None:
    """Source mapping and user-id fallback branch should both be exercised."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    mock_hass.services.has_service = (
        lambda domain, service: domain == "notify" and service == "mobile_app_device_one"
    )

    state_with_source = _state(
        state=STATE_HOME,
        friendly_name="Device One",
        source="device_tracker.device_one",
    )
    resolved = await manager._find_mobile_device_for_person("person.one", state_with_source)
    assert resolved == "mobile_app_device_one"

    mock_hass.services.has_service = lambda *_: False
    user_id_only = _state(state="not_home", source="device_tracker.ghost", user_id="user-1")
    unresolved = await manager._find_mobile_device_for_person("person.two", user_id_only)
    assert unresolved is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_mobile_device_for_person_handles_non_tracker_source_without_user(
    mock_hass,
) -> None:
    """Non tracker sources and missing user ids should return no mapping."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    mock_hass.services.has_service = lambda *_: False
    state = _state(state="not_home", source="sensor.motion")

    assert await manager._find_mobile_device_for_person("person.id", state) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_mobile_device_for_person_handles_attribute_errors(mock_hass) -> None:
    """Source values without startswith should hit the error-handling branch."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    bad_state = _state(state="not_home", source=object())

    resolved = await manager._find_mobile_device_for_person("person.bad", bad_state)

    assert resolved is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setup_state_tracking_skips_empty_person_registry(mock_hass) -> None:
    """Tracking setup should no-op when no persons are discovered."""
    manager = PersonEntityManager(mock_hass, "entry-id")

    with patch.object(pem, "async_track_state_change_event") as tracker:
        await manager._setup_state_tracking()

    tracker.assert_not_called()
    assert manager._state_listeners == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setup_state_tracking_registers_listener_and_callback(mock_hass) -> None:
    """Tracking setup should register a listener and forward events to handler."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._persons["person.alice"] = _person("person.alice")
    manager._handle_person_state_change = AsyncMock()  # type: ignore[method-assign]
    captured: dict[str, object] = {}

    def _register(_hass, entity_ids, callback):  # type: ignore[no-untyped-def]
        captured["entity_ids"] = list(entity_ids)
        captured["callback"] = callback
        return lambda: None

    with patch.object(pem, "async_track_state_change_event", side_effect=_register):
        await manager._setup_state_tracking()

    assert captured["entity_ids"] == ["person.alice"]
    callback = captured["callback"]
    await callback(SimpleNamespace(data={"entity_id": "person.alice", "new_state": _state(state=STATE_HOME)}))
    manager._handle_person_state_change.assert_awaited_once()
    assert len(manager._state_listeners) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_person_state_change_updates_entity_and_cache_on_transition(
    mock_hass,
) -> None:
    """State transitions should refresh person data and invalidate cache."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._persons["person.alice"] = _person(
        "person.alice",
        state=STATE_HOME,
        name="alice",
        friendly_name="Alice",
    )
    manager._targets_cache.store("targets", ["notify.a"], dt_util.now())

    await manager._handle_person_state_change(
        SimpleNamespace(
            data={
                "entity_id": "person.alice",
                "new_state": _state(state="not_home", friendly_name="Alice Updated"),
            }
        )
    )

    assert manager._persons["person.alice"].state == "not_home"
    assert manager._persons["person.alice"].is_home is False
    assert len(manager._targets_cache) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_person_state_change_without_status_transition_keeps_cache(
    mock_hass,
) -> None:
    """Cache should stay intact when home/away status does not change."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._persons["person.alice"] = _person(
        "person.alice",
        state="not_home",
        name="alice",
        friendly_name="Alice",
    )
    manager._targets_cache.store("targets", ["notify.a"], dt_util.now())

    await manager._handle_person_state_change(
        SimpleNamespace(
            data={
                "entity_id": "person.alice",
                "new_state": _state(state="not_home", friendly_name="Alice Updated"),
            }
        )
    )

    assert manager._persons["person.alice"].state == "not_home"
    assert len(manager._targets_cache) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_person_state_change_ignores_missing_or_unknown_entities(mock_hass) -> None:
    """No-op branches should handle unknown entities and missing new_state."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._persons["person.alice"] = _person("person.alice", state="not_home")

    await manager._handle_person_state_change(
        SimpleNamespace(data={"entity_id": "person.ghost", "new_state": _state(state=STATE_HOME)})
    )
    await manager._handle_person_state_change(
        SimpleNamespace(data={"entity_id": "person.alice", "new_state": None})
    )

    assert manager._persons["person.alice"].state == "not_home"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_discovery_task_returns_when_task_already_exists(mock_hass) -> None:
    """Starting discovery should no-op if an existing task handle is present."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    existing_task = asyncio.create_task(asyncio.sleep(0))
    await existing_task
    manager._discovery_task = existing_task

    await manager._start_discovery_task()

    assert manager._discovery_task is existing_task


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_discovery_task_loop_handles_error_and_cancel(mock_hass) -> None:
    """Discovery loop should log errors and stop cleanly on cancellation."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._config.discovery_interval = 0
    manager._discover_person_entities = AsyncMock(  # type: ignore[method-assign]
        side_effect=[RuntimeError("boom"), asyncio.CancelledError()]
    )

    with patch.object(pem.asyncio, "sleep", AsyncMock(return_value=None)):
        await manager._start_discovery_task()
        assert manager._discovery_task is not None
        await asyncio.wait_for(manager._discovery_task, timeout=1)

    assert manager._discovery_task.done() is True


@pytest.mark.unit
def test_get_person_accessors_cover_all_paths(mock_hass) -> None:
    """Person accessor helpers should expose all/home/away and direct lookup."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._persons["person.home"] = _person("person.home", state=STATE_HOME)
    manager._persons["person.away"] = _person("person.away", state="not_home")

    all_persons = manager.get_all_persons()
    assert len(all_persons) == 2
    assert [person.entity_id for person in manager.get_home_persons()] == ["person.home"]
    assert [person.entity_id for person in manager.get_away_persons()] == ["person.away"]
    assert manager.get_person_by_entity_id("person.home") is manager._persons["person.home"]
    assert manager.get_person_by_entity_id("person.missing") is None


@pytest.mark.unit
def test_get_notification_targets_handles_cache_hits_priority_and_fallback(mock_hass) -> None:
    """Notification target selection should cover cache, filters, and fallbacks."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._config.include_away_persons = False
    manager._config.fallback_to_static = True
    manager._config.static_notification_targets = ["notify.static"]
    manager._config.priority_persons = ["person.mobile"]
    manager._config.cache_ttl = 300

    manager._persons["person.service"] = _person(
        "person.service",
        state=STATE_HOME,
        name="service",
        notification_service="notify.service",
    )
    manager._persons["person.mobile"] = _person(
        "person.mobile",
        state=STATE_HOME,
        name="mobile",
        mobile_device_id="mobile_app_mobile",
    )
    manager._persons["person.auto"] = _person(
        "person.auto",
        state="not_home",
        name="auto_user",
    )

    mock_hass.services.has_service = (
        lambda domain, service: domain == "notify" and service == "mobile_app_auto_user"
    )

    first = manager.get_notification_targets()
    assert first == ["notify.service", "mobile_app_mobile"]
    assert manager._stats["cache_misses"] == 1
    assert manager._stats["notifications_targeted"] == 1

    second = manager.get_notification_targets()
    assert second == first
    assert manager._stats["cache_hits"] == 1

    priority_targets = manager.get_notification_targets(
        include_away=True,
        priority_only=True,
        cache_key="priority",
    )
    assert priority_targets == ["mobile_app_mobile"]

    auto_targets = manager.get_notification_targets(
        include_away=True,
        priority_only=False,
        cache_key="include_away",
    )
    assert "mobile_app_auto_user" in auto_targets

    manager._persons.clear()
    fallback_targets = manager.get_notification_targets(cache_key="fallback")
    assert fallback_targets == ["notify.static"]


@pytest.mark.unit
def test_get_notification_targets_skips_auto_mobile_when_service_missing(mock_hass) -> None:
    """Auto mobile-app fallback should skip persons without matching notify service."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._config.include_away_persons = True
    manager._config.fallback_to_static = False
    manager._persons["person.auto"] = _person(
        "person.auto",
        state=STATE_HOME,
        name="auto_user",
        notification_service=None,
        mobile_device_id=None,
    )
    mock_hass.services.has_service = lambda *_: False

    assert manager.get_notification_targets(cache_key="missing_service") == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_config_handles_success_toggle_and_failures(mock_hass) -> None:
    """Config updates should report success, toggles, and failure paths."""
    manager = PersonEntityManager(mock_hass, "entry-id")

    manager._config.enabled = True

    async def _disable(_new_config):  # type: ignore[no-untyped-def]
        manager._config.enabled = False

    manager.async_initialize = AsyncMock(side_effect=_disable)  # type: ignore[method-assign]
    assert await manager.async_update_config({"enabled": False}) is True

    manager._config.enabled = False

    async def _enable(_new_config):  # type: ignore[no-untyped-def]
        manager._config.enabled = True

    manager.async_initialize = AsyncMock(side_effect=_enable)  # type: ignore[method-assign]
    assert await manager.async_update_config({"enabled": True}) is True

    manager.async_initialize = AsyncMock(side_effect=RuntimeError("bad-config"))  # type: ignore[method-assign]
    assert await manager.async_update_config({"enabled": True}) is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_config_returns_true_when_enabled_state_unchanged(
    mock_hass,
) -> None:
    """When enabled state is unchanged, update should still succeed."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._config.enabled = True

    async def _noop(_new_config):  # type: ignore[no-untyped-def]
        manager._config.enabled = True

    manager.async_initialize = AsyncMock(side_effect=_noop)  # type: ignore[method-assign]

    assert await manager.async_update_config({"enabled": True}) is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_validate_configuration_covers_issue_branches(mock_hass) -> None:
    """Validation should report fallback, mapping, and excluded-entity issues."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._config.fallback_to_static = True
    manager._config.static_notification_targets = []
    manager._config.excluded_entities = ["person.missing"]
    manager._persons["person.alice"] = _person(
        "person.alice",
        state=STATE_HOME,
        friendly_name="Alice",
        notification_service=None,
        mobile_device_id=None,
    )

    result = await manager.async_validate_configuration()

    assert result["valid"] is False
    assert any("Fallback to static enabled" in issue for issue in result["issues"])
    assert any("Persons without notification mapping" in issue for issue in result["issues"])
    assert any("Excluded entity person.missing not found" in issue for issue in result["issues"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_validate_configuration_valid_path(mock_hass) -> None:
    """Validation should pass cleanly when configuration and mappings are complete."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    manager._config.fallback_to_static = False
    manager._config.excluded_entities = ["person.alice"]
    manager._persons["person.alice"] = _person(
        "person.alice",
        state=STATE_HOME,
        friendly_name="Alice",
        notification_service="notify.alice",
    )

    result = await manager.async_validate_configuration()

    assert result["valid"] is True
    assert result["issues"] == []
    assert result["notification_targets_available"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_shutdown_and_locked_helpers_cover_task_and_listener_cleanup(mock_hass) -> None:
    """Shutdown should cancel running tasks, invoke listeners, and clear caches."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    listener_called = False

    def _listener() -> None:
        nonlocal listener_called
        listener_called = True

    manager._persons["person.alice"] = _person("person.alice")
    manager._targets_cache.store("cache", ["notify.alice"], dt_util.now())
    manager._state_listeners = [_listener, "not-callable"]  # type: ignore[list-item]
    manager._discovery_task = asyncio.create_task(asyncio.sleep(60))

    await manager.async_shutdown()

    assert listener_called is True
    assert manager._persons == {}
    assert len(manager._targets_cache) == 0
    assert manager._discovery_task is None
    assert manager._state_listeners == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_discovery_task_locked_handles_none_and_completed_task(mock_hass) -> None:
    """Cancellation helper should no-op for None and clear completed tasks."""
    manager = PersonEntityManager(mock_hass, "entry-id")

    await manager._cancel_discovery_task_locked()
    assert manager._discovery_task is None

    completed = asyncio.create_task(asyncio.sleep(0))
    await completed
    manager._discovery_task = completed

    await manager._cancel_discovery_task_locked()
    assert manager._discovery_task is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_diagnostics_covers_not_started_cancelled_and_completed_states(
    mock_hass,
) -> None:
    """Diagnostics should classify discovery task lifecycle states correctly."""
    manager = PersonEntityManager(mock_hass, "entry-id")

    diagnostics = manager.get_diagnostics()
    assert diagnostics["discovery_task_state"] == "not_started"

    cancelled_task = asyncio.create_task(asyncio.sleep(60))
    cancelled_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_task
    manager._discovery_task = cancelled_task
    diagnostics = manager.get_diagnostics()
    assert diagnostics["discovery_task_state"] == "cancelled"

    completed_task = asyncio.create_task(asyncio.sleep(0))
    await completed_task
    manager._discovery_task = completed_task
    diagnostics = manager.get_diagnostics()
    assert diagnostics["discovery_task_state"] == "completed"


@pytest.mark.unit
def test_register_cache_monitors_and_clear_listeners_helpers(mock_hass) -> None:
    """Registrar integration and listener clear helper should handle both branches."""
    manager = PersonEntityManager(mock_hass, "entry-id")
    registrar = Mock()

    manager.register_cache_monitors(registrar, prefix="custom_person")

    assert manager._cache_registrar is registrar
    registrar.register_cache_monitor.assert_called_once_with("custom_person_targets", manager)

    manager._state_listeners = []
    manager._clear_state_listeners_locked()
    assert manager._state_listeners == []
