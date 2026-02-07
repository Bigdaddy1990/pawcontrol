"""Component-level flow path tests for PawControl."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol.const import (
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOGS,
  DOMAIN,
)
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_NAME_FIELD


@pytest.mark.asyncio
async def test_user_flow_aborts_when_entry_exists(
  hass: HomeAssistant,
) -> None:
  """Ensure the user flow aborts when the integration is already configured."""

  entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=DOMAIN)
  entry.add_to_hass(hass)

  result = await hass.config_entries.flow.async_init(
    DOMAIN,
    context={"source": "user"},
  )

  assert result["type"] == FlowResultType.ABORT
  assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_import_flow_normalizes_dog_id(
  hass: HomeAssistant,
) -> None:
  """Verify import flow normalizes dog identifiers."""

  result = await hass.config_entries.flow.async_init(
    DOMAIN,
    context={"source": "import"},
    data={
      CONF_DOGS: [
        {
          CONF_DOG_ID: "Buddy 1",
          CONF_DOG_NAME: "Buddy",
        }
      ]
    },
  )

  assert result["type"] == FlowResultType.CREATE_ENTRY
  dogs = result["data"][CONF_DOGS]
  assert dogs[0][DOG_ID_FIELD] == "buddy_1"
  assert dogs[0][DOG_NAME_FIELD] == "Buddy"
