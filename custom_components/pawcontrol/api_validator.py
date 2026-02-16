"""API validation module for PawControl integration.

Provides comprehensive API connection testing and validation to ensure
reliable integration setup and configuration health checks.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import logging
from typing import Final, Literal, NotRequired, TypedDict, cast

import aiohttp
from homeassistant.core import HomeAssistant

from .http_client import ensure_shared_client_session

_LOGGER = logging.getLogger(__name__)

# API validation timeouts
API_CONNECTION_TIMEOUT = 10.0  # seconds
API_TOKEN_VALIDATION_TIMEOUT = 15.0  # seconds
API_HEALTH_CHECK_TIMEOUT = 20.0  # seconds
AUTH_SUCCESS_STATUS_CODES: Final = (200, 201, 204)


type CapabilityList = list[str]
type JSONPrimitive = None | bool | float | int | str
type JSONValue = (
  JSONPrimitive
  | Mapping[
    str,
    "JSONValue",
  ]
  | Sequence["JSONValue"]
)
type JSONMapping = Mapping[str, JSONValue]
type JSONSequence = Sequence[JSONValue]


class APIAuthenticationResult(TypedDict):
  """Structured authentication probe response."""  # noqa: E111

  authenticated: bool  # noqa: E111
  api_version: str | None  # noqa: E111
  capabilities: CapabilityList | None  # noqa: E111


type HealthStatus = Literal[
  "healthy",
  "degraded",
  "unreachable",
  "authentication_failed",
  "timeout",
  "error",
]


class APIHealthStatus(TypedDict):
  """Structured payload returned by :meth:`async_test_api_health`."""  # noqa: E111

  healthy: bool  # noqa: E111
  reachable: bool  # noqa: E111
  authenticated: bool  # noqa: E111
  response_time_ms: float | None  # noqa: E111
  error: str | None  # noqa: E111
  status: HealthStatus  # noqa: E111
  api_version: str | None  # noqa: E111
  capabilities: CapabilityList | None  # noqa: E111


class _APIAuthPayload(TypedDict, total=False):
  """Subset of fields returned by PawControl API authentication endpoints."""  # noqa: E111

  version: str  # noqa: E111
  capabilities: NotRequired[JSONSequence]  # noqa: E111


class _RequestOptions(TypedDict, total=False):
  """Subset of aiohttp request keyword arguments used by the validator."""  # noqa: E111

  allow_redirects: bool  # noqa: E111
  ssl: bool  # noqa: E111


@dataclass
class APIValidationResult:
  """Results from API validation check."""  # noqa: E111

  valid: bool  # noqa: E111
  reachable: bool  # noqa: E111
  authenticated: bool  # noqa: E111
  response_time_ms: float | None  # noqa: E111
  error_message: str | None  # noqa: E111
  api_version: str | None  # noqa: E111
  capabilities: CapabilityList | None  # noqa: E111


class APIValidator:
  """Validates API connections and credentials for PawControl."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    hass: HomeAssistant,
    session: aiohttp.ClientSession,
    *,
    verify_ssl: bool = True,
  ) -> None:
    """Initialize API validator.

    Args:
        hass: Home Assistant instance
        session: Home Assistant managed session for HTTP calls.
        verify_ssl: When ``False`` the validator will skip TLS certificate
            verification. This should only be disabled for development
            scenarios that rely on self-signed certificates.
    """
    self.hass = hass
    self._session = ensure_shared_client_session(
      session,
      owner="APIValidator",
    )
    self._ssl_override: bool | None = None
    if not verify_ssl:
      # aiohttp accepts ``ssl=False`` to bypass certificate validation.  # noqa: E114
      # We only store the override when explicitly requested so production  # noqa: E114
      # systems keep the secure defaults provided by Home Assistant.  # noqa: E114
      self._ssl_override = False  # noqa: E111

  @property  # noqa: E111
  def session(self) -> aiohttp.ClientSession:  # noqa: E111
    """Return the HTTP session leveraged for validation calls."""
    return self._session

  async def async_validate_api_connection(  # noqa: E111
    self,
    api_endpoint: str,
    api_token: str | None = None,
  ) -> APIValidationResult:
    """Validate API connection and authentication.

    Args:
        api_endpoint: API endpoint URL
        api_token: Optional API token for authentication

    Returns:
        APIValidationResult with validation details

    Raises:
        HomeAssistantError: If validation encounters critical errors
    """
    import time

    start_time = time.monotonic()

    try:
      # Validate endpoint format  # noqa: E114
      if not self._validate_endpoint_format(api_endpoint):  # noqa: E111
        return APIValidationResult(
          valid=False,
          reachable=False,
          authenticated=False,
          response_time_ms=None,
          error_message="Invalid API endpoint format",
          api_version=None,
          capabilities=None,
        )

      # Test connection reachability  # noqa: E114
      async with asyncio.timeout(API_CONNECTION_TIMEOUT):  # noqa: E111
        reachable = await self._test_endpoint_reachability(api_endpoint)

      if not reachable:  # noqa: E111
        return APIValidationResult(
          valid=False,
          reachable=False,
          authenticated=False,
          response_time_ms=None,
          error_message="API endpoint not reachable",
          api_version=None,
          capabilities=None,
        )

      # Test authentication if token provided  # noqa: E114
      authenticated = False  # noqa: E111
      api_version: str | None = None  # noqa: E111
      capabilities: CapabilityList | None = None  # noqa: E111

      if api_token:  # noqa: E111
        async with asyncio.timeout(API_TOKEN_VALIDATION_TIMEOUT):
          auth_result = await self._test_authentication(  # noqa: E111
            api_endpoint,
            api_token,
          )
          authenticated = auth_result["authenticated"]  # noqa: E111
          api_version = auth_result["api_version"]  # noqa: E111
          capabilities = auth_result["capabilities"]  # noqa: E111

        if not authenticated:
          response_time_ms = (time.monotonic() - start_time) * 1000  # noqa: E111
          return APIValidationResult(  # noqa: E111
            valid=False,
            reachable=True,
            authenticated=False,
            response_time_ms=response_time_ms,
            error_message="API token authentication failed",
            api_version=None,
            capabilities=None,
          )

      # Calculate response time  # noqa: E114
      response_time_ms = (time.monotonic() - start_time) * 1000  # noqa: E111

      return APIValidationResult(  # noqa: E111
        valid=True,
        reachable=True,
        authenticated=authenticated if api_token else False,
        response_time_ms=response_time_ms,
        error_message=None,
        api_version=api_version,
        capabilities=capabilities,
      )

    except TimeoutError:
      response_time_ms = (time.monotonic() - start_time) * 1000  # noqa: E111
      return APIValidationResult(  # noqa: E111
        valid=False,
        reachable=False,
        authenticated=False,
        response_time_ms=response_time_ms,
        error_message="API connection timeout",
        api_version=None,
        capabilities=None,
      )
    except Exception as err:
      _LOGGER.error("API validation failed: %s", err)  # noqa: E111
      response_time_ms = (time.monotonic() - start_time) * 1000  # noqa: E111
      return APIValidationResult(  # noqa: E111
        valid=False,
        reachable=False,
        authenticated=False,
        response_time_ms=response_time_ms,
        error_message=f"Validation error: {err}",
        api_version=None,
        capabilities=None,
      )

  def _validate_endpoint_format(self, endpoint: str) -> bool:  # noqa: E111
    """Validate API endpoint format.

    Args:
        endpoint: API endpoint to validate

    Returns:
        True if format is valid
    """
    if not endpoint or not isinstance(endpoint, str):
      return False  # noqa: E111

    # Must start with http:// or https://
    if not endpoint.startswith(("http://", "https://")):
      return False  # noqa: E111

    # Basic URL validation
    try:
      from urllib.parse import urlparse  # noqa: E111

      result = urlparse(endpoint)  # noqa: E111
      return bool(result.scheme and result.netloc)  # noqa: E111
    except Exception:
      return False  # noqa: E111

  async def _test_endpoint_reachability(self, endpoint: str) -> bool:  # noqa: E111
    """Test if endpoint is reachable.

    Args:
        endpoint: API endpoint URL

    Returns:
        True if endpoint is reachable
    """
    try:
      session = self._session  # noqa: E111

      request_kwargs: _RequestOptions  # noqa: E111
      if self._ssl_override is None:  # noqa: E111
        request_kwargs = {"allow_redirects": True}
      else:  # noqa: E111
        request_kwargs = {
          "allow_redirects": True,
          "ssl": self._ssl_override,
        }

      response_ctx = await session.get(endpoint, **request_kwargs)  # noqa: E111

      async with response_ctx:  # noqa: E111
        # Any response (even 404) means the endpoint is reachable
        return True

    except aiohttp.ClientError as err:
      _LOGGER.debug("Endpoint not reachable: %s", err)  # noqa: E111
      return False  # noqa: E111
    except Exception as err:
      _LOGGER.debug("Unexpected error testing reachability: %s", err)  # noqa: E111
      return False  # noqa: E111

  async def _test_authentication(  # noqa: E111
    self,
    endpoint: str,
    token: str,
  ) -> APIAuthenticationResult:
    """Test API authentication with token.

    Args:
        endpoint: API endpoint URL
        token: API authentication token

    Returns:
        Dictionary with authentication results
    """
    try:
      session = self._session  # noqa: E111

      # Construct auth endpoint (common patterns)  # noqa: E114
      # Try the most common validation endpoints before falling back to  # noqa: E114
      # the base URL with an auth header.  # noqa: E114
      auth_endpoints: tuple[str, ...] = (  # noqa: E111
        f"{endpoint}/auth/validate",
        f"{endpoint}/api/auth",
        f"{endpoint}/validate",
        endpoint,
      )

      headers: dict[str, str] = {  # noqa: E111
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
      }

      request_kwargs: _RequestOptions  # noqa: E111
      request_kwargs = {} if self._ssl_override is None else {"ssl": self._ssl_override}  # noqa: E111

      # Try each endpoint until one works  # noqa: E114
      for auth_endpoint in auth_endpoints:  # noqa: E111
        try:
          async with session.get(  # noqa: E111
            auth_endpoint,
            headers=headers,
            **request_kwargs,
          ) as response:
            if response.status in AUTH_SUCCESS_STATUS_CODES:
              # Try to parse response for additional info  # noqa: E114
              try:  # noqa: E111
                data = await response.json()
              except Exception:  # noqa: E111
                return APIAuthenticationResult(
                  authenticated=True,
                  api_version=None,
                  capabilities=None,
                )
              if not isinstance(data, Mapping):  # noqa: E111
                return APIAuthenticationResult(
                  authenticated=True,
                  api_version=None,
                  capabilities=None,
                )
              payload = cast(_APIAuthPayload, data)  # noqa: E111
              return APIAuthenticationResult(  # noqa: E111
                authenticated=True,
                api_version=_extract_api_version(payload),
                capabilities=_extract_capabilities(payload),
              )

        except aiohttp.ClientError:
          continue  # noqa: E111

      # No endpoint accepted the token  # noqa: E114
      return APIAuthenticationResult(  # noqa: E111
        authenticated=False,
        api_version=None,
        capabilities=None,
      )

    except Exception as err:
      _LOGGER.error("Authentication test failed: %s", err)  # noqa: E111
      return APIAuthenticationResult(  # noqa: E111
        authenticated=False,
        api_version=None,
        capabilities=None,
      )

  async def async_test_api_health(  # noqa: E111
    self,
    api_endpoint: str,
    api_token: str | None = None,
  ) -> APIHealthStatus:
    """Perform comprehensive API health check.

    Args:
        api_endpoint: API endpoint URL
        api_token: Optional API token

    Returns:
        Health check results dictionary
    """
    try:
      async with asyncio.timeout(API_HEALTH_CHECK_TIMEOUT):  # noqa: E111
        validation_result = await self.async_validate_api_connection(
          api_endpoint,
          api_token,
        )

        health_status = APIHealthStatus(
          healthy=validation_result.valid,
          reachable=validation_result.reachable,
          authenticated=validation_result.authenticated,
          response_time_ms=validation_result.response_time_ms,
          error=validation_result.error_message,
          api_version=validation_result.api_version,
          capabilities=validation_result.capabilities,
          status="degraded",
        )

        # Determine overall health
        if not validation_result.reachable:
          health_status["status"] = "unreachable"  # noqa: E111
        elif not validation_result.authenticated and api_token:
          health_status["status"] = "authentication_failed"  # noqa: E111
        elif validation_result.valid:
          health_status["status"] = "healthy"  # noqa: E111

        return health_status

    except TimeoutError:
      return APIHealthStatus(  # noqa: E111
        healthy=False,
        reachable=False,
        authenticated=False,
        response_time_ms=None,
        error="Health check timeout",
        status="timeout",
        api_version=None,
        capabilities=None,
      )
    except Exception as err:
      _LOGGER.error("API health check failed: %s", err)  # noqa: E111
      return APIHealthStatus(  # noqa: E111
        healthy=False,
        reachable=False,
        authenticated=False,
        response_time_ms=None,
        error=str(err),
        status="error",
        api_version=None,
        capabilities=None,
      )

  async def async_close(self) -> None:  # noqa: E111
    """Close the API validator and cleanup resources."""
    if not self._session.closed:
      # The validator never owns the session; leave lifecycle management to  # noqa: E114, E501
      # Home Assistant to avoid closing the shared pool.  # noqa: E114
      return  # noqa: E111


def _extract_api_version(data: JSONMapping | _APIAuthPayload) -> str | None:
  """Return the reported API version when present."""  # noqa: E111

  if isinstance(data, Mapping):  # noqa: E111
    version = data.get("version")
    if isinstance(version, str):
      return version  # noqa: E111
  return None  # noqa: E111


def _extract_capabilities(data: JSONMapping | _APIAuthPayload) -> CapabilityList | None:
  """Return normalised capability data from a JSON payload."""  # noqa: E111

  if not isinstance(data, Mapping):  # noqa: E111
    return None

  capabilities = data.get("capabilities")  # noqa: E111
  if isinstance(capabilities, Sequence) and not isinstance(  # noqa: E111
    capabilities,
    str | bytes | bytearray,
  ):
    string_capabilities = [
      capability for capability in capabilities if isinstance(capability, str)
    ]
    if string_capabilities:
      return list(string_capabilities)  # noqa: E111
    if len(capabilities) == 0:
      return []  # noqa: E111
  return None  # noqa: E111
