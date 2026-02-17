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
    """Load bundled translations from ``translations/<language>.json``."""
    base_path = Path(__file__).resolve().parent
    translations_path = base_path / "translations" / f"{language}.json"
    if not translations_path.exists():
        return {}

    try:
        payload = json.loads(translations_path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        _LOGGER.debug("Failed to parse bundled translations: %s", translations_path)
        return {}

    common = payload.get("common")
    if not isinstance(common, Mapping):
        return {}

    resolved: dict[str, str] = {}
    for key, value in common.items():
        if isinstance(key, str) and isinstance(value, str):
            resolved[component_translation_key(key)] = value
    return resolved
def component_translation_key(key: str) -> str:
    """Return the Home Assistant translation key for ``key``."""
    return f"component.{DOMAIN}.common.{key}"
def _get_translation_cache(hass: HomeAssistant) -> MutableMapping[str, dict[str, str]]:
    """Return the translation cache from ``hass.data``."""
    data_obj = getattr(hass, "data", None)
    if not isinstance(data_obj, MutableMapping):
        data_obj = {}
        hass.data = data_obj

    domain_data = data_obj.setdefault(DOMAIN, {})
    cache = domain_data.get(_TRANSLATION_CACHE_KEY)
    if not isinstance(cache, MutableMapping):
        cache = {}
        domain_data[_TRANSLATION_CACHE_KEY] = cache
    return cache
def resolve_translation(
    translations: Mapping[str, str],
    fallback: Mapping[str, str],
    translation_key: str,
    default: str | None = None,
) -> str:
    """Resolve ``translation_key`` using the provided dictionaries."""
    if translation_key in translations:
        return translations[translation_key]
    if translation_key in fallback:
        return fallback[translation_key]
    return default if default is not None else translation_key
def resolve_component_translation(
    translations: Mapping[str, str],
    fallback: Mapping[str, str],
    key: str,
    default: str | None = None,
) -> str:
    """Resolve a component-scoped translation key."""
    return resolve_translation(
        translations,
        fallback,
        component_translation_key(key),
        default=default,
    )


def get_cached_component_translations(
    hass: HomeAssistant,
    language: str | None,
) -> Mapping[str, str]:
    """Return cached component translations for ``language``."""
    normalized = normalize_language(language)
    cached = _get_translation_cache(hass).get(normalized)
    if cached:
        return cached
    return _load_bundled_component_translations(normalized)
def get_cached_component_translation_lookup(
    hass: HomeAssistant,
    language: str | None,
) -> tuple[Mapping[str, str], Mapping[str, str]]:
    """Return cached translations with an English fallback mapping."""
    normalized = normalize_language(language)
    translations = get_cached_component_translations(hass, normalized)
    fallback = (
        translations
        if normalized == "en"
        else get_cached_component_translations(hass, "en")
    )
    return translations, fallback
async def async_get_component_translations(
    hass: HomeAssistant,
    language: str | None,
) -> dict[str, str]:
    """Return component translations for ``language`` and populate the cache."""
    normalized = normalize_language(language)
    cache = _get_translation_cache(hass)
    cached = cache.get(normalized)
    if cached is not None:
        return cached

    try:
        translations = await async_get_translations(
            hass,
            normalized,
            "component",
            {DOMAIN},
        )
    except Exception:  # pragma: no cover - defensive guard for HA API
        _LOGGER.debug("Failed to load %s translations for %s", normalized, DOMAIN)
        translations = {}

    if not translations:
        translations = dict(_load_bundled_component_translations(normalized))

    cache[normalized] = translations
    return translations
async def async_get_component_translation_lookup(
    hass: HomeAssistant,
    language: str | None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Return translations with an English fallback mapping."""
    normalized = normalize_language(language)
    translations = await async_get_component_translations(hass, normalized)
    fallback = (
        translations
        if normalized == "en"
        else await async_get_component_translations(hass, "en")
    )
    return translations, fallback
async def async_preload_component_translations(
    hass: HomeAssistant,
    languages: Iterable[str | None],
) -> None:
    """Preload translation caches for the requested languages."""
    for language in languages:
        await async_get_component_translations(hass, language)
