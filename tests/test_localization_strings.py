"""Ensure entity translation keys are defined in strings.json and translations."""

from __future__ import annotations

import ast
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_ROOT = PROJECT_ROOT / "custom_components" / "pawcontrol"


def _load_strings(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_decorator_keys(path: Path, decorator: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    keys: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for item in node.decorator_list:
            if not isinstance(item, ast.Call):
                continue
            func = item.func
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            else:
                continue
            if name != decorator:
                continue
            translation_key = _extract_call_arg(item, "translation_key", 0)
            if translation_key is not None:
                keys.add(translation_key)

    return keys


def _extract_call_arg(
    call: ast.Call, keyword_name: str, position: int
) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == keyword_name and isinstance(keyword.value, ast.Constant):
            if isinstance(keyword.value.value, str):
                return keyword.value.value

    if len(call.args) > position and isinstance(call.args[position], ast.Constant):
        value = call.args[position].value
        if isinstance(value, str):
            return value

    return None


def _extract_init_keys(
    path: Path, *, base_class: str, keyword_name: str
) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    keys: set[str] = set()

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        base_names = {
            base.id
            for base in node.bases
            if isinstance(base, ast.Name)
        } | {
            base.attr
            for base in node.bases
            if isinstance(base, ast.Attribute)
        }
        if base_class not in base_names:
            continue

        for child in node.body:
            if not isinstance(child, ast.FunctionDef):
                continue
            if child.name != "__init__":
                continue
            for call in ast.walk(child):
                if not isinstance(call, ast.Call):
                    continue
                if not isinstance(call.func, ast.Attribute):
                    continue
                if call.func.attr != "__init__":
                    continue
                if not isinstance(call.func.value, ast.Call):
                    continue
                if not isinstance(call.func.value.func, ast.Name):
                    continue
                if call.func.value.func.id != "super":
                    continue
                translation_key = _extract_call_arg(call, keyword_name, 3)
                if translation_key is not None:
                    keys.add(translation_key)

    return keys


def test_entity_translation_keys_are_defined() -> None:
    strings = _load_strings(COMPONENT_ROOT / "strings.json")
    entity = strings["entity"]

    sensor_keys = _extract_decorator_keys(
        COMPONENT_ROOT / "sensor.py", "register_sensor"
    )
    binary_keys = _extract_decorator_keys(
        COMPONENT_ROOT / "binary_sensor.py", "register_binary_sensor"
    )
    button_keys = _extract_decorator_keys(
        COMPONENT_ROOT / "button.py", "register_button"
    )
    number_keys = _extract_decorator_keys(
        COMPONENT_ROOT / "number.py", "register_number"
    )
    select_keys = _extract_decorator_keys(
        COMPONENT_ROOT / "select.py", "register_select"
    )

    text_keys = _extract_init_keys(
        COMPONENT_ROOT / "text.py",
        base_class="PawControlTextBase",
        keyword_name="text_type",
    )
    date_keys = _extract_init_keys(
        COMPONENT_ROOT / "date.py",
        base_class="PawControlDateBase",
        keyword_name="date_type",
    )
    datetime_keys = _extract_init_keys(
        COMPONENT_ROOT / "datetime.py",
        base_class="PawControlDateTimeBase",
        keyword_name="datetime_type",
    )

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
