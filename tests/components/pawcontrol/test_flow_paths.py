"""Component-level flow path tests for PawControl."""

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
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
  """Ensure the user flow aborts when the integration is already configured."""  # noqa: E111

  entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=DOMAIN)  # noqa: E111
  entry.add_to_hass(hass)  # noqa: E111

  result = await hass.config_entries.flow.async_init(  # noqa: E111
    DOMAIN,
    context={"source": "user"},
  )

  assert result["type"] == FlowResultType.ABORT  # noqa: E111
  assert result["reason"] == "already_configured"  # noqa: E111


@pytest.mark.asyncio
async def test_import_flow_normalizes_dog_id(
  hass: HomeAssistant,
) -> None:
  """Verify import flow normalizes dog identifiers."""  # noqa: E111

  result = await hass.config_entries.flow.async_init(  # noqa: E111
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

  assert result["type"] == FlowResultType.CREATE_ENTRY  # noqa: E111
  dogs = result["data"][CONF_DOGS]  # noqa: E111
  assert dogs[0][DOG_ID_FIELD] == "buddy_1"  # noqa: E111
  assert dogs[0][DOG_NAME_FIELD] == "Buddy"  # noqa: E111
