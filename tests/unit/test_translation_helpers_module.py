"""Unit tests for translation helper utilities."""

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
