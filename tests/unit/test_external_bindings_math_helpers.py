"""Additional helper coverage for external bindings internals."""

from types import SimpleNamespace

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.external_bindings import (
    _domain_store,
    _extract_coords,
    _haversine_m,
)


def test_domain_store_replaces_non_mapping_bucket() -> None:
    """Domain store should self-heal if persisted state is not a mapping."""
    hass = SimpleNamespace(data={DOMAIN: "invalid"})

    store = _domain_store(hass)

    assert store == {}
    assert isinstance(hass.data[DOMAIN], dict)


def test_extract_coords_uses_accuracy_fallback_key() -> None:
    """Coordinate extraction should use `accuracy` when gps_accuracy is absent."""
    state = SimpleNamespace(
        attributes={
            "latitude": 48.1372,
            "longitude": 11.5756,
            "accuracy": 7,
            "altitude": 520.5,
        }
    )

    assert _extract_coords(state) == (48.1372, 11.5756, 7.0, 520.5)


def test_haversine_returns_positive_distance_for_moved_position() -> None:
    """Haversine helper should report a positive distance when points differ."""
    moved_distance = _haversine_m(48.1372, 11.5756, 48.1373, 11.5757)

    assert moved_distance > 0.0
