"""Unit tests for translation helper utilities."""

import json
from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import translation_helpers


@pytest.mark.parametrize(
    ("translations", "fallback", "key", "default", "expected"),
    [
        ({"alpha": "A"}, {"alpha": "fallback"}, "alpha", None, "A"),
        ({}, {"beta": "B"}, "beta", None, "B"),
        ({}, {}, "gamma", "G", "G"),
        ({}, {}, "delta", None, "delta"),
    ],
)
def test_resolve_translation(
    translations: dict[str, str],
    fallback: dict[str, str],
    key: str,
    default: str | None,
    expected: str,
) -> None:
    """Resolution prefers primary, then fallback, then explicit default."""
    assert (
        translation_helpers.resolve_translation(
            translations,
            fallback,
            key,
            default=default,
        )
        == expected
    )


def test_get_translation_cache_initializes_hass_data() -> None:
    """The cache helper should safely initialize missing hass.data structures."""
    hass = SimpleNamespace(data=None)

    cache = translation_helpers._get_translation_cache(hass)

    assert cache == {}
    assert isinstance(hass.data, dict)
    assert translation_helpers.DOMAIN in hass.data


@pytest.mark.asyncio
async def test_async_get_component_translations_uses_ha_then_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fetched HA translations are cached and reused by subsequent lookups."""
    hass = SimpleNamespace(data={})
    calls: list[str] = []

    async def fake_async_get_translations(
        *args: object,
        **kwargs: object,
    ) -> dict[str, str]:
        calls.append("called")
        return {"component.pawcontrol.common.title": "Titel"}

    monkeypatch.setattr(
        translation_helpers,
        "async_get_translations",
        fake_async_get_translations,
    )

    first = await translation_helpers.async_get_component_translations(hass, "de")
    second = await translation_helpers.async_get_component_translations(hass, "de")

    assert first == second
    assert calls == ["called"]


@pytest.mark.asyncio
async def test_async_get_component_translations_falls_back_to_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bundled translations are used when Home Assistant returns no entries."""
    hass = SimpleNamespace(data={})

    async def fake_async_get_translations(
        *args: object,
        **kwargs: object,
    ) -> dict[str, str]:
        return {}

    monkeypatch.setattr(
        translation_helpers,
        "async_get_translations",
        fake_async_get_translations,
    )
    monkeypatch.setattr(
        translation_helpers,
        "_load_bundled_component_translations",
        lambda language: {f"component.pawcontrol.common.{language}": "Bundled"},
    )

    result = await translation_helpers.async_get_component_translations(hass, "de")

    assert result == {"component.pawcontrol.common.de": "Bundled"}


def test_get_cached_component_translation_lookup_uses_english_fallback() -> None:
    """Lookup helper should return english fallback when language is non-english."""
    hass = SimpleNamespace(
        data={"pawcontrol": {"translations": {"de": {"k": "v"}, "en": {"e": "v"}}}}
    )

    translations, fallback = (
        translation_helpers.get_cached_component_translation_lookup(hass, "de")
    )

    assert translations == {"k": "v"}
    assert fallback == {"e": "v"}


def test_load_bundled_component_translations_handles_invalid_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Bundled translation loader should safely handle malformed payloads."""
    translation_helpers._load_bundled_component_translations.cache_clear()
    module_file = tmp_path / "translation_helpers.py"
    module_file.write_text("# marker", encoding="utf-8")
    translations_dir = tmp_path / "translations"
    translations_dir.mkdir()

    monkeypatch.setattr(translation_helpers, "__file__", str(module_file))

    assert translation_helpers._load_bundled_component_translations("de") == {}

    bad_json = translations_dir / "fr.json"
    bad_json.write_text("{", encoding="utf-8")
    assert translation_helpers._load_bundled_component_translations("fr") == {}

    non_mapping_common = translations_dir / "it.json"
    non_mapping_common.write_text(json.dumps({"common": "oops"}), encoding="utf-8")
    assert translation_helpers._load_bundled_component_translations("it") == {}


def test_load_bundled_component_translations_builds_component_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Bundled translation keys should be namespaced using component keys."""
    translation_helpers._load_bundled_component_translations.cache_clear()
    module_file = tmp_path / "translation_helpers.py"
    module_file.write_text("# marker", encoding="utf-8")
    translations_dir = tmp_path / "translations"
    translations_dir.mkdir()
    (translations_dir / "en.json").write_text(
        json.dumps({"common": {"title": "PawControl", "subtitle": "Home"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(translation_helpers, "__file__", str(module_file))

    result = translation_helpers._load_bundled_component_translations("en")

    assert result == {
        "component.pawcontrol.common.title": "PawControl",
        "component.pawcontrol.common.subtitle": "Home",
    }
    assert (
        translation_helpers.component_translation_key("title")
        == "component.pawcontrol.common.title"
    )


@pytest.mark.asyncio
async def test_async_get_component_translations_handles_ha_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exceptions from HA translation APIs should fall back to bundled entries."""
    hass = SimpleNamespace(data={})

    async def fake_async_get_translations(
        *args: object,
        **kwargs: object,
    ) -> dict[str, str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        translation_helpers,
        "async_get_translations",
        fake_async_get_translations,
    )
    monkeypatch.setattr(
        translation_helpers,
        "_load_bundled_component_translations",
        lambda language: {f"component.pawcontrol.common.{language}": "Bundled"},
    )

    result = await translation_helpers.async_get_component_translations(hass, "de")

    assert result == {"component.pawcontrol.common.de": "Bundled"}


@pytest.mark.asyncio
async def test_async_preload_component_translations_preloads_languages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preload helper should request translations for each requested language."""
    hass = SimpleNamespace(data={})
    calls: list[str | None] = []

    async def fake_get_component_translations(
        hass_obj: object,
        language: str | None,
    ) -> dict[str, str]:
        calls.append(language)
        return {}

    monkeypatch.setattr(
        translation_helpers,
        "async_get_component_translations",
        fake_get_component_translations,
    )

    await translation_helpers.async_preload_component_translations(
        hass,
        ["de", "en", None],
    )

    assert calls == ["de", "en", None]
