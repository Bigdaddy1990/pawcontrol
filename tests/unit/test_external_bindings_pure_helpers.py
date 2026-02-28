"""Additional tests for pure helper utilities in external_bindings."""

from types import SimpleNamespace

from custom_components.pawcontrol.external_bindings import _extract_coords


def test_extract_coords_uses_accuracy_fallback_key() -> None:
    """The generic ``accuracy`` attribute should be accepted as fallback."""
    state = SimpleNamespace(
        attributes={
            "latitude": 52.52,
            "longitude": 13.405,
            "accuracy": 9,
        }
    )

    assert _extract_coords(state) == (52.52, 13.405, 9.0, None)


def test_extract_coords_ignores_non_numeric_accuracy_and_altitude() -> None:
    """Non-numeric optional fields should be normalized to ``None``."""
    state = SimpleNamespace(
        attributes={
            "latitude": 40.1,
            "longitude": -70.2,
            "gps_accuracy": "bad",
            "altitude": "unknown",
        }
    )

    assert _extract_coords(state) == (40.1, -70.2, None, None)
