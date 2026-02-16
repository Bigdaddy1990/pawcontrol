from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pawcontrol import diagnostics as diagnostics_mod
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.diagnostics import (
  SETUP_FLAG_LABEL_TRANSLATION_KEYS,
  SETUP_FLAG_LABELS,
  SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS,
  SETUP_FLAG_SOURCE_LABELS,
  SETUP_FLAGS_PANEL_DESCRIPTION,
  SETUP_FLAGS_PANEL_DESCRIPTION_TRANSLATION_KEY,
  SETUP_FLAGS_PANEL_TITLE,
  SETUP_FLAGS_PANEL_TITLE_TRANSLATION_KEY,
)
from custom_components.pawcontrol.types import SetupFlagsPanelPayload


@pytest.mark.asyncio
async def test_async_build_setup_flags_panel_returns_typed_payload(
  hass: HomeAssistant,
) -> None:
  """Setup flag diagnostics should emit a fully typed payload."""  # noqa: E111

  entry = MockConfigEntry(  # noqa: E111
    domain=DOMAIN,
    data={
      "enable_analytics": False,
      "enable_cloud_backup": False,
      "debug_logging": False,
    },
    options={
      "enable_analytics": True,
      "enable_cloud_backup": "ignored",
      "debug_logging": "invalid",
      "system_settings": {"enable_cloud_backup": False},
      "advanced_settings": {"debug_logging": True},
    },
    title="Doggo",
  )
  entry.add_to_hass(hass)  # noqa: E111

  translations = (  # noqa: E111
    "de",
    {
      "enable_analytics": "Analysen aktiviert",
      "debug_logging": "Protokollierung",
    },
    {
      "options": "Optionen (übersetzt)",
      "advanced_settings": "Erweitert (übersetzt)",
    },
    "Setup-Flags (übersetzt)",
    "Beschreibt den Setup-Status",
  )

  with patch(  # noqa: E111
    "custom_components.pawcontrol.diagnostics._async_resolve_setup_flag_translations",
    AsyncMock(return_value=translations),
  ):
    panel = await diagnostics_mod._async_build_setup_flags_panel(hass, entry)

  typed_panel: SetupFlagsPanelPayload = panel  # noqa: E111

  assert typed_panel["language"] == "de"  # noqa: E111
  assert typed_panel["title"] == translations[3]  # noqa: E111
  assert typed_panel["title_translation_key"] == SETUP_FLAGS_PANEL_TITLE_TRANSLATION_KEY  # noqa: E111
  assert typed_panel["title_default"] == SETUP_FLAGS_PANEL_TITLE  # noqa: E111
  assert typed_panel["description"] == translations[4]  # noqa: E111
  assert (  # noqa: E111
    typed_panel["description_translation_key"]
    == SETUP_FLAGS_PANEL_DESCRIPTION_TRANSLATION_KEY
  )
  assert typed_panel["description_default"] == SETUP_FLAGS_PANEL_DESCRIPTION  # noqa: E111

  assert typed_panel["enabled_count"] == 2  # noqa: E111
  assert typed_panel["disabled_count"] == 1  # noqa: E111
  assert typed_panel["source_breakdown"] == {  # noqa: E111
    "options": 1,
    "system_settings": 1,
    "advanced_settings": 1,
  }

  assert typed_panel["source_labels_default"] == SETUP_FLAG_SOURCE_LABELS  # noqa: E111
  assert typed_panel["source_label_translation_keys"] == (  # noqa: E111
    SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS
  )
  assert typed_panel["source_labels"] == {  # noqa: E111
    "options": "Optionen (übersetzt)",
    "advanced_settings": "Erweitert (übersetzt)",
  }

  flags = typed_panel["flags"]  # noqa: E111
  assert [flag["key"] for flag in flags] == [  # noqa: E111
    "enable_analytics",
    "enable_cloud_backup",
    "debug_logging",
  ]

  analytics_flag = flags[0]  # noqa: E111
  assert analytics_flag == {  # noqa: E111
    "key": "enable_analytics",
    "label": "Analysen aktiviert",
    "label_default": SETUP_FLAG_LABELS["enable_analytics"],
    "label_translation_key": SETUP_FLAG_LABEL_TRANSLATION_KEYS["enable_analytics"],
    "enabled": True,
    "source": "options",
    "source_label": "Optionen (übersetzt)",
    "source_label_default": SETUP_FLAG_SOURCE_LABELS["options"],
    "source_label_translation_key": SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS["options"],
  }

  backup_flag = flags[1]  # noqa: E111
  assert backup_flag == {  # noqa: E111
    "key": "enable_cloud_backup",
    "label": SETUP_FLAG_LABELS["enable_cloud_backup"],
    "label_default": SETUP_FLAG_LABELS["enable_cloud_backup"],
    "label_translation_key": SETUP_FLAG_LABEL_TRANSLATION_KEYS["enable_cloud_backup"],
    "enabled": False,
    "source": "system_settings",
    "source_label": SETUP_FLAG_SOURCE_LABELS["system_settings"],
    "source_label_default": SETUP_FLAG_SOURCE_LABELS["system_settings"],
    "source_label_translation_key": SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS[
      "system_settings"
    ],
  }

  debug_flag = flags[2]  # noqa: E111
  assert debug_flag == {  # noqa: E111
    "key": "debug_logging",
    "label": "Protokollierung",
    "label_default": SETUP_FLAG_LABELS["debug_logging"],
    "label_translation_key": SETUP_FLAG_LABEL_TRANSLATION_KEYS["debug_logging"],
    "enabled": True,
    "source": "advanced_settings",
    "source_label": "Erweitert (übersetzt)",
    "source_label_default": SETUP_FLAG_SOURCE_LABELS["advanced_settings"],
    "source_label_translation_key": SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS[
      "advanced_settings"
    ],
  }


@pytest.mark.asyncio
async def test_async_build_setup_flags_panel_supports_blueprint_and_disabled(
  hass: HomeAssistant,
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Setup flag diagnostics should handle blueprint and disabled sources."""  # noqa: E111

  entry = MockConfigEntry(  # noqa: E111
    domain=DOMAIN,
    data={},
    options={},
    title="Doggo",
  )
  entry.add_to_hass(hass)  # noqa: E111

  snapshots = {  # noqa: E111
    "enable_analytics": {"value": True, "source": "blueprint"},
    "enable_cloud_backup": {"value": False, "source": "disabled"},
    "debug_logging": {"value": False, "source": "default"},
  }
  monkeypatch.setattr(  # noqa: E111
    diagnostics_mod,
    "_collect_setup_flag_snapshots",
    lambda _: snapshots,
  )

  translations = ("en", {}, {}, SETUP_FLAGS_PANEL_TITLE, SETUP_FLAGS_PANEL_DESCRIPTION)  # noqa: E111
  with patch(  # noqa: E111
    "custom_components.pawcontrol.diagnostics._async_resolve_setup_flag_translations",
    AsyncMock(return_value=translations),
  ):
    panel = await diagnostics_mod._async_build_setup_flags_panel(hass, entry)

  flags_by_source = {flag["source"]: flag for flag in panel["flags"]}  # noqa: E111
  assert (  # noqa: E111
    flags_by_source["blueprint"]["source_label_default"]
    == (SETUP_FLAG_SOURCE_LABELS["blueprint"])
  )
  assert (  # noqa: E111
    flags_by_source["blueprint"]["source_label_translation_key"]
    == (SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS["blueprint"])
  )
  assert (  # noqa: E111
    flags_by_source["disabled"]["source_label_default"]
    == (SETUP_FLAG_SOURCE_LABELS["disabled"])
  )
  assert (  # noqa: E111
    flags_by_source["disabled"]["source_label_translation_key"]
    == (SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS["disabled"])
  )
