"""Unit tests for error_decorators module.

Tests validation and error handling decorators including dog validation,
GPS validation, error handling, retry logic, and repair issue mapping.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pawcontrol.error_decorators import (
    EXCEPTION_TO_REPAIR_ISSUE,
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


class TestValidateDogExists:
    """Test validate_dog_exists decorator."""

    def test_validate_dog_exists_success(self) -> None:
        """Test decorator allows valid dog ID."""

        class MockInstance:
            def __init__(self) -> None:
                self.coordinator = MagicMock()
                self.coordinator.data = {"buddy": {"name": "Buddy"}}

            @validate_dog_exists()
            def get_dog(self, dog_id: str) -> str:
                return f"Dog {dog_id}"

        instance = MockInstance()
        result = instance.get_dog("buddy")
        assert result == "Dog buddy"

    def test_validate_dog_exists_failure(self) -> None:
        """Test decorator raises DogNotFoundError."""

        class MockInstance:
            def __init__(self) -> None:
                self.coordinator = MagicMock()
                self.coordinator.data = {}

            @validate_dog_exists()
            def get_dog(self, dog_id: str) -> str:
                return f"Dog {dog_id}"

        instance = MockInstance()
        with pytest.raises(DogNotFoundError):
            instance.get_dog("unknown")

    def test_validate_dog_exists_no_coordinator(self) -> None:
        """Test decorator fails without coordinator."""

        class MockInstance:
            @validate_dog_exists()
            def get_dog(self, dog_id: str) -> str:
                return f"Dog {dog_id}"

        instance = MockInstance()
        with pytest.raises(PawControlError):
            instance.get_dog("buddy")

    def test_validate_dog_exists_requires_dog_id_argument(self) -> None:
        """Test decorator raises validation error when dog id is missing."""

        class MockInstance:
            def __init__(self) -> None:
                self.coordinator = MagicMock()
                self.coordinator.data = {"buddy": {"name": "Buddy"}}

            @validate_dog_exists()
            def get_dog(self, dog_id: str | None = None) -> str:
                return f"Dog {dog_id}"

        with pytest.raises(ValidationError, match="Dog ID is required"):
            MockInstance().get_dog()


class TestValidateGPSCoordinates:
    """Test validate_gps_coordinates decorator."""

    def test_validate_gps_coordinates_valid(self) -> None:
        """Test decorator allows valid coordinates."""

        class MockInstance:
            @validate_gps_coordinates()
            def set_location(
                self, latitude: float, longitude: float
            ) -> tuple[float, float]:
                return (latitude, longitude)

        instance = MockInstance()
        result = instance.set_location(45.0, -122.0)
        assert result == (45.0, -122.0)

    def test_validate_gps_coordinates_invalid_latitude(self) -> None:
        """Test decorator raises on invalid latitude."""

        class MockInstance:
            @validate_gps_coordinates()
            def set_location(
                self, latitude: float, longitude: float
            ) -> tuple[float, float]:
                return (latitude, longitude)

        instance = MockInstance()
        with pytest.raises(InvalidCoordinatesError):
            instance.set_location(95.0, -122.0)

    def test_validate_gps_coordinates_invalid_longitude(self) -> None:
        """Test decorator raises on invalid longitude."""

        class MockInstance:
            @validate_gps_coordinates()
            def set_location(
                self, latitude: float, longitude: float
            ) -> tuple[float, float]:
                return (latitude, longitude)

        instance = MockInstance()
        with pytest.raises(InvalidCoordinatesError):
            instance.set_location(45.0, -200.0)

    def test_validate_gps_coordinates_boundary_values(self) -> None:
        """Test decorator allows boundary values."""

        class MockInstance:
            @validate_gps_coordinates()
            def set_location(
                self, latitude: float, longitude: float
            ) -> tuple[float, float]:
                return (latitude, longitude)

        instance = MockInstance()

        # Valid boundaries
        assert instance.set_location(90.0, 180.0) == (90.0, 180.0)
        assert instance.set_location(-90.0, -180.0) == (-90.0, -180.0)


class TestValidateRange:
    """Test validate_range decorator."""

    def test_validate_range_valid(self) -> None:
        """Test decorator allows value in range."""

        class MockInstance:
            @validate_range("weight", 0.5, 100.0)
            def set_weight(self, weight: float) -> float:
                return weight

        instance = MockInstance()
        assert instance.set_weight(50.0) == 50.0

    def test_validate_range_too_low(self) -> None:
        """Test decorator raises on value too low."""

        class MockInstance:
            @validate_range("weight", 0.5, 100.0)
            def set_weight(self, weight: float) -> float:
                return weight

        instance = MockInstance()
        with pytest.raises(PawControlError):
            instance.set_weight(0.1)

    def test_validate_range_too_high(self) -> None:
        """Test decorator raises on value too high."""

        class MockInstance:
            @validate_range("weight", 0.5, 100.0)
            def set_weight(self, weight: float) -> float:
                return weight

        instance = MockInstance()
        with pytest.raises(PawControlError):
            instance.set_weight(150.0)

    def test_validate_range_rejects_missing_and_non_numeric_values(self) -> None:
        """Test decorator raises for missing and non-numeric range inputs."""

        class MockInstance:
            @validate_range("weight", 0.5, 100.0, field_name="dog weight")
            def set_weight(self, weight: float | None = None) -> float | None:
                return weight

        instance = MockInstance()
        with pytest.raises(ValidationError, match="Value is required"):
            instance.set_weight()

        with pytest.raises(ValidationError, match="Must be numeric"):
            instance.set_weight("heavy")


class TestHandleErrors:
    """Test handle_errors decorator."""

    @pytest.mark.asyncio
    async def test_handle_errors_success(self) -> None:
        """Test decorator allows successful execution."""

        class MockInstance:
            @handle_errors()
            async def do_something(self) -> str:
                return "success"

        instance = MockInstance()
        result = await instance.do_something()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_handle_errors_catches_exception(self) -> None:
        """Test decorator catches and handles exceptions."""

        class MockInstance:
            @handle_errors(reraise_critical=False, default_return="default")
            async def do_something(self) -> str:
                raise RuntimeError("test error")

        instance = MockInstance()
        result = await instance.do_something()
        assert result == "default"

    @pytest.mark.asyncio
    async def test_handle_errors_reraises_critical(self) -> None:
        """Test decorator reraises critical errors."""

        class MockInstance:
            @handle_errors(reraise_critical=True)
            async def do_something(self) -> str:
                raise PawControlError(
                    "critical error",
                    severity=ErrorSeverity.CRITICAL,
                )

        instance = MockInstance()
        with pytest.raises(PawControlError):
            await instance.do_something()

    def test_handle_errors_sync_function(self) -> None:
        """Test decorator works with sync functions."""

        class MockInstance:
            @handle_errors(reraise_critical=False, default_return="default")
            def do_something(self) -> str:
                raise RuntimeError("test error")

        instance = MockInstance()
        result = instance.do_something()
        assert result == "default"


@pytest.mark.asyncio
async def test_handle_errors_forced_async_wrapper_with_immediate_return() -> None:
    """Force async wrapper for sync callables and cover direct return path."""
    with patch(
        "custom_components.pawcontrol.error_decorators.inspect.iscoroutinefunction",
        return_value=True,
    ):
        wrapped = handle_errors()(lambda: "direct-result")

    assert await wrapped() == "direct-result"


class TestRetryOnError:
    """Test retry_on_error decorator."""

    @pytest.mark.asyncio
    async def test_retry_on_error_success_first_try(self) -> None:
        """Test decorator succeeds on first try."""

        class MockInstance:
            call_count = 0

            @retry_on_error(max_attempts=3, delay=0.01)
            async def fetch_data(self) -> str:
                self.call_count += 1
                return "success"

        instance = MockInstance()
        result = await instance.fetch_data()
        assert result == "success"
        assert instance.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_error_succeeds_after_retry(self) -> None:
        """Test decorator retries and eventually succeeds."""

        class MockInstance:
            call_count = 0

            @retry_on_error(max_attempts=3, delay=0.01)
            async def fetch_data(self) -> str:
                self.call_count += 1
                if self.call_count < 3:
                    raise NetworkError("network error")
                return "success"

        instance = MockInstance()
        result = await instance.fetch_data()
        assert result == "success"
        assert instance.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_error_exhausts_attempts(self) -> None:
        """Test decorator exhausts retries and raises."""

        class MockInstance:
            call_count = 0

            @retry_on_error(max_attempts=3, delay=0.01)
            async def fetch_data(self) -> str:
                self.call_count += 1
                raise NetworkError("network error")

        instance = MockInstance()
        with pytest.raises(NetworkError):
            await instance.fetch_data()
        assert instance.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_error_only_retries_specified_exceptions(self) -> None:
        """Test decorator only retries specified exception types."""

        class MockInstance:
            call_count = 0

            @retry_on_error(
                max_attempts=3,
                delay=0.01,
                exceptions=(NetworkError, RateLimitError),
            )
            async def fetch_data(self) -> str:
                self.call_count += 1
                raise ValueError("not retryable")

        instance = MockInstance()
        with pytest.raises(ValueError):
            await instance.fetch_data()
        # Should fail immediately without retries
        assert instance.call_count == 1

    def test_retry_on_error_sync_function_retries_until_success(self) -> None:
        """Test sync retry wrapper retries and eventually returns success."""

        class MockInstance:
            call_count = 0

            @retry_on_error(max_attempts=3, delay=0.01, exceptions=(NetworkError,))
            def fetch_data(self) -> str:
                self.call_count += 1
                if self.call_count < 3:
                    raise NetworkError("network error")
                return "success"

        with patch("time.sleep") as sleep:
            instance = MockInstance()
            assert instance.fetch_data() == "success"

        assert instance.call_count == 3
        assert sleep.call_count == 2


class TestRequireCoordinator:
    """Test require_coordinator decorator."""

    def test_require_coordinator_success(self) -> None:
        """Test decorator allows access when coordinator exists."""

        class MockInstance:
            def __init__(self) -> None:
                self.coordinator = MagicMock()

            @require_coordinator
            def do_something(self) -> str:
                return "success"

        instance = MockInstance()
        result = instance.do_something()
        assert result == "success"

    def test_require_coordinator_failure(self) -> None:
        """Test decorator raises when coordinator missing."""

        class MockInstance:
            @require_coordinator
            def do_something(self) -> str:
                return "success"

        instance = MockInstance()
        with pytest.raises(PawControlError):
            instance.do_something()


class TestRequireCoordinatorData:
    """Test require_coordinator_data decorator."""

    def test_require_coordinator_data_success(self) -> None:
        """Test decorator allows access when data exists."""

        class MockInstance:
            def __init__(self) -> None:
                self.dog_id = "buddy"
                self.coordinator = MagicMock()
                self.coordinator.data = {"buddy": {"name": "Buddy"}}

            @require_coordinator_data()
            def get_data(self) -> str:
                return "success"

        instance = MockInstance()
        result = instance.get_data()
        assert result == "success"

    def test_require_coordinator_data_missing_dog(self) -> None:
        """Test decorator raises when dog data missing."""

        class MockInstance:
            def __init__(self) -> None:
                self.dog_id = "buddy"
                self.coordinator = MagicMock()
                self.coordinator.data = {}

            @require_coordinator_data()
            def get_data(self) -> str:
                return "success"

        instance = MockInstance()
        with pytest.raises(PawControlError):
            instance.get_data()

    def test_require_coordinator_data_allows_partial_updates(self) -> None:
        """allow_partial=True should bypass last_update_success checks."""

        class MockInstance:
            def __init__(self) -> None:
                self.coordinator = MagicMock()
                self.coordinator.data = {"buddy": {"name": "Buddy"}}
                self.coordinator.last_update_success = False

            @require_coordinator_data(allow_partial=True)
            def get_data(self) -> str:
                return "success"

        assert MockInstance().get_data() == "success"


class TestExceptionMapping:
    """Test exception to repair issue mapping."""

    def test_get_repair_issue_id(self) -> None:
        """Test getting repair issue ID for exceptions."""
        error = DogNotFoundError("buddy")
        issue_id = get_repair_issue_id(error)
        assert issue_id == "dog_not_found"

    def test_get_repair_issue_id_invalid_coordinates(self) -> None:
        """Test repair issue ID for invalid coordinates."""
        error = InvalidCoordinatesError(95.0, -122.0)
        issue_id = get_repair_issue_id(error)
        assert issue_id == "invalid_gps_coordinates"

    def test_get_repair_issue_id_unknown(self) -> None:
        """Test repair issue ID for unknown exception."""
        error = PawControlError("unknown error")
        issue_id = get_repair_issue_id(error)
        assert issue_id is None

    def test_exception_to_repair_issue_mapping_complete(self) -> None:
        """Test that mapping dictionary is complete."""
        assert len(EXCEPTION_TO_REPAIR_ISSUE) >= 8
        assert DogNotFoundError in EXCEPTION_TO_REPAIR_ISSUE
        assert InvalidCoordinatesError in EXCEPTION_TO_REPAIR_ISSUE
        assert NetworkError in EXCEPTION_TO_REPAIR_ISSUE


class TestCombinedDecorators:
    """Test combined decorator patterns."""

    def test_validate_and_handle_decorator(self) -> None:
        """Test combined validation and error handling."""

        class MockInstance:
            def __init__(self) -> None:
                self.coordinator = MagicMock()
                self.coordinator.data = {"buddy": {"name": "Buddy"}}

            @validate_and_handle(dog_id_param="dog_id", gps_coords=True)
            def update_location(
                self,
                dog_id: str,
                latitude: float,
                longitude: float,
            ) -> str:
                return f"{dog_id} at ({latitude}, {longitude})"

        instance = MockInstance()

        # Valid call
        result = instance.update_location("buddy", 45.0, -122.0)
        assert result == "buddy at (45.0, -122.0)"

        # Invalid dog
        with pytest.raises(DogNotFoundError):
            instance.update_location("unknown", 45.0, -122.0)

        # Invalid coordinates
        with pytest.raises(InvalidCoordinatesError):
            instance.update_location("buddy", 95.0, -122.0)


@pytest.mark.asyncio
async def test_create_repair_issue_from_exception() -> None:
    """Test creating repair issue from exception."""
    mock_hass = MagicMock()

    error = DogNotFoundError("buddy", ["max", "charlie"])

    with patch(
        "custom_components.pawcontrol.error_decorators.issue_registry"
    ) as mock_ir:
        await create_repair_issue_from_exception(mock_hass, error)
        mock_ir.async_create_issue.assert_called_once()


@pytest.mark.asyncio
async def test_map_to_repair_issue_creates_issue_and_reraises() -> None:
    """Decorator should create a repair issue when hass is available."""

    class MockInstance:
        def __init__(self) -> None:
            self.hass = AsyncMock()

        @map_to_repair_issue("network_issue", severity="error")
        async def perform(self) -> None:
            raise NetworkError("offline")

    with (
        patch("custom_components.pawcontrol.error_decorators.issue_registry") as ir,
        pytest.raises(NetworkError),
    ):
        await MockInstance().perform()

    ir.async_create_issue.assert_called_once()


def test_map_to_repair_issue_without_hass_only_reraises() -> None:
    """Decorator should not create issues when no hass context is available."""

    class MockInstance:
        @map_to_repair_issue("storage_issue")
        def perform(self) -> None:
            raise PawControlError("boom")

    with (
        patch("custom_components.pawcontrol.error_decorators.issue_registry") as ir,
        pytest.raises(PawControlError),
    ):
        MockInstance().perform()

    ir.async_create_issue.assert_not_called()


@pytest.mark.asyncio
async def test_map_to_repair_issue_forced_async_wrapper_immediate_return() -> None:
    """Force async wrapper branch for direct non-awaitable return values."""
    with patch(
        "custom_components.pawcontrol.error_decorators.inspect.iscoroutinefunction",
        return_value=True,
    ):
        wrapped = map_to_repair_issue("network_issue")(lambda: "ok")

    assert await wrapped() == "ok"


def test_require_coordinator_decorator_raises_without_instance_args() -> None:
    """Calling the wrapper without ``self`` should raise a decorator error."""

    @require_coordinator
    def _wrapped() -> str:
        return "ok"

    with pytest.raises(PawControlError, match="Decorator requires an instance method"):
        _wrapped()


def test_require_coordinator_data_raises_without_coordinator_attribute() -> None:
    """Decorator should reject instances that do not expose ``coordinator``."""

    class MockInstance:
        @require_coordinator_data()
        def get_data(self) -> str:
            return "success"

    with pytest.raises(PawControlError, match="coordinator attribute"):
        MockInstance().get_data()


def test_require_coordinator_data_rejects_failed_last_update() -> None:
    """allow_partial=False should enforce ``last_update_success`` guard."""

    class MockInstance:
        def __init__(self) -> None:
            self.coordinator = MagicMock()
            self.coordinator.data = {"buddy": {"name": "Buddy"}}
            self.coordinator.last_update_success = False

        @require_coordinator_data()
        def get_data(self) -> str:
            return "success"

    with pytest.raises(PawControlError, match="last update failed"):
        MockInstance().get_data()


@pytest.mark.asyncio
async def test_create_repair_issue_from_exception_uses_fallback_issue_id() -> None:
    """Unknown mapped exceptions should use the ``error_<code>`` fallback ID."""
    mock_hass = MagicMock()
    error = PawControlError("boom", error_code="custom_failure")

    with patch(
        "custom_components.pawcontrol.error_decorators.issue_registry"
    ) as mock_ir:
        await create_repair_issue_from_exception(mock_hass, error)

    issue_id = mock_ir.async_create_issue.call_args.args[2]
    assert issue_id == "error_custom_failure"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_validate_dog_exists_custom_param_name(self) -> None:
        """Test validate_dog_exists with custom parameter name."""

        class MockInstance:
            def __init__(self) -> None:
                self.coordinator = MagicMock()
                self.coordinator.data = {"buddy": {}}

            @validate_dog_exists(dog_id_param="custom_id")
            def get_dog(self, custom_id: str) -> str:
                return f"Dog {custom_id}"

        instance = MockInstance()
        result = instance.get_dog("buddy")
        assert result == "Dog buddy"

    def test_validate_gps_coordinates_custom_param_names(self) -> None:
        """Test validate_gps_coordinates with custom parameter names."""

        class MockInstance:
            @validate_gps_coordinates(latitude_param="lat", longitude_param="lon")
            def set_location(self, lat: float, lon: float) -> tuple[float, float]:
                return (lat, lon)

        instance = MockInstance()
        result = instance.set_location(45.0, -122.0)
        assert result == (45.0, -122.0)

    @pytest.mark.asyncio
    async def test_retry_on_error_with_backoff(self) -> None:
        """Test retry_on_error applies exponential backoff."""

        class MockInstance:
            call_count = 0
            call_times: list[float] = []

            @retry_on_error(max_attempts=3, delay=0.01, backoff=2.0)
            async def fetch_data(self) -> str:
                import time

                self.call_times.append(time.time())
                self.call_count += 1
                if self.call_count < 3:
                    raise NetworkError("network error")
                return "success"

        instance = MockInstance()
        result = await instance.fetch_data()
        assert result == "success"
        assert instance.call_count == 3


@pytest.mark.asyncio
async def test_retry_on_error_forced_async_wrapper_immediate_return() -> None:
    """Force async retry wrapper branch for direct non-awaitable return values."""
    with patch(
        "custom_components.pawcontrol.error_decorators.inspect.iscoroutinefunction",
        return_value=True,
    ):
        wrapped = retry_on_error(max_attempts=1)(lambda: "immediate")

    assert await wrapped() == "immediate"


def test_validate_dog_exists_raises_when_called_without_instance() -> None:
    """Decorator should reject usage without an instance ``self`` argument."""

    @validate_dog_exists()
    def _wrapped(dog_id: str) -> str:
        return dog_id

    with pytest.raises(PawControlError, match="coordinator attribute"):
        _wrapped("buddy")


def test_validate_gps_coordinates_rejects_missing_and_non_numeric_values() -> None:
    """Decorator should guard both missing and non-numeric coordinate payloads."""

    class MockInstance:
        @validate_gps_coordinates()
        def set_location(
            self,
            latitude: float | str | None = None,
            longitude: float | str | None = None,
        ) -> tuple[float | str | None, float | str | None]:
            return latitude, longitude

    instance = MockInstance()
    with pytest.raises(InvalidCoordinatesError):
        instance.set_location(45.0, None)

    with pytest.raises(TypeError):
        instance.set_location("north", -122.0)


@pytest.mark.asyncio
async def test_handle_errors_reraises_wrapped_generic_errors_for_async_functions() -> (
    None
):
    """Generic async exceptions should be wrapped and re-raised when configured."""

    class MockInstance:
        @handle_errors(reraise_critical=True)
        async def do_something(self) -> str:
            raise RuntimeError("unexpected boom")

    with pytest.raises(PawControlError, match="unexpected boom"):
        await MockInstance().do_something()


def test_handle_errors_reraises_wrapped_generic_errors_for_sync_functions() -> None:
    """Generic sync exceptions should also be wrapped and re-raised."""

    class MockInstance:
        @handle_errors(reraise_critical=True)
        def do_something(self) -> str:
            raise RuntimeError("sync boom")

    with pytest.raises(PawControlError, match="sync boom"):
        MockInstance().do_something()


@pytest.mark.asyncio
async def test_map_to_repair_issue_uses_coordinator_hass_for_async_methods() -> None:
    """Decorator should resolve Home Assistant from ``self.coordinator.hass``."""

    class MockInstance:
        def __init__(self) -> None:
            self.coordinator = MagicMock()
            self.coordinator.hass = object()

        @map_to_repair_issue("network_issue", severity="error")
        async def perform(self) -> None:
            raise NetworkError("offline")

    with (
        patch("custom_components.pawcontrol.error_decorators.issue_registry") as ir,
        pytest.raises(NetworkError),
    ):
        await MockInstance().perform()

    assert ir.async_create_issue.call_args.args[0] is not None


def test_map_to_repair_issue_uses_hass_attribute_for_sync_methods() -> None:
    """Sync wrappers should create issues when ``self.hass`` is present."""

    class MockInstance:
        def __init__(self) -> None:
            self.hass = object()

        @map_to_repair_issue("storage_issue", severity="warning")
        def perform(self) -> None:
            raise PawControlError("sync issue")

    with (
        patch("custom_components.pawcontrol.error_decorators.issue_registry") as ir,
        pytest.raises(PawControlError),
    ):
        MockInstance().perform()

    ir.async_create_issue.assert_called_once()


def test_retry_on_error_sync_exhausts_attempts_and_raises() -> None:
    """Sync retry wrapper should re-raise after exhausting retries."""

    class MockInstance:
        call_count = 0

        @retry_on_error(max_attempts=2, delay=0.01, exceptions=(NetworkError,))
        def fetch_data(self) -> str:
            self.call_count += 1
            raise NetworkError("still offline")

    with patch("time.sleep") as sleep, pytest.raises(NetworkError):
        MockInstance().fetch_data()

    assert sleep.call_count == 1


def test_require_coordinator_data_raises_without_instance_args() -> None:
    """Calling decorated function directly should fail with clear guidance."""

    @require_coordinator_data()
    def _wrapped() -> str:
        return "ok"

    with pytest.raises(PawControlError, match="instance method"):
        _wrapped()


@pytest.mark.asyncio
async def test_handle_errors_async_wrapper_returns_default_on_noncritical_error() -> (
    None
):
    """Async handlers should return configured defaults for noncritical errors."""

    class MockInstance:
        @handle_errors(default_return="fallback", reraise_validation_errors=False)
        async def _wrapped(self) -> str:
            raise PawControlError("recoverable", severity=ErrorSeverity.MEDIUM)

    assert await MockInstance()._wrapped() == "fallback"


def test_handle_errors_sync_wrapper_returns_default_on_noncritical_error() -> None:
    """Sync handlers should return configured defaults for noncritical errors."""

    class MockInstance:
        @handle_errors(default_return="fallback", reraise_validation_errors=False)
        def _wrapped(self) -> str:
            raise PawControlError("recoverable", severity=ErrorSeverity.MEDIUM)

    assert MockInstance()._wrapped() == "fallback"


@pytest.mark.asyncio
async def test_retry_on_error_async_returns_none_when_attempts_are_zero() -> None:
    """Retry wrappers should gracefully return ``None`` with zero attempts."""
    calls = 0

    @retry_on_error(max_attempts=0)
    async def _wrapped() -> str:
        nonlocal calls
        calls += 1
        return "never"

    assert await _wrapped() is None
    assert calls == 0


def test_retry_on_error_sync_returns_none_when_attempts_are_zero() -> None:
    """Sync retry wrappers should mirror the zero-attempt async behaviour."""
    calls = 0

    @retry_on_error(max_attempts=0)
    def _wrapped() -> str:
        nonlocal calls
        calls += 1
        return "never"

    assert _wrapped() is None
    assert calls == 0


def test_validate_dog_exists_wrapper_errors_without_bound_instance() -> None:
    """Decorator should fail fast when called as a free function with kwargs."""

    @validate_dog_exists()
    def _wrapped(self: object, dog_id: str) -> str:
        return dog_id

    with pytest.raises(PawControlError, match="instance method"):
        _wrapped(dog_id="buddy")


def test_map_to_repair_issue_sync_uses_coordinator_hass() -> None:
    """Sync wrapper should derive hass from ``self.coordinator`` when needed."""

    class MockInstance:
        def __init__(self) -> None:
            self.coordinator = MagicMock()
            self.coordinator.hass = object()

        @map_to_repair_issue("sync_network_issue", severity="error")
        def perform(self) -> None:
            raise NetworkError("offline")

    with (
        patch("custom_components.pawcontrol.error_decorators.issue_registry") as ir,
        pytest.raises(NetworkError),
    ):
        MockInstance().perform()

    assert ir.async_create_issue.call_args.args[0] is not None
