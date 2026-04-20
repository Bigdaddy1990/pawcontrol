"""Deterministic branch coverage tests for translation_helpers without tmp_path."""

from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import translation_helpers as helpers


def _patch_path_io(
    monkeypatch: pytest.MonkeyPatch,
    *,
    exists: bool,
    payload: str | None = None,
    exc: Exception | None = None,
) -> None:
    monkeypatch.setattr(helpers.Path, "exists", lambda _self: exists)

    def _read_text(_self, *_args, **_kwargs):  # noqa: ANN001
        if exc is not None:
            raise exc
        return payload if payload is not None else '{"common": {"ok": "yes"}}'

    monkeypatch.setattr(helpers.Path, "read_text", _read_text)


@pytest.mark.unit
def test_cached_loader_covers_missing_io_json_and_common_shape_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cached loader should handle missing files and malformed payloads safely."""
    helpers._load_bundled_component_translations.cache_clear()

    _patch_path_io(monkeypatch, exists=False)
    assert helpers._load_bundled_component_translations_cached("x1", "C:/fake") == {}

    _patch_path_io(monkeypatch, exists=True, exc=OSError("denied"))
    assert helpers._load_bundled_component_translations_cached("x2", "C:/fake") == {}

    _patch_path_io(monkeypatch, exists=True, payload="{")
    assert helpers._load_bundled_component_translations_cached("x3", "C:/fake") == {}

    _patch_path_io(monkeypatch, exists=True, payload='{"common": ["invalid"]}')
    assert helpers._load_bundled_component_translations_cached("x4", "C:/fake") == {}

    _patch_path_io(
        monkeypatch,
        exists=True,
        payload='{"common": {"ok": "yes", "bad": 1, "null": null}}',
    )
    assert helpers._load_bundled_component_translations_cached("x5", "C:/fake") == {
        helpers.component_translation_key("ok"): "yes"
    }


@pytest.mark.unit
def test_loader_wrapper_delegates_to_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wrapper should forward language and resolved module base path."""
    called: list[tuple[str, str]] = []

    def _fake_cached(language: str, base_path: str) -> dict[str, str]:
        called.append((language, base_path))
        return {"k": "v"}

    monkeypatch.setattr(
        helpers,
        "_load_bundled_component_translations_cached",
        _fake_cached,
    )

    assert helpers._load_bundled_component_translations("de") == {"k": "v"}
    assert called and called[0][0] == "de"
    assert isinstance(called[0][1], str)


@pytest.mark.unit
def test_fresh_loader_covers_missing_io_json_and_common_shape_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh loader should mirror error handling without process cache."""
    monkeypatch.setattr(helpers, "__file__", "D:/virtual/translation_helpers.py")

    _patch_path_io(monkeypatch, exists=False)
    assert helpers.load_bundled_component_translations_fresh("x1") == {}

    _patch_path_io(monkeypatch, exists=True, exc=OSError("denied"))
    assert helpers.load_bundled_component_translations_fresh("x2") == {}

    _patch_path_io(monkeypatch, exists=True, payload="{")
    assert helpers.load_bundled_component_translations_fresh("x3") == {}

    _patch_path_io(monkeypatch, exists=True, payload='{"common": ["invalid"]}')
    assert helpers.load_bundled_component_translations_fresh("x4") == {}

    _patch_path_io(
        monkeypatch,
        exists=True,
        payload='{"common": {"ok": "yes", "bad": 1, "null": null}}',
    )
    assert helpers.load_bundled_component_translations_fresh("x5") == {
        helpers.component_translation_key("ok"): "yes"
    }


@pytest.mark.unit
def test_cache_initialization_and_resolution_helpers_cover_all_paths() -> None:
    """Cache creation and resolution helpers should cover fallback ordering."""
    hass_missing_data = SimpleNamespace(data="invalid")
    cache = helpers._get_translation_cache(hass_missing_data)
    assert isinstance(cache, dict)
    assert isinstance(hass_missing_data.data[helpers.DOMAIN], dict)

    hass_invalid_domain = SimpleNamespace(data={helpers.DOMAIN: "invalid"})
    cache = helpers._get_translation_cache(hass_invalid_domain)
    assert isinstance(cache, dict)
    assert isinstance(hass_invalid_domain.data[helpers.DOMAIN], dict)

    hass_invalid_cache = SimpleNamespace(data={helpers.DOMAIN: {"translations": "bad"}})
    cache = helpers._get_translation_cache(hass_invalid_cache)
    assert isinstance(cache, dict)
    assert hass_invalid_cache.data[helpers.DOMAIN]["translations"] is cache

    assert helpers.resolve_translation({"k": "v"}, {"k": "x"}, "k") == "v"
    assert helpers.resolve_translation({}, {"k": "x"}, "k") == "x"
    assert helpers.resolve_translation({}, {}, "k", default="d") == "d"
    assert helpers.resolve_translation({}, {}, "k") == "k"

    scoped = helpers.component_translation_key("walk")
    assert helpers.resolve_translation({"walk": "legacy"}, {}, scoped) == "legacy"
    assert helpers.resolve_translation({}, {"walk": "fallback"}, scoped) == "fallback"

    assert (
        helpers.resolve_component_translation(
            {helpers.component_translation_key("action"): "Aktion"},
            {},
            "action",
        )
        == "Aktion"
    )
    assert (
        helpers.resolve_component_translation(
            {},
            {"title": "Fallback title"},
            "profile_label_title",
        )
        == "Fallback title"
    )
    assert (
        helpers.resolve_component_translation(
            {},
            {},
            "missing",
            default="default",
        )
        == "default"
    )


@pytest.mark.unit
def test_cached_translation_lookup_paths_cover_english_and_non_english(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cached lookup helpers should normalize language and resolve fallbacks."""
    monkeypatch.setattr(
        helpers,
        "_load_bundled_component_translations",
        lambda language: {f"component.pawcontrol.common.{language}": language},
    )

    hass = SimpleNamespace(data={helpers.DOMAIN: {"translations": {"de": {"k": "v"}}}})
    assert helpers.get_cached_component_translations(hass, "de") == {"k": "v"}

    hass_empty = SimpleNamespace(
        data={helpers.DOMAIN: {"translations": {"de": {}, "en": {"fallback": "v"}}}}
    )
    assert helpers.get_cached_component_translations(hass_empty, "de") == {
        "component.pawcontrol.common.de": "de"
    }

    translations, fallback = helpers.get_cached_component_translation_lookup(
        hass_empty,
        "de",
    )
    assert translations == {"component.pawcontrol.common.de": "de"}
    assert fallback == {"fallback": "v"}

    hass_en = SimpleNamespace(
        data={helpers.DOMAIN: {"translations": {"en": {"component.pawcontrol.common.en": "en"}}}}
    )
    translations, fallback = helpers.get_cached_component_translation_lookup(
        hass_en,
        "en",
    )
    assert translations is fallback


@pytest.mark.asyncio
@pytest.mark.unit
async def test_async_translation_helpers_cover_cache_fetch_exception_and_preload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Async translation helpers should cache, fallback, and preload correctly."""
    calls: list[str] = []

    async def _fake_async_get_translations(
        _hass, language: str, *_args
    ) -> dict[str, str]:
        calls.append(language)
        if language == "de":
            return {"component.pawcontrol.common.de": "de"}
        if language == "fr":
            return {}
        raise RuntimeError("boom")

    monkeypatch.setattr(helpers, "async_get_translations", _fake_async_get_translations)
    monkeypatch.setattr(
        helpers,
        "_load_bundled_component_translations",
        lambda language: {f"component.pawcontrol.common.{language}": f"bundled-{language}"},
    )

    hass = SimpleNamespace(data={})

    de = await helpers.async_get_component_translations(hass, "de")
    assert de == {"component.pawcontrol.common.de": "de"}

    # Cached branch (``cached is not None``) should return without fetching again.
    hass.data[helpers.DOMAIN]["translations"]["de"] = {}
    assert await helpers.async_get_component_translations(hass, "de") == {}

    fr = await helpers.async_get_component_translations(hass, "fr")
    assert fr == {"component.pawcontrol.common.fr": "bundled-fr"}

    es = await helpers.async_get_component_translations(hass, "es")
    assert es == {"component.pawcontrol.common.es": "bundled-es"}

    de_lookup, en_fallback = await helpers.async_get_component_translation_lookup(
        hass,
        "de",
    )
    assert de_lookup == {}
    assert en_fallback == {"component.pawcontrol.common.en": "bundled-en"}

    en_lookup, en_lookup_fallback = await helpers.async_get_component_translation_lookup(
        hass,
        "en",
    )
    assert en_lookup is en_lookup_fallback

    await helpers.async_preload_component_translations(hass, ["de", None, "en"])
    assert "de" in calls

