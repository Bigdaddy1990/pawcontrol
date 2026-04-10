"""Tests for translation helper utilities."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.translation_helpers import (
    _get_translation_cache,
    _load_bundled_component_translations,
    async_get_component_translation_lookup,
    async_get_component_translations,
    async_preload_component_translations,
    component_translation_key,
    get_cached_component_translation_lookup,
    get_cached_component_translations,
    load_bundled_component_translations_fresh,
    resolve_component_translation,
    resolve_translation,
)


def test_component_key_and_resolution_priority() -> None:
    """Helper should prioritize dynamic translations over fallback/default values."""
    key = component_translation_key("walk")
    assert key == f"component.{DOMAIN}.common.walk"

    translations = {key: "Walk now"}
    fallback = {key: "Fallback walk"}
    assert (
        resolve_translation(translations, fallback, key, default="default")
        == "Walk now"
    )
    assert resolve_component_translation(translations, fallback, "walk") == "Walk now"

    assert resolve_translation({}, fallback, key, default="default") == "Fallback walk"
    assert resolve_translation({}, {}, key, default="default") == "default"
    assert resolve_translation({}, {}, key) == key


def test_resolve_translation_supports_legacy_unprefixed_keys() -> None:
    """Legacy unprefixed translations should still be resolved."""
    key = component_translation_key("feed")

    assert resolve_translation({"feed": "Feed now"}, {}, key) == "Feed now"
    assert resolve_translation({}, {"feed": "Fallback feed"}, key) == "Fallback feed"


def test_cache_initialization_for_non_mapping_hass_data() -> None:
    """Cache helper should always create a mutable domain cache."""
    hass = SimpleNamespace(data=None)

    cache = _get_translation_cache(hass)

    assert cache == {}
    assert isinstance(hass.data, dict)
    assert isinstance(hass.data[DOMAIN], dict)
    assert hass.data[DOMAIN]["translations"] is cache


def test_cache_replaces_non_mapping_domain_bucket() -> None:
    """Cache helper should repair invalid domain buckets before use."""
    hass = SimpleNamespace(data={DOMAIN: 42})

    cache = _get_translation_cache(hass)

    assert cache == {}
    assert isinstance(hass.data[DOMAIN], dict)
    assert hass.data[DOMAIN]["translations"] is cache


def test_cache_replaces_non_mapping_translation_cache_bucket() -> None:
    """Cache helper should repair invalid translation cache buckets before use."""
    hass = SimpleNamespace(data={DOMAIN: {"translations": 42}})

    cache = _get_translation_cache(hass)

    assert cache == {}
    assert isinstance(hass.data[DOMAIN]["translations"], dict)
    assert hass.data[DOMAIN]["translations"] is cache


def test_cached_component_translations_use_runtime_cache_and_bundled_fallback() -> None:
    """Lookup should prefer runtime cache and fallback to bundled data when missing."""
    _load_bundled_component_translations.cache_clear()

    hass = SimpleNamespace(data={DOMAIN: {"translations": {"en": {"x": "y"}}}})
    assert get_cached_component_translations(hass, "en") == {"x": "y"}

    bundled = get_cached_component_translations(hass, "xx")
    assert bundled == {}

    translations, fallback = get_cached_component_translation_lookup(hass, "de")
    assert translations
    assert fallback == {"x": "y"}


def test_cached_component_translation_lookup_uses_self_fallback_for_english() -> None:
    """English lookups should use the same mapping for translation and fallback."""
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                "translations": {"en": {component_translation_key("door"): "Door"}},
            },
        },
    )

    translations, fallback = get_cached_component_translation_lookup(hass, "EN")

    assert translations is fallback


def test_resolve_component_translation_uses_separator_candidates() -> None:
    """Resolution should include suffix candidates for known separator patterns."""
    translations = {"quiet_hours": "Quiet hours"}

    assert (
        resolve_component_translation(
            translations,
            {},
            "door_sensor_label_quiet_hours",
        )
        == "Quiet hours"
    )


def test_resolve_component_translation_checks_all_suffix_separators() -> None:
    """Known key suffix separators should resolve through stripped candidate keys."""
    translations = {
        "quiet_hours": "Quiet hours",
        "door_sensor": "Door sensor",
        "walk_state": "Walk state",
    }

    assert (
        resolve_component_translation(
            translations,
            {},
            "door_sensor_label_quiet_hours",
        )
        == "Quiet hours"
    )
    assert (
        resolve_component_translation(
            translations,
            {},
            "geo_fallback_door_sensor",
        )
        == "Door sensor"
    )
    assert (
        resolve_component_translation(
            translations,
            {},
            "summary_template_walk_state",
        )
        == "Walk state"
    )


def test_resolve_component_translation_returns_explicit_default() -> None:
    """Explicit defaults should win when no candidate key is present."""
    assert (
        resolve_component_translation({}, {}, "missing_label_value", default="Fallback")
        == "Fallback"
    )


def test_bundled_translation_loader_handles_invalid_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bundled translation loader should fail closed on invalid files."""
    _load_bundled_component_translations.cache_clear()

    monkeypatch.setattr("pathlib.Path.exists", lambda _self: True)
    monkeypatch.setattr(
        "pathlib.Path.read_text",
        lambda _self, encoding="utf-8": (_ for _ in ()).throw(OSError("boom")),
    )
    assert _load_bundled_component_translations("en") == {}

    _load_bundled_component_translations.cache_clear()
    monkeypatch.setattr(
        "pathlib.Path.read_text",
        lambda _self, encoding="utf-8": "{bad-json",
    )
    assert _load_bundled_component_translations("en") == {}

    _load_bundled_component_translations.cache_clear()
    monkeypatch.setattr("pathlib.Path.read_text", lambda _self, encoding="utf-8": "{}")
    assert _load_bundled_component_translations("en") == {}


def test_bundled_translation_loader_filters_non_string_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bundled translation loader should only keep string keys/values."""
    _load_bundled_component_translations.cache_clear()

    monkeypatch.setattr("pathlib.Path.exists", lambda _self: True)
    monkeypatch.setattr(
        "pathlib.Path.read_text",
        lambda _self, encoding="utf-8": json.dumps({
            "common": {
                "feed": "Feed",
                "invalid_value": 123,
            }
        }),
    )

    assert _load_bundled_component_translations("en") == {
        component_translation_key("feed"): "Feed",
    }


def test_fresh_bundled_translation_loader_handles_io_and_parse_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh loader should fail closed when translation files are unreadable."""
    monkeypatch.setattr("pathlib.Path.exists", lambda _self: True)
    monkeypatch.setattr(
        "pathlib.Path.read_text",
        lambda _self, encoding="utf-8": (_ for _ in ()).throw(OSError("boom")),
    )
    assert load_bundled_component_translations_fresh("en") == {}

    monkeypatch.setattr(
        "pathlib.Path.read_text",
        lambda _self, encoding="utf-8": "{bad-json",
    )
    assert load_bundled_component_translations_fresh("en") == {}


def test_fresh_bundled_translation_loader_handles_missing_or_invalid_common_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh loader should return an empty mapping for missing/invalid payloads."""
    monkeypatch.setattr("pathlib.Path.exists", lambda _self: False)
    assert load_bundled_component_translations_fresh("en") == {}

    monkeypatch.setattr("pathlib.Path.exists", lambda _self: True)
    monkeypatch.setattr(
        "pathlib.Path.read_text",
        lambda _self, encoding="utf-8": json.dumps({"common": ["not-a-mapping"]}),
    )
    assert load_bundled_component_translations_fresh("en") == {}


def test_fresh_bundled_translation_loader_returns_filtered_common_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh loader should only include valid string key/value pairs."""
    monkeypatch.setattr("pathlib.Path.exists", lambda _self: True)
    monkeypatch.setattr(
        "pathlib.Path.read_text",
        lambda _self, encoding="utf-8": json.dumps({
            "common": {
                "walk": "Walk now",
                "invalid_value": 1,
            }
        }),
    )

    assert load_bundled_component_translations_fresh("en") == {
        component_translation_key("walk"): "Walk now"
    }


@pytest.mark.asyncio
async def test_async_get_component_translations_caches_api_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Async helper should cache API responses by normalized language."""
    hass = SimpleNamespace(data={})
    fake_api = AsyncMock(return_value={component_translation_key("feed"): "Feed now"})
    monkeypatch.setattr(
        "custom_components.pawcontrol.translation_helpers.async_get_translations",
        fake_api,
    )

    first = await async_get_component_translations(hass, "EN")
    second = await async_get_component_translations(hass, "en")

    assert first == second
    assert fake_api.await_count == 1


@pytest.mark.asyncio
async def test_async_get_component_translations_falls_back_to_bundled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failures from HA translation API should return bundled translations."""
    hass = SimpleNamespace(data={})

    async def _boom(*_args: object, **_kwargs: object) -> dict[str, str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "custom_components.pawcontrol.translation_helpers.async_get_translations",
        _boom,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.translation_helpers._load_bundled_component_translations",
        lambda _lang: {component_translation_key("door"): "Door status"},
    )

    translations, fallback = await async_get_component_translation_lookup(hass, "de")
    assert translations == {component_translation_key("door"): "Door status"}
    assert fallback == {component_translation_key("door"): "Door status"}


@pytest.mark.asyncio
async def test_async_get_component_translations_keeps_cached_empty_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cached empty mapping should short-circuit API lookups."""
    hass = SimpleNamespace(data={DOMAIN: {"translations": {"en": {}}}})
    fake_api = AsyncMock(return_value={component_translation_key("feed"): "Feed now"})
    monkeypatch.setattr(
        "custom_components.pawcontrol.translation_helpers.async_get_translations",
        fake_api,
    )

    assert await async_get_component_translations(hass, "en") == {}
    fake_api.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_get_component_translations_uses_bundled_when_api_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty API response should fall back to bundled translations."""
    hass = SimpleNamespace(data={})

    async def _empty_api(*_args: object, **_kwargs: object) -> dict[str, str]:
        return {}

    monkeypatch.setattr(
        "custom_components.pawcontrol.translation_helpers.async_get_translations",
        _empty_api,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.translation_helpers._load_bundled_component_translations",
        lambda _lang: {component_translation_key("door"): "Door status"},
    )

    assert await async_get_component_translations(hass, "de") == {
        component_translation_key("door"): "Door status"
    }


@pytest.mark.asyncio
async def test_async_preload_component_translations_warms_requested_languages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preloading should normalize and cache each requested language."""
    hass = SimpleNamespace(data={})

    async def _fake_get_translations(
        *_args: object, **_kwargs: object
    ) -> dict[str, str]:
        return {}

    monkeypatch.setattr(
        "custom_components.pawcontrol.translation_helpers.async_get_translations",
        _fake_get_translations,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.translation_helpers._load_bundled_component_translations",
        lambda lang: {component_translation_key("lang"): lang},
    )

    await async_preload_component_translations(hass, ["EN", "de", None])

    cache = hass.data[DOMAIN]["translations"]
    assert cache["en"][component_translation_key("lang")] == "en"
    assert cache["de"][component_translation_key("lang")] == "de"
