"""Ensure entity translation keys are defined in strings.json and translations."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from custom_components.pawcontrol.dashboard_templates import DASHBOARD_TRANSLATION_KEYS
from custom_components.pawcontrol.feeding_translations import (
  FEEDING_COMPLIANCE_TRANSLATION_KEYS,
)
from custom_components.pawcontrol.grooming_translations import (
  GROOMING_LABEL_TRANSLATION_KEYS,
  GROOMING_TEMPLATE_TRANSLATION_KEYS,
)
from custom_components.pawcontrol.weather_translations import (
  WEATHER_ALERT_KEYS,
  WEATHER_RECOMMENDATION_KEYS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_ROOT = PROJECT_ROOT / "custom_components" / "pawcontrol"


def _load_strings(path: Path) -> dict[str, object]:
  return json.loads(path.read_text(encoding="utf-8"))  # noqa: E111


def _extract_decorator_keys(path: Path, decorator: str) -> set[str]:
  tree = ast.parse(path.read_text(encoding="utf-8"))  # noqa: E111
  keys: set[str] = set()  # noqa: E111

  for node in ast.walk(tree):  # noqa: E111
    if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
      continue  # noqa: E111
    for item in node.decorator_list:
      if not isinstance(item, ast.Call):  # noqa: E111
        continue
      func = item.func  # noqa: E111
      if isinstance(func, ast.Attribute):  # noqa: E111
        name = func.attr
      elif isinstance(func, ast.Name):  # noqa: E111
        name = func.id
      else:  # noqa: E111
        continue
      if name != decorator:  # noqa: E111
        continue
      translation_key = _extract_call_arg(item, "translation_key", 0)  # noqa: E111
      if translation_key is not None:  # noqa: E111
        keys.add(translation_key)

  return keys  # noqa: E111


def _extract_call_arg(call: ast.Call, keyword_name: str, position: int) -> str | None:
  for keyword in call.keywords:  # noqa: E111
    if (
      keyword.arg == keyword_name
      and isinstance(keyword.value, ast.Constant)
      and isinstance(keyword.value.value, str)
    ):
      return keyword.value.value  # noqa: E111

  if len(call.args) > position and isinstance(call.args[position], ast.Constant):  # noqa: E111
    value = call.args[position].value
    if isinstance(value, str):
      return value  # noqa: E111

  return None  # noqa: E111


def _extract_init_keys(path: Path, *, base_class: str, keyword_name: str) -> set[str]:
  tree = ast.parse(path.read_text(encoding="utf-8"))  # noqa: E111
  keys: set[str] = set()  # noqa: E111

  for node in tree.body:  # noqa: E111
    if not isinstance(node, ast.ClassDef):
      continue  # noqa: E111
    base_names = {base.id for base in node.bases if isinstance(base, ast.Name)} | {
      base.attr for base in node.bases if isinstance(base, ast.Attribute)
    }
    if base_class not in base_names:
      continue  # noqa: E111

    for child in node.body:
      if not isinstance(child, ast.FunctionDef):  # noqa: E111
        continue
      if child.name != "__init__":  # noqa: E111
        continue
      for call in ast.walk(child):  # noqa: E111
        if not isinstance(call, ast.Call):
          continue  # noqa: E111
        if not isinstance(call.func, ast.Attribute):
          continue  # noqa: E111
        if call.func.attr != "__init__":
          continue  # noqa: E111
        if not isinstance(call.func.value, ast.Call):
          continue  # noqa: E111
        if not isinstance(call.func.value.func, ast.Name):
          continue  # noqa: E111
        if call.func.value.func.id != "super":
          continue  # noqa: E111
        translation_key = _extract_call_arg(call, keyword_name, 3)
        if translation_key is not None:
          keys.add(translation_key)  # noqa: E111

  return keys  # noqa: E111


def test_entity_translation_keys_are_defined() -> None:
  strings = _load_strings(COMPONENT_ROOT / "strings.json")  # noqa: E111
  entity = strings["entity"]  # noqa: E111

  sensor_keys = _extract_decorator_keys(  # noqa: E111
    COMPONENT_ROOT / "sensor.py",
    "register_sensor",
  )
  binary_keys = _extract_init_keys(  # noqa: E111
    COMPONENT_ROOT / "binary_sensor.py",
    base_class="PawControlBinarySensorBase",
    keyword_name="sensor_type",
  )
  button_keys = _extract_init_keys(  # noqa: E111
    COMPONENT_ROOT / "button.py",
    base_class="PawControlButtonBase",
    keyword_name="button_type",
  )
  number_keys = _extract_init_keys(  # noqa: E111
    # For numbers, prefer explicit `translation_key` but fall back to the
    # `number_type` positional argument to match the entity logic.
    COMPONENT_ROOT / "number.py",
    base_class="PawControlNumberBase",
    keyword_name="translation_key",
  )
  select_keys = _extract_init_keys(  # noqa: E111
    COMPONENT_ROOT / "select.py",
    base_class="PawControlSelectBase",
    keyword_name="select_type",
  )

  text_keys = _extract_init_keys(  # noqa: E111
    COMPONENT_ROOT / "text.py",
    base_class="PawControlTextBase",
    keyword_name="text_type",
  )
  date_keys = _extract_init_keys(  # noqa: E111
    COMPONENT_ROOT / "date.py",
    base_class="PawControlDateBase",
    keyword_name="date_type",
  )
  datetime_keys = _extract_init_keys(  # noqa: E111
    COMPONENT_ROOT / "datetime.py",
    base_class="PawControlDateTimeBase",
    keyword_name="datetime_type",
  )

  assert sensor_keys.issubset(set(entity["sensor"].keys()))  # noqa: E111
  assert binary_keys.issubset(set(entity["binary_sensor"].keys()))  # noqa: E111
  assert button_keys.issubset(set(entity["button"].keys()))  # noqa: E111
  assert number_keys.issubset(set(entity["number"].keys()))  # noqa: E111
  assert select_keys.issubset(set(entity["select"].keys()))  # noqa: E111

  assert text_keys.issubset(set(entity["text"].keys()))  # noqa: E111
  assert date_keys.issubset(set(entity["date"].keys()))  # noqa: E111
  assert datetime_keys.issubset(set(entity["datetime"].keys()))  # noqa: E111
  assert "gps" in entity["device_tracker"]  # noqa: E111


def test_translation_files_cover_new_entity_keys() -> None:
  strings = _load_strings(COMPONENT_ROOT / "strings.json")  # noqa: E111
  entity = strings["entity"]  # noqa: E111

  locales = {}  # noqa: E111
  for locale in ("en", "de", "es", "fr"):  # noqa: E111
    locales[locale] = _load_strings(COMPONENT_ROOT / "translations" / f"{locale}.json")[
      "entity"
    ]

  for section in ("text", "date", "datetime"):  # noqa: E111
    keys = set(entity[section].keys())
    for locale, data in locales.items():
      assert keys.issubset(set(data[section].keys())), locale  # noqa: E111

  sensor_keys = {  # noqa: E111
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
  for locale, data in locales.items():  # noqa: E111
    assert sensor_keys.issubset(set(data["sensor"].keys())), locale


def test_common_translation_keys_are_defined() -> None:
  strings = _load_strings(COMPONENT_ROOT / "strings.json")  # noqa: E111
  common = strings["common"]  # noqa: E111

  weather_keys = {  # noqa: E111
    f"weather_alert_{alert_key}_title" for alert_key in WEATHER_ALERT_KEYS
  } | {f"weather_alert_{alert_key}_message" for alert_key in WEATHER_ALERT_KEYS}
  weather_keys |= {  # noqa: E111
    f"weather_recommendation_{recommendation}"
    for recommendation in WEATHER_RECOMMENDATION_KEYS
  }

  expected_keys = (  # noqa: E111
    set(FEEDING_COMPLIANCE_TRANSLATION_KEYS.values())
    | set(GROOMING_LABEL_TRANSLATION_KEYS.values())
    | set(GROOMING_TEMPLATE_TRANSLATION_KEYS.values())
    | set(DASHBOARD_TRANSLATION_KEYS)
    | weather_keys
  )

  assert expected_keys.issubset(set(common.keys()))  # noqa: E111

  for locale in ("en", "de", "es", "fr"):  # noqa: E111
    locale_common = _load_strings(COMPONENT_ROOT / "translations" / f"{locale}.json")[
      "common"
    ]
    assert expected_keys.issubset(set(locale_common.keys())), locale
