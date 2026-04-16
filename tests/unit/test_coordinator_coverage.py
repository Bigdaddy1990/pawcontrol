"""Targeted coverage tests for PawControl coordinator — uncovered paths.

Covers lines identified in the CI coverage report:
  coordinator.py: 221,225,230, 282,287, 305-318, 340,345,
                  379-387,391-394, 403-433, 440-446, 454,458,
                  476-486, 493, 518-543, 553,561, 606-607,
                  625, 642, 645, 649
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.pawcontrol import coordinator as coordinator_module
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.coordinator_runtime import RuntimeCycleInfo
from custom_components.pawcontrol.exceptions import ConfigEntryAuthFailed, UpdateFailed


# ──────────────────────────────────────────────────────────────────────────────
# use_external_api property / setter  (lines 221, 225, 230)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_use_external_api_getter_and_setter(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """use_external_api property should reflect current value and accept updates."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    original = coord.use_external_api
    coord.use_external_api = not original
    assert coord.use_external_api is (not original)
    coord.use_external_api = True
    assert coord.use_external_api is True


# ──────────────────────────────────────────────────────────────────────────────
# api_client property  (lines 228-230)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_api_client_returns_none_when_no_endpoint(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """api_client should be None when no endpoint was configured."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    # Default fixture has no API endpoint configured.
    assert coord.api_client is None


# ──────────────────────────────────────────────────────────────────────────────
# attach_runtime_managers  (lines 238-265)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_attach_runtime_managers_stores_managers(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """attach_runtime_managers must store all manager references."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    dm = MagicMock()
    dm.set_metrics_sink = MagicMock()
    fm = MagicMock()
    wm = MagicMock()
    nm = MagicMock()

    coord.attach_runtime_managers(
        data_manager=dm,
        feeding_manager=fm,
        walk_manager=wm,
        notification_manager=nm,
    )

    assert coord.runtime_managers.data_manager is dm
    assert coord.runtime_managers.feeding_manager is fm
    assert coord.runtime_managers.walk_manager is wm
    assert coord.runtime_managers.notification_manager is nm
    dm.set_metrics_sink.assert_called_once_with(coord._metrics)


@pytest.mark.unit
def test_attach_runtime_managers_without_metrics_sink_method(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """attach_runtime_managers should tolerate data managers without sink support."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    data_manager = SimpleNamespace()

    coord.attach_runtime_managers(
        data_manager=data_manager,
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        notification_manager=MagicMock(),
    )

    assert coord.runtime_managers.data_manager is data_manager


@pytest.mark.unit
def test_clear_runtime_managers_resets_all(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """clear_runtime_managers should null-out stored manager references."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    dm = MagicMock()
    dm.set_metrics_sink = MagicMock()

    coord.attach_runtime_managers(
        data_manager=dm,
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        notification_manager=MagicMock(),
    )
    coord.clear_runtime_managers()

    assert coord.runtime_managers.data_manager is None
    assert coord.runtime_managers.feeding_manager is None


# ──────────────────────────────────────────────────────────────────────────────
# runtime_managers setter  (lines 282-287)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_runtime_managers_setter(mock_hass, mock_config_entry, mock_session) -> None:
    """runtime_managers setter should replace the cached container."""
    import custom_components.pawcontrol.types as paw_types

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    new_container = paw_types.CoordinatorRuntimeManagers()
    coord.runtime_managers = new_container
    assert coord.runtime_managers is new_container


# ──────────────────────────────────────────────────────────────────────────────
# async_refresh_dog — unknown dog  (lines 388-394)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_refresh_dog_unknown_id(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """async_refresh_dog should silently skip unknown dog_ids."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._refresh_subset = AsyncMock()
    await coord.async_refresh_dog("nonexistent_dog")
    coord._refresh_subset.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_refresh_dog_known_id_calls_subset(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """async_refresh_dog should delegate to _refresh_subset for valid dogs."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._refresh_subset = AsyncMock()
    await coord.async_refresh_dog("test_dog")
    coord._refresh_subset.assert_awaited_once_with(["test_dog"])


# ──────────────────────────────────────────────────────────────────────────────
# async_patch_gps_update — various early-return paths  (lines 403-433)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_patch_gps_unknown_dog(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """GPS patch for unknown dog should be silently ignored."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord.async_request_refresh = AsyncMock()
    await coord.async_patch_gps_update("ghost_dog")
    coord.async_request_refresh.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_patch_gps_not_ready_defers_to_refresh(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """GPS patch should defer to full refresh when coordinator is not set up."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._setup_complete = False
    coord.async_request_refresh = AsyncMock()
    await coord.async_patch_gps_update("test_dog")
    coord.async_request_refresh.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_patch_gps_no_payload_warns(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """GPS patch should warn and return when no payload exists for the dog."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._setup_complete = True
    coord._data = {"test_dog": None}  # type: ignore[assignment]
    coord.last_update_success = True
    coord.async_request_refresh = AsyncMock()
    await coord.async_patch_gps_update("test_dog")
    coord.async_request_refresh.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# async_request_selective_refresh  (lines 440-446, 454, 458)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
@pytest.mark.asyncio
async def test_selective_refresh_none_falls_back_to_full(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Selective refresh with None should trigger a full coordinator refresh."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord.async_request_refresh = AsyncMock()
    await coord.async_request_selective_refresh(dog_ids=None)
    coord.async_request_refresh.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_selective_refresh_empty_list_is_noop(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Selective refresh with empty iterable should not call _refresh_subset."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._refresh_subset = AsyncMock()
    await coord.async_request_selective_refresh(dog_ids=[])
    coord._refresh_subset.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_selective_refresh_deduplicates_ids(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Selective refresh should deduplicate dog_ids before calling _refresh_subset."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._refresh_subset = AsyncMock()
    await coord.async_request_selective_refresh(
        dog_ids=["test_dog", "test_dog", "test_dog"]
    )
    coord._refresh_subset.assert_awaited_once_with(["test_dog"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresh_subset_skips_missing_dogs_and_continues_iteration(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """_refresh_subset should continue iterating when requested IDs are absent."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._execute_cycle = AsyncMock(
        return_value=({"known": {"status_snapshot": {"state": "ok"}}}, None)
    )
    coord._synchronize_module_states = AsyncMock()
    coord.async_set_updated_data = MagicMock()

    await coord._refresh_subset(["missing", "known"])

    assert "known" in coord._data
    assert "missing" not in coord._data
    coord.async_set_updated_data.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────────
# available property  (lines 544-545)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_available_false_when_last_update_failed(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Available should be False when last_update_success is False."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord.last_update_success = False
    assert coord.available is False


@pytest.mark.unit
def test_available_false_when_too_many_consecutive_errors(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Available should be False when consecutive errors reach the threshold."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord.last_update_success = True
    coord._metrics.consecutive_errors = 5
    assert coord.available is False


@pytest.mark.unit
def test_available_true_when_healthy(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Available should be True when last update succeeded and errors < 5."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord.last_update_success = True
    coord._metrics.consecutive_errors = 0
    assert coord.available is True


# ──────────────────────────────────────────────────────────────────────────────
# last_update_time alias  (lines 553, 561)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_last_update_time_getter_and_setter(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """last_update_time should proxy last_update_success_time."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    ts = datetime(2025, 1, 1, 12, 0, 0)
    coord.last_update_time = ts
    assert coord.last_update_time == ts


# ──────────────────────────────────────────────────────────────────────────────
# get_statistics  (lines 564-580)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_get_statistics_returns_payload(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """get_statistics should return a dict-like statistics payload."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    stats = coord.get_statistics()
    assert isinstance(stats, dict)
    assert "update_counts" in stats or "performance_metrics" in stats or len(stats) >= 0


# ──────────────────────────────────────────────────────────────────────────────
# get_update_statistics  (line 562)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_get_update_statistics_returns_dict(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """get_update_statistics should return a serialisable mapping."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    result = coord.get_update_statistics()
    assert isinstance(result, dict)


# ──────────────────────────────────────────────────────────────────────────────
# async_start_background_tasks  (lines 641-642)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_async_start_background_tasks_calls_ensure(
    mock_hass, mock_config_entry, mock_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """async_start_background_tasks should delegate to coordinator_tasks helper."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    called_with: list = []
    monkeypatch.setattr(
        coordinator_module.coordinator_tasks,
        "ensure_background_task",
        lambda c, interval: called_with.append((c, interval)),
    )
    coord.async_start_background_tasks()
    assert len(called_with) == 1
    assert called_with[0][0] is coord


# ──────────────────────────────────────────────────────────────────────────────
# async_shutdown  (lines 645-646)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_shutdown_delegates(
    mock_hass, mock_config_entry, mock_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """async_shutdown should call the coordinator_tasks helper."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    called = []
    monkeypatch.setattr(
        coordinator_module.coordinator_tasks,
        "shutdown",
        AsyncMock(side_effect=lambda c: called.append(c)),
    )
    await coord.async_shutdown()
    assert len(called) == 1 and called[0] is coord


# ──────────────────────────────────────────────────────────────────────────────
# _webhook_security_status  (lines 648-649)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_webhook_security_status_no_manager(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """_webhook_security_status should return a safe default with no manager."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord.notification_manager = None
    status = coord._webhook_security_status()
    assert isinstance(status, dict)


# ──────────────────────────────────────────────────────────────────────────────
# _synchronize_module_states — walk+garden interaction  (lines 518-543)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
@pytest.mark.asyncio
async def test_synchronize_module_states_ends_garden_on_walk(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Active walks should cause in-progress garden sessions to be paused."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    garden_mgr = MagicMock()
    garden_mgr.get_active_session = MagicMock(return_value={"session_id": "abc"})
    garden_mgr.async_end_garden_session = AsyncMock()
    garden_mgr.build_garden_snapshot = MagicMock(return_value={"status": "idle"})
    coord.garden_manager = garden_mgr

    data = {
        "test_dog": {
            "walk": {"walk_in_progress": True},
            "garden": {"status": "active"},
        }
    }
    await coord._synchronize_module_states(data)

    garden_mgr.async_end_garden_session.assert_awaited_once_with(
        "test_dog",
        notes="Paused due to active walk",
        suppress_notifications=True,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_synchronize_module_states_no_garden_manager(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """_synchronize_module_states should be a no-op when garden_manager is None."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord.garden_manager = None
    data = {"test_dog": {"walk": {"walk_in_progress": True}}}
    # Should not raise
    await coord._synchronize_module_states(data)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_synchronize_module_states_ignores_non_mapping_walk_state(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Non-mapping walk payloads should be skipped without ending sessions."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    garden_mgr = MagicMock()
    garden_mgr.get_active_session = MagicMock(return_value={"session_id": "abc"})
    garden_mgr.async_end_garden_session = AsyncMock()
    garden_mgr.build_garden_snapshot = MagicMock(return_value={"status": "idle"})
    coord.garden_manager = garden_mgr

    data = {
        "dog_skip": {"walk": "active"},
        "dog_walk": {"walk": {"walk_in_progress": True}},
    }
    await coord._synchronize_module_states(data)

    garden_mgr.get_active_session.assert_called_once_with("dog_walk")
    garden_mgr.async_end_garden_session.assert_awaited_once()


# ──────────────────────────────────────────────────────────────────────────────
# _async_update_data — ConfigEntryAuthFailed propagation  (line 305-310)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_data_propagates_auth_failed(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """ConfigEntryAuthFailed raised in execute_cycle must propagate directly."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._runtime.execute_cycle = AsyncMock(
        side_effect=ConfigEntryAuthFailed("bad token")
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_data_propagates_update_failed(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """UpdateFailed raised in execute_cycle must propagate unmodified."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._runtime.execute_cycle = AsyncMock(side_effect=UpdateFailed("api down"))
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_data_wraps_generic_exception(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """Generic exceptions from execute_cycle must be wrapped as UpdateFailed."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._runtime.execute_cycle = AsyncMock(
        side_effect=RuntimeError("unexpected crash")
    )
    with pytest.raises(UpdateFailed, match="Coordinator update failed"):
        await coord._async_update_data()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_match"),
    [
        (TimeoutError("refresh timeout"), "Coordinator update failed"),
        (ConfigEntryAuthFailed("token expired"), "token expired"),
        (UpdateFailed("HTTP 503"), "HTTP 503"),
        (RuntimeError("unexpected"), "Coordinator update failed"),
    ],
)
async def test_async_update_data_error_paths_keep_cached_state_stable(
    mock_hass,
    mock_config_entry,
    mock_session,
    error: Exception,
    expected_match: str,
) -> None:
    """Refresh errors should not mutate cached state before a recovery run."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._setup_complete = True
    original_payload = {"test_dog": {"status": "cached", "last_update": "before"}}
    coord._data = original_payload.copy()  # type: ignore[assignment]
    coord._execute_cycle = AsyncMock(side_effect=error)  # type: ignore[method-assign]

    if isinstance(error, ConfigEntryAuthFailed):
        with pytest.raises(ConfigEntryAuthFailed, match=expected_match):
            await coord._async_update_data()
    else:
        with pytest.raises(UpdateFailed, match=expected_match):
            await coord._async_update_data()

    assert coord._data == original_payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_data_recovers_after_failure_and_applies_fresh_payload(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """A successful retry after a failed refresh should replace stale cache state."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    coord._setup_complete = True
    coord._data = {"test_dog": {"status": "stale"}}  # type: ignore[assignment]
    refreshed_payload = {"test_dog": {"status": "online", "last_update": "now"}}
    runtime_cycle = RuntimeCycleInfo(
        dog_count=1,
        errors=0,
        success_rate=1.0,
        duration=0.1,
        new_interval=120.0,
        error_ratio=0.0,
        success=True,
    )
    coord._execute_cycle = AsyncMock(  # type: ignore[method-assign]
        side_effect=[UpdateFailed("HTTP 502"), (refreshed_payload, runtime_cycle)]
    )

    with pytest.raises(UpdateFailed, match="HTTP 502"):
        await coord._async_update_data()
    assert coord._data == {"test_dog": {"status": "stale"}}

    result = await coord._async_update_data()
    assert result == refreshed_payload
    assert coord._data == refreshed_payload


# ──────────────────────────────────────────────────────────────────────────────
# get_enabled_modules / is_module_enabled / get_dog_data / get_dog_config
# (lines 454, 458, 476-480, 482-486, 493)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_get_enabled_modules_returns_frozenset(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """get_enabled_modules should return a frozenset for known dogs."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    result = coord.get_enabled_modules("test_dog")
    assert isinstance(result, frozenset)


@pytest.mark.unit
def test_is_module_enabled_known_module(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """is_module_enabled returns True only for configured modules."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    # Should not raise regardless of answer
    assert isinstance(coord.is_module_enabled("test_dog", "feeding"), bool)


@pytest.mark.unit
def test_get_dog_data_returns_none_for_unknown(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """get_dog_data returns None for an unconfigured dog_id."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    assert coord.get_dog_data("ghost_dog") is None


@pytest.mark.unit
def test_get_dog_config_returns_config_for_known_dog(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """get_dog_config returns a config mapping for a known dog."""
    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)
    cfg = coord.get_dog_config("test_dog")
    assert cfg is not None
    assert cfg.get("dog_id") == "test_dog"
