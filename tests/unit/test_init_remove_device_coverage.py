"""Targeted coverage tests for ``async_remove_config_entry_device``."""

import asyncio
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import custom_components.pawcontrol as pawcontrol_init
from custom_components.pawcontrol.const import CONF_DOG_OPTIONS, CONF_DOGS, DOMAIN
from custom_components.pawcontrol.exceptions import PawControlSetupError
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD
from homeassistant.exceptions import ConfigEntryNotReady


def _fake_ensure_dog_config_data(candidate: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(candidate.get(DOG_ID_FIELD), str):
        return None
    if not candidate[DOG_ID_FIELD]:
        return None
    candidate.setdefault(DOG_NAME_FIELD, str(candidate[DOG_ID_FIELD]))
    return candidate


def _fake_sanitize_dog_id(raw_id: str) -> str:
    if raw_id == "skip-me":
        return ""
    return str(raw_id).strip().lower().replace(" ", "_")


def _patch_setup_global(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: Any,
) -> None:
    monkeypatch.setitem(pawcontrol_init.async_setup_entry.__globals__, name, value)


def _patch_rollback_global(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: Any,
) -> None:
    monkeypatch.setitem(
        pawcontrol_init._async_rollback_failed_setup.__globals__,
        name,
        value,
    )


@pytest.mark.asyncio
async def test_remove_device_returns_false_for_non_pawcontrol_identifiers() -> None:
    """Devices not owned by this integration should not be removable here."""
    hass = SimpleNamespace()
    entry = SimpleNamespace(data={}, options={})
    device = SimpleNamespace(id="device-1", identifiers={("other_domain", "dog-1")})

    result = await pawcontrol_init.async_remove_config_entry_device(hass, entry, device)

    assert result is False


@pytest.mark.asyncio
async def test_remove_device_refuses_when_identifier_is_still_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A device must not be removed while any matching dog ID remains configured."""
    monkeypatch.setattr(
        pawcontrol_init,
        "ensure_dog_config_data",
        _fake_ensure_dog_config_data,
    )
    monkeypatch.setattr(
        pawcontrol_init,
        "sanitize_dog_id",
        _fake_sanitize_dog_id,
    )

    runtime_data = SimpleNamespace(
        dogs=[
            {DOG_ID_FIELD: "runtime-dog", DOG_NAME_FIELD: 123},
            {DOG_NAME_FIELD: "missing-id"},
            {DOG_ID_FIELD: "skip-me"},
            "invalid",
        ]
    )
    monkeypatch.setattr(
        pawcontrol_init,
        "get_runtime_data",
        lambda *_: runtime_data,
    )

    entry = SimpleNamespace(
        entry_id="entry-target",
        data={
            CONF_DOGS: {
                "from-key": {DOG_NAME_FIELD: 999},
                "bad": "invalid",
            },
            CONF_DOG_OPTIONS: [
                {DOG_NAME_FIELD: "missing-id"},
                {DOG_ID_FIELD: "seq-dog"},
                "invalid",
            ],
        },
        options={
            CONF_DOGS: [
                {DOG_NAME_FIELD: "missing-id"},
                {DOG_ID_FIELD: "options-dog", DOG_NAME_FIELD: None},
            ],
            CONF_DOG_OPTIONS: {
                "target_dog": {DOG_ID_FIELD: "alt-target"},
                "": {DOG_ID_FIELD: "blank-key"},
                "other": "invalid",
            },
        },
    )
    device = SimpleNamespace(
        id="device-target",
        identifiers={
            ("other_domain", "ignored"),
            (DOMAIN, "target_dog"),
            (DOMAIN,),
        },
    )

    result = await pawcontrol_init.async_remove_config_entry_device(hass=SimpleNamespace(), entry=entry, device_entry=device)

    assert result is False


@pytest.mark.asyncio
async def test_remove_device_allows_when_no_active_identifier_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Removal should be allowed once no configured dog maps to the device identifiers."""
    monkeypatch.setattr(
        pawcontrol_init,
        "ensure_dog_config_data",
        _fake_ensure_dog_config_data,
    )
    monkeypatch.setattr(
        pawcontrol_init,
        "sanitize_dog_id",
        _fake_sanitize_dog_id,
    )
    monkeypatch.setattr(
        pawcontrol_init,
        "get_runtime_data",
        lambda *_: None,
    )

    entry = SimpleNamespace(
        entry_id="entry-ghost",
        data={
            CONF_DOGS: 123,
            CONF_DOG_OPTIONS: [
                {DOG_ID_FIELD: "other-seq"},
                {DOG_NAME_FIELD: "missing-id"},
            ],
        },
        options={
            CONF_DOGS: "invalid",
            CONF_DOG_OPTIONS: {"other-map": {DOG_ID_FIELD: "other-map-value"}},
        },
    )
    device = SimpleNamespace(id="device-ghost", identifiers={(DOMAIN, "ghost-id")})

    result = await pawcontrol_init.async_remove_config_entry_device(hass=SimpleNamespace(), entry=entry, device_entry=device)

    assert result is True


def test_get_platforms_skips_non_mapping_module_payloads() -> None:
    """Dogs with malformed modules should be ignored when computing platforms."""
    platforms = pawcontrol_init.get_platforms_for_profile_and_modules(
        [
            {DOG_ID_FIELD: "a", DOG_NAME_FIELD: "A", "modules": ["invalid"]},
            {DOG_ID_FIELD: "b", DOG_NAME_FIELD: "B", "modules": {"gps": True}},
        ],
        "standard",
    )

    assert isinstance(platforms, tuple)
    assert platforms


def test_enable_debug_logging_handles_already_tracked_entries() -> None:
    """Repeated enables should keep tracking stable when logger is already DEBUG."""
    package_logger = logging.getLogger("custom_components.pawcontrol")
    previous_level = package_logger.level
    previous_entries = set(pawcontrol_init._DEBUG_LOGGER_ENTRIES)
    previous_default = pawcontrol_init._DEFAULT_LOGGER_LEVEL
    try:
        package_logger.setLevel(logging.DEBUG)
        pawcontrol_init._DEBUG_LOGGER_ENTRIES.clear()

        entry = SimpleNamespace(entry_id="debug-entry", options={"debug_logging": True})
        assert pawcontrol_init._enable_debug_logging(entry) is True
        assert pawcontrol_init._enable_debug_logging(entry) is True
    finally:
        pawcontrol_init._DEBUG_LOGGER_ENTRIES.clear()
        pawcontrol_init._DEBUG_LOGGER_ENTRIES.update(previous_entries)
        pawcontrol_init._DEFAULT_LOGGER_LEVEL = previous_default
        package_logger.setLevel(previous_level)


@pytest.mark.asyncio
async def test_async_rollback_failed_setup_runs_best_effort_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rollback should attempt MQTT/webhook/runtime cleanup and clear runtime store."""
    mqtt_unreg = AsyncMock()
    webhook_unreg = AsyncMock()
    cleanup_runtime = AsyncMock()
    pop_runtime = MagicMock()

    _patch_rollback_global(monkeypatch, "async_unregister_entry_mqtt", mqtt_unreg)
    _patch_rollback_global(monkeypatch, "async_unregister_entry_webhook", webhook_unreg)
    _patch_rollback_global(monkeypatch, "async_cleanup_runtime_data", cleanup_runtime)
    _patch_rollback_global(monkeypatch, "pop_runtime_data", pop_runtime)

    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry-rollback")
    runtime_data = SimpleNamespace()

    await pawcontrol_init._async_rollback_failed_setup(
        hass,
        entry,
        runtime_data,
        runtime_data_stored=True,
        webhook_registered=True,
        mqtt_registered=True,
        reason=RuntimeError("boom"),
    )

    mqtt_unreg.assert_awaited_once_with(hass, entry)
    webhook_unreg.assert_awaited_once_with(hass, entry)
    cleanup_runtime.assert_awaited_once_with(runtime_data)
    pop_runtime.assert_called_once_with(hass, entry)


@pytest.mark.asyncio
async def test_async_unload_entry_skips_service_shutdown_when_other_entries_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service manager shutdown should be skipped when other entries are still active."""
    runtime_data = None
    service_manager = SimpleNamespace(async_shutdown=AsyncMock())

    hass = SimpleNamespace(
        data={DOMAIN: {"service_manager": service_manager}},
        config_entries=SimpleNamespace(
            async_unload_platforms=AsyncMock(return_value=True),
            async_loaded_entries=lambda _domain: ["entry-1", "entry-2"],
        ),
    )
    entry = SimpleNamespace(entry_id="entry-1", data={}, options={})

    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unregister_entry_webhook",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unregister_entry_mqtt",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unload_external_bindings",
        AsyncMock(),
    )
    monkeypatch.setattr("custom_components.pawcontrol.get_runtime_data", lambda *_: runtime_data)
    monkeypatch.setattr("custom_components.pawcontrol.pop_runtime_data", MagicMock())
    monkeypatch.setattr("custom_components.pawcontrol._disable_debug_logging", MagicMock())

    assert await pawcontrol_init.async_unload_entry(hass, entry) is True
    service_manager.async_shutdown.assert_not_called()


@pytest.mark.asyncio
async def test_remove_device_covers_additional_sequence_and_option_edge_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Additional shapes should traverse remaining mapping/sequence branches."""
    monkeypatch.setattr(
        pawcontrol_init,
        "ensure_dog_config_data",
        _fake_ensure_dog_config_data,
    )
    monkeypatch.setattr(
        pawcontrol_init,
        "sanitize_dog_id",
        _fake_sanitize_dog_id,
    )
    monkeypatch.setattr(
        pawcontrol_init,
        "get_runtime_data",
        lambda *_: SimpleNamespace(dogs=[{DOG_ID_FIELD: "skip-me"}, "invalid"]),
    )

    entry = SimpleNamespace(
        entry_id="entry-extra",
        data={
            CONF_DOGS: {"a": {DOG_NAME_FIELD: "already-string"}},
            CONF_DOG_OPTIONS: 5,
        },
        options={
            CONF_DOGS: [{DOG_ID_FIELD: "opt-seq", DOG_NAME_FIELD: "already-string"}, "invalid"],
            CONF_DOG_OPTIONS: {"map-id": {DOG_ID_FIELD: "skip-me"}},
        },
    )
    device = SimpleNamespace(id="device-extra", identifiers={(DOMAIN, "never-match")})

    assert (
        await pawcontrol_init.async_remove_config_entry_device(
            hass=SimpleNamespace(),
            entry=entry,
            device_entry=device,
        )
        is True
    )


@pytest.mark.asyncio
async def test_remove_device_covers_non_mapping_entry_options_and_loop_back_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-mapping options and multi-item sources should traverse remaining branches."""
    monkeypatch.setattr(
        pawcontrol_init,
        "ensure_dog_config_data",
        _fake_ensure_dog_config_data,
    )
    monkeypatch.setattr(
        pawcontrol_init,
        "sanitize_dog_id",
        _fake_sanitize_dog_id,
    )
    monkeypatch.setattr(
        pawcontrol_init,
        "get_runtime_data",
        lambda *_: SimpleNamespace(
            dogs=[
                {DOG_ID_FIELD: "runtime-a", DOG_NAME_FIELD: "A"},
                {DOG_ID_FIELD: "runtime-b", DOG_NAME_FIELD: "B"},
            ]
        ),
    )

    entry = SimpleNamespace(
        entry_id="entry-loop",
        data={
            CONF_DOGS: {
                "map-a": {DOG_NAME_FIELD: "Map A"},
                "map-b": {DOG_NAME_FIELD: "Map B"},
            },
            CONF_DOG_OPTIONS: [
                {DOG_ID_FIELD: "seq-a"},
                {DOG_ID_FIELD: "seq-b"},
            ],
        },
        # Intentionally not a Mapping to cover the options type checks.
        options="invalid-options",
    )
    device = SimpleNamespace(id="device-loop", identifiers={(DOMAIN, "never-match")})

    assert (
        await pawcontrol_init.async_remove_config_entry_device(
            hass=SimpleNamespace(),
            entry=entry,
            device_entry=device,
        )
        is True
    )


@pytest.mark.asyncio
async def test_remove_device_covers_remaining_iter_loop_and_option_raw_id_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise loop-back and key-only option branches in nested iterators."""
    monkeypatch.setattr(
        pawcontrol_init,
        "ensure_dog_config_data",
        _fake_ensure_dog_config_data,
    )
    monkeypatch.setattr(
        pawcontrol_init,
        "sanitize_dog_id",
        _fake_sanitize_dog_id,
    )
    monkeypatch.setattr(
        pawcontrol_init,
        "get_runtime_data",
        lambda *_: SimpleNamespace(
            dogs=[
                # Empty ID forces ensure_dog_config_data -> None (630->621).
                {DOG_ID_FIELD: "", DOG_NAME_FIELD: "Invalid"},
                {DOG_ID_FIELD: "runtime-two", DOG_NAME_FIELD: "Two"},
            ]
        ),
    )

    entry = SimpleNamespace(
        entry_id="entry-loop-arcs",
        data={
            # Mapping source with two valid dogs to force mapping-loop back edge.
            CONF_DOGS: {
                # Empty mapping key forces ensure_dog_config_data -> None (614->606).
                "": {DOG_NAME_FIELD: "Invalid Empty Key"},
                "map-one": {DOG_NAME_FIELD: "Map One"},
                "map-two": {DOG_NAME_FIELD: "Map Two"},
            },
            # Include one "skip-me" item to force sanitize_dog_id -> "" (704->697).
            CONF_DOG_OPTIONS: [
                {DOG_ID_FIELD: "skip-me"},
                {DOG_ID_FIELD: "seq-one"},
                {DOG_ID_FIELD: "seq-two"},
            ],
        },
        options={
            # Keep mapping options path enabled.
            CONF_DOGS: [{DOG_ID_FIELD: "opt-dog", DOG_NAME_FIELD: "Opt"}],
            CONF_DOG_OPTIONS: {
                # Key-only candidate (no raw_id) forces the 687->689 false branch.
                "key-only": {},
                "with-raw-id": {DOG_ID_FIELD: "raw-id"},
            },
        },
    )
    device = SimpleNamespace(id="device-loop-arcs", identifiers={(DOMAIN, "missing")})

    assert (
        await pawcontrol_init.async_remove_config_entry_device(
            hass=SimpleNamespace(),
            entry=entry,
            device_entry=device,
        )
        is True
    )


@pytest.mark.asyncio
async def test_async_setup_entry_handles_known_error_without_debug_tracking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Known setup errors should propagate even when debug logging is not tracked."""
    rollback = AsyncMock()
    disable_debug = MagicMock()
    _patch_setup_global(monkeypatch, "_enable_debug_logging", lambda *_: False)
    _patch_setup_global(
        monkeypatch,
        "async_validate_entry_config",
        AsyncMock(side_effect=ConfigEntryNotReady("not ready")),
    )
    _patch_setup_global(monkeypatch, "_async_rollback_failed_setup", rollback)
    _patch_setup_global(monkeypatch, "_disable_debug_logging", disable_debug)

    hass = SimpleNamespace(data={DOMAIN: {}})
    entry = SimpleNamespace(entry_id="entry-known", options={})

    with pytest.raises(ConfigEntryNotReady):
        await pawcontrol_init.async_setup_entry(hass, entry)

    assert rollback.await_count == 1
    disable_debug.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_wraps_unexpected_error_without_debug_tracking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected setup errors should be wrapped as PawControlSetupError."""
    rollback = AsyncMock()
    disable_debug = MagicMock()
    _patch_setup_global(monkeypatch, "_enable_debug_logging", lambda *_: False)
    _patch_setup_global(
        monkeypatch,
        "async_validate_entry_config",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    _patch_setup_global(monkeypatch, "_async_rollback_failed_setup", rollback)
    _patch_setup_global(monkeypatch, "_disable_debug_logging", disable_debug)

    hass = SimpleNamespace(data={DOMAIN: {}})
    entry = SimpleNamespace(entry_id="entry-unexpected", options={})

    with pytest.raises(PawControlSetupError, match="Unexpected setup failure"):
        await pawcontrol_init.async_setup_entry(hass, entry)

    assert rollback.await_count == 1
    disable_debug.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_handles_none_reset_unsubscriber(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should continue when daily reset scheduler returns ``None``."""
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(async_start_background_tasks=MagicMock()),
        helper_manager=None,
        door_sensor_manager=None,
        geofencing_manager=None,
        daily_reset_unsub=None,
        background_monitor_task=None,
    )

    _patch_setup_global(monkeypatch, "_enable_debug_logging", lambda *_: False)
    _patch_setup_global(
        monkeypatch,
        "async_validate_entry_config",
        AsyncMock(
            return_value=(
                [{DOG_ID_FIELD: "buddy", DOG_NAME_FIELD: "Buddy"}],
                "standard",
                {},
            )
        ),
    )
    _patch_setup_global(monkeypatch, "_should_skip_optional_setup", lambda *_: False)
    _patch_setup_global(
        monkeypatch,
        "async_initialize_managers",
        AsyncMock(return_value=runtime_data),
    )
    _patch_setup_global(monkeypatch, "store_runtime_data", MagicMock())
    _patch_setup_global(monkeypatch, "async_register_entry_webhook", AsyncMock())
    _patch_setup_global(monkeypatch, "async_register_entry_mqtt", AsyncMock())
    _patch_setup_global(monkeypatch, "async_setup_platforms", AsyncMock())
    _patch_setup_global(monkeypatch, "async_register_cleanup", AsyncMock())
    _patch_setup_global(
        monkeypatch,
        "async_setup_daily_reset_scheduler",
        AsyncMock(return_value=None),
    )
    _patch_setup_global(monkeypatch, "async_check_for_issues", AsyncMock())
    _patch_setup_global(
        monkeypatch,
        "_async_monitor_background_tasks",
        AsyncMock(),
    )

    hass = SimpleNamespace(
        data={DOMAIN: {}},
        async_create_task=lambda _coroutine: SimpleNamespace(done=lambda: False),
    )
    entry = SimpleNamespace(entry_id="entry-reset-none", options={})

    assert await pawcontrol_init.async_setup_entry(hass, entry) is True
    assert runtime_data.daily_reset_unsub is None


class _TaskStub:
    def __init__(self, done: bool) -> None:
        self._done = done

    def done(self) -> bool:
        return self._done


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("garden_manager", "expect_cleanup_restart", "expect_stats_restart"),
    [
        (None, False, False),
        (
            SimpleNamespace(
                _cleanup_task=_TaskStub(True),
                async_start_cleanup_task=None,
                _stats_update_task=_TaskStub(True),
                async_start_stats_update_task=None,
            ),
            False,
            False,
        ),
        (
            SimpleNamespace(
                _cleanup_task=_TaskStub(False),
                async_start_cleanup_task=AsyncMock(),
                _stats_update_task=_TaskStub(False),
                async_start_stats_update_task=AsyncMock(),
            ),
            False,
            False,
        ),
    ],
)
async def test_async_monitor_background_tasks_covers_remaining_branch_paths(
    monkeypatch: pytest.MonkeyPatch,
    garden_manager: Any,
    expect_cleanup_restart: bool,
    expect_stats_restart: bool,
) -> None:
    """Background monitor should tolerate absent managers and dead/non-callable restarts."""
    sleep_calls = {"count": 0}

    async def _fake_sleep(_seconds: int) -> None:
        sleep_calls["count"] += 1
        if sleep_calls["count"] >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(pawcontrol_init.asyncio, "sleep", _fake_sleep)
    runtime_data = SimpleNamespace(garden_manager=garden_manager)

    await pawcontrol_init._async_monitor_background_tasks(runtime_data)

    if garden_manager and callable(getattr(garden_manager, "async_start_cleanup_task", None)):
        assert bool(getattr(garden_manager.async_start_cleanup_task, "await_count", 0)) is expect_cleanup_restart
    if garden_manager and callable(getattr(garden_manager, "async_start_stats_update_task", None)):
        assert bool(getattr(garden_manager.async_start_stats_update_task, "await_count", 0)) is expect_stats_restart
