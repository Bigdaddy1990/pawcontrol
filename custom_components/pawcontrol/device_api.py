"""HTTP client helpers for communicating with Paw Control hardware."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientResponse, ClientSession, ClientTimeout
from homeassistant.exceptions import ConfigEntryAuthFailed
from yarl import URL

from .exceptions import NetworkError, RateLimitError
from .http_client import ensure_shared_client_session
from .resilience import ResilienceManager, RetryConfig

_DEFAULT_TIMEOUT = ClientTimeout(total=15.0)


@dataclass(slots=True)
class DeviceEndpoint:
    """Descriptor for a Paw Control hardware endpoint."""

    base_url: URL
    api_key: str | None = None


def validate_device_endpoint(endpoint: str) -> URL:
    """Validate and normalize the configured device endpoint."""

    if not endpoint:
        raise ValueError("endpoint must be provided for device client")

    try:
        base_url = URL(endpoint)
    except ValueError as err:  # pragma: no cover - defensive
        raise ValueError(f"Invalid Paw Control endpoint: {endpoint}") from err

    if base_url.scheme not in {"http", "https"}:
        raise ValueError("endpoint must use http or https scheme")
    if not base_url.host:
        raise ValueError("endpoint must include a valid hostname")

    return base_url


class PawControlDeviceClient:
    """Optional fallback client for Paw Control companion hardware."""

    def __init__(
        self,
        session: ClientSession,
        *,
        endpoint: str,
        api_key: str | None = None,
        timeout: ClientTimeout | None = None,
        resilience_manager: ResilienceManager | None = None,
    ) -> None:
        """Initialize the client for the Paw Control companion device.

        Args:
            session: The `aiohttp.ClientSession` to use for requests.
            endpoint: The base URL for the companion device API.
            api_key: An optional API key for bearer token authentication.
            timeout: An optional client timeout configuration.
            resilience_manager: Optional ResilienceManager for fault tolerance.

        """

        base_url = validate_device_endpoint(endpoint)

        self._session = ensure_shared_client_session(
            session, owner="PawControlDeviceClient"
        )
        self._endpoint = DeviceEndpoint(base_url=base_url, api_key=api_key)
        self._timeout = timeout or _DEFAULT_TIMEOUT
        self._resilience_manager = resilience_manager

        # Configure retry for transient failures
        self._retry_config = RetryConfig(
            max_attempts=3,
            initial_delay=1.0,
            max_delay=10.0,
            exponential_base=2.0,
            jitter=True,
        )

    @property
    def base_url(self) -> URL:
        """Return the configured base URL for the companion endpoint."""

        return self._endpoint.base_url

    async def async_get_json(self, path: str) -> Mapping[str, Any]:
        """Perform a JSON GET request against the companion device with resilience."""

        # RESILIENCE: Wrap in circuit breaker and retry if available
        if self._resilience_manager:
            response = await self._resilience_manager.execute_with_resilience(
                self._async_request_protected,
                "GET",
                path,
                circuit_breaker_name="device_api_request",
                retry_config=self._retry_config,
            )
        else:
            response = await self._async_request("GET", path)

        try:
            payload = await response.json()
        except Exception as err:  # pragma: no cover - defensive
            raise NetworkError(f"Invalid JSON response from device: {err}") from err
        return payload

    async def async_get_feeding_payload(self, dog_id: str) -> Mapping[str, Any]:
        """Fetch the latest feeding payload for a dog from the companion device."""

        return await self.async_get_json(f"/api/dogs/{dog_id}/feeding")

    async def _async_request_protected(self, method: str, path: str) -> ClientResponse:
        """Protected request wrapper - called through resilience patterns.

        This method is wrapped by circuit breaker and retry logic.

        Args:
            method: HTTP method
            path: API path

        Returns:
            ClientResponse

        Raises:
            ConfigEntryAuthFailed: If authentication fails
            RateLimitError: If rate limited
            NetworkError: For other errors
        """
        return await self._async_request(method, path)

    async def _async_request(self, method: str, path: str) -> ClientResponse:
        """Execute an HTTP request and normalize errors."""

        url = self._endpoint.base_url.join(URL(path))
        headers: dict[str, str] | None = None
        if self._endpoint.api_key:
            headers = {"Authorization": f"Bearer {self._endpoint.api_key}"}

        try:
            response = await self._session.request(
                method,
                url,
                timeout=self._timeout,
                headers=headers,
            )
        except Exception as err:  # pragma: no cover - transport errors
            raise NetworkError(f"Error talking to device API: {err}") from err

        if response.status == 401:
            raise ConfigEntryAuthFailed("Authentication with Paw Control device failed")
        if response.status == 429:
            retry_after = response.headers.get("Retry-After")
            retry_seconds = (
                int(retry_after) if retry_after and retry_after.isdigit() else 60
            )
            raise RateLimitError("device_api", retry_after=retry_seconds)
        if response.status >= 400:
            text = await response.text()
            raise NetworkError(
                f"Device API returned HTTP {response.status}: {text.strip()}"
            )

        return response


__all__ = ["PawControlDeviceClient", "validate_device_endpoint"]
