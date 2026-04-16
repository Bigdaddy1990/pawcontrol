"""Setup-flag coverage tests without tmp_path fixture dependencies."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import custom_components.pawcontrol.options_flow_main as options_flow_main
from custom_components.pawcontrol.options_flow_main import PawControlOptionsFlow


class _ExecutorHass:
    """Minimal hass stub implementing async_add_executor_job."""

    async def async_add_executor_job(self, func: Any, *args: Any) -> Any:
        return func(*args)


def _workspace_temp_dir() -> Path:
    root = Path("pytest_tmp_local_setup_flags")
    root.mkdir(exist_ok=True)
    path = root / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    return path


def test_setup_flag_supported_languages_defaults_to_en_without_files() -> None:
    temp_dir = _workspace_temp_dir()
    try:
        translations_dir = temp_dir / "translations"
        translations_dir.mkdir()
        strings_path = temp_dir / "strings.json"

        languages = options_flow_main._resolve_setup_flag_supported_languages(
            translations_dir,
            strings_path,
        )

        assert languages == frozenset({"en"})
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_setup_flag_supported_languages_includes_strings_and_translation_files() -> (
    None
):
    temp_dir = _workspace_temp_dir()
    try:
        translations_dir = temp_dir / "translations"
        translations_dir.mkdir()
        (translations_dir / "de.json").write_text("{}", encoding="utf-8")
        (translations_dir / "fr.json").write_text("{}", encoding="utf-8")
        strings_path = temp_dir / "strings.json"
        strings_path.write_text("{}", encoding="utf-8")

        languages = options_flow_main._resolve_setup_flag_supported_languages(
            translations_dir,
            strings_path,
        )

        assert languages == frozenset({"de", "en", "fr"})
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_setup_flag_supported_languages_uses_translation_stems_without_strings() -> (
    None
):
    temp_dir = _workspace_temp_dir()
    try:
        translations_dir = temp_dir / "translations"
        translations_dir.mkdir()
        (translations_dir / "it.json").write_text("{}", encoding="utf-8")
        strings_path = temp_dir / "strings.json"

        languages = options_flow_main._resolve_setup_flag_supported_languages(
            translations_dir,
            strings_path,
        )

        assert languages == frozenset({"it"})
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_load_setup_flag_translations_from_mapping_handles_missing_common_and_invalid_entries() -> (
    None
):
    assert PawControlOptionsFlow._load_setup_flag_translations_from_mapping({}) == {}
    assert (
        PawControlOptionsFlow._load_setup_flag_translations_from_mapping(
            {"common": ["not", "mapping"]},
        )
        == {}
    )

    translations = PawControlOptionsFlow._load_setup_flag_translations_from_mapping(
        {
            "common": {
                "setup_flags_panel_flag_ready": "Ready",
                "setup_flags_panel_source_default": 99,
                4: "ignored-key",
            }
        },
    )
    assert translations == {"setup_flags_panel_flag_ready": "Ready"}


@pytest.mark.asyncio
async def test_translation_loaders_handle_missing_non_mapping_and_malformed_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    temp_dir = _workspace_temp_dir()
    hass = _ExecutorHass()
    try:
        missing = await PawControlOptionsFlow._load_setup_flag_translations_from_path(
            temp_dir / "missing.json",
            hass,
        )
        assert missing == {}

        non_mapping_path = temp_dir / "list.json"
        non_mapping_path.write_text(
            json.dumps(["not", "a", "mapping"]), encoding="utf-8"
        )
        non_mapping = (
            await PawControlOptionsFlow._load_setup_flag_translations_from_path(
                non_mapping_path,
                hass,
            )
        )
        assert non_mapping == {}

        malformed_path = temp_dir / "broken.json"
        malformed_path.write_text("{", encoding="utf-8")
        with caplog.at_level(
            "WARNING",
            logger="custom_components.pawcontrol.options_flow_main",
        ):
            malformed = (
                await PawControlOptionsFlow._load_setup_flag_translations_from_path(
                    malformed_path,
                    hass,
                )
            )
        assert malformed == {}
        assert "Failed to parse setup flag translations" in caplog.text

        assert (
            PawControlOptionsFlow._load_setup_flag_translations_from_path_sync(
                temp_dir / "missing-sync.json"
            )
            == {}
        )
        assert (
            PawControlOptionsFlow._load_setup_flag_translations_from_path_sync(
                non_mapping_path
            )
            == {}
        )
        with caplog.at_level(
            "WARNING",
            logger="custom_components.pawcontrol.options_flow_main",
        ):
            malformed_sync = (
                PawControlOptionsFlow._load_setup_flag_translations_from_path_sync(
                    malformed_path
                )
            )
        assert malformed_sync == {}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_translation_loaders_return_filtered_mapping_for_valid_json() -> None:
    temp_dir = _workspace_temp_dir()
    hass = _ExecutorHass()
    try:
        valid_path = temp_dir / "valid.json"
        valid_path.write_text(
            json.dumps(
                {
                    "common": {
                        "setup_flags_panel_flag_ready": "Ready",
                        "manual_event_source_badge_default": "Default",
                        "unrelated_key": "skip",
                    }
                },
            ),
            encoding="utf-8",
        )

        async_result = (
            await PawControlOptionsFlow._load_setup_flag_translations_from_path(
                valid_path,
                hass,
            )
        )
        sync_result = (
            PawControlOptionsFlow._load_setup_flag_translations_from_path_sync(
                valid_path,
            )
        )

        assert async_result == {
            "setup_flags_panel_flag_ready": "Ready",
            "manual_event_source_badge_default": "Default",
        }
        assert sync_result == async_result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_setup_flag_translation_lookup_merges_and_caches_without_tmp_path() -> (
    None
):
    temp_dir = _workspace_temp_dir()
    try:
        strings_path = temp_dir / "strings.json"
        strings_path.write_text(
            json.dumps({
                "common": {
                    "setup_flags_panel_flag_ready": "Ready",
                    "manual_event_source_badge_default": "Default",
                }
            }),
            encoding="utf-8",
        )
        translations_dir = temp_dir / "translations"
        translations_dir.mkdir()
        (translations_dir / "es.json").write_text(
            json.dumps({
                "common": {
                    "setup_flags_panel_flag_ready": "Listo",
                    "setup_flags_panel_source_default": "Predeterminado",
                }
            }),
            encoding="utf-8",
        )

        original_en = PawControlOptionsFlow._SETUP_FLAG_EN_TRANSLATIONS
        original_cache = dict(PawControlOptionsFlow._SETUP_FLAG_TRANSLATION_CACHE)
        try:
            PawControlOptionsFlow._SETUP_FLAG_EN_TRANSLATIONS = None
            PawControlOptionsFlow._SETUP_FLAG_TRANSLATION_CACHE.clear()

            with (
                pytest.MonkeyPatch.context() as mp,
            ):
                mp.setattr(PawControlOptionsFlow, "_STRINGS_PATH", strings_path)
                mp.setattr(PawControlOptionsFlow, "_TRANSLATIONS_DIR", translations_dir)

                sync_translations = (
                    PawControlOptionsFlow._setup_flag_translations_for_language("es")
                )
                sync_cached = (
                    PawControlOptionsFlow._setup_flag_translations_for_language("es")
                )
                async_translations = await PawControlOptionsFlow._async_setup_flag_translations_for_language(
                    "es",
                    _ExecutorHass(),
                )
                async_cached = await PawControlOptionsFlow._async_setup_flag_translations_for_language(
                    "es",
                    _ExecutorHass(),
                )
        finally:
            PawControlOptionsFlow._SETUP_FLAG_EN_TRANSLATIONS = original_en
            PawControlOptionsFlow._SETUP_FLAG_TRANSLATION_CACHE.clear()
            PawControlOptionsFlow._SETUP_FLAG_TRANSLATION_CACHE.update(original_cache)

        assert sync_translations["setup_flags_panel_flag_ready"] == "Listo"
        assert sync_translations["manual_event_source_badge_default"] == "Default"
        assert sync_translations["setup_flags_panel_source_default"] == "Predeterminado"
        assert sync_cached is sync_translations
        assert async_translations is async_cached
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_async_setup_flag_translations_initializes_base_and_overlay_without_sync() -> (
    None
):
    temp_dir = _workspace_temp_dir()
    try:
        strings_path = temp_dir / "strings.json"
        strings_path.write_text(
            json.dumps({
                "common": {
                    "setup_flags_panel_flag_ready": "Ready",
                    "manual_event_source_badge_default": "Default",
                }
            }),
            encoding="utf-8",
        )
        translations_dir = temp_dir / "translations"
        translations_dir.mkdir()
        (translations_dir / "pt.json").write_text(
            json.dumps({
                "common": {
                    "setup_flags_panel_flag_ready": "Pronto",
                    "setup_flags_panel_source_default": "Padrão",
                }
            }),
            encoding="utf-8",
        )

        original_en = PawControlOptionsFlow._SETUP_FLAG_EN_TRANSLATIONS
        original_cache = dict(PawControlOptionsFlow._SETUP_FLAG_TRANSLATION_CACHE)
        try:
            PawControlOptionsFlow._SETUP_FLAG_EN_TRANSLATIONS = None
            PawControlOptionsFlow._SETUP_FLAG_TRANSLATION_CACHE.clear()

            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(PawControlOptionsFlow, "_STRINGS_PATH", strings_path)
                mp.setattr(PawControlOptionsFlow, "_TRANSLATIONS_DIR", translations_dir)

                first = await PawControlOptionsFlow._async_setup_flag_translations_for_language(
                    "pt",
                    _ExecutorHass(),
                )
                second = await PawControlOptionsFlow._async_setup_flag_translations_for_language(
                    "pt",
                    _ExecutorHass(),
                )
        finally:
            PawControlOptionsFlow._SETUP_FLAG_EN_TRANSLATIONS = original_en
            PawControlOptionsFlow._SETUP_FLAG_TRANSLATION_CACHE.clear()
            PawControlOptionsFlow._SETUP_FLAG_TRANSLATION_CACHE.update(original_cache)

        assert first["setup_flags_panel_flag_ready"] == "Pronto"
        assert first["manual_event_source_badge_default"] == "Default"
        assert first["setup_flags_panel_source_default"] == "Padrão"
        assert second is first
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_determine_language_defaults_to_en_without_hass() -> None:
    flow = PawControlOptionsFlow()
    flow.hass = None

    assert flow._determine_language() == "en"


def test_determine_language_handles_hass_without_config_object() -> None:
    flow = PawControlOptionsFlow()
    flow.hass = SimpleNamespace(config=None)

    assert flow._determine_language() == "en"


@pytest.mark.asyncio
async def test_async_prepare_setup_flag_translations_returns_for_non_homeassistant_hass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = PawControlOptionsFlow()
    flow.hass = object()
    loader = AsyncMock()
    monkeypatch.setattr(flow, "_async_setup_flag_translations_for_language", loader)

    await flow._async_prepare_setup_flag_translations()

    loader.assert_not_awaited()


def test_collect_manual_event_sources_handles_empty_default_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = PawControlOptionsFlow()
    monkeypatch.setattr(flow, "_current_options", lambda: {})
    monkeypatch.setattr(flow, "_manual_events_snapshot", lambda: None)

    def _normalise(value: Any) -> str | None:
        if value == options_flow_main.DEFAULT_MANUAL_GUARD_EVENT:
            return ""
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return None

    monkeypatch.setattr(flow, "_normalise_manual_event_value", _normalise)

    sources = flow._collect_manual_event_sources(
        "manual_guard_event",
        {},
        manual_snapshot=None,
    )

    assert options_flow_main.DEFAULT_MANUAL_GUARD_EVENT not in sources


def test_manual_event_choices_omit_disabled_badge_and_help_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = PawControlOptionsFlow()
    monkeypatch.setattr(flow, "_determine_language", lambda: "en")
    monkeypatch.setattr(
        flow,
        "_setup_flag_translation",
        lambda key, *, language: f"{language}:{key}",
    )
    monkeypatch.setattr(flow, "_collect_manual_event_sources", lambda *_, **__: {})
    monkeypatch.setattr(PawControlOptionsFlow, "_MANUAL_SOURCE_BADGE_KEYS", {})
    monkeypatch.setattr(PawControlOptionsFlow, "_MANUAL_SOURCE_HELP_KEYS", {})

    options = flow._manual_event_choices(
        "manual_check_event",
        {},
        manual_snapshot=None,
    )

    disabled = options[0]
    assert disabled["value"] == ""
    assert "badge" not in disabled
    assert "help_text" not in disabled
