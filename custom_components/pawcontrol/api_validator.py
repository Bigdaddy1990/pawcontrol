"""API validation module for PawControl integration.

Provides comprehensive API connection testing and validation to ensure
reliable integration setup and configuration health checks.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant

from .http_client import ensure_shared_client_session

_LOGGER = logging.getLogger(__name__)

# API validation timeouts
API_CONNECTION_TIMEOUT = 10.0  # seconds
API_TOKEN_VALIDATION_TIMEOUT = 15.0  # seconds
API_HEALTH_CHECK_TIMEOUT = 20.0  # seconds


@dataclass
class APIValidationResult:
    """Results from API validation check."""

    valid: bool
    reachable: bool
    authenticated: bool
    response_time_ms: float | None
    error_message: str | None
    api_version: str | None
    capabilities: list[str] | None


class APIValidator:
    """Validates API connections and credentials for PawControl."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize API validator.

        Args:
            hass: Home Assistant instance
            session: Home Assistant managed session for HTTP calls.
        """
        self.hass = hass
        self._session = ensure_shared_client_session(
            session, owner="APIValidator"
        )

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
                    error_message="Invalid API endpoint format",
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
                    error_message="API endpoint not reachable",
                    api_version=None,
                    capabilities=None,
                )

            # Test authentication if token provided
            authenticated = False
            api_version = None
            capabilities = None

            if api_token:
                async with asyncio.timeout(API_TOKEN_VALIDATION_TIMEOUT):
                    auth_result = await self._test_authentication(
                        api_endpoint, api_token
                    )
                    authenticated = auth_result["authenticated"]
                    api_version = auth_result.get("api_version")
                    capabilities = auth_result.get("capabilities")

                if not authenticated:
                    response_time_ms = (time.monotonic() - start_time) * 1000
                    return APIValidationResult(
                        valid=False,
                        reachable=True,
                        authenticated=False,
                        response_time_ms=response_time_ms,
                        error_message="API token authentication failed",
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
                error_message="API connection timeout",
                api_version=None,
                capabilities=None,
            )
        except Exception as err:
            _LOGGER.error("API validation failed: %s", err)
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
        if not endpoint.startswith(("http://", "https://")):
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

            # Try to connect to the endpoint
            async with session.get(
                endpoint,
                allow_redirects=True,
                ssl=False,  # For self-signed certificates
            ):
                # Any response (even 404) means the endpoint is reachable
                return True

        except aiohttp.ClientError as err:
            _LOGGER.debug("Endpoint not reachable: %s", err)
            return False
        except Exception as err:
            _LOGGER.debug("Unexpected error testing reachability: %s", err)
            return False

    async def _test_authentication(self, endpoint: str, token: str) -> dict[str, Any]:
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
            auth_endpoints = [
                f"{endpoint}/auth/validate",
                f"{endpoint}/api/auth",
                f"{endpoint}/validate",
                endpoint,  # Try base endpoint with auth header
            ]

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            # Try each endpoint until one works
            for auth_endpoint in auth_endpoints:
                try:
                    async with session.get(
                        auth_endpoint,
                        headers=headers,
                        ssl=False,
                    ) as response:
                        if response.status in (200, 201, 204):
                            # Try to parse response for additional info
                            try:
                                data = await response.json()
                                return {
                                    "authenticated": True,
                                    "api_version": data.get("version"),
                                    "capabilities": data.get("capabilities"),
                                }
                            except Exception:
                                # JSON parsing failed, but auth succeeded
                                return {
                                    "authenticated": True,
                                    "api_version": None,
                                    "capabilities": None,
                                }

                except aiohttp.ClientError:
                    continue

            # No endpoint accepted the token
            return {
                "authenticated": False,
                "api_version": None,
                "capabilities": None,
            }

        except Exception as err:
            _LOGGER.error("Authentication test failed: %s", err)
            return {
                "authenticated": False,
                "api_version": None,
                "capabilities": None,
            }

    async def async_test_api_health(
        self,
        api_endpoint: str,
        api_token: str | None = None,
    ) -> dict[str, Any]:
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
                    api_endpoint, api_token
                )

                health_status = {
                    "healthy": validation_result.valid,
                    "reachable": validation_result.reachable,
                    "authenticated": validation_result.authenticated,
                    "response_time_ms": validation_result.response_time_ms,
                    "error": validation_result.error_message,
                    "api_version": validation_result.api_version,
                    "capabilities": validation_result.capabilities,
                }

                # Determine overall health
                if not validation_result.reachable:
                    health_status["status"] = "unreachable"
                elif not validation_result.authenticated and api_token:
                    health_status["status"] = "authentication_failed"
                elif validation_result.valid:
                    health_status["status"] = "healthy"
                else:
                    health_status["status"] = "degraded"

                return health_status

        except TimeoutError:
            return {
                "healthy": False,
                "reachable": False,
                "authenticated": False,
                "response_time_ms": None,
                "error": "Health check timeout",
                "status": "timeout",
                "api_version": None,
                "capabilities": None,
            }
        except Exception as err:
            _LOGGER.error("API health check failed: %s", err)
            return {
                "healthy": False,
                "reachable": False,
                "authenticated": False,
                "response_time_ms": None,
                "error": str(err),
                "status": "error",
                "api_version": None,
                "capabilities": None,
            }

    async def async_close(self) -> None:
        """Close the API validator and cleanup resources."""
        if not self._session.closed:
            # The validator never owns the session; leave lifecycle management to
            # Home Assistant to avoid closing the shared pool.
            return
