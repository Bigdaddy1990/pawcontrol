"""Unit tests for the dashboard generator metadata exports."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    MODULE_NOTIFICATIONS,
)
from custom_components.pawcontrol.dashboard_generator import (
    DashboardViewSummary,
    PawControlDashboardGenerator,
)


def test_summarise_dashboard_views_marks_notifications() -> None:
    """The view summariser should flag the notifications module view."""

    dashboard_config = {
        "views": [
            {
                "path": "overview",
                "title": "Overview",
                "icon": "mdi:home",
                "cards": [{"type": "entities"}],
            },
            {
                "path": MODULE_NOTIFICATIONS,
                "title": "Notifications",
                "icon": "mdi:bell",
                "cards": [
                    {"type": "entities"},
                    {"type": "markdown"},
                ],
            },
        ]
    }

    summaries = PawControlDashboardGenerator._summarise_dashboard_views(dashboard_config)

    assert any(summary["path"] == "overview" for summary in summaries)

    notifications_summary = next(
        summary for summary in summaries if summary["path"] == MODULE_NOTIFICATIONS
    )

    assert notifications_summary["card_count"] == 2
    assert notifications_summary.get("module") == MODULE_NOTIFICATIONS
    assert notifications_summary.get("notifications") is True


@pytest.mark.asyncio
async def test_store_metadata_includes_notifications_view(
    mock_config_entry,
    tmp_path: Path,
) -> None:
    """Storing dashboard metadata should export the notifications view summary."""

    generator = object.__new__(PawControlDashboardGenerator)
    generator.entry = mock_config_entry
    generator._dashboards = {}
    generator._save_dashboard_metadata_async = AsyncMock(return_value=None)
    generator._performance_metrics = {
        "total_generations": 0,
        "avg_generation_time": 0.0,
        "cache_hits": 0,
        "cache_misses": 0,
        "file_operations": 0,
        "errors": 0,
    }

    dashboard_config = {
        "views": [
            {
                "path": "overview",
                "title": "Overview",
                "icon": "mdi:dog",
                "cards": [{"type": "entities"}],
            },
            {
                "path": MODULE_NOTIFICATIONS,
                "title": "Notifications",
                "icon": "mdi:bell",
                "cards": [
                    {"type": "entities"},
                    {"type": "markdown"},
                    {"type": "horizontal-stack"},
                ],
            },
        ]
    }

    dogs_config = [
        {
            CONF_DOG_ID: "buddy",
            CONF_DOG_NAME: "Buddy",
            "modules": {MODULE_NOTIFICATIONS: True},
        }
    ]

    await generator._store_dashboard_metadata_batch(
        "pawcontrol-main",
        "Paw Control",
        str(tmp_path / "lovelace.pawcontrol-main"),
        dashboard_config,
        dogs_config,
        {"theme": "modern"},
    )

    metadata = generator.get_dashboard_info("pawcontrol-main")
    assert metadata is not None
    assert metadata["has_notifications_view"] is True

    views: list[DashboardViewSummary] = metadata["views"]
    assert any(view["path"] == MODULE_NOTIFICATIONS for view in views)
    notifications_view = next(
        view for view in views if view["path"] == MODULE_NOTIFICATIONS
    )
    assert notifications_view["card_count"] == 3
    assert notifications_view.get("notifications") is True


@pytest.mark.asyncio
async def test_validate_single_dashboard_rehydrates_notifications_view(
    tmp_path: Path,
) -> None:
    """Stored dashboards missing metadata should be refreshed during validation."""

    generator = object.__new__(PawControlDashboardGenerator)

    dashboard_file = tmp_path / "lovelace.test-dashboard"
    config_payload = {
        "views": [
            {
                "path": "overview",
                "title": "Overview",
                "icon": "mdi:dog",
                "cards": [{"type": "entities"}],
            },
            {
                "path": MODULE_NOTIFICATIONS,
                "title": "Notifications",
                "icon": "mdi:bell",
                "cards": [
                    {"type": "entities"},
                    {"type": "markdown"},
                ],
            },
        ]
    }
    dashboard_file.write_text(
        json.dumps({"data": {"config": config_payload}}, ensure_ascii=False),
        encoding="utf-8",
    )

    dashboard_info = {
        "path": str(dashboard_file),
        "title": "Paw Control",
        "created": "2024-01-01T00:00:00+00:00",
        "type": "main",
        "version": 3,
    }

    valid, updated = await generator._validate_single_dashboard("test", dashboard_info)

    assert valid is True
    assert updated is True
    assert dashboard_info["has_notifications_view"] is True

    views = dashboard_info["views"]
    assert isinstance(views, list)
    notifications_view = next(
        view for view in views if view["path"] == MODULE_NOTIFICATIONS
    )
    assert notifications_view["card_count"] == 2
    assert notifications_view.get("module") == MODULE_NOTIFICATIONS
    assert notifications_view.get("notifications") is True
