"""Unit tests for push router helper behavior."""

from types import SimpleNamespace

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


def test_entry_store_and_snapshot_recover_invalid_structures() -> None:
    """Entry store should self-heal malformed hass data and expose telemetry."""
    hass = SimpleNamespace(data={push_router.DOMAIN: "broken"})

    entry_store = push_router._entry_store(hass, "entry-id")

    assert isinstance(entry_store["telemetry"], dict)
    snapshot = push_router.get_entry_push_telemetry_snapshot(hass, "entry-id")
    assert snapshot["accepted_total"] == 0
    assert snapshot["rejected_total"] == 0
    assert snapshot["dogs"] == {}
