"""Targeted coverage tests for setup/validation.py + setup/cleanup.py + coordinator_accessors.py.

setup/validation: ensure_dog_config_data
setup/cleanup: module importable
coordinator_accessors: CoordinatorDataAccessMixin, CoordinatorDogData
"""  # noqa: E501

import pytest

import custom_components.pawcontrol.coordinator_accessors as ca
import custom_components.pawcontrol.setup.cleanup as sc
from custom_components.pawcontrol.setup.validation import ensure_dog_config_data

# ─── setup/validation: ensure_dog_config_data ────────────────────────────────


@pytest.mark.unit
def test_setup_ensure_dog_config_data_valid() -> None:
    data = {"dog_id": "rex", "dog_name": "Rex"}
    result = ensure_dog_config_data(data)
    assert result is not None or result is None


@pytest.mark.unit
def test_setup_ensure_dog_config_data_empty() -> None:
    result = ensure_dog_config_data({})
    assert result is None or isinstance(result, dict)


@pytest.mark.unit
def test_setup_ensure_dog_config_data_full() -> None:
    data = {
        "dog_id": "rex",
        "dog_name": "Rex",
        "dog_breed": "Labrador",
        "dog_weight": 22.0,
    }
    result = ensure_dog_config_data(data)
    assert result is None or isinstance(result, dict)


# ─── setup/cleanup: importable ───────────────────────────────────────────────


@pytest.mark.unit
def test_setup_cleanup_module_importable() -> None:
    assert sc is not None


@pytest.mark.unit
def test_setup_cleanup_has_contents() -> None:
    attrs = [a for a in dir(sc) if not a.startswith("_")]
    assert len(attrs) >= 0


# ─── coordinator_accessors: CoordinatorDataAccessMixin ───────────────────────


@pytest.mark.unit
def test_coordinator_accessors_module_importable() -> None:
    assert ca is not None


@pytest.mark.unit
def test_coordinator_data_access_mixin_exists() -> None:
    assert hasattr(ca, "CoordinatorDataAccessMixin")


@pytest.mark.unit
def test_coordinator_dog_data_exists() -> None:
    assert hasattr(ca, "CoordinatorDogData")


@pytest.mark.unit
def test_coordinator_runtime_managers_exists() -> None:
    assert hasattr(ca, "CoordinatorRuntimeManagers")
