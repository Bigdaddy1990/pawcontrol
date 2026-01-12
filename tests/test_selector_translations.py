"""Ensure selector translations cover select options used in flows."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_ROOT = PROJECT_ROOT / "custom_components" / "pawcontrol"


def _load_strings(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_selector_options_are_localized() -> None:
    strings = _load_strings(COMPONENT_ROOT / "strings.json")
    selectors = strings["selector"]["select"]

    en = _load_strings(COMPONENT_ROOT / "translations" / "en.json")["selector"][
        "select"
    ]
    de = _load_strings(COMPONENT_ROOT / "translations" / "de.json")["selector"][
        "select"
    ]

    required = {
        "activity_level": {
            "very_low",
            "low",
            "moderate",
            "high",
            "very_high",
        },
        "dog_size": {"toy", "small", "medium", "large", "giant"},
        "feeding_schedule": {"flexible", "strict", "custom"},
        "food_type": {"dry_food", "wet_food", "barf", "home_cooked", "mixed"},
        "gps_source": {"manual", "webhook", "mqtt", "tractive"},
        "import_export_action": {"export", "import"},
        "medication_frequency": {"daily", "twice_daily", "weekly", "as_needed"},
        "performance_mode": {"minimal", "balanced", "full"},
        "weather_entity": {"none"},
        "weather_notification_threshold": {"low", "moderate", "high"},
        "weight_goal": {"lose", "maintain", "gain"},
    }

    for key, option_keys in required.items():
        assert key in selectors
        assert option_keys.issubset(set(selectors[key]["options"]))
        assert option_keys.issubset(set(en[key]["options"]))
        assert option_keys.issubset(set(de[key]["options"]))
