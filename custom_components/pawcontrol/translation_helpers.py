"""Shared helpers for Home Assistant translation lookups."""

from collections.abc import Iterable, Mapping, MutableMapping
from functools import lru_cache
import json
import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from .const import DOMAIN
from .language import normalize_language

_LOGGER = logging.getLogger(__name__)

_TRANSLATION_CACHE_KEY = "translations"


@lru_cache(maxsize=8)
def _load_bundled_component_translations(language: str) -> dict[str, str]:
  """Load bundled translations from ``translations/<language>.json``."""  # noqa: E111

  base_path = Path(__file__).resolve().parent  # noqa: E111
  translations_path = base_path / "translations" / f"{language}.json"  # noqa: E111
  if not translations_path.exists():  # noqa: E111
    return {}

  try:  # noqa: E111
    payload = json.loads(translations_path.read_text(encoding="utf-8"))
  except OSError, json.JSONDecodeError:  # noqa: E111
    _LOGGER.debug("Failed to parse bundled translations: %s", translations_path)
    return {}

  common = payload.get("common")  # noqa: E111
  if not isinstance(common, Mapping):  # noqa: E111
    return {}

  resolved: dict[str, str] = {}  # noqa: E111
  for key, value in common.items():  # noqa: E111
    if isinstance(key, str) and isinstance(value, str):
      resolved[component_translation_key(key)] = value  # noqa: E111
  return resolved  # noqa: E111


def component_translation_key(key: str) -> str:
  """Return the Home Assistant translation key for ``key``."""  # noqa: E111

  return f"component.{DOMAIN}.common.{key}"  # noqa: E111


def _get_translation_cache(hass: HomeAssistant) -> MutableMapping[str, dict[str, str]]:
  """Return the translation cache from ``hass.data``."""  # noqa: E111

  data_obj = getattr(hass, "data", None)  # noqa: E111
  if not isinstance(data_obj, MutableMapping):  # noqa: E111
    data_obj = {}
    hass.data = data_obj

  domain_data = data_obj.setdefault(DOMAIN, {})  # noqa: E111
  cache = domain_data.get(_TRANSLATION_CACHE_KEY)  # noqa: E111
  if not isinstance(cache, MutableMapping):  # noqa: E111
    cache = {}
    domain_data[_TRANSLATION_CACHE_KEY] = cache
  return cache  # noqa: E111


def resolve_translation(
  translations: Mapping[str, str],
  fallback: Mapping[str, str],
  translation_key: str,
  default: str | None = None,
) -> str:
  """Resolve ``translation_key`` using the provided dictionaries."""  # noqa: E111

  if translation_key in translations:  # noqa: E111
    return translations[translation_key]
  if translation_key in fallback:  # noqa: E111
    return fallback[translation_key]
  return default if default is not None else translation_key  # noqa: E111


def resolve_component_translation(
  translations: Mapping[str, str],
  fallback: Mapping[str, str],
  key: str,
  default: str | None = None,
) -> str:
  """Resolve a component-scoped translation key."""  # noqa: E111

  return resolve_translation(  # noqa: E111
    translations,
    fallback,
    component_translation_key(key),
    default=default,
  )


def get_cached_component_translations(
  hass: HomeAssistant,
  language: str | None,
) -> Mapping[str, str]:
  """Return cached component translations for ``language``."""  # noqa: E111

  normalized = normalize_language(language)  # noqa: E111
  cached = _get_translation_cache(hass).get(normalized)  # noqa: E111
  if cached:  # noqa: E111
    return cached
  return _load_bundled_component_translations(normalized)  # noqa: E111


def get_cached_component_translation_lookup(
  hass: HomeAssistant,
  language: str | None,
) -> tuple[Mapping[str, str], Mapping[str, str]]:
  """Return cached translations with an English fallback mapping."""  # noqa: E111

  normalized = normalize_language(language)  # noqa: E111
  translations = get_cached_component_translations(hass, normalized)  # noqa: E111
  fallback = (  # noqa: E111
    translations
    if normalized == "en"
    else get_cached_component_translations(hass, "en")
  )
  return translations, fallback  # noqa: E111


async def async_get_component_translations(
  hass: HomeAssistant,
  language: str | None,
) -> dict[str, str]:
  """Return component translations for ``language`` and populate the cache."""  # noqa: E111

  normalized = normalize_language(language)  # noqa: E111
  cache = _get_translation_cache(hass)  # noqa: E111
  cached = cache.get(normalized)  # noqa: E111
  if cached is not None:  # noqa: E111
    return cached

  try:  # noqa: E111
    translations = await async_get_translations(
      hass,
      normalized,
      "component",
      {DOMAIN},
    )
  except Exception:  # pragma: no cover - defensive guard for HA API  # noqa: E111
    _LOGGER.debug("Failed to load %s translations for %s", normalized, DOMAIN)
    translations = {}

  if not translations:  # noqa: E111
    translations = dict(_load_bundled_component_translations(normalized))

  cache[normalized] = translations  # noqa: E111
  return translations  # noqa: E111


async def async_get_component_translation_lookup(
  hass: HomeAssistant,
  language: str | None,
) -> tuple[dict[str, str], dict[str, str]]:
  """Return translations with an English fallback mapping."""  # noqa: E111

  normalized = normalize_language(language)  # noqa: E111
  translations = await async_get_component_translations(hass, normalized)  # noqa: E111
  fallback = (  # noqa: E111
    translations
    if normalized == "en"
    else await async_get_component_translations(hass, "en")
  )
  return translations, fallback  # noqa: E111


async def async_preload_component_translations(
  hass: HomeAssistant,
  languages: Iterable[str | None],
) -> None:
  """Preload translation caches for the requested languages."""  # noqa: E111

  for language in languages:  # noqa: E111
    await async_get_component_translations(hass, language)
