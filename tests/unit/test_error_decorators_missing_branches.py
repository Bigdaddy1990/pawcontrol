"""Additional branch coverage tests for ``error_decorators``."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.pawcontrol.error_decorators import (
    handle_errors,
    map_to_repair_issue,
    require_coordinator_data,
    retry_on_error,
    validate_and_handle,
    validate_dog_exists,
)
from custom_components.pawcontrol.exceptions import PawControlError, ValidationError


@pytest.mark.unit
def test_validate_dog_exists_requires_instance_for_keyword_only_dog_id() -> None:
    """Cover branch where dog_id is present but positional args are absent."""

    @validate_dog_exists()
    def _handler(*, dog_id: str) -> str:
        return dog_id

    with pytest.raises(PawControlError, match="instance method"):
        _handler(dog_id="luna")


@pytest.mark.asyncio
async def test_handle_errors_async_wrapper_reraises_validation_error() -> None:
    """Validation errors should reraise by default in the async wrapper."""

    @handle_errors()
    async def _failing() -> str:
        raise ValidationError(field="dog_id", constraint="required")

    with pytest.raises(ValidationError):
        await _failing()


@pytest.mark.asyncio
async def test_map_to_repair_issue_async_direct_return_and_coordinator_hass() -> None:
    """Exercise async direct return and coordinator.hass issue lookup branches."""
    with patch(
        "custom_components.pawcontrol.error_decorators.inspect.iscoroutinefunction",
        return_value=True,
    ):
        wrapped = map_to_repair_issue("ok_issue")(lambda: "ok")
    assert await wrapped() == "ok"

    class _WithCoordinator:
        def __init__(self) -> None:
            self.coordinator = SimpleNamespace(hass=object())

        @map_to_repair_issue("coord_issue")
        async def failing(self) -> None:
            raise PawControlError("boom", error_code="coord")

    with (
        patch(
            "custom_components.pawcontrol.error_decorators.issue_registry.async_create_issue"
        ) as create_issue,
        pytest.raises(PawControlError),
    ):
        await _WithCoordinator().failing()

    create_issue.assert_called_once()


@pytest.mark.unit
def test_map_to_repair_issue_sync_uses_coordinator_hass_branch() -> None:
    """Cover sync fallback to ``instance.coordinator.hass``."""

    class _WithCoordinator:
        def __init__(self) -> None:
            self.coordinator = SimpleNamespace(hass=object())

        @map_to_repair_issue("coord_issue_sync")
        def failing(self) -> None:
            raise PawControlError("boom", error_code="coord_sync")

    with (
        patch(
            "custom_components.pawcontrol.error_decorators.issue_registry.async_create_issue"
        ) as create_issue,
        pytest.raises(PawControlError),
    ):
        _WithCoordinator().failing()

    create_issue.assert_called_once()


@pytest.mark.asyncio
async def test_retry_on_error_zero_attempts_returns_none() -> None:
    """When max_attempts=0 both wrappers should fall through to ``return None``."""

    @retry_on_error(max_attempts=0)
    async def _async_zero() -> str:
        return "never"

    @retry_on_error(max_attempts=0)
    def _sync_zero() -> str:
        return "never"

    assert await _async_zero() is None
    assert _sync_zero() is None


@pytest.mark.asyncio
async def test_retry_on_error_async_wrapper_direct_non_awaitable_return() -> None:
    """Force async wrapper for a sync callable and hit direct return path."""
    with patch(
        "custom_components.pawcontrol.error_decorators.inspect.iscoroutinefunction",
        return_value=True,
    ):
        wrapped = retry_on_error()(lambda: "done")

    assert await wrapped() == "done"


@pytest.mark.unit
def test_require_coordinator_data_explicit_guard_branches() -> None:
    """Cover missing-args and missing-coordinator-attribute guard branches."""

    @require_coordinator_data()
    def _needs_data() -> str:
        return "ok"

    with pytest.raises(PawControlError, match="instance method"):
        _needs_data()

    class _NoCoordinatorAttr:
        @require_coordinator_data()
        def _needs_data(self) -> str:
            return "ok"

    with pytest.raises(PawControlError, match="coordinator attribute"):
        _NoCoordinatorAttr()._needs_data()


@pytest.mark.asyncio
async def test_handle_errors_async_skips_logging_when_disabled_for_pawcontrol_errors() -> None:
    """Async wrapper should bypass error logging when ``log_errors`` is disabled."""

    @handle_errors(
        log_errors=False,
        default_return="fallback",
        reraise_critical=False,
        reraise_validation_errors=False,
    )
    async def _failing() -> str:
        raise PawControlError("boom", error_code="pc_async")

    with patch("custom_components.pawcontrol.error_decorators._LOGGER.error") as log_error:
        assert await _failing() == "fallback"
    log_error.assert_not_called()


@pytest.mark.asyncio
async def test_handle_errors_async_skips_exception_logging_when_disabled() -> None:
    """Async wrapper should bypass exception logging when ``log_errors`` is disabled."""

    @handle_errors(
        log_errors=False,
        default_return="fallback",
        reraise_critical=False,
    )
    async def _failing() -> str:
        raise RuntimeError("boom")

    with patch(
        "custom_components.pawcontrol.error_decorators._LOGGER.exception"
    ) as log_exception:
        assert await _failing() == "fallback"
    log_exception.assert_not_called()


@pytest.mark.unit
def test_handle_errors_sync_skips_logging_when_disabled_for_pawcontrol_errors() -> None:
    """Sync wrapper should bypass error logging when ``log_errors`` is disabled."""

    @handle_errors(
        log_errors=False,
        default_return="fallback",
        reraise_critical=False,
        reraise_validation_errors=False,
    )
    def _failing() -> str:
        raise PawControlError("boom", error_code="pc_sync")

    with patch("custom_components.pawcontrol.error_decorators._LOGGER.error") as log_error:
        assert _failing() == "fallback"
    log_error.assert_not_called()


@pytest.mark.unit
def test_handle_errors_sync_skips_exception_logging_when_disabled() -> None:
    """Sync wrapper should bypass exception logging when ``log_errors`` is disabled."""

    @handle_errors(
        log_errors=False,
        default_return="fallback",
        reraise_critical=False,
    )
    def _failing() -> str:
        raise RuntimeError("boom")

    with patch(
        "custom_components.pawcontrol.error_decorators._LOGGER.exception"
    ) as log_exception:
        assert _failing() == "fallback"
    log_exception.assert_not_called()


@pytest.mark.asyncio
async def test_map_to_repair_issue_async_without_args_skips_issue_creation() -> None:
    """Async mapping should skip repair issue creation when no instance args exist."""

    @map_to_repair_issue("no_hass_async")
    async def _failing() -> None:
        raise PawControlError("boom", error_code="no_hass_async")

    with (
        patch(
            "custom_components.pawcontrol.error_decorators.issue_registry.async_create_issue"
        ) as create_issue,
        pytest.raises(PawControlError),
    ):
        await _failing()

    create_issue.assert_not_called()


@pytest.mark.asyncio
async def test_map_to_repair_issue_async_without_hass_or_coordinator() -> None:
    """Async mapping should skip issue creation when instance lacks hass bindings."""

    class _PlainService:
        @map_to_repair_issue("no_hass_instance")
        async def _failing(self) -> None:
            raise PawControlError("boom", error_code="no_hass_instance")

    with (
        patch(
            "custom_components.pawcontrol.error_decorators.issue_registry.async_create_issue"
        ) as create_issue,
        pytest.raises(PawControlError),
    ):
        await _PlainService()._failing()

    create_issue.assert_not_called()


@pytest.mark.unit
def test_map_to_repair_issue_sync_without_args_skips_issue_creation() -> None:
    """Sync mapping should skip repair issue creation when no instance args exist."""

    @map_to_repair_issue("no_hass_sync")
    def _failing() -> None:
        raise PawControlError("boom", error_code="no_hass_sync")

    with (
        patch(
            "custom_components.pawcontrol.error_decorators.issue_registry.async_create_issue"
        ) as create_issue,
        pytest.raises(PawControlError),
    ):
        _failing()

    create_issue.assert_not_called()


@pytest.mark.unit
def test_validate_and_handle_skips_optional_validators_when_disabled() -> None:
    """Composition should work when dog-id and GPS validators are both disabled."""

    @validate_and_handle(dog_id_param="", gps_coords=False)
    def _plain() -> str:
        return "ok"

    assert _plain() == "ok"
