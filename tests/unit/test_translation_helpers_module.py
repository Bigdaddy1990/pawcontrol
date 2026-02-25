"""Unit tests for translation helper utilities."""

from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import translation_helpers


def test_resolve_translation_prefers_primary_then_fallback_then_default() -> None:
    """Resolution order should be deterministic."""
    assert translation_helpers.resolve_translation({"k": "v"}, {"k": "x"}, "k") == "v"
    assert translation_helpers.resolve_translation({}, {"k": "x"}, "k") == "x"
    assert translation_helpers.resolve_translation({}, {}, "k", default="d") == "d"
    assert translation_helpers.resolve_translation({}, {}, "k") == "k"


def test_get_translation_cache_initializes_hass_data() -> None:
    """The cache helper should initialize missing hass.data structures."""
    hass = SimpleNamespace(data=None)

    cache = translation_helpers._get_translation_cache(hass)

    assert cache == {}
    assert isinstance(hass.data, dict)
    assert translation_helpers.DOMAIN in hass.data


def test_get_translation_cache_replaces_non_mapping_cache_value() -> None:
    """The cache helper should replace malformed cache payloads."""
    hass = SimpleNamespace(data={"pawcontrol": {"translations": "invalid"}})

    cache = translation_helpers._get_translation_cache(hass)

    assert cache == {}
    assert hass.data["pawcontrol"]["translations"] is cache


def test_get_translation_cache_replaces_non_mapping_domain_data() -> None:
    """The cache helper should recover when domain data is malformed."""
    hass = SimpleNamespace(data={"pawcontrol": "invalid"})

    cache = translation_helpers._get_translation_cache(hass)

    assert cache == {}
    assert isinstance(hass.data["pawcontrol"], dict)
    assert hass.data["pawcontrol"]["translations"] is cache


def test_get_translation_cache_initializes_when_hass_has_no_data_attribute() -> None:
    """The cache helper should create hass.data when the attribute is absent."""

    class _Hass:
        pass

    hass = _Hass()

    cache = translation_helpers._get_translation_cache(hass)

    assert cache == {}
    assert isinstance(hass.data, dict)
    assert hass.data["pawcontrol"]["translations"] is cache


@pytest.mark.asyncio
async def test_async_get_component_translations_uses_ha_then_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fetched HA translations should be cached and reused."""
    hass = SimpleNamespace(data={})
    calls = 0

    async def fake_async_get_translations(
        *_args: object, **_kwargs: object
    ) -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"component.pawcontrol.common.title": "Titel"}

    monkeypatch.setattr(
        translation_helpers,
        "async_get_translations",
        fake_async_get_translations,
    )

    first = await translation_helpers.async_get_component_translations(hass, "de")
    second = await translation_helpers.async_get_component_translations(hass, "de")

    assert first == second
    assert calls == 1


@pytest.mark.asyncio
async def test_async_get_component_translations_falls_back_to_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bundled translations should be used when HA returns no entries."""
    hass = SimpleNamespace(data={})

    async def fake_async_get_translations(
        *_args: object, **_kwargs: object
    ) -> dict[str, str]:
        return {}

    monkeypatch.setattr(
        translation_helpers, "async_get_translations", fake_async_get_translations
    )
    monkeypatch.setattr(
        translation_helpers,
        "_load_bundled_component_translations",
        lambda language: {f"component.pawcontrol.common.{language}": "Bundled"},
    )

    result = await translation_helpers.async_get_component_translations(hass, "de")

    assert result == {"component.pawcontrol.common.de": "Bundled"}


@pytest.mark.asyncio
async def test_async_get_component_translations_handles_ha_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HA exceptions should also route to bundled fallback."""
    hass = SimpleNamespace(data={})

    async def fake_async_get_translations(
        *_args: object, **_kwargs: object
    ) -> dict[str, str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        translation_helpers, "async_get_translations", fake_async_get_translations
    )
    monkeypatch.setattr(
        translation_helpers,
        "_load_bundled_component_translations",
        lambda language: {"component.pawcontrol.common.fallback": language},
    )

    assert await translation_helpers.async_get_component_translations(hass, "de") == {
        "component.pawcontrol.common.fallback": "de"
    }


@pytest.mark.asyncio
async def test_async_get_component_translations_returns_cached_empty_mapping() -> None:
    """An explicitly cached empty mapping should be returned without refetching."""
    cached: dict[str, str] = {}
    hass = SimpleNamespace(data={"pawcontrol": {"translations": {"de": cached}}})

    result = await translation_helpers.async_get_component_translations(hass, "de")

    assert result is cached


def test_cached_lookup_uses_english_fallback() -> None:
    """Synchronous lookup should use English fallback for non-English language."""
    hass = SimpleNamespace(
        data={
            "pawcontrol": {"translations": {"de": {"k": "v"}, "en": {"fallback": "v"}}}
        }
    )

    translations, fallback = (
        translation_helpers.get_cached_component_translation_lookup(hass, "de")
    )

    assert translations == {"k": "v"}
    assert fallback == {"fallback": "v"}


def test_get_cached_component_translations_uses_bundled_when_cache_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing cache entries should fall back to bundled translations."""
    hass = SimpleNamespace(data={"pawcontrol": {"translations": {}}})
    monkeypatch.setattr(
        translation_helpers,
        "_load_bundled_component_translations",
        lambda language: {f"component.pawcontrol.common.{language}": "Bundled"},
    )

    assert translation_helpers.get_cached_component_translations(hass, "de") == {
        "component.pawcontrol.common.de": "Bundled"
    }


def test_get_cached_component_translations_prefers_non_empty_cached_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-empty cached mapping should be returned without bundled fallback."""
    cached = {"component.pawcontrol.common.de": "Gespeichert"}
    hass = SimpleNamespace(data={"pawcontrol": {"translations": {"de": cached}}})

    def _unexpected_loader(_language: str) -> dict[str, str]:
        raise AssertionError("Bundled loader should not be called")

    monkeypatch.setattr(
        translation_helpers,
        "_load_bundled_component_translations",
        _unexpected_loader,
    )

    assert translation_helpers.get_cached_component_translations(hass, "de") is cached


def test_get_cached_component_translations_uses_bundled_for_cached_empty_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty cached mapping should still trigger bundled fallback resolution."""
    hass = SimpleNamespace(data={"pawcontrol": {"translations": {"de": {}}}})
    monkeypatch.setattr(
        translation_helpers,
        "_load_bundled_component_translations",
        lambda language: {f"component.pawcontrol.common.{language}": "Bundled"},
    )

    assert translation_helpers.get_cached_component_translations(hass, "de") == {
        "component.pawcontrol.common.de": "Bundled"
    }


def test_cached_lookup_for_english_reuses_same_mapping() -> None:
    """English lookup should return the same mapping as fallback."""
    english = {"component.pawcontrol.common.title": "Title"}
    hass = SimpleNamespace(data={"pawcontrol": {"translations": {"en": english}}})

    translations, fallback = (
        translation_helpers.get_cached_component_translation_lookup(hass, "en")
    )

    assert translations is fallback


@pytest.mark.asyncio
async def test_async_translation_lookup_reuses_english_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When language is English, translations and fallback should be the same object."""
    hass = SimpleNamespace(data={})

    async def fake_get(*_args: object, **_kwargs: object) -> dict[str, str]:
        return {"component.pawcontrol.common.title": "Title"}

    monkeypatch.setattr(translation_helpers, "async_get_translations", fake_get)

    (
        translations,
        fallback,
    ) = await translation_helpers.async_get_component_translation_lookup(hass, "en")

    assert translations == fallback


@pytest.mark.asyncio
async def test_async_translation_lookup_fetches_english_fallback_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-English lookups should fetch the requested and English mapping."""
    hass = SimpleNamespace(data={})
    calls: list[str] = []

    async def fake_get(*_args: object, **_kwargs: object) -> dict[str, str]:
        language = _args[1]
        calls.append(language)
        return {f"component.pawcontrol.common.{language}": language}

    monkeypatch.setattr(translation_helpers, "async_get_translations", fake_get)

    (
        translations,
        fallback,
    ) = await translation_helpers.async_get_component_translation_lookup(
        hass,
        "de",
    )

    assert translations == {"component.pawcontrol.common.de": "de"}
    assert fallback == {"component.pawcontrol.common.en": "en"}
    assert calls == ["de", "en"]


@pytest.mark.asyncio
async def test_async_preload_component_translations_calls_each_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preload helper should request each provided language in order."""
    hass = SimpleNamespace(data={})
    seen: list[str | None] = []

    async def fake_get_component_translations(
        _hass: object, language: str | None
    ) -> dict[str, str]:
        seen.append(language)
        return {}

    monkeypatch.setattr(
        translation_helpers,
        "async_get_component_translations",
        fake_get_component_translations,
    )

    await translation_helpers.async_preload_component_translations(
        hass, ["de", None, "en"]
    )

    assert seen == ["de", None, "en"]


@pytest.mark.asyncio
async def test_async_preload_component_translations_noop_for_empty_languages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preload helper should not call translation fetch for empty iterables."""
    hass = SimpleNamespace(data={})
    called = False

    async def fake_get_component_translations(
        _hass: object, _language: str | None
    ) -> dict[str, str]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(
        translation_helpers,
        "async_get_component_translations",
        fake_get_component_translations,
    )

    await translation_helpers.async_preload_component_translations(hass, [])

    assert called is False


def test_load_bundled_component_translations_reads_only_common_strings(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bundled loader should map only string values from common section."""
    translation_helpers._load_bundled_component_translations.cache_clear()
    module_file = tmp_path / "translation_helpers.py"
    translations_dir = tmp_path / "translations"
    translations_dir.mkdir()
    (translations_dir / "de.json").write_text(
        '{"common": {"action": "Aktion", "nested": 5}}',
        encoding="utf-8",
    )
    module_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(translation_helpers, "__file__", str(module_file))

    result = translation_helpers._load_bundled_component_translations("de")

    assert result == {"component.pawcontrol.common.action": "Aktion"}


def test_load_bundled_component_translations_handles_missing_or_invalid_payload(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loader should return empty mappings for missing or malformed files."""
    translation_helpers._load_bundled_component_translations.cache_clear()
    module_file = tmp_path / "translation_helpers.py"
    translations_dir = tmp_path / "translations"
    translations_dir.mkdir()
    (translations_dir / "fr.json").write_text("not json", encoding="utf-8")
    (translations_dir / "it.json").write_text('{"common": []}', encoding="utf-8")
    module_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(translation_helpers, "__file__", str(module_file))

    assert translation_helpers._load_bundled_component_translations("es") == {}
    assert translation_helpers._load_bundled_component_translations("fr") == {}
    assert translation_helpers._load_bundled_component_translations("it") == {}


def test_load_bundled_component_translations_handles_oserror(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I/O errors while reading bundled files should return an empty mapping."""
    translation_helpers._load_bundled_component_translations.cache_clear()
    module_file = tmp_path / "translation_helpers.py"
    translations_dir = tmp_path / "translations"
    translations_dir.mkdir()
    (translations_dir / "de.json").write_text(
        '{"common": {"action": "Aktion"}}',
        encoding="utf-8",
    )
    module_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(translation_helpers, "__file__", str(module_file))

    def _raise_oserror(self: object, *_args: object, **_kwargs: object) -> str:
        raise OSError("denied")

    monkeypatch.setattr(translation_helpers.Path, "read_text", _raise_oserror)

    assert translation_helpers._load_bundled_component_translations("de") == {}


def test_component_translation_helpers_resolve_component_key() -> None:
    """Component key helper should produce namespaced keys and resolve them."""
    key = translation_helpers.component_translation_key("action")
    assert key == "component.pawcontrol.common.action"

    resolved = translation_helpers.resolve_component_translation(
        {key: "Aktion"}, {}, "action"
    )
    assert resolved == "Aktion"


def test_resolve_component_translation_uses_default_when_key_missing() -> None:
    """Component lookup should return default text for missing translation keys."""
    resolved = translation_helpers.resolve_component_translation(
        {}, {}, "action", "Run"
    )

    assert resolved == "Run"
