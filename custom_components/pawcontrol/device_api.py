"""HTTP client helpers for communicating with Paw Control hardware."""

from dataclasses import dataclass

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout
from aiohttp.client_exceptions import ContentTypeError
from yarl import URL

from .exceptions import ConfigEntryAuthFailed, NetworkError, RateLimitError
from .http_client import ensure_shared_client_session
from .resilience import ResilienceManager, RetryConfig
from .types import JSONMutableMapping
from .utils import _coerce_json_mutable  # type: ignore[attr-defined]

_DEFAULT_TIMEOUT = ClientTimeout(total=15.0)


@dataclass(slots=True)
class DeviceEndpoint:
  """Descriptor for a Paw Control hardware endpoint."""  # noqa: E111

  base_url: URL  # noqa: E111
  api_key: str | None = None  # noqa: E111


def validate_device_endpoint(endpoint: str) -> URL:
  """Validate and normalize the configured device endpoint."""  # noqa: E111

  if not endpoint:  # noqa: E111
    raise ValueError("endpoint must be provided for device client")

  try:  # noqa: E111
    base_url = URL(endpoint)
  except ValueError as err:  # pragma: no cover - defensive  # noqa: E111
    raise ValueError(f"Invalid Paw Control endpoint: {endpoint}") from err

  if base_url.scheme not in {"http", "https"}:  # noqa: E111
    raise ValueError("endpoint must use http or https scheme")
  if not base_url.host:  # noqa: E111
    raise ValueError("endpoint must include a valid hostname")

  return base_url  # noqa: E111


class PawControlDeviceClient:
  """Optional fallback client for Paw Control companion hardware."""  # noqa: E111

  def __init__(  # noqa: E111
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
      session,
      owner="PawControlDeviceClient",
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

  @property  # noqa: E111
  def base_url(self) -> URL:  # noqa: E111
    """Return the configured base URL for the companion endpoint."""

    return self._endpoint.base_url

  async def async_get_json(self, path: str) -> JSONMutableMapping:  # noqa: E111
    """Perform a JSON GET request against the companion device with resilience."""

    # RESILIENCE: Wrap in circuit breaker and retry if available
    if self._resilience_manager:
      response = await self._resilience_manager.execute_with_resilience(  # noqa: E111
        self._async_request_protected,
        "GET",
        path,
        circuit_breaker_name="device_api_request",
        retry_config=self._retry_config,
      )
    else:
      response = await self._async_request("GET", path)  # noqa: E111

    try:
      payload = await response.json()  # noqa: E111
    except (ContentTypeError, ValueError) as err:  # pragma: no cover - defensive
      raise NetworkError(  # noqa: E111
        "Device API returned a non-JSON response. Check the configured endpoint.",
      ) from err
    return _coerce_json_mutable(payload)

  async def async_get_feeding_payload(self, dog_id: str) -> JSONMutableMapping:  # noqa: E111
    """Fetch the latest feeding payload for a dog from the companion device."""

    return await self.async_get_json(f"/api/dogs/{dog_id}/feeding")

  async def _async_request_protected(self, method: str, path: str) -> ClientResponse:  # noqa: E111
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

  async def _async_request(self, method: str, path: str) -> ClientResponse:  # noqa: E111
    """Execute an HTTP request and normalize errors."""

    url = self._endpoint.base_url.join(URL(path))
    headers: dict[str, str] | None = None
    if self._endpoint.api_key:
      headers = {"Authorization": f"Bearer {self._endpoint.api_key}"}  # noqa: E111

    try:
      response = await self._session.request(  # noqa: E111
        method,
        url,
        timeout=self._timeout,
        headers=headers,
      )
    except TimeoutError as err:  # pragma: no cover - transport timeout
      raise NetworkError(  # noqa: E111
        "Timed out while contacting the Paw Control device API",
      ) from err
    except ClientError as err:  # pragma: no cover - transport errors
      raise NetworkError(  # noqa: E111
        f"Client error talking to device API: {err}",
      ) from err
    except OSError as err:  # pragma: no cover - local network failures
      raise NetworkError(  # noqa: E111
        f"Network error talking to device API: {err}",
      ) from err

    if response.status == 401:
      raise ConfigEntryAuthFailed(  # noqa: E111
        "Authentication with Paw Control device failed",
      )
    if response.status == 429:
      retry_after = response.headers.get("Retry-After")  # noqa: E111
      retry_seconds = int(retry_after) if retry_after and retry_after.isdigit() else 60  # noqa: E111
      raise RateLimitError("device_api", retry_after=retry_seconds)  # noqa: E111
    if response.status >= 400:
      text = await response.text()  # noqa: E111
      raise NetworkError(  # noqa: E111
        f"Device API returned HTTP {response.status}: {text.strip()}",
      )

    return response


__all__ = ["PawControlDeviceClient", "validate_device_endpoint"]
