from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
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
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.asyncio
async def test_async_build_setup_flags_panel_returns_typed_payload(
    hass: HomeAssistant,
) -> None:
    """Setup flag diagnostics should emit a fully typed payload."""

    entry = MockConfigEntry(
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
    entry.add_to_hass(hass)

    translations = (
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

    with patch(
        "custom_components.pawcontrol.diagnostics._async_resolve_setup_flag_translations",
        AsyncMock(return_value=translations),
    ):
        panel = await diagnostics_mod._async_build_setup_flags_panel(hass, entry)

    typed_panel: SetupFlagsPanelPayload = panel

    assert typed_panel["language"] == "de"
    assert typed_panel["title"] == translations[3]
    assert (
        typed_panel["title_translation_key"]
        == SETUP_FLAGS_PANEL_TITLE_TRANSLATION_KEY
    )
    assert typed_panel["title_default"] == SETUP_FLAGS_PANEL_TITLE
    assert typed_panel["description"] == translations[4]
    assert (
        typed_panel["description_translation_key"]
        == SETUP_FLAGS_PANEL_DESCRIPTION_TRANSLATION_KEY
    )
    assert typed_panel["description_default"] == SETUP_FLAGS_PANEL_DESCRIPTION

    assert typed_panel["enabled_count"] == 2
    assert typed_panel["disabled_count"] == 1
    assert typed_panel["source_breakdown"] == {
        "options": 1,
        "system_settings": 1,
        "advanced_settings": 1,
    }

    assert typed_panel["source_labels_default"] == SETUP_FLAG_SOURCE_LABELS
    assert typed_panel["source_label_translation_keys"] == (
        SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS
    )
    assert typed_panel["source_labels"] == {
        "options": "Optionen (übersetzt)",
        "advanced_settings": "Erweitert (übersetzt)",
    }

    flags = typed_panel["flags"]
    assert [flag["key"] for flag in flags] == [
        "enable_analytics",
        "enable_cloud_backup",
        "debug_logging",
    ]

    analytics_flag = flags[0]
    assert analytics_flag == {
        "key": "enable_analytics",
        "label": "Analysen aktiviert",
        "label_default": SETUP_FLAG_LABELS["enable_analytics"],
        "label_translation_key": SETUP_FLAG_LABEL_TRANSLATION_KEYS[
            "enable_analytics"
        ],
        "enabled": True,
        "source": "options",
        "source_label": "Optionen (übersetzt)",
        "source_label_default": SETUP_FLAG_SOURCE_LABELS["options"],
        "source_label_translation_key": SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS[
            "options"
        ],
    }

    backup_flag = flags[1]
    assert backup_flag == {
        "key": "enable_cloud_backup",
        "label": SETUP_FLAG_LABELS["enable_cloud_backup"],
        "label_default": SETUP_FLAG_LABELS["enable_cloud_backup"],
        "label_translation_key": SETUP_FLAG_LABEL_TRANSLATION_KEYS[
            "enable_cloud_backup"
        ],
        "enabled": False,
        "source": "system_settings",
        "source_label": SETUP_FLAG_SOURCE_LABELS["system_settings"],
        "source_label_default": SETUP_FLAG_SOURCE_LABELS["system_settings"],
        "source_label_translation_key": SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS[
            "system_settings"
        ],
    }

    debug_flag = flags[2]
    assert debug_flag == {
        "key": "debug_logging",
        "label": "Protokollierung",
        "label_default": SETUP_FLAG_LABELS["debug_logging"],
        "label_translation_key": SETUP_FLAG_LABEL_TRANSLATION_KEYS[
            "debug_logging"
        ],
        "enabled": True,
        "source": "advanced_settings",
        "source_label": "Erweitert (übersetzt)",
        "source_label_default": SETUP_FLAG_SOURCE_LABELS["advanced_settings"],
        "source_label_translation_key": SETUP_FLAG_SOURCE_LABEL_TRANSLATION_KEYS[
            "advanced_settings"
        ],
    }
