"""Unit tests for push router helper behavior."""

from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import push_router
from custom_components.pawcontrol.const import (
    CONF_PUSH_NONCE_TTL_SECONDS,
    CONF_PUSH_PAYLOAD_MAX_BYTES,
    CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE,
    CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE,
    CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
    DEFAULT_PUSH_NONCE_TTL_SECONDS,
    DEFAULT_PUSH_PAYLOAD_MAX_BYTES,
)


def test_payload_limit_falls_back_and_clamps_values() -> None:
    """Payload limit should reject bools, and clamp numeric ranges."""
    entry = SimpleNamespace(options={CONF_PUSH_PAYLOAD_MAX_BYTES: True})
    assert push_router._payload_limit(entry) == DEFAULT_PUSH_PAYLOAD_MAX_BYTES

    entry.options[CONF_PUSH_PAYLOAD_MAX_BYTES] = 10
    assert push_router._payload_limit(entry) == 1024

    entry.options[CONF_PUSH_PAYLOAD_MAX_BYTES] = 10_000_000
    assert push_router._payload_limit(entry) == 256 * 1024


def test_nonce_ttl_falls_back_and_clamps_values() -> None:
    """Nonce TTL should reject bools, and clamp numeric ranges."""
    entry = SimpleNamespace(options={CONF_PUSH_NONCE_TTL_SECONDS: False})
    assert push_router._nonce_ttl(entry) == DEFAULT_PUSH_NONCE_TTL_SECONDS

    entry.options[CONF_PUSH_NONCE_TTL_SECONDS] = 5
    assert push_router._nonce_ttl(entry) == 60

    entry.options[CONF_PUSH_NONCE_TTL_SECONDS] = 99_999
    assert push_router._nonce_ttl(entry) == 24 * 3600


def test_rate_limit_uses_source_specific_keys_and_clamps() -> None:
    """Per-source rate limits should be selected and clamped safely."""
    entry = SimpleNamespace(
        options={
            CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE: "17",
            CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE: 700,
            CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE: None,
        }
    )

    assert push_router._rate_limit(entry, "webhook") == 17
    assert push_router._rate_limit(entry, "mqtt") == 600
    assert push_router._rate_limit(entry, "entity") == 60


def test_check_nonce_rejects_replay_and_cleans_expired_entries() -> None:
    """Nonce state should prune expired entries and reject duplicate replay."""
    entry_store: dict[str, object] = {
        "nonces": {
            "expired": 1.0,
            "valid": 100.0,
        }
    }
    entry = SimpleNamespace(options={CONF_PUSH_NONCE_TTL_SECONDS: 60})

    assert push_router._check_nonce(entry_store, entry, "fresh", now=120.0) is True
    assert push_router._check_nonce(entry_store, entry, "fresh", now=120.0) is False

    nonces = entry_store["nonces"]
    assert isinstance(nonces, dict)
    assert "expired" not in nonces
    assert set(nonces) == {"valid", "fresh"}


def test_entry_store_repairs_router_container() -> None:
    """Entry store should replace malformed router containers in-place."""
    hass = SimpleNamespace(data={push_router.DOMAIN: {"_push_router": []}})

    entry_store = push_router._entry_store(hass, "entry-id")

    assert isinstance(entry_store, dict)
    assert isinstance(hass.data[push_router.DOMAIN]["_push_router"], dict)


def test_entry_store_repairs_existing_entry_container() -> None:
    """Entry store should replace malformed per-entry containers in-place."""
    hass = SimpleNamespace(
        data={push_router.DOMAIN: {"_push_router": {"entry-id": []}}}
    )

    entry_store = push_router._entry_store(hass, "entry-id")

    assert isinstance(entry_store, dict)
    assert isinstance(
        hass.data[push_router.DOMAIN]["_push_router"]["entry-id"],
        dict,
    )


def test_dog_telemetry_repairs_invalid_existing_dog_bucket() -> None:
    """Dog telemetry should replace malformed existing dog buckets."""
    telemetry: dict[str, object] = {"dogs": {"dog-1": []}}

    dog_telemetry = push_router._dog_telemetry(telemetry, "dog-1")

    assert isinstance(dog_telemetry, dict)
    assert telemetry["dogs"] == {"dog-1": dog_telemetry}


def test_bump_reason_repairs_non_mapping_bucket() -> None:
    """Reason buckets should be recreated when previous data is malformed."""
    dog_tel: dict[str, object] = {"by_reason": []}

    push_router._bump_reason(dog_tel, "gps_source_mismatch")

    assert dog_tel["by_reason"] == {"gps_source_mismatch": 1}


def test_rate_limit_rejects_bool_values() -> None:
    """Bool values should fall back to the safe default rate limit."""
    entry = SimpleNamespace(options={CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE: True})

    assert push_router._rate_limit(entry, "webhook") == 60


def test_check_nonce_repairs_non_mapping_nonce_store() -> None:
    """Nonce helper should recreate malformed nonce stores before writing."""
    entry_store: dict[str, object] = {"nonces": []}
    entry = SimpleNamespace(options={CONF_PUSH_NONCE_TTL_SECONDS: 60})

    assert push_router._check_nonce(entry_store, entry, "fresh", now=120.0) is True
    assert entry_store["nonces"] == {"fresh": 120.0}


def test_limiter_repairs_non_mapping_container() -> None:
    """Limiter helper should recreate malformed limiter containers."""
    entry_store: dict[str, object] = {"limiters": []}

    limiter = push_router._limiter(entry_store, "dog-1", "webhook", 10)

    assert isinstance(entry_store["limiters"], dict)
    assert entry_store["limiters"]["dog-1:webhook"] is limiter


def test_accept_and_reject_repair_invalid_source_buckets() -> None:
    """Accept/reject helpers should recreate malformed per-source buckets."""
    telemetry: dict[str, object] = {
        "dogs": {
            "dog-1": {
                "by_source_accepted": [],
                "by_source_rejected": [],
            }
        }
    }

    push_router._accept(telemetry, "dog-1", "webhook", "2026-01-01T00:00:00+00:00")
    push_router._reject(
        telemetry,
        "dog-1",
        "webhook",
        "2026-01-01T00:01:00+00:00",
        "gps_source_mismatch",
        409,
    )

    dog_telemetry = telemetry["dogs"]["dog-1"]
    assert dog_telemetry["by_source_accepted"] == {"webhook": 1}
    assert dog_telemetry["by_source_rejected"] == {"webhook": 1}


def test_entry_store_and_snapshot_recover_invalid_structures() -> None:
    """Entry store should self-heal malformed hass data and expose telemetry."""
    hass = SimpleNamespace(data={push_router.DOMAIN: "broken"})

    entry_store = push_router._entry_store(hass, "entry-id")

    assert isinstance(entry_store["telemetry"], dict)
    snapshot = push_router.get_entry_push_telemetry_snapshot(hass, "entry-id")
    assert snapshot["accepted_total"] == 0
    assert snapshot["rejected_total"] == 0
    assert snapshot["dogs"] == {}


def test_dog_expected_source_handles_nested_and_flat_configs() -> None:
    """Expected source should resolve nested gps_config and fallback flat keys."""
    entry = SimpleNamespace(
        data={
            "dogs": [
                {"dog_id": "dog-1", "gps_config": {"gps_source": " webhook "}},
                {"dog_id": "dog-2", "gps_source": "mqtt"},
                {"dog_id": "dog-3", "gps_config": {"gps_source": 1}},
            ]
        }
    )

    assert push_router._dog_expected_source(entry, "dog-1") == "webhook"
    assert push_router._dog_expected_source(entry, "dog-2") == "mqtt"
    assert push_router._dog_expected_source(entry, "dog-3") is None
    assert push_router._dog_expected_source(entry, "missing") is None


def test_limiter_reuses_matching_instance_and_replaces_with_new_limit() -> None:
    """Limiter cache should reuse exact limiters and rebuild when limits change."""
    entry_store: dict[str, object] = {"limiters": {}}

    limiter_a = push_router._limiter(entry_store, "dog-1", "webhook", 10)
    limiter_b = push_router._limiter(entry_store, "dog-1", "webhook", 10)
    limiter_c = push_router._limiter(entry_store, "dog-1", "webhook", 20)

    assert limiter_a is limiter_b
    assert limiter_c is not limiter_a


def test_rate_limiter_allow_prunes_expired_and_enforces_capacity() -> None:
    """Limiter should evict old events and reject bursts over configured max."""
    limiter = push_router._RateLimiter(
        window_seconds=60, max_events=2, events=push_router.deque()
    )

    assert limiter.allow(100.0) is True
    assert limiter.allow(150.0) is True
    assert limiter.allow(159.0) is False

    assert limiter.allow(161.0) is True


def test_dog_expected_source_returns_none_when_dogs_payload_not_list() -> None:
    """Expected source lookup should reject malformed dog lists."""
    entry = SimpleNamespace(data={"dogs": "not-a-list"})

    assert push_router._dog_expected_source(entry, "dog-1") is None


def test_dog_telemetry_repairs_invalid_nested_store() -> None:
    """Dog telemetry helper should heal non-dict dog stores before updating counters."""
    telemetry: dict[str, object] = {"dogs": "broken"}

    dog_telemetry = push_router._dog_telemetry(telemetry, "dog-1")

    assert dog_telemetry["accepted_total"] == 0
    assert dog_telemetry["rejected_total"] == 0
    assert telemetry["dogs"] == {"dog-1": dog_telemetry}


def test_bump_reason_limits_bucket_count_to_max_reasons() -> None:
    """Reason buckets should be trimmed to avoid unbounded telemetry growth."""
    dog_tel = {"by_reason": {f"reason-{idx}": idx for idx in range(30)}}

    push_router._bump_reason(dog_tel, "reason-30")

    by_reason = dog_tel["by_reason"]
    assert isinstance(by_reason, dict)
    assert len(by_reason) == 25
    assert "reason-0" not in by_reason
    assert "reason-29" in by_reason


def test_accept_and_reject_update_telemetry_counters() -> None:
    """Accept/reject helpers should maintain aggregate and per-dog counters."""
    telemetry: dict[str, object] = {}

    push_router._accept(telemetry, "dog-1", "webhook", "2026-01-01T00:00:00+00:00")
    result = push_router._reject(
        telemetry,
        "dog-1",
        "webhook",
        "2026-01-01T00:01:00+00:00",
        "gps_source_mismatch",
        409,
    )

    assert telemetry["accepted_total"] == 1
    assert telemetry["rejected_total"] == 1
    dog_telemetry = telemetry["dogs"]["dog-1"]
    assert dog_telemetry["accepted_total"] == 1
    assert dog_telemetry["rejected_total"] == 1
    assert dog_telemetry["last_rejection_reason"] == "gps_source_mismatch"
    assert result == {
        "ok": False,
        "status": 409,
        "error": "gps_source_mismatch",
        "dog_id": "dog-1",
    }


def test_snapshot_returns_empty_mapping_for_non_dict_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Snapshot helper should fail closed when telemetry is not a mapping."""
    monkeypatch.setattr(
        push_router,
        "_entry_store",
        lambda _hass, _entry_id: {"telemetry": "broken"},
    )

    assert (
        push_router.get_entry_push_telemetry_snapshot(
            SimpleNamespace(),
            "entry-id",
        )
        == {}
    )


def test_snapshot_repairs_corrupted_telemetry_storage() -> None:
    """Snapshot helper should repair malformed telemetry storage in-place."""
    hass = SimpleNamespace(
        data={
            push_router.DOMAIN: {
                "_push_router": {
                    "entry-id": {
                        "telemetry": "broken",
                    }
                }
            }
        }
    )

    snapshot = push_router.get_entry_push_telemetry_snapshot(hass, "entry-id")
    assert snapshot["accepted_total"] == 0
    assert snapshot["rejected_total"] == 0
    assert snapshot["dogs"] == {}


def test_dog_expected_source_skips_non_mapping_entries() -> None:
    """Expected source lookup should ignore malformed dog entries."""
    entry = SimpleNamespace(
        data={
            "dogs": [
                "broken",
                {"dog_id": "dog-1", "gps_source": "webhook"},
            ]
        }
    )

    assert push_router._dog_expected_source(entry, "dog-1") == "webhook"


def test_payload_limit_and_nonce_ttl_handle_none_values() -> None:
    """None configuration values should fall back to defaults."""
    entry = SimpleNamespace(
        options={
            CONF_PUSH_PAYLOAD_MAX_BYTES: None,
            CONF_PUSH_NONCE_TTL_SECONDS: None,
        }
    )

    assert push_router._payload_limit(entry) == DEFAULT_PUSH_PAYLOAD_MAX_BYTES
    assert push_router._nonce_ttl(entry) == DEFAULT_PUSH_NONCE_TTL_SECONDS
