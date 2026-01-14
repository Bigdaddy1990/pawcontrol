"""API validation module for PawControl integration.

Provides comprehensive API connection testing and validation to ensure
reliable integration setup and configuration health checks.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast
from typing import Final
from typing import Literal
from typing import NotRequired
from typing import TypedDict

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
        'JSONValue',
    ]
    | Sequence['JSONValue']
)
type JSONMapping = Mapping[str, JSONValue]
type JSONSequence = Sequence[JSONValue]


class APIAuthenticationResult(TypedDict):
    """Structured authentication probe response."""

    authenticated: bool
    api_version: str | None
    capabilities: CapabilityList | None


type HealthStatus = Literal[
    'healthy',
    'degraded',
    'unreachable',
    'authentication_failed',
    'timeout',
    'error',
]


class APIHealthStatus(TypedDict):
    """Structured payload returned by :meth:`async_test_api_health`."""

    healthy: bool
    reachable: bool
    authenticated: bool
    response_time_ms: float | None
    error: str | None
    status: HealthStatus
    api_version: str | None
    capabilities: CapabilityList | None


class _APIAuthPayload(TypedDict, total=False):
    """Subset of fields returned by PawControl API authentication endpoints."""

    version: str
    capabilities: NotRequired[JSONSequence]


class _RequestOptions(TypedDict, total=False):
    """Subset of aiohttp request keyword arguments used by the validator."""

    allow_redirects: bool
    ssl: bool


@dataclass
class APIValidationResult:
    """Results from API validation check."""

    valid: bool
    reachable: bool
    authenticated: bool
    response_time_ms: float | None
    error_message: str | None
    api_version: str | None
    capabilities: CapabilityList | None


class APIValidator:
    """Validates API connections and credentials for PawControl."""

    def __init__(
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
            owner='APIValidator',
        )
        self._ssl_override: bool | None = None
        if not verify_ssl:
            # aiohttp accepts ``ssl=False`` to bypass certificate validation.
            # We only store the override when explicitly requested so production
            # systems keep the secure defaults provided by Home Assistant.
            self._ssl_override = False

    @property
    def session(self) -> aiohttp.ClientSession:
        """Return the HTTP session leveraged for validation calls."""
        return self._session

    async def async_validate_api_connection(
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
            # Validate endpoint format
            if not self._validate_endpoint_format(api_endpoint):
                return APIValidationResult(
                    valid=False,
                    reachable=False,
                    authenticated=False,
                    response_time_ms=None,
                    error_message='Invalid API endpoint format',
                    api_version=None,
                    capabilities=None,
                )

            # Test connection reachability
            async with asyncio.timeout(API_CONNECTION_TIMEOUT):
                reachable = await self._test_endpoint_reachability(api_endpoint)

            if not reachable:
                return APIValidationResult(
                    valid=False,
                    reachable=False,
                    authenticated=False,
                    response_time_ms=None,
                    error_message='API endpoint not reachable',
                    api_version=None,
                    capabilities=None,
                )

            # Test authentication if token provided
            authenticated = False
            api_version: str | None = None
            capabilities: CapabilityList | None = None

            if api_token:
                async with asyncio.timeout(API_TOKEN_VALIDATION_TIMEOUT):
                    auth_result = await self._test_authentication(
                        api_endpoint,
                        api_token,
                    )
                    authenticated = auth_result['authenticated']
                    api_version = auth_result['api_version']
                    capabilities = auth_result['capabilities']

                if not authenticated:
                    response_time_ms = (time.monotonic() - start_time) * 1000
                    return APIValidationResult(
                        valid=False,
                        reachable=True,
                        authenticated=False,
                        response_time_ms=response_time_ms,
                        error_message='API token authentication failed',
                        api_version=None,
                        capabilities=None,
                    )

            # Calculate response time
            response_time_ms = (time.monotonic() - start_time) * 1000

            return APIValidationResult(
                valid=True,
                reachable=True,
                authenticated=authenticated if api_token else True,
                response_time_ms=response_time_ms,
                error_message=None,
                api_version=api_version,
                capabilities=capabilities,
            )

        except TimeoutError:
            response_time_ms = (time.monotonic() - start_time) * 1000
            return APIValidationResult(
                valid=False,
                reachable=False,
                authenticated=False,
                response_time_ms=response_time_ms,
                error_message='API connection timeout',
                api_version=None,
                capabilities=None,
            )
        except Exception as err:
            _LOGGER.error('API validation failed: %s', err)
            response_time_ms = (time.monotonic() - start_time) * 1000
            return APIValidationResult(
                valid=False,
                reachable=False,
                authenticated=False,
                response_time_ms=response_time_ms,
                error_message=f"Validation error: {err}",
                api_version=None,
                capabilities=None,
            )

    def _validate_endpoint_format(self, endpoint: str) -> bool:
        """Validate API endpoint format.

        Args:
            endpoint: API endpoint to validate

        Returns:
            True if format is valid
        """
        if not endpoint or not isinstance(endpoint, str):
            return False

        # Must start with http:// or https://
        if not endpoint.startswith(('http://', 'https://')):
            return False

        # Basic URL validation
        try:
            from urllib.parse import urlparse

            result = urlparse(endpoint)
            return bool(result.scheme and result.netloc)
        except Exception:
            return False

    async def _test_endpoint_reachability(self, endpoint: str) -> bool:
        """Test if endpoint is reachable.

        Args:
            endpoint: API endpoint URL

        Returns:
            True if endpoint is reachable
        """
        try:
            session = self._session

            request_kwargs: _RequestOptions
            if self._ssl_override is None:
                request_kwargs = {'allow_redirects': True}
            else:
                request_kwargs = {
                    'allow_redirects': True,
                    'ssl': self._ssl_override,
                }

            response_ctx = await session.get(endpoint, **request_kwargs)

            async with response_ctx:
                # Any response (even 404) means the endpoint is reachable
                return True

        except aiohttp.ClientError as err:
            _LOGGER.debug('Endpoint not reachable: %s', err)
            return False
        except Exception as err:
            _LOGGER.debug('Unexpected error testing reachability: %s', err)
            return False

    async def _test_authentication(
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
            session = self._session

            # Construct auth endpoint (common patterns)
            # Try the most common validation endpoints before falling back to
            # the base URL with an auth header.
            auth_endpoints: tuple[str, ...] = (
                f"{endpoint}/auth/validate",
                f"{endpoint}/api/auth",
                f"{endpoint}/validate",
                endpoint,
            )

            headers: dict[str, str] = {
                'Authorization': f"Bearer {token}",
                'Content-Type': 'application/json',
            }

            request_kwargs: _RequestOptions
            if self._ssl_override is None:
                request_kwargs = {}
            else:
                request_kwargs = {'ssl': self._ssl_override}

            # Try each endpoint until one works
            for auth_endpoint in auth_endpoints:
                try:
                    async with session.get(
                        auth_endpoint,
                        headers=headers,
                        **request_kwargs,
                    ) as response:
                        if response.status in AUTH_SUCCESS_STATUS_CODES:
                            # Try to parse response for additional info
                            try:
                                data = await response.json()
                            except Exception:
                                return APIAuthenticationResult(
                                    authenticated=True,
                                    api_version=None,
                                    capabilities=None,
                                )
                            if not isinstance(data, Mapping):
                                return APIAuthenticationResult(
                                    authenticated=True,
                                    api_version=None,
                                    capabilities=None,
                                )
                            payload = cast(_APIAuthPayload, data)
                            return APIAuthenticationResult(
                                authenticated=True,
                                api_version=_extract_api_version(payload),
                                capabilities=_extract_capabilities(payload),
                            )

                except aiohttp.ClientError:
                    continue

            # No endpoint accepted the token
            return APIAuthenticationResult(
                authenticated=False,
                api_version=None,
                capabilities=None,
            )

        except Exception as err:
            _LOGGER.error('Authentication test failed: %s', err)
            return APIAuthenticationResult(
                authenticated=False,
                api_version=None,
                capabilities=None,
            )

    async def async_test_api_health(
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
            async with asyncio.timeout(API_HEALTH_CHECK_TIMEOUT):
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
                    status='degraded',
                )

                # Determine overall health
                if not validation_result.reachable:
                    health_status['status'] = 'unreachable'
                elif not validation_result.authenticated and api_token:
                    health_status['status'] = 'authentication_failed'
                elif validation_result.valid:
                    health_status['status'] = 'healthy'

                return health_status

        except TimeoutError:
            return APIHealthStatus(
                healthy=False,
                reachable=False,
                authenticated=False,
                response_time_ms=None,
                error='Health check timeout',
                status='timeout',
                api_version=None,
                capabilities=None,
            )
        except Exception as err:
            _LOGGER.error('API health check failed: %s', err)
            return APIHealthStatus(
                healthy=False,
                reachable=False,
                authenticated=False,
                response_time_ms=None,
                error=str(err),
                status='error',
                api_version=None,
                capabilities=None,
            )

    async def async_close(self) -> None:
        """Close the API validator and cleanup resources."""
        if not self._session.closed:
            # The validator never owns the session; leave lifecycle management to
            # Home Assistant to avoid closing the shared pool.
            return


def _extract_api_version(data: JSONMapping | _APIAuthPayload) -> str | None:
    """Return the reported API version when present."""

    if isinstance(data, Mapping):
        version = data.get('version')
        if isinstance(version, str):
            return version
    return None


def _extract_capabilities(data: JSONMapping | _APIAuthPayload) -> CapabilityList | None:
    """Return normalised capability data from a JSON payload."""

    if not isinstance(data, Mapping):
        return None

    capabilities = data.get('capabilities')
    if isinstance(capabilities, Sequence) and not isinstance(
        capabilities,
        str | bytes | bytearray,
    ):
        string_capabilities = [
            capability for capability in capabilities if isinstance(capability, str)
        ]
        if string_capabilities:
            return list(string_capabilities)
        if len(capabilities) == 0:
            return []
    return None
