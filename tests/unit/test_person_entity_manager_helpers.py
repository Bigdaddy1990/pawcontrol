"""Additional helper coverage tests for person_entity_manager."""

from datetime import timedelta
from types import SimpleNamespace

from homeassistant.const import STATE_HOME
from homeassistant.util import dt as dt_util
import pytest

from custom_components.pawcontrol import person_entity_manager as pem


def test_resolve_cache_snapshot_class_uses_dynamic_types_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The resolver should prefer a dynamically imported snapshot class."""

    class _CustomSnapshot(dict):
        pass

    monkeypatch.setattr(
        pem,
        "import_module",
        lambda _name: SimpleNamespace(CacheDiagnosticsSnapshot=_CustomSnapshot),
    )

    assert pem._resolve_cache_snapshot_class() is _CustomSnapshot


def test_resolve_cache_snapshot_class_falls_back_on_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Import failures should gracefully return the default snapshot class."""

    def _raise(_name: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(pem, "import_module", _raise)

    assert pem._resolve_cache_snapshot_class() is pem.CacheDiagnosticsSnapshot


def test_resolve_cache_snapshot_class_falls_back_when_attribute_is_not_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolver should ignore dynamic attributes that are not classes."""
    monkeypatch.setattr(
        pem,
        "import_module",
        lambda _name: SimpleNamespace(CacheDiagnosticsSnapshot="not-a-class"),
    )

    assert pem._resolve_cache_snapshot_class() is pem.CacheDiagnosticsSnapshot


def test_person_notification_cache_store_lookup_and_snapshot() -> None:
    """Cache entries should deduplicate targets and expose stale metadata."""
    cache: pem.PersonNotificationCache[dict[str, object]] = (
        pem.PersonNotificationCache()
    )
    now = dt_util.utcnow()

    stored = cache.store("home", ["notify.a", "notify.a", "notify.b"], now)

    assert stored == ("notify.a", "notify.b")
    assert len(cache) == 1
    assert cache.try_get("home", now=now + timedelta(seconds=10), ttl=60) == stored
    assert cache.try_get("home", now=now + timedelta(seconds=61), ttl=60) is None
    assert cache.try_get("missing", now=now, ttl=60) is None

    snapshot = cache.snapshot(now=now + timedelta(seconds=61), ttl=60)
    assert snapshot["home"]["stale"] is True
    assert snapshot["home"]["targets"] == stored

    cache.clear()
    assert len(cache) == 0


def test_person_notification_cache_snapshot_clamps_negative_age() -> None:
    """Snapshot age should never be negative when generated_at is in the future."""
    cache: pem.PersonNotificationCache[dict[str, object]] = (
        pem.PersonNotificationCache()
    )
    now = dt_util.utcnow()
    generated_at = now + timedelta(seconds=30)
    cache.store("future", ["notify.future"], generated_at)

    snapshot = cache.snapshot(now=now, ttl=60)

    assert snapshot["future"]["age_seconds"] == 0.0
    assert snapshot["future"]["stale"] is False


def test_person_entity_info_to_from_dict_and_state_normalization() -> None:
    """PersonEntityInfo should normalize home state and hydrate from storage."""
    now = dt_util.utcnow()
    info = pem.PersonEntityInfo(
        entity_id="person.max",
        name="max",
        friendly_name="Max",
        state=STATE_HOME,
        is_home=False,
        last_updated=now,
        notification_service="notify.mobile_app_max",
    )

    assert info.is_home is True
    serialized = info.to_dict()
    restored = pem.PersonEntityInfo.from_dict(serialized)

    assert restored.entity_id == "person.max"
    assert restored.is_home is True
    assert restored.notification_service == "notify.mobile_app_max"

    invalid_timestamp_payload = {
        **serialized,
        "last_updated": "invalid",
        "state": "not_home",
    }
    restored_with_fallback = pem.PersonEntityInfo.from_dict(invalid_timestamp_payload)
    assert restored_with_fallback.state == "not_home"
    assert restored_with_fallback.is_home is False


def test_person_entity_manager_build_config_from_input_normalizes_types() -> None:
    """Config coercion should clamp ranges and filter invalid containers."""
    config = pem.PersonEntityManager._build_config_from_input({
        "enabled": 1,
        "auto_discovery": 0,
        "discovery_interval": 9,
        "cache_ttl": -2,
        "include_away_persons": "yes",
        "fallback_to_static": "",
        "static_notification_targets": ["notify.a", 7, "notify.b"],
        "excluded_entities": ["person.a", None],
        "notification_mapping": {"person.a": "notify.a", 2: "bad", "x": 9},
        "priority_persons": ["person.vip", 3],
    })

    assert config.enabled is True
    assert config.auto_discovery is False
    assert config.discovery_interval == pem.MIN_DISCOVERY_INTERVAL
    assert config.cache_ttl == pem.DEFAULT_CACHE_TTL
    assert config.include_away_persons is True
    assert config.fallback_to_static is False
    assert config.static_notification_targets == ["notify.a", "notify.b"]
    assert config.excluded_entities == ["person.a"]
    assert config.notification_mapping == {"person.a": "notify.a"}
    assert config.priority_persons == ["person.vip"]
