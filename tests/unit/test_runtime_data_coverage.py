"""Comprehensive coverage tests for runtime_data.py."""

# ruff: noqa: D103

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.const import DOMAIN
import custom_components.pawcontrol.runtime_data as runtime_mod
from custom_components.pawcontrol.runtime_data import (
    RuntimeDataIncompatibleError,
    RuntimeDataUnavailableError,
    describe_runtime_store_status,
    get_runtime_data,
    pop_runtime_data,
    require_runtime_data,
    store_runtime_data,
)
from custom_components.pawcontrol.types import (
    DomainRuntimeStoreEntry,
    PawControlRuntimeData,
)


def _make_runtime_data(
    *,
    schema_version: int | None = None,
    created_version: int | None = None,
) -> PawControlRuntimeData:
    runtime = PawControlRuntimeData(
        coordinator=MagicMock(),
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
    )
    if schema_version is not None:
        runtime.schema_version = schema_version
    if created_version is not None:
        runtime.schema_created_version = created_version
    return runtime


def _make_entry(
    entry_id: str,
    *,
    domain: str = DOMAIN,
    runtime_data: PawControlRuntimeData | None = None,
    version: int | None = None,
    created_version: int | None = None,
) -> SimpleNamespace:
    entry = SimpleNamespace(entry_id=entry_id, domain=domain, runtime_data=runtime_data)
    if version is not None:
        setattr(entry, runtime_mod._ENTRY_VERSION_ATTR, version)
    if created_version is not None:
        setattr(entry, runtime_mod._ENTRY_CREATED_VERSION_ATTR, created_version)
    return entry


def _make_hass(
    *,
    data: object,
    entry: SimpleNamespace | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        data=data,
        config_entries=SimpleNamespace(async_get_entry=MagicMock(return_value=entry)),
    )


def test_resolve_entry_id_and_get_entry_paths() -> None:
    entry = _make_entry("entry-1")
    hass = _make_hass(data={}, entry=entry)

    assert runtime_mod._resolve_entry_id("entry-1") == "entry-1"
    assert runtime_mod._resolve_entry_id(entry) == "entry-1"
    assert runtime_mod._get_entry(hass, "entry-1") is entry
    assert runtime_mod._get_entry(hass, entry) is entry

    hass.config_entries.async_get_entry.return_value = _make_entry(
        "entry-2", domain="other_domain"
    )
    assert runtime_mod._get_entry(hass, "entry-2") is None
    hass.config_entries.async_get_entry.return_value = None
    assert runtime_mod._get_entry(hass, "missing") is None


def test_get_domain_store_initialization_and_normalization() -> None:
    hass_invalid = _make_hass(data="not-a-mapping")
    assert runtime_mod._get_domain_store(hass_invalid, create=False) is None
    created_store = runtime_mod._get_domain_store(hass_invalid, create=True)
    assert isinstance(created_store, dict)
    assert isinstance(hass_invalid.data, dict)

    hass_bad_domain = _make_hass(data={DOMAIN: "invalid"})
    assert runtime_mod._get_domain_store(hass_bad_domain, create=False) is None
    assert DOMAIN not in hass_bad_domain.data

    hass_bad_domain_create = _make_hass(data={DOMAIN: "invalid"})
    fixed_store = runtime_mod._get_domain_store(hass_bad_domain_create, create=True)
    assert isinstance(fixed_store, dict)
    assert isinstance(hass_bad_domain_create.data[DOMAIN], dict)


def test_as_runtime_data_and_coerce_version_helpers() -> None:
    runtime = _make_runtime_data()
    assert runtime_mod._as_runtime_data(runtime) is runtime
    assert runtime_mod._as_runtime_data(None) is None
    assert runtime_mod._as_runtime_data(object()) is None

    fake_runtime_cls = type("PawControlRuntimeData", (), {})
    assert runtime_mod._as_runtime_data(fake_runtime_cls()) is None

    assert runtime_mod._coerce_version(True) is None
    assert runtime_mod._coerce_version(2) == 2
    assert runtime_mod._coerce_version(0) is None


def test_stamp_runtime_schema_upgrades_and_rejects_future(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = DomainRuntimeStoreEntry.CURRENT_VERSION

    runtime = _make_runtime_data(schema_version=1, created_version=1)
    version, created = runtime_mod._stamp_runtime_schema("entry-1", runtime)
    assert version == current
    assert created == 1
    assert runtime.schema_version == current

    future = _make_runtime_data(schema_version=current + 1, created_version=current)
    with pytest.raises(RuntimeDataIncompatibleError):
        runtime_mod._stamp_runtime_schema("entry-future", future)

    monkeypatch.setattr(
        runtime_mod.DomainRuntimeStoreEntry, "MINIMUM_COMPATIBLE_VERSION", 2
    )
    legacy = _make_runtime_data(schema_version=current, created_version=1)
    _, legacy_created = runtime_mod._stamp_runtime_schema("entry-legacy", legacy)
    assert legacy_created == 2


def test_as_store_entry_from_supported_shapes() -> None:
    runtime = _make_runtime_data()
    existing_entry = DomainRuntimeStoreEntry(runtime_data=runtime)
    assert runtime_mod._as_store_entry(existing_entry) is existing_entry

    from_runtime = runtime_mod._as_store_entry(runtime)
    assert isinstance(from_runtime, DomainRuntimeStoreEntry)
    assert from_runtime.runtime_data is runtime
    assert runtime_mod._as_store_entry(None) is None
    assert runtime_mod._as_store_entry({"runtime_data": object()}) is None

    mapping_default = runtime_mod._as_store_entry({"runtime_data": runtime})
    assert isinstance(mapping_default, DomainRuntimeStoreEntry)
    assert mapping_default.version == DomainRuntimeStoreEntry.CURRENT_VERSION

    mapping_with_version = runtime_mod._as_store_entry({
        "runtime_data": runtime,
        "version": 1,
    })
    assert isinstance(mapping_with_version, DomainRuntimeStoreEntry)
    assert mapping_with_version.version == 1
    assert mapping_with_version.created_version == 1

    mapping_with_created = runtime_mod._as_store_entry({
        "runtime_data": runtime,
        "version": 1,
        "created_version": 1,
    })
    assert isinstance(mapping_with_created, DomainRuntimeStoreEntry)
    assert mapping_with_created.version == 1
    assert mapping_with_created.created_version == 1

    fake_wrong_module_cls = type("DomainRuntimeStoreEntry", (), {})
    assert runtime_mod._as_store_entry(fake_wrong_module_cls()) is None

    fake_entry_cls = type(
        "DomainRuntimeStoreEntry",
        (),
        {"__module__": DomainRuntimeStoreEntry.__module__},
    )
    fake_missing_version = fake_entry_cls()
    fake_missing_version.runtime_data = runtime
    from_fake_default = runtime_mod._as_store_entry(fake_missing_version)
    assert isinstance(from_fake_default, DomainRuntimeStoreEntry)
    assert from_fake_default.version == DomainRuntimeStoreEntry.CURRENT_VERSION

    fake_version_only = fake_entry_cls()
    fake_version_only.runtime_data = runtime
    fake_version_only.version = 1
    fake_version_only.created_version = None
    from_fake_version = runtime_mod._as_store_entry(fake_version_only)
    assert isinstance(from_fake_version, DomainRuntimeStoreEntry)
    assert from_fake_version.version == 1
    assert from_fake_version.created_version == 1


@pytest.mark.parametrize(
    ("available", "version", "created_version", "expected"),
    [
        (False, None, None, "missing"),
        (True, None, None, "unstamped"),
        (True, DomainRuntimeStoreEntry.CURRENT_VERSION + 1, 1, "future_incompatible"),
        (True, DomainRuntimeStoreEntry.CURRENT_VERSION, 0, "legacy_upgrade_required"),
        (True, 1, 1, "upgrade_pending"),
        (
            True,
            DomainRuntimeStoreEntry.CURRENT_VERSION,
            DomainRuntimeStoreEntry.CURRENT_VERSION,
            "current",
        ),
    ],
)
def test_resolve_entry_status_variants(
    available: bool,
    version: int | None,
    created_version: int | None,
    expected: str,
) -> None:
    assert (
        runtime_mod._resolve_entry_status(
            available=available,
            version=version,
            created_version=created_version,
        )
        == expected
    )


def test_build_snapshot_cleanup_apply_and_detach_helpers() -> None:
    snapshot = runtime_mod._build_runtime_store_snapshot(
        available=True,
        version=DomainRuntimeStoreEntry.CURRENT_VERSION,
        created_version=DomainRuntimeStoreEntry.CURRENT_VERSION,
    )
    assert snapshot["status"] == "current"

    runtime = _make_runtime_data()
    entry = _make_entry("entry-1", runtime_data=None)
    store_entry = DomainRuntimeStoreEntry(runtime_data=runtime)
    runtime_mod._apply_entry_metadata(entry, store_entry)
    assert entry.runtime_data is runtime
    assert getattr(entry, runtime_mod._ENTRY_VERSION_ATTR) == store_entry.version
    assert getattr(entry, runtime_mod._ENTRY_CREATED_VERSION_ATTR) == (
        store_entry.created_version
    )

    runtime_mod._detach_runtime_from_entry(entry)
    assert entry.runtime_data is None
    assert getattr(entry, runtime_mod._ENTRY_VERSION_ATTR) is None
    assert getattr(entry, runtime_mod._ENTRY_CREATED_VERSION_ATTR) is None
    runtime_mod._detach_runtime_from_entry(None)

    hass = _make_hass(data={DOMAIN: {}})
    runtime_mod._cleanup_domain_store(hass, hass.data[DOMAIN])
    assert DOMAIN not in hass.data


def test_get_store_entry_from_entry_variants() -> None:
    assert runtime_mod._get_store_entry_from_entry(None) is None

    entry_without_runtime = _make_entry("entry-1", runtime_data=None)
    assert runtime_mod._get_store_entry_from_entry(entry_without_runtime) is None

    runtime = _make_runtime_data(schema_version=1, created_version=1)
    entry_with_versions = _make_entry(
        "entry-2",
        runtime_data=runtime,
        version=1,
        created_version=1,
    )
    store_entry = runtime_mod._get_store_entry_from_entry(entry_with_versions)
    assert isinstance(store_entry, DomainRuntimeStoreEntry)
    assert store_entry.version == 1
    assert store_entry.created_version == 1

    future_runtime = _make_runtime_data(
        schema_version=DomainRuntimeStoreEntry.CURRENT_VERSION + 1,
        created_version=1,
    )
    future_entry = _make_entry("entry-3", runtime_data=future_runtime)
    with pytest.raises(RuntimeDataIncompatibleError):
        runtime_mod._get_store_entry_from_entry(future_entry)


def test_normalise_store_entry_upgrades_and_rejects_future(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _make_runtime_data(schema_version=1, created_version=1)
    legacy = DomainRuntimeStoreEntry(runtime_data=runtime, version=1, created_version=1)
    normalized = runtime_mod._normalise_store_entry("entry-1", legacy)
    assert normalized.version == DomainRuntimeStoreEntry.CURRENT_VERSION
    assert normalized.created_version >= 1

    monkeypatch.setattr(
        runtime_mod.DomainRuntimeStoreEntry, "MINIMUM_COMPATIBLE_VERSION", 2
    )
    runtime_with_legacy_created = _make_runtime_data(
        schema_version=DomainRuntimeStoreEntry.CURRENT_VERSION,
        created_version=1,
    )
    legacy_created = DomainRuntimeStoreEntry(
        runtime_data=runtime_with_legacy_created,
        version=1,
        created_version=1,
    )
    normalized_legacy = runtime_mod._normalise_store_entry("entry-2", legacy_created)
    assert normalized_legacy.version == DomainRuntimeStoreEntry.CURRENT_VERSION
    assert normalized_legacy.created_version == 2

    future = DomainRuntimeStoreEntry(
        runtime_data=_make_runtime_data(),
        version=DomainRuntimeStoreEntry.CURRENT_VERSION + 1,
        created_version=DomainRuntimeStoreEntry.CURRENT_VERSION + 1,
    )
    with pytest.raises(RuntimeDataIncompatibleError):
        runtime_mod._normalise_store_entry("entry-future", future)


def test_store_runtime_data_and_get_runtime_data_from_entry() -> None:
    runtime = _make_runtime_data()
    entry = _make_entry("entry-1", runtime_data=None)
    hass = _make_hass(data={}, entry=entry)

    store_runtime_data(hass, entry, runtime)
    assert hass.data[DOMAIN]["entry-1"].unwrap() is runtime

    resolved = get_runtime_data(hass, entry)
    assert resolved is runtime


def test_get_runtime_data_handles_entry_incompatible_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _make_runtime_data()
    entry = _make_entry("entry-1", runtime_data=runtime)
    hass = _make_hass(data={}, entry=entry)

    monkeypatch.setattr(
        runtime_mod,
        "_get_store_entry_from_entry",
        MagicMock(side_effect=RuntimeDataIncompatibleError("bad-entry")),
    )
    assert get_runtime_data(hass, entry) is None
    assert entry.runtime_data is None

    with pytest.raises(RuntimeDataIncompatibleError):
        get_runtime_data(hass, entry, raise_on_incompatible=True)

    monkeypatch.setattr(
        runtime_mod,
        "_get_store_entry_from_entry",
        MagicMock(
            return_value=DomainRuntimeStoreEntry(runtime_data=_make_runtime_data())
        ),
    )
    monkeypatch.setattr(
        runtime_mod,
        "_normalise_store_entry",
        MagicMock(side_effect=RuntimeDataIncompatibleError("bad-normalise")),
    )
    assert get_runtime_data(hass, entry) is None
    with pytest.raises(RuntimeDataIncompatibleError):
        get_runtime_data(hass, entry, raise_on_incompatible=True)


def test_get_runtime_data_store_paths_and_cleanup() -> None:
    entry = _make_entry("entry-1", runtime_data=None)
    hass_no_store = _make_hass(data={}, entry=entry)
    assert get_runtime_data(hass_no_store, "entry-1") is None

    hass_invalid_store = _make_hass(data={DOMAIN: {"entry-1": "invalid"}}, entry=entry)
    assert get_runtime_data(hass_invalid_store, "entry-1") is None
    assert DOMAIN not in hass_invalid_store.data

    future_store = DomainRuntimeStoreEntry(
        runtime_data=_make_runtime_data(),
        version=DomainRuntimeStoreEntry.CURRENT_VERSION + 1,
        created_version=DomainRuntimeStoreEntry.CURRENT_VERSION + 1,
    )
    hass_incompatible = _make_hass(
        data={DOMAIN: {"entry-1": future_store}}, entry=entry
    )
    assert get_runtime_data(hass_incompatible, "entry-1") is None
    hass_incompatible_raise = _make_hass(
        data={DOMAIN: {"entry-1": future_store}},
        entry=entry,
    )
    with pytest.raises(RuntimeDataIncompatibleError):
        get_runtime_data(hass_incompatible_raise, "entry-1", raise_on_incompatible=True)

    runtime = _make_runtime_data()
    hass_valid = _make_hass(
        data={DOMAIN: {"entry-1": DomainRuntimeStoreEntry(runtime_data=runtime)}},
        entry=entry,
    )
    assert get_runtime_data(hass_valid, "entry-1") is runtime
    assert entry.runtime_data is runtime


def test_describe_runtime_store_status_variants() -> None:
    runtime_entry = _make_runtime_data()
    runtime_store = _make_runtime_data()
    entry = _make_entry(
        "entry-1",
        runtime_data=runtime_entry,
        version=DomainRuntimeStoreEntry.CURRENT_VERSION,
        created_version=DomainRuntimeStoreEntry.CURRENT_VERSION,
    )

    current_hass = _make_hass(
        data={DOMAIN: {"entry-1": DomainRuntimeStoreEntry(runtime_data=runtime_entry)}},
        entry=entry,
    )
    current_snapshot = describe_runtime_store_status(current_hass, "entry-1")
    assert current_snapshot["status"] == "current"

    diverged_hass = _make_hass(
        data={DOMAIN: {"entry-1": DomainRuntimeStoreEntry(runtime_data=runtime_store)}},
        entry=entry,
    )
    diverged_snapshot = describe_runtime_store_status(diverged_hass, "entry-1")
    assert diverged_snapshot["status"] == "diverged"
    assert diverged_snapshot["divergence_detected"] is True

    detached_store_hass = _make_hass(data={}, entry=entry)
    assert describe_runtime_store_status(detached_store_hass, "entry-1")["status"] == (
        "detached_store"
    )

    detached_entry_hass = _make_hass(
        data={
            DOMAIN: {
                "entry-1": DomainRuntimeStoreEntry(runtime_data=_make_runtime_data())
            }
        },
        entry=_make_entry("entry-1", runtime_data=None),
    )
    assert describe_runtime_store_status(detached_entry_hass, "entry-1")["status"] == (
        "detached_entry"
    )

    missing_hass = _make_hass(data={}, entry=_make_entry("entry-1", runtime_data=None))
    assert describe_runtime_store_status(missing_hass, "entry-1")["status"] == "missing"

    unstamped_entry = _make_entry("entry-2", runtime_data=_make_runtime_data())
    unstamped_hass = _make_hass(data={}, entry=unstamped_entry)
    assert describe_runtime_store_status(unstamped_hass, "entry-2")["status"] == (
        "needs_migration"
    )

    mapping_store_hass = _make_hass(
        data={
            DOMAIN: {
                "entry-3": {
                    "runtime_data": _make_runtime_data(),
                    "version": 1,
                    "created_version": 1,
                }
            }
        },
        entry=_make_entry("entry-3", runtime_data=None),
    )
    assert describe_runtime_store_status(mapping_store_hass, "entry-3")["status"] == (
        "needs_migration"
    )

    direct_runtime_store_hass = _make_hass(
        data={DOMAIN: {"entry-4": _make_runtime_data()}},
        entry=_make_entry("entry-4", runtime_data=None),
    )
    assert describe_runtime_store_status(direct_runtime_store_hass, "entry-4")[
        "status"
    ] == ("needs_migration")

    future_store_hass = _make_hass(
        data={
            DOMAIN: {
                "entry-5": DomainRuntimeStoreEntry(
                    runtime_data=_make_runtime_data(),
                    version=DomainRuntimeStoreEntry.CURRENT_VERSION + 1,
                    created_version=DomainRuntimeStoreEntry.CURRENT_VERSION + 1,
                )
            }
        },
        entry=_make_entry("entry-5", runtime_data=None),
    )
    assert describe_runtime_store_status(future_store_hass, "entry-5")["status"] == (
        "future_incompatible"
    )


def test_pop_runtime_data_prefers_entry_then_falls_back_to_store() -> None:
    runtime = _make_runtime_data()
    entry = _make_entry(
        "entry-1",
        runtime_data=runtime,
        version=DomainRuntimeStoreEntry.CURRENT_VERSION,
        created_version=DomainRuntimeStoreEntry.CURRENT_VERSION,
    )
    hass = _make_hass(
        data={DOMAIN: {"entry-1": DomainRuntimeStoreEntry(runtime_data=runtime)}},
        entry=entry,
    )
    assert pop_runtime_data(hass, entry) is runtime
    assert entry.runtime_data is None
    assert DOMAIN not in hass.data

    store_only_runtime = _make_runtime_data()
    store_only_hass = _make_hass(
        data={
            DOMAIN: {
                "entry-2": DomainRuntimeStoreEntry(runtime_data=store_only_runtime)
            }
        },
        entry=_make_entry("entry-2", runtime_data=None),
    )
    assert pop_runtime_data(store_only_hass, "entry-2") is store_only_runtime
    assert DOMAIN not in store_only_hass.data

    future_store = DomainRuntimeStoreEntry(
        runtime_data=_make_runtime_data(),
        version=DomainRuntimeStoreEntry.CURRENT_VERSION + 1,
        created_version=DomainRuntimeStoreEntry.CURRENT_VERSION + 1,
    )
    incompatible_store_hass = _make_hass(
        data={DOMAIN: {"entry-3": future_store}},
        entry=_make_entry("entry-3", runtime_data=None),
    )
    assert pop_runtime_data(incompatible_store_hass, "entry-3") is None


def test_require_runtime_data_behaviour() -> None:
    runtime = _make_runtime_data()
    entry = _make_entry("entry-1", runtime_data=None)
    hass = _make_hass(data={}, entry=entry)
    store_runtime_data(hass, entry, runtime)
    assert require_runtime_data(hass, entry) is runtime

    missing_hass = _make_hass(data={}, entry=_make_entry("entry-2", runtime_data=None))
    with pytest.raises(RuntimeDataUnavailableError):
        require_runtime_data(missing_hass, "entry-2")


def test_as_runtime_data_handles_classless_and_matching_name_object() -> None:
    class _Classless:
        def __getattribute__(self, name: str):
            if name == "__class__":
                return None
            return object.__getattribute__(self, name)

    assert runtime_mod._as_runtime_data(_Classless()) is None

    fake_runtime_cls = type(
        "PawControlRuntimeData",
        (),
        {"__module__": PawControlRuntimeData.__module__},
    )
    fake_runtime = fake_runtime_cls()
    assert runtime_mod._as_runtime_data(fake_runtime) is fake_runtime


def test_stamp_runtime_schema_defaults_missing_versions() -> None:
    runtime = _make_runtime_data(schema_version=0, created_version=0)
    version, created = runtime_mod._stamp_runtime_schema("entry-defaults", runtime)
    assert version == DomainRuntimeStoreEntry.CURRENT_VERSION
    assert created == DomainRuntimeStoreEntry.CURRENT_VERSION


def test_as_store_entry_handles_classless_and_fake_entry_shapes() -> None:
    class _Classless:
        def __getattribute__(self, name: str):
            if name == "__class__":
                return None
            return object.__getattribute__(self, name)

    assert runtime_mod._as_store_entry(_Classless()) is None

    runtime = _make_runtime_data()
    fake_entry_cls = type(
        "DomainRuntimeStoreEntry",
        (),
        {"__module__": DomainRuntimeStoreEntry.__module__},
    )
    fake_invalid_runtime = fake_entry_cls()
    fake_invalid_runtime.runtime_data = object()
    assert runtime_mod._as_store_entry(fake_invalid_runtime) is None

    fake_full = fake_entry_cls()
    fake_full.runtime_data = runtime
    fake_full.version = 1
    fake_full.created_version = 1
    converted = runtime_mod._as_store_entry(fake_full)
    assert isinstance(converted, DomainRuntimeStoreEntry)
    assert converted.created_version == 1


def test_get_store_entry_from_entry_uses_schema_defaults_when_metadata_missing() -> (
    None
):
    runtime = _make_runtime_data(schema_version=1, created_version=1)
    entry = _make_entry("entry-schema-defaults", runtime_data=runtime)
    store_entry = runtime_mod._get_store_entry_from_entry(entry)
    assert isinstance(store_entry, DomainRuntimeStoreEntry)
    assert store_entry.version == DomainRuntimeStoreEntry.CURRENT_VERSION
    assert store_entry.created_version == 1


def test_cleanup_and_detach_skip_when_not_applicable() -> None:
    hass = _make_hass(data={DOMAIN: {"entry-1": "value"}})
    runtime_mod._cleanup_domain_store(hass, hass.data[DOMAIN])
    assert DOMAIN in hass.data

    entry_without_runtime = SimpleNamespace(entry_id="entry-1")
    runtime_mod._detach_runtime_from_entry(entry_without_runtime)
    assert not hasattr(entry_without_runtime, runtime_mod._ENTRY_VERSION_ATTR)


def test_normalise_store_entry_exercises_legacy_upgrade_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _make_runtime_data()
    store_entry = DomainRuntimeStoreEntry(
        runtime_data=runtime, version=1, created_version=1
    )

    monkeypatch.setattr(
        runtime_mod.DomainRuntimeStoreEntry, "MINIMUM_COMPATIBLE_VERSION", 2
    )
    monkeypatch.setattr(
        runtime_mod,
        "_stamp_runtime_schema",
        MagicMock(return_value=(1, 1)),
    )

    normalised = runtime_mod._normalise_store_entry(
        "entry-legacy-branches", store_entry
    )
    assert normalised.created_version == 2
    assert normalised.version == DomainRuntimeStoreEntry.CURRENT_VERSION


def test_get_runtime_data_entry_store_sync_edge_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _make_runtime_data()
    entry = _make_entry("entry-sync", runtime_data=runtime)
    hass = _make_hass(
        data={
            DOMAIN: {
                "entry-sync": DomainRuntimeStoreEntry(runtime_data=_make_runtime_data())
            }
        },
        entry=entry,
    )
    result = get_runtime_data(hass, entry)
    assert result is runtime
    assert hass.data[DOMAIN]["entry-sync"].runtime_data is runtime

    hass_none_store = _make_hass(data={}, entry=entry)
    monkeypatch.setattr(
        runtime_mod,
        "_get_domain_store",
        MagicMock(return_value=None),
    )
    assert get_runtime_data(hass_none_store, entry) is runtime

    entryless_hass = _make_hass(data={}, entry=None)
    monkeypatch.setattr(
        runtime_mod,
        "_get_store_entry_from_entry",
        MagicMock(return_value=DomainRuntimeStoreEntry(runtime_data=runtime)),
    )
    assert get_runtime_data(entryless_hass, "entry-sync") is runtime


def test_get_runtime_data_store_missing_and_incompatible_pop_branches() -> None:
    entry = _make_entry("entry-pop", runtime_data=None)
    hass_missing_key = _make_hass(data={DOMAIN: {}}, entry=entry)
    assert get_runtime_data(hass_missing_key, "entry-pop") is None

    class _PhantomStore(dict[str, object]):
        def __init__(self, phantom: object) -> None:
            super().__init__()
            self._phantom = phantom

        def get(self, key: object, default=None):  # type: ignore[override]
            return self._phantom

        def pop(self, key: object, default=None):  # type: ignore[override]
            return None

    future_store_entry = DomainRuntimeStoreEntry(
        runtime_data=_make_runtime_data(),
        version=DomainRuntimeStoreEntry.CURRENT_VERSION + 1,
        created_version=DomainRuntimeStoreEntry.CURRENT_VERSION + 1,
    )
    phantom_hass = _make_hass(
        data={DOMAIN: _PhantomStore(future_store_entry)}, entry=entry
    )
    assert get_runtime_data(phantom_hass, "entry-pop") is None

    runtime = _make_runtime_data()
    entry_none_hass = _make_hass(
        data={DOMAIN: {"entry-pop": DomainRuntimeStoreEntry(runtime_data=runtime)}},
        entry=None,
    )
    assert get_runtime_data(entry_none_hass, "entry-pop") is runtime


def test_pop_runtime_data_covers_remaining_fallback_paths() -> None:
    current = DomainRuntimeStoreEntry.CURRENT_VERSION

    future_runtime = _make_runtime_data(
        schema_version=current + 1, created_version=current
    )
    incompatible_entry = _make_entry("entry-future", runtime_data=future_runtime)
    incompatible_hass = _make_hass(data={}, entry=incompatible_entry)
    assert pop_runtime_data(incompatible_hass, incompatible_entry) is None

    runtime = _make_runtime_data()
    bad_version_entry = _make_entry(
        "entry-bad-version",
        runtime_data=runtime,
        version=current + 1,
        created_version=current + 1,
    )
    bad_version_hass = _make_hass(data={}, entry=bad_version_entry)
    assert pop_runtime_data(bad_version_hass, bad_version_entry) is None
    assert bad_version_entry.runtime_data is None

    entry_without_store = _make_entry(
        "entry-no-store",
        runtime_data=runtime,
        version=current,
        created_version=current,
    )
    hass_without_store = _make_hass(data={DOMAIN: {}}, entry=entry_without_store)
    assert pop_runtime_data(hass_without_store, entry_without_store) is runtime

    missing_store_hass = _make_hass(
        data={},
        entry=_make_entry("entry-none", runtime_data=None),
    )
    assert pop_runtime_data(missing_store_hass, "entry-none") is None

    invalid_store_hass = _make_hass(
        data={DOMAIN: {"entry-invalid": "invalid"}},
        entry=_make_entry("entry-invalid", runtime_data=None),
    )
    assert pop_runtime_data(invalid_store_hass, "entry-invalid") is None
