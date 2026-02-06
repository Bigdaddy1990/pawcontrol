"""HTTP client helpers for communicating with Paw Control hardware."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from yarl import URL

from .exceptions import ConfigEntryAuthFailed, NetworkError, RateLimitError
from .resilience import async_retry
from .types import JSONMutableMapping
from .utils import _coerce_json_mutable

_DEFAULT_TIMEOUT = ClientTimeout(total=15.0)


@dataclass(slots=True)
class DeviceEndpoint:
  """Descriptor for a Paw Control hardware endpoint."""

  base_url: URL
  api_key: str | None = None


def validate_device_endpoint(endpoint: str) -> URL:
  """Validate and normalize the configured device endpoint."""

  if not endpoint:
    raise ValueError("endpoint must be provided")

  try:
    base_url = URL(endpoint)
  except ValueError as err:
    raise ValueError(f"Invalid endpoint: {endpoint}") from err

  if base_url.scheme not in {"http", "https"}:
    raise ValueError("endpoint must use http or https scheme")
  if not base_url.host:
    raise ValueError("endpoint must include a valid hostname")

  return base_url


class PawControlDeviceClient:
  """Client for Paw Control companion hardware."""

  def __init__(
    self,
    session: ClientSession,
    *,
    endpoint: str,
    api_key: str | None = None,
    timeout: ClientTimeout | None = None,
    resilience_manager: Any = None,
  ) -> None:
    self._session = session
    self._endpoint = DeviceEndpoint(
      base_url=validate_device_endpoint(endpoint),
      api_key=api_key,
    )
    self._timeout = timeout or _DEFAULT_TIMEOUT
    del resilience_manager

  @property
  def base_url(self) -> URL:
    return self._endpoint.base_url

  async def async_get_json(self, path: str) -> JSONMutableMapping:
    """Perform a JSON GET request with transient retry handling."""

    payload = await async_retry(self._async_request, "GET", path, attempts=3)
    return _coerce_json_mutable(payload)

  async def async_get_feeding_payload(self, dog_id: str) -> JSONMutableMapping:
    """Fetch feeding payload for a specific dog from the device API."""

    return await self.async_get_json(f"/api/dogs/{dog_id}/feeding")

  async def _async_request(self, method: str, path: str) -> JSONMutableMapping:
    """Execute a single HTTP request and normalize common API failures."""

    url = self._endpoint.base_url.join(URL(path))
    headers: dict[str, str] = {}
    if self._endpoint.api_key:
      headers["Authorization"] = f"Bearer {self._endpoint.api_key}"

    try:
      async with self._session.request(
        method,
        url,
        timeout=self._timeout,
        headers=headers,
      ) as response:
        if response.status == 401:
          raise ConfigEntryAuthFailed("Authentication failed")

        if response.status == 429:
          retry_after = response.headers.get("Retry-After", "60")
          raise RateLimitError(f"Rate limited, retry after {retry_after}s")

        response.raise_for_status()
        return _coerce_json_mutable(await response.json())

    except TimeoutError as err:
      raise NetworkError("Timeout connecting to device") from err
    except ClientError as err:
      raise NetworkError(f"Client error: {err}") from err


__all__ = ["PawControlDeviceClient", "validate_device_endpoint"]
