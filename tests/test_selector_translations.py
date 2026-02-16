"""Ensure selector translations cover select options used in flows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_ROOT = PROJECT_ROOT / "custom_components" / "pawcontrol"


def _load_strings(path: Path) -> dict[str, object]:
  return json.loads(path.read_text(encoding="utf-8"))  # noqa: E111


def _select_options(selectors: dict[str, object], key: str) -> set[str]:
  entry = selectors[key]  # noqa: E111
  if isinstance(entry, dict):  # noqa: E111
    options = entry.get("options")
    if isinstance(options, dict):
      return set(options)  # noqa: E111
  return set(cast(dict[str, object], entry))  # noqa: E111


def test_selector_options_are_localized() -> None:
  strings = _load_strings(COMPONENT_ROOT / "strings.json")  # noqa: E111
  selectors = strings["selector"]  # noqa: E111

  en = _load_strings(COMPONENT_ROOT / "translations" / "en.json")["selector"]  # noqa: E111
  de = _load_strings(COMPONENT_ROOT / "translations" / "de.json")["selector"]  # noqa: E111

  required = {  # noqa: E111
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

  for key, option_keys in required.items():  # noqa: E111
    assert key in selectors
    assert option_keys.issubset(_select_options(selectors, key))
    assert option_keys.issubset(_select_options(en, key))
    assert option_keys.issubset(_select_options(de, key))
