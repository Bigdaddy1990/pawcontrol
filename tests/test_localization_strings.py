"""Ensure entity translation keys are defined in strings.json and translations."""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_ROOT = PROJECT_ROOT / "custom_components" / "pawcontrol"


def _load_strings(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_decorator_keys(path: Path, decorator: str) -> set[str]:
    pattern = rf"@{decorator}\\(\\\"([^\\\"]+)\\\"\\)"
    return set(re.findall(pattern, path.read_text(encoding="utf-8")))


def _extract_init_keys(path: Path) -> set[str]:
    pattern = r'dog_name,\\s*\\\"([a-z0-9_]+)\\\"'
    return set(re.findall(pattern, path.read_text(encoding="utf-8")))


def test_entity_translation_keys_are_defined() -> None:
    strings = _load_strings(COMPONENT_ROOT / "strings.json")
    entity = strings["entity"]

    sensor_keys = _extract_decorator_keys(COMPONENT_ROOT / "sensor.py", "register_sensor")
    binary_keys = _extract_decorator_keys(
        COMPONENT_ROOT / "binary_sensor.py", "register_binary_sensor"
    )
    button_keys = _extract_decorator_keys(COMPONENT_ROOT / "button.py", "register_button")
    number_keys = _extract_decorator_keys(COMPONENT_ROOT / "number.py", "register_number")
    select_keys = _extract_decorator_keys(COMPONENT_ROOT / "select.py", "register_select")

    text_keys = _extract_init_keys(COMPONENT_ROOT / "text.py")
    date_keys = _extract_init_keys(COMPONENT_ROOT / "date.py")
    datetime_keys = _extract_init_keys(COMPONENT_ROOT / "datetime.py")

    assert sensor_keys.issubset(set(entity["sensor"].keys()))
    assert binary_keys.issubset(set(entity["binary_sensor"].keys()))
    assert button_keys.issubset(set(entity["button"].keys()))
    assert number_keys.issubset(set(entity["number"].keys()))
    assert select_keys.issubset(set(entity["select"].keys()))

    assert text_keys.issubset(set(entity["text"].keys()))
    assert date_keys.issubset(set(entity["date"].keys()))
    assert datetime_keys.issubset(set(entity["datetime"].keys()))
    assert "gps" in entity["device_tracker"]


def test_translation_files_cover_new_entity_keys() -> None:
    strings = _load_strings(COMPONENT_ROOT / "strings.json")
    entity = strings["entity"]

    en = _load_strings(COMPONENT_ROOT / "translations" / "en.json")["entity"]
    de = _load_strings(COMPONENT_ROOT / "translations" / "de.json")["entity"]

    for section in ("text", "date", "datetime"):
        keys = set(entity[section].keys())
        assert keys.issubset(set(en[section].keys()))
        assert keys.issubset(set(de[section].keys()))

    sensor_keys = {
        "activity_score",
        "body_condition_score",
        "calorie_goal_progress",
        "calories_burned_today",
        "current_walk_duration",
        "current_zone",
        "daily_portions",
        "feeding_recommendation",
        "food_consumption",
        "gps_battery_level",
        "health_status",
        "last_action",
        "last_vet_visit",
        "portions_today",
        "speed",
        "status",
        "total_feedings_today",
        "total_walk_distance",
        "walk_count_today",
        "walks_this_week",
        "walks_today",
        "weight_trend",
    }
    assert sensor_keys.issubset(set(en["sensor"].keys()))
    assert sensor_keys.issubset(set(de["sensor"].keys()))
