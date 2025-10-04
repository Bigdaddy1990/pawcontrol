"""Tests for the API validator session management logic."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytest.importorskip(
    "homeassistant", reason="Home Assistant test dependencies not available"
)

from custom_components.pawcontrol.api_validator import APIValidator


@pytest.mark.unit
def test_api_validator_reuses_injected_session(mock_hass, session_factory) -> None:
    """The validator should rely on the injected Home Assistant session."""

    hass_session = session_factory()

    validator = APIValidator(mock_hass, session=hass_session)

    assert validator.session is hass_session


@pytest.mark.unit
def test_api_validator_rejects_missing_session(mock_hass) -> None:
    """Providing ``None`` should raise a helpful error."""

    with pytest.raises(ValueError):
        APIValidator(mock_hass, session=None)  # type: ignore[arg-type]


@pytest.mark.unit
def test_api_validator_rejects_closed_session(mock_hass, session_factory) -> None:
    """A closed session must not be accepted."""

    hass_session = session_factory(closed=True)

    with pytest.raises(ValueError):
        APIValidator(mock_hass, session=hass_session)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_api_validator_does_not_close_hass_session(
    mock_hass, session_factory
) -> None:
    """Closing the validator must not dispose the shared hass session."""

    hass_session = session_factory()

    validator = APIValidator(mock_hass, session=hass_session)
    await validator.async_close()

    hass_session.close.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_api_validator_cleanup_is_noop(mock_hass, session_factory) -> None:
    """Validator cleanup should succeed even if the session is already closed."""

    hass_session = session_factory()

    validator = APIValidator(mock_hass, session=hass_session)
    hass_session.closed = True
    await validator.async_close()

    hass_session.close.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reachability_uses_secure_ssl_defaults(
    mock_hass, session_factory
) -> None:
    """TLS verification should remain enabled unless explicitly disabled."""

    hass_session = session_factory()
    context_manager = AsyncMock()
    context_manager.__aenter__.return_value = AsyncMock(status=200)
    context_manager.__aexit__.return_value = False
    hass_session.request.return_value = context_manager

    validator = APIValidator(mock_hass, session=hass_session)

    assert await validator._test_endpoint_reachability("https://example.com")
    kwargs = hass_session.get.call_args.kwargs
    assert kwargs["allow_redirects"] is True
    assert "ssl" not in kwargs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reachability_allows_disabling_ssl_verification(
    mock_hass, session_factory
) -> None:
    """Setting ``verify_ssl=False`` should opt into insecure requests explicitly."""

    hass_session = session_factory()
    context_manager = AsyncMock()
    context_manager.__aenter__.return_value = AsyncMock(status=200)
    context_manager.__aexit__.return_value = False
    hass_session.request.return_value = context_manager

    validator = APIValidator(mock_hass, session=hass_session, verify_ssl=False)

    assert await validator._test_endpoint_reachability("https://example.org")
    kwargs = hass_session.get.call_args.kwargs
    assert kwargs["allow_redirects"] is True
    assert kwargs["ssl"] is False
