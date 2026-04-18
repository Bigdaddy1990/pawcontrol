"""High-coverage tests for helper_manager."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import time
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.const import (
    CONF_DOGS,
    CONF_MODULES,
    DEFAULT_RESET_TIME,
    MODULE_FEEDING,
    MODULE_HEALTH,
    MODULE_MEDICATION,
)
import custom_components.pawcontrol.helper_manager as helper_manager
from custom_components.pawcontrol.helper_manager import PawControlHelperManager
from custom_components.pawcontrol.service_guard import ServiceGuardResult


class _DummyEntityRegistry:
    """Simple entity registry stub."""

    def __init__(self, existing: set[str] | None = None) -> None:
        self._existing = existing or set()

    def async_get(self, entity_id: str) -> object | None:
        if entity_id in self._existing:
            return object()
        return None


def _make_manager(
    *,
    dogs: object | None = None,
    options: Mapping[str, object] | None = None,
    language: str = "en",
) -> tuple[PawControlHelperManager, SimpleNamespace, SimpleNamespace]:
    """Create a helper manager with lightweight Home Assistant/config entry stubs."""

    def _close_coroutine(coro: Any) -> None:
        coro.close()

    hass = SimpleNamespace(
        config=SimpleNamespace(language=language),
        async_create_task=_close_coroutine,
    )
    entry = SimpleNamespace(
        entry_id="entry-id",
        data={CONF_DOGS: [] if dogs is None else dogs},
        options=dict(options or {}),
    )
    return PawControlHelperManager(hass, entry), hass, entry


def _service_result(
    *,
    domain: str,
    service: str,
    executed: bool,
    reason: str | None = None,
    description: str | None = None,
) -> ServiceGuardResult:
    return ServiceGuardResult(
        domain=domain,
        service=service,
        executed=executed,
        reason=reason,
        description=description,
    )


@pytest.mark.unit
def test_guard_metrics_state_record_and_reset() -> None:
    """Guard metrics aggregate executed/skipped calls and can be reset."""
    state = helper_manager._HelperGuardMetricsState()

    state.record(
        _service_result(domain="input_boolean", service="create", executed=True)
    )
    state.record(
        _service_result(domain="input_boolean", service="create", executed=False)
    )

    snapshot_before = state.snapshot()
    assert snapshot_before["executed"] == 1
    assert snapshot_before["skipped"] == 1
    assert snapshot_before["reasons"] == {"unknown": 1}
    assert len(snapshot_before["last_results"]) == 2

    state.reset()
    snapshot_after = state.snapshot()
    assert snapshot_after == {
        "executed": 0,
        "skipped": 0,
        "reasons": {},
        "last_results": [],
    }


@pytest.mark.unit
def test_collate_entity_domains_tracks_unknown_ids() -> None:
    """Entity domain collation should classify malformed ids as unknown."""
    entities = cast(
        Mapping[str, helper_manager.HelperEntityMetadata],
        {
            "input_boolean.pawcontrol_a": {"domain": "input_boolean", "name": "A"},
            "invalid_entity_id": {"domain": "input_select", "name": "B"},
            42: {"domain": "input_number", "name": "C"},  # type: ignore[dict-item]
        },
    )
    domains = helper_manager._collate_entity_domains(entities)
    assert domains["input_boolean"] == 1
    assert domains["unknown"] == 2


@pytest.mark.unit
def test_cache_monitor_exports_payloads() -> None:
    """Cache monitor should expose stats, snapshot, and diagnostics payloads."""
    manager, _hass, _entry = _make_manager()
    manager._created_helpers.update(
        {
            "input_boolean.pawcontrol_rex_breakfast_fed",
            "input_datetime.pawcontrol_rex_breakfast_time",
        },
    )
    manager._managed_entities = cast(
        helper_manager.HelperEntityMetadataMapping,
        {
            "input_boolean.pawcontrol_rex_breakfast_fed": {
                "domain": "input_boolean",
                "name": "Rex Breakfast Fed",
            },
            "invalid_id": {
                "domain": "input_datetime",
                "name": "Invalid",
            },
        },
    )
    manager._dog_helpers = cast(
        helper_manager.DogHelperAssignments,
        {
            "rex": ["input_boolean.pawcontrol_rex_breakfast_fed"],
            "skip": 123,  # type: ignore[dict-item]
        },
    )
    manager._cleanup_listeners.append(lambda: None)
    manager._daily_reset_configured = True
    manager._record_guard_result(
        _service_result(
            domain="input_boolean",
            service="create",
            executed=False,
            reason="missing_service",
        ),
    )

    monitor = helper_manager._HelperManagerCacheMonitor(manager)
    snapshot = monitor.coordinator_snapshot()
    stats = monitor.get_stats()
    diagnostics = monitor.get_diagnostics()

    assert stats == {"helpers": 2, "dogs": 1, "managed_entities": 2}
    assert snapshot.stats is not None
    assert snapshot.snapshot is not None
    assert snapshot.stats["helpers"] == 2
    assert snapshot.snapshot["per_dog"] == {"rex": 1}
    assert snapshot.snapshot["entity_domains"] == {
        "input_boolean": 1,
        "unknown": 1,
    }
    assert diagnostics["cleanup_listeners"] == 1
    assert diagnostics["daily_reset_configured"] is True
    assert diagnostics["service_guard_metrics"]["reasons"] == {"missing_service": 1}


@pytest.mark.unit
def test_register_cache_monitors_validates_registrar() -> None:
    """Registering cache monitors should fail for missing registrar."""
    manager, _hass, _entry = _make_manager()

    with pytest.raises(ValueError, match="registrar is required"):
        manager.register_cache_monitors(None)  # type: ignore[arg-type]

    class _Registrar:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def register_cache_monitor(self, key: str, monitor: object) -> None:
            self.calls.append((key, monitor))

    registrar = _Registrar()
    manager.register_cache_monitors(registrar, prefix="helpers_x")
    assert len(registrar.calls) == 1
    key, monitor = registrar.calls[0]
    assert key == "helpers_x_cache"
    assert isinstance(monitor, helper_manager._HelperManagerCacheMonitor)


@pytest.mark.unit
def test_normalize_dogs_config_variants() -> None:
    """Dog normalization handles mapping, sequence, and invalid payloads."""
    mapping_result = PawControlHelperManager._normalize_dogs_config(
        {
            "rex": {"dog_name": "Rex"},
            "otto": {"dog_id": "otto", "dog_name": 9},
            "": {"dog_name": ""},
            "skip": "invalid",
        },
    )
    assert {dog["dog_id"] for dog in mapping_result} == {"rex", "otto"}
    assert any(
        dog["dog_id"] == "otto" and dog["dog_name"] == "otto" for dog in mapping_result
    )

    sequence_result = PawControlHelperManager._normalize_dogs_config(
        [
            {"dog_id": "luna", "dog_name": "Luna"},
            {"dog_id": "milo"},
            {"dog_id": ""},
            {"dog_id": 3},
            "invalid",
        ],
    )
    assert {dog["dog_id"] for dog in sequence_result} == {"luna", "milo"}
    assert any(
        dog["dog_id"] == "milo" and dog["dog_name"] == "milo" for dog in sequence_result
    )

    assert PawControlHelperManager._normalize_dogs_config("nope") == []
    assert PawControlHelperManager._normalize_dogs_config(b"nope") == []


@pytest.mark.unit
def test_normalize_enabled_modules_variants() -> None:
    """Module normalization supports mappings, sequences, strings, and invalid payloads."""
    mapped = PawControlHelperManager._normalize_enabled_modules(
        {
            MODULE_FEEDING: 1,
            MODULE_HEALTH: False,
            "invalid": True,
        },
    )
    assert mapped == frozenset({MODULE_FEEDING})

    sequenced = PawControlHelperManager._normalize_enabled_modules(
        [MODULE_FEEDING, "invalid", MODULE_MEDICATION],
    )
    assert sequenced == frozenset({MODULE_FEEDING, MODULE_MEDICATION})

    assert PawControlHelperManager._normalize_enabled_modules(
        MODULE_HEALTH
    ) == frozenset(
        {MODULE_HEALTH},
    )
    assert PawControlHelperManager._normalize_enabled_modules(7) == frozenset()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_initialize_resets_internal_state() -> None:
    """Initialization should clear runtime state and guard metrics."""
    manager, _hass, _entry = _make_manager()

    calls: list[str] = []

    def _ok_unsub() -> None:
        calls.append("ok")

    def _failing_unsub() -> None:
        raise RuntimeError("listener failed")

    manager._cleanup_listeners = [_ok_unsub, _failing_unsub]
    manager._created_helpers.add("input_boolean.a")
    manager._managed_entities["input_boolean.a"] = {
        "domain": "input_boolean",
        "name": "A",
    }
    manager._dog_helpers["dog-1"] = ["input_boolean.a"]
    manager._daily_reset_configured = True
    manager._record_guard_result(
        _service_result(
            domain="input_boolean",
            service="create",
            executed=False,
            reason="missing",
        ),
    )

    await manager.async_initialize()

    assert calls == ["ok"]
    assert manager._cleanup_listeners == []
    assert manager._created_helpers == set()
    assert manager._managed_entities == {}
    assert manager._dog_helpers == {}
    assert manager._daily_reset_configured is False
    assert manager.guard_metrics == {
        "executed": 0,
        "skipped": 0,
        "reasons": {},
        "last_results": [],
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_setup_creates_helpers_and_schedules_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup creates helper entities and schedules a daily reset callback."""
    manager, hass, _entry = _make_manager(
        dogs={"dog-1": {"dog_name": "Buddy"}},
        options={
            CONF_MODULES: {
                MODULE_FEEDING: True,
                MODULE_HEALTH: True,
                MODULE_MEDICATION: True,
            },
            "reset_time": "06:45:30",
        },
        language="de",
    )
    monkeypatch.setattr(
        helper_manager.er, "async_get", lambda _hass: _DummyEntityRegistry()
    )

    captured_calls: list[dict[str, object]] = []

    async def _capture_service_call(
        _hass: Any,
        domain: str,
        service: str,
        service_data: Mapping[str, object] | None = None,
        *,
        target: Mapping[str, object] | None = None,
        blocking: bool,
        description: str | None,
        logger: Any,
    ) -> ServiceGuardResult:
        del logger
        captured_calls.append(
            {
                "domain": domain,
                "service": service,
                "service_data": dict(service_data or {}),
                "target": dict(target or {}),
                "blocking": blocking,
                "description": description,
            },
        )
        return _service_result(
            domain=domain,
            service=service,
            executed=True,
            description=description,
        )

    monkeypatch.setattr(
        helper_manager,
        "async_call_hass_service_if_available",
        _capture_service_call,
    )

    scheduled: dict[str, object] = {}

    def _fake_track_time_change(
        _hass: Any,
        action: Callable[..., None],
        *,
        hour: int,
        minute: int,
        second: int,
    ) -> Callable[[], None]:
        scheduled["hms"] = (hour, minute, second)
        scheduled["callback"] = action

        def _unsub() -> None:
            scheduled["unsub_called"] = True

        return _unsub

    monkeypatch.setattr(
        helper_manager, "async_track_time_change", _fake_track_time_change
    )
    monkeypatch.setattr(
        helper_manager,
        "dt_util",
        SimpleNamespace(parse_time=lambda _value: time(6, 45, 30)),
    )
    monkeypatch.setattr(
        helper_manager,
        "translated_grooming_template",
        lambda _hass, _lang, _key, *, dog_name: f"{dog_name} Grooming Due",
    )

    scheduled_tasks: list[Any] = []

    def _create_task(coro: Any) -> None:
        scheduled_tasks.append(coro)
        coro.close()

    hass.async_create_task = _create_task

    await manager.async_setup()

    assert manager.get_helper_count() == 14
    assert manager._daily_reset_configured is True
    assert scheduled["hms"] == (6, 45, 30)
    assert len(manager._cleanup_listeners) == 1
    assert captured_calls

    reset_callback = cast(Callable[[Any], None], scheduled["callback"])
    reset_callback(None)
    assert len(scheduled_tasks) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_setup_wraps_failures_as_home_assistant_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should raise HomeAssistantError when helper creation fails."""
    manager, _hass, _entry = _make_manager(
        dogs=[{"dog_id": "dog-1", "dog_name": "Dog"}]
    )
    monkeypatch.setattr(
        manager,
        "async_create_helpers_for_dogs",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(
        helper_manager.HomeAssistantError, match="Helper manager setup failed: boom"
    ):
        await manager.async_setup()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_create_helpers_for_dogs_mapping_and_sequence_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bulk helper creation should handle mapping and sequence module payloads."""
    manager, _hass, _entry = _make_manager()

    async def _create_for_dog(
        dog_id: str,
        _dog_config: helper_manager.DogConfigData,
        _enabled: helper_manager.DogModulesConfig,
    ) -> None:
        if dog_id == "dog-1":
            manager._created_helpers.update(
                {"input_boolean.pawcontrol_dog_1_breakfast_fed"},
            )

    ensure_listener = AsyncMock()
    monkeypatch.setattr(manager, "_async_create_helpers_for_dog", _create_for_dog)
    monkeypatch.setattr(manager, "_ensure_daily_reset_listener", ensure_listener)

    created = await manager.async_create_helpers_for_dogs(
        [
            {"dog_id": "dog-1", "dog_name": "One"},
            {"dog_id": "dog-2", "dog_name": "Two"},
            {"dog_id": "", "dog_name": "Skip"},
        ],
        {MODULE_FEEDING: True, "invalid": True},
    )
    assert list(created) == ["dog-1"]
    ensure_listener.assert_awaited_once()

    manager_two, _hass_two, _entry_two = _make_manager()
    monkeypatch.setattr(
        manager_two,
        "_async_create_helpers_for_dog",
        AsyncMock(return_value=None),
    )
    ensure_listener_two = AsyncMock()
    monkeypatch.setattr(
        manager_two, "_ensure_daily_reset_listener", ensure_listener_two
    )

    created_two = await manager_two.async_create_helpers_for_dogs(
        [{"dog_id": "dog-3", "dog_name": "Three"}],
        [MODULE_HEALTH, "invalid"],
    )
    assert created_two == {}
    ensure_listener_two.assert_not_awaited()

    manager_three, _hass_three, _entry_three = _make_manager()
    manager_three._dog_helpers["dog-dup"] = [
        "input_boolean.pawcontrol_dog_dup_breakfast_fed"
    ]

    async def _create_duplicate_helper(
        dog_id: str,
        _dog_config: helper_manager.DogConfigData,
        _enabled: helper_manager.DogModulesConfig,
    ) -> None:
        if dog_id == "dog-dup":
            manager_three._created_helpers.add(
                "input_boolean.pawcontrol_dog_dup_breakfast_fed"
            )

    ensure_listener_three = AsyncMock()
    monkeypatch.setattr(
        manager_three, "_async_create_helpers_for_dog", _create_duplicate_helper
    )
    monkeypatch.setattr(
        manager_three, "_ensure_daily_reset_listener", ensure_listener_three
    )

    created_three = await manager_three.async_create_helpers_for_dogs(
        [{"dog_id": "dog-dup", "dog_name": "Duplicate"}],
        {MODULE_FEEDING: True},
    )
    assert created_three["dog-dup"] == [
        "input_boolean.pawcontrol_dog_dup_breakfast_fed"
    ]
    assert manager_three._dog_helpers["dog-dup"] == [
        "input_boolean.pawcontrol_dog_dup_breakfast_fed"
    ]
    ensure_listener_three.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_create_helpers_for_dog_respects_module_switches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-dog helper creation should only call enabled module builders."""
    manager, _hass, _entry = _make_manager()
    feeding = AsyncMock()
    health = AsyncMock()
    medication = AsyncMock()
    visitor = AsyncMock()
    monkeypatch.setattr(manager, "_async_create_feeding_helpers", feeding)
    monkeypatch.setattr(manager, "_async_create_health_helpers", health)
    monkeypatch.setattr(manager, "_async_create_medication_helpers", medication)
    monkeypatch.setattr(manager, "_async_create_visitor_helper", visitor)

    await manager._async_create_helpers_for_dog(
        "dog-1",
        {"dog_id": "dog-1", "dog_name": ""},
        {
            MODULE_FEEDING: True,
            MODULE_HEALTH: False,
            MODULE_MEDICATION: True,
        },
    )

    feeding.assert_awaited_once_with("dog-1", "dog-1")
    health.assert_not_awaited()
    medication.assert_awaited_once_with("dog-1", "dog-1")
    visitor.assert_awaited_once_with("dog-1", "dog-1")

    await manager._async_create_helpers_for_dog(
        "dog-2",
        {"dog_id": "dog-2", "dog_name": "Buddy"},
        {
            MODULE_FEEDING: False,
            MODULE_HEALTH: True,
            MODULE_MEDICATION: False,
        },
    )
    assert health.await_count == 1
    assert visitor.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_feeding_helpers_use_default_time_for_unknown_meal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown meal types should use the fallback feeding time value."""
    manager, _hass, _entry = _make_manager()

    booleans: list[tuple[str, str, str | None, bool]] = []
    datetimes: list[tuple[str, str, bool, bool, str | None]] = []

    async def _capture_boolean(
        entity_id: str,
        name: str,
        icon: str | None = None,
        initial: bool = False,
    ) -> None:
        booleans.append((entity_id, name, icon, initial))

    async def _capture_datetime(
        entity_id: str,
        name: str,
        has_date: bool = True,
        has_time: bool = True,
        initial: str | None = None,
    ) -> None:
        datetimes.append((entity_id, name, has_date, has_time, initial))

    monkeypatch.setattr(manager, "_async_create_input_boolean", _capture_boolean)
    monkeypatch.setattr(manager, "_async_create_input_datetime", _capture_datetime)
    monkeypatch.setattr(helper_manager, "MEAL_TYPES", ["breakfast", "mystery"])

    await manager._async_create_feeding_helpers("dog-1", "Buddy")

    assert len(booleans) == 2
    assert len(datetimes) == 2
    assert any(call[-1] == "12:00:00" for call in datetimes)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_helpers_build_weight_status_and_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health helper builder should create number/select/datetime helpers."""
    manager, _hass, _entry = _make_manager(language="fr")
    number_calls: list[
        tuple[str, str, float, float, float, str | None, str | None, str, float | None]
    ] = []
    select_calls: list[tuple[str, str, list[str], str | None, str | None]] = []
    datetime_calls: list[tuple[str, str, bool, bool, str | None]] = []

    async def _capture_number(
        entity_id: str,
        name: str,
        min: float,
        max: float,
        step: float = 1.0,
        unit_of_measurement: str | None = None,
        icon: str | None = None,
        mode: str = "slider",
        initial: float | None = None,
    ) -> None:
        number_calls.append(
            (
                entity_id,
                name,
                min,
                max,
                step,
                unit_of_measurement,
                icon,
                mode,
                initial,
            ),
        )

    async def _capture_select(
        entity_id: str,
        name: str,
        options: list[str],
        initial: str | None = None,
        icon: str | None = None,
    ) -> None:
        select_calls.append((entity_id, name, options, initial, icon))

    async def _capture_datetime(
        entity_id: str,
        name: str,
        has_date: bool = True,
        has_time: bool = True,
        initial: str | None = None,
    ) -> None:
        datetime_calls.append((entity_id, name, has_date, has_time, initial))

    monkeypatch.setattr(manager, "_async_create_input_number", _capture_number)
    monkeypatch.setattr(manager, "_async_create_input_select", _capture_select)
    monkeypatch.setattr(manager, "_async_create_input_datetime", _capture_datetime)
    monkeypatch.setattr(
        helper_manager,
        "translated_grooming_template",
        lambda _hass, _lang, _key, *, dog_name: f"{dog_name} translated grooming",
    )

    await manager._async_create_health_helpers("dog-1", "")

    assert len(number_calls) == 1
    assert len(select_calls) == 1
    assert len(datetime_calls) == 2
    assert any("translated grooming" in call[1] for call in datetime_calls)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_medication_and_visitor_helper_builders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Medication and visitor helper builders should delegate to helper creators."""
    manager, _hass, _entry = _make_manager()
    datetime_calls: list[tuple[str, str, bool, bool, str | None]] = []
    boolean_calls: list[tuple[str, str, str | None, bool]] = []

    async def _capture_datetime(
        entity_id: str,
        name: str,
        has_date: bool = True,
        has_time: bool = True,
        initial: str | None = None,
    ) -> None:
        datetime_calls.append((entity_id, name, has_date, has_time, initial))

    async def _capture_boolean(
        entity_id: str,
        name: str,
        icon: str | None = None,
        initial: bool = False,
    ) -> None:
        boolean_calls.append((entity_id, name, icon, initial))

    monkeypatch.setattr(manager, "_async_create_input_datetime", _capture_datetime)
    monkeypatch.setattr(manager, "_async_create_input_boolean", _capture_boolean)

    await manager._async_create_medication_helpers("dog-1", "Buddy")
    await manager._async_create_visitor_helper("dog-1", "Buddy")

    assert len(datetime_calls) == 1
    assert datetime_calls[0][-1] == "08:00:00"
    assert len(boolean_calls) == 1
    assert boolean_calls[0][-1] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_input_helper_creation_success_with_optional_fields_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Input helper creators should succeed with minimal payloads."""
    manager, _hass, _entry = _make_manager()
    monkeypatch.setattr(
        helper_manager.er, "async_get", lambda _hass: _DummyEntityRegistry()
    )

    captured: list[tuple[str, Mapping[str, object]]] = []

    async def _capture_service_call(
        _hass: Any,
        domain: str,
        service: str,
        service_data: Mapping[str, object] | None = None,
        *,
        target: Mapping[str, object] | None = None,
        blocking: bool,
        description: str | None,
        logger: Any,
    ) -> ServiceGuardResult:
        del service, target, blocking, description, logger
        captured.append((domain, dict(service_data or {})))
        return _service_result(domain=domain, service="create", executed=True)

    monkeypatch.setattr(
        helper_manager,
        "async_call_hass_service_if_available",
        _capture_service_call,
    )

    await manager._async_create_input_boolean(
        "input_boolean.min", "Minimal", icon=None, initial=True
    )
    await manager._async_create_input_datetime(
        "input_datetime.min",
        "Minimal DT",
        has_date=True,
        has_time=False,
        initial=None,
    )
    await manager._async_create_input_number(
        "input_number.min",
        "Minimal Number",
        min=0.0,
        max=10.0,
        step=1.0,
        unit_of_measurement=None,
        icon=None,
        mode="slider",
        initial=2.5,
    )
    await manager._async_create_input_select(
        "input_select.min",
        "Minimal Select",
        options=["a", "b"],
        initial=None,
        icon=None,
    )

    assert len(captured) == 4
    assert "icon" not in captured[0][1]
    assert "initial" not in captured[1][1]
    assert "unit_of_measurement" not in captured[2][1]
    assert captured[2][1]["initial"] == 2.5
    assert "icon" not in captured[3][1]
    assert manager.managed_entities["input_number.min"]["initial"] == 2.5
    assert manager.get_helper_count() == 4


@pytest.mark.unit
@pytest.mark.asyncio
async def test_input_helper_creation_skips_existing_false_guards_and_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Input helper creators should skip existing entities and handle failures."""
    manager, _hass, _entry = _make_manager()
    existing = _DummyEntityRegistry(
        {
            "input_boolean.existing",
            "input_datetime.existing",
            "input_number.existing",
            "input_select.existing",
        },
    )
    monkeypatch.setattr(helper_manager.er, "async_get", lambda _hass: existing)
    service_not_called = AsyncMock()
    monkeypatch.setattr(
        helper_manager,
        "async_call_hass_service_if_available",
        service_not_called,
    )

    await manager._async_create_input_boolean("input_boolean.existing", "Existing")
    await manager._async_create_input_datetime("input_datetime.existing", "Existing")
    await manager._async_create_input_number(
        "input_number.existing", "Existing", min=0.0, max=1.0
    )
    await manager._async_create_input_select(
        "input_select.existing", "Existing", options=["a"]
    )
    service_not_called.assert_not_awaited()

    monkeypatch.setattr(
        helper_manager.er, "async_get", lambda _hass: _DummyEntityRegistry()
    )

    async def _return_false(
        _hass: Any,
        domain: str,
        service: str,
        _service_data: Mapping[str, object] | None = None,
        *,
        target: Mapping[str, object] | None = None,
        blocking: bool,
        description: str | None,
        logger: Any,
    ) -> ServiceGuardResult:
        del target, blocking, description, logger
        return _service_result(
            domain=domain,
            service=service,
            executed=False,
            reason="disabled",
        )

    monkeypatch.setattr(
        helper_manager, "async_call_hass_service_if_available", _return_false
    )

    await manager._async_create_input_boolean("input_boolean.false", "False")
    await manager._async_create_input_datetime("input_datetime.false", "False")
    await manager._async_create_input_number(
        "input_number.false", "False", min=0.0, max=1.0
    )
    await manager._async_create_input_select(
        "input_select.false", "False", options=["x"]
    )
    assert "input_boolean.false" not in manager._created_helpers

    async def _raise_error(*_args: Any, **_kwargs: Any) -> ServiceGuardResult:
        raise RuntimeError("service failure")

    monkeypatch.setattr(
        helper_manager, "async_call_hass_service_if_available", _raise_error
    )

    await manager._async_create_input_boolean("input_boolean.error", "Error")
    await manager._async_create_input_datetime("input_datetime.error", "Error")
    await manager._async_create_input_number(
        "input_number.error", "Error", min=0.0, max=1.0
    )
    await manager._async_create_input_select(
        "input_select.error", "Error", options=["x"]
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_daily_reset_listener_configuration_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Daily reset listener should short-circuit, fail gracefully, then configure."""
    manager, _hass, _entry = _make_manager()

    manager._daily_reset_configured = True
    setup_mock = AsyncMock()
    monkeypatch.setattr(manager, "_async_setup_daily_reset", setup_mock)
    await manager._ensure_daily_reset_listener()
    setup_mock.assert_not_awaited()

    manager._daily_reset_configured = False
    failing_setup = AsyncMock(side_effect=RuntimeError("cannot schedule"))
    monkeypatch.setattr(manager, "_async_setup_daily_reset", failing_setup)
    await manager._ensure_daily_reset_listener()
    assert manager._daily_reset_configured is False

    success_setup = AsyncMock(return_value=None)
    monkeypatch.setattr(manager, "_async_setup_daily_reset", success_setup)
    await manager._ensure_daily_reset_listener()
    assert manager._daily_reset_configured is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_setup_daily_reset_handles_invalid_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid reset times should fall back to default and no-op when unparseable."""
    manager, _hass, _entry = _make_manager(options={"reset_time": "invalid"})
    parse_calls: list[str] = []

    def _parse_time(value: str) -> time | None:
        parse_calls.append(value)
        return None

    monkeypatch.setattr(
        helper_manager, "dt_util", SimpleNamespace(parse_time=_parse_time)
    )
    await manager._async_setup_daily_reset()
    assert parse_calls == ["invalid", DEFAULT_RESET_TIME]
    assert manager._cleanup_listeners == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_reset_feeding_toggles_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feeding reset should handle dog sources, short-circuit, and errors."""
    manager, _hass, _entry = _make_manager()
    manager._dog_helpers = {"dog-1": ["helper"]}
    reset_calls: list[str] = []

    async def _turn_off(
        _hass: Any,
        domain: str,
        service: str,
        _service_data: Mapping[str, object] | None = None,
        *,
        target: Mapping[str, object] | None = None,
        blocking: bool,
        description: str | None,
        logger: Any,
    ) -> ServiceGuardResult:
        del _service_data, blocking, description, logger
        reset_calls.append(cast(str, (target or {}).get("entity_id", "")))
        return _service_result(domain=domain, service=service, executed=True)

    monkeypatch.setattr(
        helper_manager, "async_call_hass_service_if_available", _turn_off
    )
    await manager._async_reset_feeding_toggles()
    assert len(reset_calls) == len(helper_manager.MEAL_TYPES)

    manager_mapping, _hass_mapping, _entry_mapping = _make_manager(
        dogs={"dog-map": {"dog_name": "Mapped"}},
    )
    monkeypatch.setattr(
        helper_manager, "async_call_hass_service_if_available", _turn_off
    )
    await manager_mapping._async_reset_feeding_toggles()
    assert any(
        ("dog-map" in entity_id) or ("dog_map" in entity_id)
        for entity_id in reset_calls
    )

    manager_sequence, _hass_sequence, _entry_sequence = _make_manager(
        dogs=[
            {helper_manager.CONF_DOG_ID: "dog-seq"},
            {helper_manager.CONF_DOG_ID: 7},
            "invalid",
        ],
    )
    short_circuit_calls: list[str] = []

    async def _turn_off_false(
        _hass: Any,
        domain: str,
        service: str,
        _service_data: Mapping[str, object] | None = None,
        *,
        target: Mapping[str, object] | None = None,
        blocking: bool,
        description: str | None,
        logger: Any,
    ) -> ServiceGuardResult:
        del _service_data, blocking, description, logger
        short_circuit_calls.append(cast(str, (target or {}).get("entity_id", "")))
        return _service_result(
            domain=domain,
            service=service,
            executed=False,
            reason="disabled",
        )

    monkeypatch.setattr(
        helper_manager, "async_call_hass_service_if_available", _turn_off_false
    )
    await manager_sequence._async_reset_feeding_toggles()
    assert len(short_circuit_calls) == 1

    manager_error, _hass_error, _entry_error = _make_manager(
        dogs={"dog-err": {"dog_name": "Err"}}
    )

    async def _turn_off_error(*_args: Any, **_kwargs: Any) -> ServiceGuardResult:
        raise RuntimeError("reset failed")

    monkeypatch.setattr(
        helper_manager, "async_call_hass_service_if_available", _turn_off_error
    )
    await manager_error._async_reset_feeding_toggles()

    manager_string, _hass_string, _entry_string = _make_manager(
        dogs="not-a-dog-sequence"
    )
    monkeypatch.setattr(
        helper_manager, "async_call_hass_service_if_available", _turn_off
    )
    before = len(reset_calls)
    await manager_string._async_reset_feeding_toggles()
    assert len(reset_calls) == before


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_add_dog_helpers_invalid_and_valid_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding dog helpers should ignore invalid payloads and normalize valid data."""
    manager, _hass, _entry = _make_manager(
        options={CONF_MODULES: [MODULE_FEEDING, MODULE_HEALTH]}
    )
    create_mock = AsyncMock()
    monkeypatch.setattr(manager, "async_create_helpers_for_dogs", create_mock)

    original_ensure = helper_manager.ensure_dog_config_data
    monkeypatch.setattr(helper_manager, "ensure_dog_config_data", lambda _payload: None)
    await manager.async_add_dog_helpers("dog-invalid", {"dog_name": "Ignored"})
    create_mock.assert_not_awaited()

    monkeypatch.setattr(helper_manager, "ensure_dog_config_data", original_ensure)
    await manager.async_add_dog_helpers("dog-valid", {"custom": "value"})
    create_mock.assert_awaited_once()

    dogs_payload = create_mock.await_args.args[0]
    modules_payload = create_mock.await_args.args[1]
    assert dogs_payload[0]["dog_id"] == "dog-valid"
    assert dogs_payload[0]["dog_name"] == "dog-valid"
    assert modules_payload == frozenset({MODULE_FEEDING, MODULE_HEALTH})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_remove_update_accessors_cleanup_and_unload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Removal/update flows and accessors should behave consistently."""
    manager, _hass, _entry = _make_manager()
    slug_dog_id = helper_manager.slugify("dog-1")
    manager._created_helpers = {
        f"input_boolean.pawcontrol_{slug_dog_id}_breakfast_fed",
        f"input_datetime.pawcontrol_{slug_dog_id}_breakfast_time",
        f"input_number.pawcontrol_{slug_dog_id}_current_weight",
        "input_select.pawcontrol_other_health_status",
    }
    manager._managed_entities = {
        f"input_boolean.pawcontrol_{slug_dog_id}_breakfast_fed": {
            "domain": "input_boolean",
            "name": "Breakfast",
        },
        f"input_datetime.pawcontrol_{slug_dog_id}_breakfast_time": {
            "domain": "input_datetime",
            "name": "Breakfast Time",
        },
        f"input_number.pawcontrol_{slug_dog_id}_current_weight": {
            "domain": "input_number",
            "name": "Weight",
        },
    }
    manager._dog_helpers = {"dog-1": ["x"]}

    async def _delete_helper(
        _hass: Any,
        domain: str,
        service: str,
        _service_data: Mapping[str, object] | None = None,
        *,
        target: Mapping[str, object] | None = None,
        blocking: bool,
        description: str | None,
        logger: Any,
    ) -> ServiceGuardResult:
        del _service_data, blocking, description, logger
        entity_id = cast(str, (target or {}).get("entity_id", ""))
        if entity_id.endswith("_breakfast_fed"):
            return _service_result(
                domain=domain,
                service=service,
                executed=False,
                reason="blocked",
            )
        if entity_id.endswith("_breakfast_time"):
            raise RuntimeError("delete failed")
        if entity_id.endswith("_current_weight"):
            return _service_result(domain=domain, service=service, executed=True)
        return _service_result(domain=domain, service=service, executed=True)

    monkeypatch.setattr(
        helper_manager, "async_call_hass_service_if_available", _delete_helper
    )
    await manager.async_remove_dog_helpers("dog-1")

    assert "dog-1" not in manager._dog_helpers
    assert (
        f"input_number.pawcontrol_{slug_dog_id}_current_weight"
        not in manager._created_helpers
    )
    assert (
        f"input_datetime.pawcontrol_{slug_dog_id}_breakfast_time"
        in manager._created_helpers
    )

    remove_mock = AsyncMock()
    add_mock = AsyncMock()
    monkeypatch.setattr(manager, "async_remove_dog_helpers", remove_mock)
    monkeypatch.setattr(manager, "async_add_dog_helpers", add_mock)
    await manager.async_update_dog_helpers("dog-updated", {"dog_name": "Updated"})
    remove_mock.assert_awaited_once_with("dog-updated")
    add_mock.assert_awaited_once_with("dog-updated", {"dog_name": "Updated"})

    slug_display_id = helper_manager.slugify("Dog 1")
    assert manager.get_feeding_status_entity("Dog 1", "breakfast").startswith(
        f"input_boolean.pawcontrol_{slug_display_id}_",
    )
    assert manager.get_feeding_time_entity("Dog 1", "dinner").startswith(
        f"input_datetime.pawcontrol_{slug_display_id}_",
    )
    assert (
        manager.get_weight_entity("Dog 1")
        == f"input_number.pawcontrol_{slug_display_id}_current_weight"
    )
    assert (
        manager.get_health_status_entity("Dog 1")
        == f"input_select.pawcontrol_{slug_display_id}_health_status"
    )
    assert (
        manager.get_visitor_mode_entity("Dog 1")
        == f"input_boolean.pawcontrol_{slug_display_id}_visitor_mode"
    )

    manager._created_helpers = {"input_boolean.copy_test"}
    copied_helpers = manager.created_helpers
    copied_helpers.add("input_boolean.local_only")
    assert "input_boolean.local_only" not in manager._created_helpers
    assert manager.get_helper_count() == 1

    manager._managed_entities = {
        "input_boolean.copy_test": {"domain": "input_boolean", "name": "Copy Test"},
    }
    copied_entities = manager.managed_entities
    copied_entities["new_entity"] = {"domain": "input_select", "name": "New"}
    assert "new_entity" not in manager._managed_entities

    def _ok_unsub() -> None:
        return None

    def _bad_unsub() -> None:
        raise RuntimeError("cleanup failed")

    manager._cleanup_listeners = [_ok_unsub, _bad_unsub]
    manager._dog_helpers = {"dog": ["entity"]}
    manager._daily_reset_configured = True
    await manager.async_cleanup()
    assert manager._cleanup_listeners == []
    assert manager._dog_helpers == {}
    assert manager._daily_reset_configured is False

    manager._created_helpers = {"input_boolean.persisted"}
    cleanup_mock = AsyncMock()
    monkeypatch.setattr(manager, "async_cleanup", cleanup_mock)
    await manager.async_unload()
    cleanup_mock.assert_awaited_once()
