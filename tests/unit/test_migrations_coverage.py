"""Targeted branch-coverage tests for ``migrations.py``."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import custom_components.pawcontrol.migrations as migrations
from custom_components.pawcontrol.const import (
    CONF_DOG_OPTIONS,
    CONF_DOGS,
    CONF_MODULES,
    CONFIG_ENTRY_VERSION,
)
from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.types import DOG_ID_FIELD, DOG_MODULES_FIELD, DOG_NAME_FIELD
from custom_components.pawcontrol.validation import InputCoercionError


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        (True, True),
        (False, False),
        (2, True),
        (0, False),
        (0.0, False),
        (3.14, True),
        ("", True),
        ("   ", True),
        ("disabled", False),
        ("off", False),
        ("false", False),
        ("enabled", True),
        ("yes", True),
        ("1", True),
        ("unsupported", False),
        ([], False),
        ([1], True),
    ],
)
def test_coerce_legacy_toggle_branches(value: object, expected: bool) -> None:
    """Legacy toggle coercion should cover scalar/string/fallback branches."""
    assert migrations._coerce_legacy_toggle(value) is expected


@pytest.mark.unit
def test_coerce_modules_payload_from_mapping_calls_type_coercer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mapping payloads should be delegated to ``ensure_dog_modules_config``."""
    captured: dict[str, object] = {}

    def _fake(payload: object) -> dict[str, bool]:
        captured["payload"] = payload
        return {"gps": True}

    monkeypatch.setattr(migrations, "ensure_dog_modules_config", _fake)
    payload = {"gps": 1}

    assert migrations._coerce_modules_payload(payload) == {"gps": True}
    assert captured["payload"] == payload


@pytest.mark.unit
def test_coerce_modules_payload_from_sequence_branches() -> None:
    """Sequence payloads should parse strings, dict aliases, and toggle values."""
    payload = [
        "gps",
        "unknown",
        {"module": "feeding", "enabled": "off"},
        {"key": "walk", "value": "yes"},
        {"name": "health", "enabled": 0},
        {"module": "notifications", "value": 1},
        {"module": "grooming"},
        {"module": "invalid", "enabled": True},
        {"value": True},
        5,
    ]

    result = migrations._coerce_modules_payload(payload)

    assert result == {
        "gps": True,
        "feeding": False,
        "walk": True,
        "health": False,
        "notifications": True,
        "grooming": True,
    }


@pytest.mark.unit
def test_coerce_modules_payload_invalid_sequence_and_non_sequence() -> None:
    """Unsupported payload shapes should yield ``None``."""
    assert migrations._coerce_modules_payload(["unknown", {"module": "invalid"}, 5]) is None
    assert migrations._coerce_modules_payload("gps") is None


@pytest.mark.unit
def test_resolve_dog_identifier_skips_invalid_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Identifier resolver should continue when normalization raises coercion errors."""

    def _normalize(value: object) -> str:
        text = str(value).strip().lower()
        if text == "bad":
            raise InputCoercionError("dog_id", value, "invalid")
        return text

    monkeypatch.setattr(migrations, "normalize_dog_id", _normalize)
    candidate = {DOG_ID_FIELD: "bad", "id": "  Good-Dog  "}

    assert migrations._resolve_dog_identifier(candidate, None) == "good-dog"


@pytest.mark.unit
def test_resolve_dog_identifier_fallback_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback IDs should normalize when possible and strip on coercion failure."""
    monkeypatch.setattr(
        migrations,
        "normalize_dog_id",
        lambda value: (_ for _ in ()).throw(
            InputCoercionError("dog_id", value, "invalid")
        )
        if str(value).strip() == "Raw Fallback"
        else str(value).strip().lower(),
    )

    assert migrations._resolve_dog_identifier({}, "  Alpha  ") == "alpha"
    assert migrations._resolve_dog_identifier({}, "  Raw Fallback  ") == "Raw Fallback"
    assert migrations._resolve_dog_identifier({DOG_ID_FIELD: "   "}, None) is None


@pytest.mark.unit
def test_resolve_dog_identifier_continues_after_empty_normalized_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty normalized ID should continue scanning legacy keys."""
    monkeypatch.setattr(
        migrations,
        "normalize_dog_id",
        lambda value: "" if str(value).strip().lower() == "empty" else str(value).strip().lower(),
    )

    assert migrations._resolve_dog_identifier({DOG_ID_FIELD: "empty", "id": "Final"}, None) == "final"


@pytest.mark.unit
def test_normalize_dog_entry_non_mapping_and_missing_identifier() -> None:
    """Normalization should reject non-mapping payloads and entries without IDs."""
    assert migrations._normalize_dog_entry("invalid") is None
    assert migrations._normalize_dog_entry({"name": "Buddy"}) is None


@pytest.mark.unit
def test_normalize_dog_entry_name_fallback_and_module_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Name fallback and invalid module cleanup paths should be applied."""
    monkeypatch.setattr(migrations, "_resolve_dog_identifier", lambda *_args, **_kwargs: "buddy")
    monkeypatch.setattr(migrations, "_coerce_modules_payload", lambda _payload: None)

    def _validate_name(value: object, *, required: bool = False) -> str | None:
        if value == "bad":
            raise ValidationError("dog_name", value, "invalid")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    monkeypatch.setattr(migrations, "validate_dog_name", _validate_name)

    normalized = migrations._normalize_dog_entry(
        {
            DOG_NAME_FIELD: "bad",
            "name": " Legacy Name ",
            DOG_MODULES_FIELD: "legacy-string",
            5: "drop-me",
        },
    )

    assert normalized is not None
    assert normalized[DOG_ID_FIELD] == "buddy"
    assert normalized[DOG_NAME_FIELD] == "Legacy Name"
    assert DOG_MODULES_FIELD not in normalized
    assert "5" not in normalized


@pytest.mark.unit
def test_normalize_dog_entry_defaults_name_and_keeps_coerced_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing/invalid names should fall back to dog ID and preserve valid modules."""
    monkeypatch.setattr(migrations, "_resolve_dog_identifier", lambda *_args, **_kwargs: "buddy")
    monkeypatch.setattr(migrations, "_coerce_modules_payload", lambda _payload: {"gps": True})
    monkeypatch.setattr(migrations, "validate_dog_name", lambda *_args, **_kwargs: None)

    normalized = migrations._normalize_dog_entry({DOG_MODULES_FIELD: {"legacy": 1}})

    assert normalized is not None
    assert normalized[DOG_ID_FIELD] == "buddy"
    assert normalized[DOG_NAME_FIELD] == "buddy"
    assert normalized[DOG_MODULES_FIELD] == {"gps": True}


@pytest.mark.unit
def test_normalize_dog_entry_keeps_payload_when_modules_field_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entries without a modules payload should avoid module-pop cleanup branch."""
    monkeypatch.setattr(migrations, "_resolve_dog_identifier", lambda *_args, **_kwargs: "buddy")
    monkeypatch.setattr(migrations, "_coerce_modules_payload", lambda _payload: None)
    monkeypatch.setattr(migrations, "validate_dog_name", lambda *_args, **_kwargs: "Buddy")

    normalized = migrations._normalize_dog_entry({"name": "Buddy"})

    assert normalized is not None
    assert normalized[DOG_ID_FIELD] == "buddy"
    assert normalized[DOG_NAME_FIELD] == "Buddy"
    assert DOG_MODULES_FIELD not in normalized


@pytest.mark.unit
def test_normalize_dog_options_mapping_branch_and_key_filtering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mapping payload normalization should filter non-mappings and empty keys."""
    calls: list[str | None] = []
    monkeypatch.setattr(migrations, "normalize_dog_id", lambda value: str(value).strip().lower())

    def _ensure_entry(value: dict[str, object], *, dog_id: str | None = None) -> dict[str, object]:
        calls.append(dog_id)
        if value.get("drop"):
            return {"modules": {"gps": True}}
        if value.get("skip_entry"):
            return {}
        if value.get("override"):
            return {"dog_id": "manual-id", "source": "override"}
        if dog_id is None:
            return {}
        return {"dog_id": dog_id, "source": "from-id"}

    monkeypatch.setattr(migrations, "ensure_dog_options_entry", _ensure_entry)

    normalized = migrations._normalize_dog_options(
        {
            " Dog-One ": {"x": 1},
            "": {"drop": True},
            "Dog-Two": {"override": True},
            "dog-three": {"skip_entry": True},
            "skip": "not-a-mapping",
        },
    )

    assert normalized == {
        "dog-one": {"dog_id": "dog-one", "source": "from-id"},
        "manual-id": {"dog_id": "manual-id", "source": "override"},
    }
    assert calls == ["dog-one", None, "dog-two", "dog-three"]


@pytest.mark.unit
def test_normalize_dog_options_sequence_and_fallback_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sequence payload normalization should keep only entries with resolved IDs."""
    monkeypatch.setattr(migrations, "normalize_dog_id", lambda value: str(value).strip().lower())

    def _ensure_entry(value: dict[str, object], *, dog_id: str | None = None) -> dict[str, object]:
        if value.get("drop"):
            return {"notes": "missing-id"}
        if dog_id:
            return {"dog_id": dog_id, "source": "sequence"}
        return {}

    monkeypatch.setattr(migrations, "ensure_dog_options_entry", _ensure_entry)

    normalized = migrations._normalize_dog_options(
        [
            {DOG_ID_FIELD: " Rex ", "keep": True},
            {"keep": True},
            {"drop": True},
            "skip",
        ],
    )

    assert normalized == {"rex": {"dog_id": "rex", "source": "sequence"}}
    assert migrations._normalize_dog_options("legacy-string") == {}


@pytest.mark.unit
def test_migrate_v1_to_v2_mapping_modules_and_options_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v1->v2 migration should normalize dogs, apply legacy modules, and merge options."""
    seen_fallback_ids: list[str] = []

    def _normalize_entry(raw_entry: object, *, fallback_id: str | None = None) -> dict[str, object] | None:
        if fallback_id is None:
            return None
        seen_fallback_ids.append(fallback_id)
        if fallback_id == "first":
            return {DOG_ID_FIELD: "alpha", DOG_NAME_FIELD: "Alpha"}
        if fallback_id == "second":
            return {
                DOG_ID_FIELD: "beta",
                DOG_NAME_FIELD: "Beta",
                DOG_MODULES_FIELD: {"walk": False},
            }
        return None

    monkeypatch.setattr(migrations, "_normalize_dog_entry", _normalize_entry)
    monkeypatch.setattr(
        migrations,
        "_coerce_modules_payload",
        lambda payload: {"gps": True} if payload == {"legacy": True} else None,
    )

    def _normalize_options(payload: object) -> dict[str, dict[str, object]]:
        if payload == {"from_data": True}:
            return {"alpha": {"dog_id": "alpha", "source": "data"}}
        if payload == {"from_options": True}:
            return {
                "alpha": {"dog_id": "alpha", "source": "options"},
                "beta": {"dog_id": "beta", "source": "options"},
            }
        return {}

    monkeypatch.setattr(migrations, "_normalize_dog_options", _normalize_options)

    data = {
        CONF_DOGS: {"first": {"raw": 1}, "second": {"raw": 2}, "third": "invalid"},
        CONF_MODULES: {"legacy": True},
        CONF_DOG_OPTIONS: {"from_data": True},
    }
    options = {CONF_DOG_OPTIONS: {"from_options": True}}

    migrated_data, migrated_options = migrations._migrate_v1_to_v2(data, options)

    assert seen_fallback_ids == ["first", "second", "third"]
    assert CONF_MODULES not in migrated_data
    assert CONF_DOG_OPTIONS not in migrated_data
    assert migrated_data[CONF_DOGS] == [
        {
            DOG_ID_FIELD: "alpha",
            DOG_NAME_FIELD: "Alpha",
            DOG_MODULES_FIELD: {"gps": True},
        },
        {
            DOG_ID_FIELD: "beta",
            DOG_NAME_FIELD: "Beta",
            DOG_MODULES_FIELD: {"walk": False},
        },
    ]
    assert migrated_options[CONF_DOG_OPTIONS] == {
        "alpha": {"dog_id": "alpha", "source": "options"},
        "beta": {"dog_id": "beta", "source": "options"},
    }


@pytest.mark.unit
def test_migrate_v1_to_v2_sequence_without_normalized_dogs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no dogs normalize, legacy keys should still be popped without replacements."""
    seen_entries: list[object] = []
    monkeypatch.setattr(
        migrations,
        "_normalize_dog_entry",
        lambda raw, *, fallback_id=None: (seen_entries.append(raw), None)[1],
    )
    monkeypatch.setattr(migrations, "_coerce_modules_payload", lambda _payload: None)
    monkeypatch.setattr(migrations, "_normalize_dog_options", lambda _payload: {})

    original_dogs = [{"dog_id": "one"}, {"dog_id": "two"}]
    data = {
        CONF_DOGS: list(original_dogs),
        CONF_MODULES: "legacy-string",
        CONF_DOG_OPTIONS: [{"dog_id": "one"}],
    }
    options: dict[str, object] = {}

    migrated_data, migrated_options = migrations._migrate_v1_to_v2(data, options)

    assert seen_entries == original_dogs
    assert migrated_data[CONF_DOGS] == original_dogs
    assert CONF_MODULES not in migrated_data
    assert CONF_DOG_OPTIONS not in migrated_data
    assert migrated_options == {}


@pytest.mark.unit
def test_migrate_v1_to_v2_sequence_appends_normalized_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sequence dog payloads should append normalized entries when available."""
    monkeypatch.setattr(
        migrations,
        "_normalize_dog_entry",
        lambda raw, *, fallback_id=None: (
            {DOG_ID_FIELD: "alpha", DOG_NAME_FIELD: "Alpha"}
            if raw == {"candidate": 1}
            else None
        ),
    )
    monkeypatch.setattr(migrations, "_coerce_modules_payload", lambda _payload: None)
    monkeypatch.setattr(migrations, "_normalize_dog_options", lambda _payload: {})

    data = {CONF_DOGS: [{"candidate": 1}, {"candidate": 2}], CONF_MODULES: None}
    options: dict[str, object] = {}

    migrated_data, _migrated_options = migrations._migrate_v1_to_v2(data, options)

    assert migrated_data[CONF_DOGS] == [{DOG_ID_FIELD: "alpha", DOG_NAME_FIELD: "Alpha"}]


@pytest.mark.unit
def test_migrate_v1_to_v2_empty_sequence_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty sequence should hit the direct sequence->post-loop migration path."""
    monkeypatch.setattr(migrations, "_coerce_modules_payload", lambda _payload: None)
    monkeypatch.setattr(migrations, "_normalize_dog_options", lambda _payload: {})

    data = {CONF_DOGS: [], CONF_MODULES: "legacy"}
    options: dict[str, object] = {}

    migrated_data, migrated_options = migrations._migrate_v1_to_v2(data, options)

    assert migrated_data[CONF_DOGS] == []
    assert CONF_MODULES not in migrated_data
    assert migrated_options == {}


@pytest.mark.unit
def test_migrate_v1_to_v2_non_collection_dogs_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-mapping/non-sequence dog payloads should skip normalization branches."""
    monkeypatch.setattr(migrations, "_coerce_modules_payload", lambda _payload: None)
    monkeypatch.setattr(migrations, "_normalize_dog_options", lambda _payload: {})

    data = {CONF_DOGS: "legacy-string", CONF_MODULES: "legacy"}
    options: dict[str, object] = {}

    migrated_data, migrated_options = migrations._migrate_v1_to_v2(data, options)

    assert migrated_data[CONF_DOGS] == "legacy-string"
    assert CONF_MODULES not in migrated_data
    assert migrated_options == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_migrate_entry_rejects_future_entry_versions() -> None:
    """Migration must fail when entry version exceeds the supported version."""
    update_entry = Mock()
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update_entry))
    entry = SimpleNamespace(
        entry_id="entry-1",
        version=CONFIG_ENTRY_VERSION + 1,
        data={},
        options={},
    )

    assert await migrations.async_migrate_entry(hass, entry) is False
    update_entry.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_migrate_entry_runs_legacy_upgrade_and_updates_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy versions (<1 and v1) should migrate to v2 and call update."""
    update_entry = Mock()
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update_entry))
    entry = SimpleNamespace(
        entry_id="entry-2",
        version=0,
        data={"legacy": True},
        options={"old": True},
    )
    captured: dict[str, object] = {}

    def _migrate(data: dict[str, object], options: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
        captured["data_arg"] = data
        captured["options_arg"] = options
        assert data is not entry.data
        assert options is not entry.options
        return {"migrated": True}, {"options": True}

    monkeypatch.setattr(migrations, "_migrate_v1_to_v2", _migrate)

    assert await migrations.async_migrate_entry(hass, entry) is True
    assert captured["data_arg"] == {"legacy": True}
    assert captured["options_arg"] == {"old": True}
    update_entry.assert_called_once_with(
        entry,
        data={"migrated": True},
        options={"options": True},
        version=2,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_migrate_entry_noop_for_current_version() -> None:
    """Current versions should return success without mutating the entry."""
    update_entry = Mock()
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update_entry))
    entry = SimpleNamespace(
        entry_id="entry-3",
        version=CONFIG_ENTRY_VERSION,
        data={"already": "current"},
        options={"keep": True},
    )

    assert await migrations.async_migrate_entry(hass, entry) is True
    update_entry.assert_not_called()
