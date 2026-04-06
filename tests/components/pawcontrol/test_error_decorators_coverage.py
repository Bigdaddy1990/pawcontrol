"""Coverage-focused tests for error and validation decorators."""

from dataclasses import dataclass
import inspect
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.pawcontrol.error_decorators import (
    create_repair_issue_from_exception,
    get_repair_issue_id,
    handle_errors,
    map_to_repair_issue,
    require_coordinator,
    require_coordinator_data,
    retry_on_error,
    validate_and_handle,
    validate_dog_exists,
    validate_gps_coordinates,
    validate_range,
)
from custom_components.pawcontrol.exceptions import (
    DogNotFoundError,
    ErrorCategory,
    ErrorSeverity,
    InvalidCoordinatesError,
    NetworkError,
    PawControlError,
    RateLimitError,
    ValidationError,
)


@dataclass(slots=True)
class _Coordinator:
    data: dict[str, Any]
    hass: Any = None
    last_update_success: bool = True


@dataclass(slots=True)
class _Service:
    coordinator: _Coordinator | None = None
    hass: Any = None


def test_validate_dog_exists_success_and_failures() -> None:
    """Dog validation decorator should enforce coordinator and dog-id checks."""

    class Handler:
        def __init__(self) -> None:
            self.coordinator = _Coordinator(data={"luna": {"name": "Luna"}})

        @validate_dog_exists()
        def get(self, dog_id: str) -> str:
            return dog_id

    assert Handler().get("luna") == "luna"

    with pytest.raises(ValidationError):
        Handler().get()  # type: ignore[call-arg]

    with pytest.raises(DogNotFoundError):
        Handler().get("buddy")

    @validate_dog_exists()
    def _no_instance(dog_id: str) -> str:
        return dog_id

    with pytest.raises(PawControlError, match="coordinator attribute"):
        _no_instance("luna")

    class NoCoordinator:
        @validate_dog_exists()
        def get(self, dog_id: str) -> str:
            return dog_id

    with pytest.raises(PawControlError, match="coordinator"):
        NoCoordinator().get("luna")


def test_validate_gps_coordinates_and_validate_range() -> None:
    """Coordinate and range validators should reject bad inputs and pass valid ones."""

    @validate_gps_coordinates()
    def _coords(latitude: float, longitude: float) -> tuple[float, float]:
        return latitude, longitude

    assert _coords(47.0, 8.0) == (47.0, 8.0)

    with pytest.raises(InvalidCoordinatesError):
        _coords(91, 8)
    with pytest.raises(InvalidCoordinatesError):
        _coords(47, -181)
    with pytest.raises(TypeError):
        _coords("47", 8)  # type: ignore[arg-type]
    with pytest.raises(InvalidCoordinatesError):
        _coords(latitude=47)  # type: ignore[call-arg]

    @validate_range("age", 1, 20, field_name="dog_age")
    def _age(age: int) -> int:
        return age

    assert _age(4) == 4
    with pytest.raises(ValidationError, match="required"):
        _age()  # type: ignore[call-arg]
    with pytest.raises(ValidationError, match="numeric"):
        _age("young")  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="between"):
        _age(99)


def test_handle_errors_sync_branches() -> None:
    """handle_errors should map known errors and wrap unknown sync errors."""

    @handle_errors(default_return="fallback", reraise_validation_errors=False)
    def _validation_error() -> str:
        raise ValidationError(field="name", constraint="required")

    assert _validation_error() == "fallback"

    @handle_errors(default_return="fallback", reraise_critical=True)
    def _critical_error() -> str:
        raise PawControlError("boom", severity=ErrorSeverity.CRITICAL)

    with pytest.raises(PawControlError, match="boom"):
        _critical_error()

    @handle_errors(default_return="fallback", reraise_critical=False)
    def _unexpected() -> str:
        raise RuntimeError("unexpected")

    assert _unexpected() == "fallback"

    @handle_errors(
        default_return="never",
        reraise_critical=True,
        error_category=ErrorCategory.NETWORK,
    )
    def _unexpected_critical() -> str:
        raise RuntimeError("network broke")

    with pytest.raises(PawControlError) as err:
        _unexpected_critical()
    assert err.value.category is ErrorCategory.NETWORK


@pytest.mark.asyncio
async def test_handle_errors_async_branches() -> None:
    """Async wrapper should await awaitables and apply configured fallback behavior."""

    @handle_errors(default_return="ok")
    async def _works() -> str:
        return "ok"

    assert await _works() == "ok"

    @handle_errors(default_return="fallback", reraise_validation_errors=False)
    async def _known_error() -> str:
        raise ValidationError(field="age", constraint="invalid")

    assert await _known_error() == "fallback"

    @handle_errors(default_return="fallback", reraise_critical=False)
    async def _unknown_error() -> str:
        raise RuntimeError("boom")

    assert await _unknown_error() == "fallback"


@pytest.mark.asyncio
async def test_map_to_repair_issue_sync_and_async_paths() -> None:
    """Repair issue mapping should report through hass or coordinator when present."""
    hass = SimpleNamespace()
    service = _Service(hass=hass)
    coordinator_service = _Service(
        coordinator=_Coordinator(data={}, hass=hass),
        hass=hass,
    )

    with patch(
        "custom_components.pawcontrol.error_decorators.issue_registry.async_create_issue"
    ) as create_issue:

        @map_to_repair_issue("dog_problem", severity="error")
        def _sync_fail(instance: _Service) -> None:
            raise PawControlError("sync failed", error_code="sync_code")

        with pytest.raises(PawControlError):
            _sync_fail(service)

        create_issue.assert_called_once()
        kwargs = create_issue.call_args.kwargs
        assert kwargs["severity"] == "error"
        assert kwargs["translation_placeholders"]["error_code"] == "sync_code"

    with patch(
        "custom_components.pawcontrol.error_decorators.issue_registry.async_create_issue"
    ) as create_issue:

        @map_to_repair_issue("coord_problem")
        async def _async_fail(instance: _Service) -> None:
            raise PawControlError("async failed", error_code="async_code")

        with pytest.raises(PawControlError):
            await _async_fail(coordinator_service)

        create_issue.assert_called_once()

    @map_to_repair_issue("no_hass")
    def _sync_no_hass(instance: _Service) -> None:
        raise PawControlError("no hass", error_code="code")

    with patch(
        "custom_components.pawcontrol.error_decorators.issue_registry.async_create_issue"
    ) as create_issue:
        with pytest.raises(PawControlError):
            _sync_no_hass(_Service())
        create_issue.assert_not_called()


@pytest.mark.asyncio
async def test_retry_on_error_async_and_sync_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry decorator should backoff, retry configured errors, and stop on success."""
    async_sleep = AsyncMock()
    monkeypatch.setattr(
        "custom_components.pawcontrol.error_decorators.asyncio.sleep", async_sleep
    )

    attempts = {"count": 0}

    @retry_on_error(max_attempts=3, delay=0.1)
    async def _flaky_async() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise NetworkError("temporary")
        return "done"

    assert await _flaky_async() == "done"
    assert attempts["count"] == 3
    assert async_sleep.await_count == 2

    with pytest.raises(RateLimitError):

        @retry_on_error(max_attempts=2, delay=0.01)
        async def _always_fail_async() -> None:
            raise RateLimitError("limited")

        await _always_fail_async()

    sleep_calls: list[float] = []
    monkeypatch.setattr(
        "time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    sync_attempts = {"count": 0}

    @retry_on_error(max_attempts=2, delay=0.2)
    def _flaky_sync() -> str:
        sync_attempts["count"] += 1
        if sync_attempts["count"] < 2:
            raise NetworkError("temp")
        return "ok"

    assert _flaky_sync() == "ok"
    assert sleep_calls == [0.2]


def test_validate_dog_exists_rejects_keyword_only_calls_without_instance() -> None:
    """Keyword-only invocation should hit the no-instance guard branch."""

    @validate_dog_exists()
    def _no_instance(dog_id: str) -> str:
        return dog_id

    with pytest.raises(PawControlError, match="instance method"):
        _no_instance(dog_id="luna")


@pytest.mark.asyncio
async def test_handle_errors_async_wrapper_direct_return_and_reraise_paths() -> None:
    """Cover direct return path and re-raise branches in async wrapper."""

    with patch(
        "custom_components.pawcontrol.error_decorators.inspect.iscoroutinefunction",
        return_value=True,
    ):
        direct_wrapper = handle_errors()(lambda: "direct")
    assert await direct_wrapper() == "direct"

    @handle_errors(default_return="fallback", reraise_validation_errors=True)
    async def _raises_validation() -> str:
        raise ValidationError(field="dog_id", constraint="required")

    with pytest.raises(ValidationError):
        await _raises_validation()

    @handle_errors(default_return="fallback", reraise_critical=True)
    async def _raises_unexpected() -> str:
        raise RuntimeError("unexpected")

    with pytest.raises(PawControlError, match="unexpected"):
        await _raises_unexpected()


@pytest.mark.asyncio
async def test_map_to_repair_issue_coordinator_hass_and_direct_return_paths() -> None:
    """Exercise coordinator.hass resolution and non-awaitable async return path."""

    @dataclass(slots=True)
    class _CoordinatorOnly:
        coordinator: _Coordinator

    coordinator_only = _CoordinatorOnly(
        coordinator=_Coordinator(data={}, hass=SimpleNamespace()),
    )

    with patch(
        "custom_components.pawcontrol.error_decorators.issue_registry.async_create_issue"
    ) as create_issue:

        @map_to_repair_issue("coord_async")
        async def _async_fail(instance: _CoordinatorOnly) -> None:
            raise PawControlError("async", error_code="coord_async")

        with pytest.raises(PawControlError):
            await _async_fail(coordinator_only)

        create_issue.assert_called_once()

    with patch(
        "custom_components.pawcontrol.error_decorators.issue_registry.async_create_issue"
    ) as create_issue:

        @map_to_repair_issue("coord_sync")
        def _sync_fail(instance: _CoordinatorOnly) -> None:
            raise PawControlError("sync", error_code="coord_sync")

        with pytest.raises(PawControlError):
            _sync_fail(coordinator_only)

        create_issue.assert_called_once()

    with patch(
        "custom_components.pawcontrol.error_decorators.inspect.iscoroutinefunction",
        return_value=True,
    ):
        direct_wrapper = map_to_repair_issue("direct")(lambda: "ok")

    assert await direct_wrapper() == "ok"


@pytest.mark.asyncio
async def test_retry_on_error_direct_async_return_and_sync_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover direct async return branch and sync exhaustion fallback path."""

    with patch(
        "custom_components.pawcontrol.error_decorators.inspect.iscoroutinefunction",
        return_value=True,
    ):
        direct_wrapper = retry_on_error(max_attempts=1)(lambda: "immediate")
    assert await direct_wrapper() == "immediate"

    monkeypatch.setattr("time.sleep", lambda _: None)

    @retry_on_error(max_attempts=2, delay=0.01, exceptions=(NetworkError,))
    def _always_fail_sync() -> None:
        raise NetworkError("offline")

    with pytest.raises(NetworkError):
        _always_fail_sync()


@pytest.mark.asyncio
async def test_retry_on_error_zero_attempts_returns_none() -> None:
    """Zero-attempt configuration should short-circuit and return ``None``."""

    @retry_on_error(max_attempts=0)
    async def _async_never_called() -> str:
        return "never"

    @retry_on_error(max_attempts=0)
    def _sync_never_called() -> str:
        return "never"

    assert await _async_never_called() is None
    assert _sync_never_called() is None


def test_require_coordinator_and_data_guards() -> None:
    """Coordinator guard decorators should enforce runtime coordinator state."""

    @require_coordinator
    def _needs_coordinator(service: _Service) -> str:
        return "ok"

    with pytest.raises(PawControlError, match="instance method"):
        _needs_coordinator()  # type: ignore[call-arg]
    with pytest.raises(PawControlError, match="Coordinator is required"):
        _needs_coordinator(_Service())
    assert _needs_coordinator(_Service(coordinator=_Coordinator(data={}))) == "ok"

    @dataclass(slots=True)
    class Handler:
        coordinator: _Coordinator | None

        @require_coordinator_data()
        def _require_data(self) -> str:
            return "ready"

        @require_coordinator_data(allow_partial=True)
        def _allow_partial(self) -> str:
            return "partial-ready"

    with pytest.raises(PawControlError, match="Coordinator data not available"):
        Handler(_Coordinator(data={}))._require_data()
    with pytest.raises(PawControlError, match="last update failed"):
        Handler(
            _Coordinator(data={"luna": {}}, last_update_success=False)
        )._require_data()
    assert (
        Handler(
            _Coordinator(data={"luna": {}}, last_update_success=False)
        )._allow_partial()
        == "partial-ready"
    )

    with pytest.raises(PawControlError, match="instance method"):

        @require_coordinator_data()
        def _no_instance() -> str:
            return "never"

        _no_instance()

    class _NoCoordinator:
        @require_coordinator_data()
        def run(self) -> str:
            return "never"

    with pytest.raises(PawControlError, match="coordinator attribute"):
        _NoCoordinator().run()


def test_validate_and_handle_combines_decorators() -> None:
    """Combined decorator should validate dog and GPS input before executing body."""

    class Handler:
        def __init__(self) -> None:
            self.coordinator = _Coordinator(data={"luna": {}})

        @validate_and_handle(dog_id_param="dog_id", gps_coords=True)
        def update(self, dog_id: str, latitude: float, longitude: float) -> str:
            return f"{dog_id}:{latitude}:{longitude}"

    handler = Handler()
    assert handler.update("luna", 1.0, 2.0) == "luna:1.0:2.0"

    with pytest.raises(DogNotFoundError):
        handler.update("unknown", 1.0, 2.0)
    with pytest.raises(InvalidCoordinatesError):
        handler.update("luna", 91.0, 2.0)


@pytest.mark.asyncio
async def test_repair_issue_helpers_cover_mappings() -> None:
    """Repair-issue helpers should map known errors and fallback for unknown codes."""
    assert get_repair_issue_id(DogNotFoundError("luna", ["buddy"])) == "dog_not_found"
    assert get_repair_issue_id(PawControlError("other", error_code="x")) is None

    hass = SimpleNamespace()
    with patch(
        "custom_components.pawcontrol.error_decorators.issue_registry.async_create_issue"
    ) as create_issue:
        await create_repair_issue_from_exception(
            hass,
            PawControlError(
                "boom",
                error_code="custom",
                severity=ErrorSeverity.CRITICAL,
                recovery_suggestions=["retry"],
                technical_details="trace",
            ),
            is_fixable=False,
        )

        args = create_issue.call_args.args
        kwargs = create_issue.call_args.kwargs
        assert args[2] == "error_custom"
        assert kwargs["is_fixable"] is False
        assert kwargs["translation_placeholders"]["details"] == "trace"
        assert "retry" in kwargs["translation_placeholders"]["suggestions"]


def test_validate_dog_exists_without_instance_args_raises() -> None:
    """Calling with keyword dog_id and no instance should fail with instance error."""

    @validate_dog_exists()
    def _no_instance(dog_id: str) -> str:
        return dog_id

    with pytest.raises(PawControlError, match="instance method"):
        _no_instance(dog_id="luna")


@pytest.mark.asyncio
async def test_async_wrappers_handle_non_awaitable_marked_coroutines() -> None:
    """Marked coroutine functions returning plain values should use direct return path."""

    @inspect.markcoroutinefunction
    def _plain_handle() -> str:
        return "ok"

    @inspect.markcoroutinefunction
    def _plain_repair() -> str:
        return "mapped"

    @inspect.markcoroutinefunction
    def _plain_retry() -> str:
        return "retry-ok"

    assert await handle_errors()(_plain_handle)() == "ok"
    assert await map_to_repair_issue("plain_issue")(_plain_repair)() == "mapped"
    assert await retry_on_error()(_plain_retry)() == "retry-ok"


@pytest.mark.asyncio
async def test_handle_errors_async_reraise_paths() -> None:
    """Async handler should reraise validation and wrapped critical errors when enabled."""

    @handle_errors(default_return="fallback")
    async def _raise_validation() -> str:
        raise ValidationError(field="age", constraint="invalid")

    with pytest.raises(ValidationError):
        await _raise_validation()

    @handle_errors(default_return="fallback", reraise_critical=True)
    async def _raise_runtime() -> str:
        raise RuntimeError("boom")

    with pytest.raises(PawControlError, match="boom"):
        await _raise_runtime()


@pytest.mark.asyncio
async def test_map_to_repair_issue_uses_coordinator_hass_fallback() -> None:
    """When ``hass`` is absent, decorator should read hass from ``coordinator``."""

    service = SimpleNamespace(coordinator=_Coordinator(data={}, hass=SimpleNamespace()))

    with patch(
        "custom_components.pawcontrol.error_decorators.issue_registry.async_create_issue"
    ) as create_issue:

        @map_to_repair_issue("coord_only")
        async def _async_fail(instance: Any) -> None:
            raise PawControlError("async failed", error_code="async_code")

        with pytest.raises(PawControlError):
            await _async_fail(service)

        create_issue.assert_called_once()

    with patch(
        "custom_components.pawcontrol.error_decorators.issue_registry.async_create_issue"
    ) as create_issue:

        @map_to_repair_issue("coord_only_sync")
        def _sync_fail(instance: Any) -> None:
            raise PawControlError("sync failed", error_code="sync_code")

        with pytest.raises(PawControlError):
            _sync_fail(service)

        create_issue.assert_called_once()


@pytest.mark.asyncio
async def test_retry_on_error_zero_attempts_returns_none_and_sync_error_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry wrapper should return None for zero attempts and re-raise final sync errors."""

    @retry_on_error(max_attempts=0)
    async def _never_called_async() -> str:
        raise AssertionError("should not execute")

    assert await _never_called_async() is None

    @retry_on_error(max_attempts=0)
    def _never_called_sync() -> str:
        raise AssertionError("should not execute")

    assert _never_called_sync() is None

    monkeypatch.setattr("time.sleep", lambda _: None)

    @retry_on_error(max_attempts=1, delay=0.01)
    def _always_fail_sync() -> None:
        raise NetworkError("final")

    with pytest.raises(NetworkError):
        _always_fail_sync()


def test_require_coordinator_data_instance_guards() -> None:
    """Decorator should reject missing instance args and missing coordinator attribute."""

    @require_coordinator_data()
    def _guarded(service: Any) -> str:
        return "ok"

    with pytest.raises(PawControlError, match="instance method"):
        _guarded()  # type: ignore[call-arg]

    with pytest.raises(PawControlError, match="coordinator attribute"):
        _guarded(SimpleNamespace())
