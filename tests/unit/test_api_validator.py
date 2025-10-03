"""Tests for the API validator session management logic."""

from __future__ import annotations

import pytest

pytest.importorskip(
    "homeassistant", reason="Home Assistant test dependencies not available"
)

from custom_components.pawcontrol.api_validator import APIValidator


@pytest.mark.unit
def test_api_validator_reuses_injected_session(
    mock_hass, session_factory
) -> None:
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
async def test_api_validator_cleanup_is_noop(
    mock_hass, session_factory
) -> None:
    """Validator cleanup should succeed even if the session is already closed."""

    hass_session = session_factory()

    validator = APIValidator(mock_hass, session=hass_session)
    hass_session.closed = True
    await validator.async_close()

    hass_session.close.assert_not_awaited()
