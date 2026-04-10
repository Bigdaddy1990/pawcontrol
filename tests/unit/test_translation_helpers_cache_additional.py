"""Additional coverage tests for translation helper cache and async fallback paths."""

from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import translation_helpers as helpers


@pytest.mark.unit
def test_get_translation_cache_initializes_invalid_hass_data() -> None:
    hass = SimpleNamespace(data="invalid")

    cache = helpers._get_translation_cache(hass)

    assert isinstance(cache, dict)
    assert helpers.DOMAIN in hass.data
    assert hass.data[helpers.DOMAIN]["translations"] is cache


@pytest.mark.unit
def test_resolve_translation_legacy_key_fallback() -> None:
    full_key = helpers.component_translation_key("walk_status")

    resolved = helpers.resolve_translation(
        {"walk_status": "Walk status"},
        {},
        full_key,
    )

    assert resolved == "Walk status"


@pytest.mark.unit
def test_load_bundled_component_translations_cached_ignores_non_string_values(
    tmp_path,
) -> None:
    translations_dir = tmp_path / "translations"
    translations_dir.mkdir()
    (translations_dir / "en.json").write_text(
        '{"common": {"valid": "yes", "invalid": 5, "other": null}}',
        encoding="utf-8",
    )

    helpers._load_bundled_component_translations.cache_clear()
    resolved = helpers._load_bundled_component_translations_cached("en", str(tmp_path))

    assert resolved == {helpers.component_translation_key("valid"): "yes"}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_async_get_component_translations_uses_bundled_fallback_on_exception(
    monkeypatch,
) -> None:
    hass = SimpleNamespace(data={})

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(helpers, "async_get_translations", _raise)
    monkeypatch.setattr(
        helpers,
        "_load_bundled_component_translations",
        lambda _lang: {helpers.component_translation_key("status"): "OK"},
    )

    resolved = await helpers.async_get_component_translations(hass, "de")

    assert resolved == {helpers.component_translation_key("status"): "OK"}
    assert hass.data[helpers.DOMAIN]["translations"]["de"] == resolved


@pytest.mark.asyncio
@pytest.mark.unit
async def test_async_get_component_translation_lookup_reuses_same_mapping_for_en() -> None:
    hass = SimpleNamespace(data={})

    first = await helpers.async_get_component_translations(hass, "en")
    second, fallback = await helpers.async_get_component_translation_lookup(hass, "en")

    assert second == first
    assert fallback is second


@pytest.mark.asyncio
@pytest.mark.unit
async def test_async_preload_component_translations_populates_all_languages() -> None:
    hass = SimpleNamespace(data={})

    await helpers.async_preload_component_translations(hass, ["de", "en", None])

    cache = hass.data[helpers.DOMAIN]["translations"]
    assert "de" in cache
    assert "en" in cache
